"""다섯 주제의 출시본을 dev · test 로 나눈다.

한 문서의 질문은 모두 한쪽으로 간다. dev 에서 틀린 질문을 보고 그 문서에 맞춘 별칭 · 사용자 단어를 넣으면
같은 문서의 test 질문 점수도 올라, test 가 실제보다 좋게 나오기 때문이다.
그 안에서 주제 × 난이도 칸마다 dev 몫이 DEV_SHARE 에 가깝도록 문서를 고른다.
"""
import collections
import random

from golden_pipeline import storage
from golden_pipeline.schema import TOPICS

DEV_SHARE = 0.3
SEED = 20261015


def split(version):
    """출시본 version 들을 splits/{version}/ 의 dev.jsonl · test.jsonl 로 나누고, 칸별 개수를 매니페스트에 남긴다."""
    items, sources = [], {}
    for topic in TOPICS:
        released, manifest = storage.read_release(topic, version)
        items += released
        sources[topic] = manifest["golden_sha256"]
    dev_docs = _dev_documents(items)
    parts = {"dev": [item for item in items if _doc(item) in dev_docs],
             "test": [item for item in items if _doc(item) not in dev_docs]}
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
        "sources": sources,
        **{name: {"count": len(rows), "documents": len({_doc(item) for item in rows}),
                  "sha256": storage._sha256(split_dir / f"{name}.jsonl"),
                  "cells": {"-".join(cell): count for cell, count in sorted(collections.Counter(map(_cell, rows)).items())}}
           for name, rows in parts.items()},
    })
    return split_dir


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
    return item["evidence"][0]["doc_sha"]


def _cell(item):
    return item["primary_topic"], item["difficulty"]
