"""주제들의 출시본을 dev · test 로 나눈다.

한 문서의 질문은 모두 한쪽으로 간다. dev 에서 틀린 질문을 보고 그 문서에 맞춘 별칭 · 사용자 단어를 넣으면
같은 문서의 test 질문 점수도 올라, test 가 실제보다 좋게 나오기 때문이다.
그 안에서 주제 × 난이도 칸마다 dev 몫이 DEV_SHARE 에 가깝도록 문서를 고른다.
앞 분할(base)에 주제를 더할 때는 앞 분할을 그대로 두고, 새 질문을 그 문서가 앞 분할에서 간 쪽으로 보낸다.
"""
import collections
import random

from golden_pipeline import plan, storage
from golden_pipeline.schema import TOPICS

DEV_SHARE = 0.3
SEED = 20261015
PARTS = ("dev", "test")


def split(version, base=None, replace=()):
    """출시본 version 들을 splits/{version}/ 의 dev.jsonl · test.jsonl 로 나누고, 칸별 개수를 매니페스트에 남긴다.

    base 가 없으면 모든 주제의 출시본 version 을 새로 나눈다. base 가 있으면 splits/{base} 를 그대로 두고
    base 에 없는 주제와 replace 의 주제의 출시본 version 을 더한다 (_extend).
    """
    if replace and not base:
        raise ValueError("replace 는 앞 분할(base)의 주제를 바꿀 때만 씁니다")
    parts, sources = _extend(version, base, replace) if base else _fresh(version)
    split_dir = storage._child(storage.OUTPUTS / "splits", version)
    split_dir.mkdir(parents=True, exist_ok=False)
    for name, rows in parts.items():
        storage._write_jsonl(split_dir / f"{name}.jsonl", rows)
    storage._write_json(split_dir / "manifest.json", {
        "version": version,
        "created_at": storage._now(),
        "code_commit": storage._code_commit(),
        "dev_share": DEV_SHARE,
        "seed": SEED,
        "base": base and {"version": base, "manifest_sha256": storage._sha256(_split_dir(base) / "manifest.json")},
        "sources": sources,
        **{name: {"count": len(rows), "documents": len({_doc(item) for item in rows}),
                  "sha256": storage._sha256(split_dir / f"{name}.jsonl"),
                  "cells": {"-".join(cell): count for cell, count in sorted(collections.Counter(map(_cell, rows)).items())}}
           for name, rows in parts.items()},
    })
    return split_dir


def _fresh(version):
    items, sources = [], {}
    for topic in TOPICS:
        released, manifest = storage.read_release(topic, version)
        items += released
        sources[topic] = manifest["golden_sha256"]
    dev_docs = _dev_documents(items)
    parts = {"dev": [item for item in items if _doc(item) in dev_docs],
             "test": [item for item in items if _doc(item) not in dev_docs]}
    return parts, sources


def _extend(version, base, replace):
    """splits/{base} 의 dev · test 를 차례 그대로 두고, base 에 없는 주제의 출시본 version 의 질문을 뒤에 붙인다.

    새 질문은 그 질문이 묻는 문서가 base 에서 간 쪽으로 간다. 문서가 쪽을 바꾸면 팀이 dev 로 맞춰 온 test 가 더는 held-out 이 아니다.
    base 에 없는 문서의 질문은 갈 쪽이 정해지지 않아 멈춘다.
    replace 의 주제는 출시본 version 으로 바꾼다. 그 출시본에 없는 base 질문은 빼고, 남는 질문은 같은 쪽 같은 차례에 그 출시본의 레코드로 둔다.
    """
    manifest = storage._read_json(_split_dir(base) / "manifest.json")
    parts = {}
    for name in PARTS:
        path = _split_dir(base) / f"{name}.jsonl"
        if storage._sha256(path) != manifest[name]["sha256"]:
            raise ValueError(f"분할 {base} 의 {name}.jsonl 이 매니페스트의 SHA-256 과 다릅니다")
        parts[name] = storage._read_jsonl(path)
    sides = {_doc(item): name for name in PARTS for item in parts[name]}
    sources = dict(manifest["sources"])
    unknown = set(replace) - set(manifest["sources"])
    if unknown:
        raise ValueError(f"바꿀 주제 {sorted(unknown)} 가 분할 {base} 에 없습니다")
    for topic in (topic for topic in TOPICS if topic not in manifest["sources"] or topic in replace):
        released, release_manifest = storage.read_release(topic, version)
        sources[topic] = release_manifest["golden_sha256"]
        # 남는 질문도 새 출시본의 레코드로 바꾼다. rename 한 출시본은 같은 ID 의 질문 앞 문서 이름이 다르다.
        kept = {item["candidate_id"]: item for item in released}
        for name in PARTS:
            parts[name] = [kept[item["candidate_id"]] if item["primary_topic"] == topic else item
                           for item in parts[name] if item["primary_topic"] != topic or item["candidate_id"] in kept]
        present = {item["candidate_id"] for name in PARTS for item in parts[name]}
        for item in (item for item in released if item["candidate_id"] not in present):
            if _doc(item) not in sides:
                raise ValueError(f"{item['candidate_id']} 이 묻는 문서 {_doc(item)} 가 분할 {base} 에 없습니다")
            parts[sides[_doc(item)]].append(item)
    return parts, sources


def _dev_documents(items):
    """dev 로 보낼 문서. 무작위로 시작해, 문서 하나를 옮겨 칸별 최대 오차가 줄어드는 동안 옮긴다."""
    total = collections.Counter(map(_cell, items))
    by_doc = collections.defaultdict(collections.Counter)
    for item in items:
        by_doc[_doc(item)][_cell(item)] += 1
    docs = sorted(by_doc)
    rng = random.Random(SEED)
    dev = {doc for doc in docs if rng.random() < DEV_SHARE}
    improved = True
    while improved:
        improved = False
        for doc in docs:
            moved = dev ^ {doc}
            if _gap(moved, by_doc, total) < _gap(dev, by_doc, total):
                dev, improved = moved, True
    return dev


def _gap(dev, by_doc, total):
    """칸마다 dev 몫과 DEV_SHARE 의 차이 중 가장 큰 것."""
    counts = sum((by_doc[doc] for doc in dev), collections.Counter())
    return max(abs(counts[cell] / total[cell] - DEV_SHARE) for cell in total)


def _doc(item):
    # unanswerable 은 근거와 다른 문서에 묻는다. 질문이 묻는 문서로 나눈다.
    return plan.asked_document(item)


def _split_dir(version):
    return storage._child(storage.OUTPUTS / "splits", version)


def _cell(item):
    return item["primary_topic"], item["difficulty"]
