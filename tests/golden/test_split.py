"""출시본을 문서 단위로 dev · test 로 나눈다. API 호출은 없다."""
import json

import pytest

from golden_pipeline import split, storage
from golden_pipeline.schema import TOPICS
from golden_pipeline.state import transition

DOCS = [str(n) * 64 for n in range(1, 9)]
ORIGINAL = TOPICS[:5]
ADDED = ("unanswerable", "false_premise")


def release(make_item, topics, version, evidence_doc=lambda doc: doc, docs=DOCS):
    """주제마다 문서 8개에 질문 둘씩 등록해 출시본 version 을 내고 {candidate_id: 질문이 묻는 문서} 를 돌려준다.

    묶음은 계획 p-{version} 에 둔다. unanswerable 은 근거 문서(evidence_doc)와 묻는 문서(묶음의 doc_sha)가 다를 수 있다.
    """
    asked, bundles, released = {}, [], []
    for topic in topics:
        for d, doc in enumerate(docs):
            for k in range(2):
                item = make_item(candidate_id=f"{topic}-A-{version}-{d}{k}", run_id=version, primary_topic=topic,
                                 secondary_tags=[], question=f"{topic} 문서 {d} 질문 {k}은?", bundle_id=f"b-{topic}-{d}{k}")
                cited = evidence_doc(doc) if topic == "unanswerable" else doc
                item["evidence"] = [{**item["evidence"][0], "doc_sha": cited, "chunk_id": f"c-{topic}-{d}{k}"}]
                released.append(transition(item, "auto_validated", "통과", validator_version="val-0.1",
                                           difficulty="hard" if topic == "multi_hop" else "easy"))
                asked[item["candidate_id"]] = doc
                bundles.append({"bundle_id": item["bundle_id"], "topic": topic, "doc_sha": doc})
    plan_path = storage.OUTPUTS / "plans" / f"p-{version}.json"
    plan_path.parent.mkdir(exist_ok=True)
    plan_path.write_text(json.dumps({"bundles": bundles}), encoding="utf-8")
    for topic in topics:
        accepted = [item for item in released if item["primary_topic"] == topic]
        storage.write_run(topic, "A", version, accepted,
                          info={"plan_id": f"p-{version}", "plan_sha256": storage._sha256(plan_path)})
        storage.write_release(topic, version, [transition(item, "released", "출시") for item in accepted], [("A", version)])
    return asked


def read_parts(split_dir):
    return {name: [json.loads(line) for line in (split_dir / f"{name}.jsonl").read_text(encoding="utf-8").splitlines()]
            for name in ("dev", "test")}


def test_a_split_puts_every_item_once_and_each_document_on_one_side(outputs, make_item):
    # 한 문서가 양쪽에 있으면 dev 를 보고 그 문서에 맞춰 고친 것이 test 점수까지 올린다.
    # unanswerable 은 근거 문서가 아니라 질문이 묻는 문서로 나뉜다.
    asked = release(make_item, TOPICS, "v1", evidence_doc=lambda doc: DOCS[(DOCS.index(doc) + 4) % len(DOCS)])

    split_dir = split.split("v1")

    parts = read_parts(split_dir)
    assert sorted(item["candidate_id"] for rows in parts.values() for item in rows) == sorted(asked)
    docs = {name: {asked[item["candidate_id"]] for item in rows} for name, rows in parts.items()}
    assert docs["dev"] and docs["test"] and not docs["dev"] & docs["test"]
    manifest = json.loads((split_dir / "manifest.json").read_text(encoding="utf-8"))
    assert {name: manifest[name]["count"] for name in parts} == {name: len(rows) for name, rows in parts.items()}


