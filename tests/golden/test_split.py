"""출시본을 문서 단위로 dev · test 로 나눈다. API 호출은 없다."""
import json

from golden_pipeline import split, storage
from golden_pipeline.schema import TOPICS
from golden_pipeline.state import transition

DOCS = [str(n) * 64 for n in range(1, 9)]


def release_every_topic(make_item):
    """주제마다 문서 8개에 질문 둘씩 등록해 출시본 v1 을 낸다."""
    ids = []
    for topic in TOPICS:
        accepted = []
        for d, doc in enumerate(DOCS):
            for k in range(2):
                item = make_item(candidate_id=f"{topic}-A-r1-{d}{k}", primary_topic=topic, secondary_tags=[],
                                 question=f"{topic} 문서 {d} 질문 {k}은?", bundle_id=f"b-{topic}-{d}{k}")
                item["evidence"] = [{**item["evidence"][0], "doc_sha": doc, "chunk_id": f"c-{topic}-{d}{k}"}]
                accepted.append(transition(item, "auto_validated", "통과", validator_version="val-0.1",
                                           difficulty="hard" if topic == "multi_hop" else "easy"))
        storage.write_run(topic, "A", "r1", accepted)
        storage.write_release(topic, "v1", [transition(item, "released", "출시") for item in accepted], [("A", "r1")])
        ids += [item["candidate_id"] for item in accepted]
    return ids


def test_a_split_puts_every_item_once_and_each_document_on_one_side(outputs, make_item):
    # 한 문서가 양쪽에 있으면 dev 를 보고 그 문서에 맞춰 고친 것이 test 점수까지 올린다.
    ids = release_every_topic(make_item)

    split_dir = split.split("v1")

    parts = {name: [json.loads(line) for line in (split_dir / f"{name}.jsonl").read_text(encoding="utf-8").splitlines()]
             for name in ("dev", "test")}
    assert sorted(item["candidate_id"] for rows in parts.values() for item in rows) == sorted(ids)
    docs = {name: {item["evidence"][0]["doc_sha"] for item in rows} for name, rows in parts.items()}
    assert docs["dev"] and docs["test"] and not docs["dev"] & docs["test"]
    manifest = json.loads((split_dir / "manifest.json").read_text(encoding="utf-8"))
    assert {name: manifest[name]["count"] for name in parts} == {name: len(rows) for name, rows in parts.items()}