def test_adding_topics_keeps_the_base_split_and_sends_each_question_to_its_documents_side(outputs, make_item, monkeypatch):
    # 앞 분할의 문서가 쪽을 바꾸면 팀이 dev 로 맞춰 온 test 가 더는 held-out 이 아니다.
    monkeypatch.setattr(split, "TOPICS", ORIGINAL)
    release(make_item, ORIGINAL, "v1")
    base = read_parts(split.split("v1"))
    side = {item["evidence"][0]["doc_sha"]: name for name, rows in base.items() for item in rows}
    monkeypatch.setattr(split, "TOPICS", TOPICS)
    # unanswerable 의 근거는 묻는 문서와 반대쪽 문서다. 근거 문서로 나누면 반대쪽으로 간다.
    other = {name: next(doc for doc in DOCS if side[doc] == name) for name in ("dev", "test")}
    asked = release(make_item, ADDED, "v2", evidence_doc=lambda doc: other["test" if side[doc] == "dev" else "dev"])

    split_dir = split.split("v2", base="v1")

    parts = read_parts(split_dir)
    for name, rows in parts.items():
        assert rows[:len(base[name])] == base[name]
        assert {item["primary_topic"] for item in rows[len(base[name]):]} == set(ADDED)
        assert all(side[asked[item["candidate_id"]]] == name for item in rows[len(base[name]):])
    manifest = json.loads((split_dir / "manifest.json").read_text(encoding="utf-8"))
    assert set(manifest["sources"]) == set(TOPICS) and manifest["base"]["version"] == "v1"


def test_replacing_a_topic_drops_its_missing_questions_and_sends_new_ones_to_their_documents_side(outputs, make_item):
    # 규칙으로 뺀 비교 문항을 다시 만들어 채울 때, 다른 질문이 쪽을 바꾸면 dev 로 맞춰 온 test 가 더는 held-out 이 아니다.
    release(make_item, TOPICS, "v1")
    base = read_parts(split.split("v1"))
    side = {item["evidence"][0]["doc_sha"]: name for name, rows in base.items() for item in rows}
    old, _ = storage.read_release("comparison", "v1")
    added = release(make_item, ["comparison"], "v2")
    new, _ = storage.read_release("comparison", "v2")
    storage.write_release("comparison", "v3", old[1:] + new, [("A", "v1"), ("A", "v2")])

    parts = read_parts(split.split("v3", base="v1", replace=["comparison"]))

    for name in parts:
        kept = [item for item in base[name] if item["candidate_id"] != old[0]["candidate_id"]]
        assert parts[name][:len(kept)] == kept
        assert all(side[added[item["candidate_id"]]] == name for item in parts[name][len(kept):])
    assert sum(len(rows) for rows in parts.values()) == sum(len(rows) for rows in base.values()) - 1 + len(new)


def test_adding_a_topic_refuses_a_question_on_a_document_the_base_split_lacks(outputs, make_item, monkeypatch):
    monkeypatch.setattr(split, "TOPICS", ORIGINAL)
    release(make_item, ORIGINAL, "v1")
    split.split("v1")
    monkeypatch.setattr(split, "TOPICS", TOPICS)
    release(make_item, ADDED, "v2", docs=[*DOCS[:-1], "9" * 64])

    with pytest.raises(ValueError, match="분할 v1 에 없습니다"):
        split.split("v2", base="v1")


def test_a_plan_changed_after_generation_cannot_decide_which_document_an_unanswerable_question_asks(outputs, make_item):
    # 출시 뒤 계획의 묶음 doc_sha 를 바꾸면, 해시를 보지 않는 분할은 바뀐 문서의 쪽으로 질문을 보냈다.
    release(make_item, TOPICS, "v1")
    plan_path = storage.OUTPUTS / "plans" / "p-v1.json"
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    changed = next(bundle for bundle in plan["bundles"] if bundle["topic"] == "unanswerable")
    changed["doc_sha"] = DOCS[-1] if changed["doc_sha"] != DOCS[-1] else DOCS[0]
    plan_path.write_text(json.dumps(plan), encoding="utf-8")

    with pytest.raises(ValueError, match="계획 p-v1 가 생성 run v1 을 만든 뒤 바뀌었습니다"):
        split.split("v1")
