"""골든 릴리스 행이 주제별 structure 에서 핵심 사실을 뽑아 평가 항목이 되는지 확인한다."""
import json

import pytest

from rag.validation.validation import load_eval_items


def _release_row(topic: str, answer: str, structure: dict) -> dict:
    """eval/golden/dev.jsonl 과 같은 필드의 한 행"""
    return {"run_id": "night1-r1", "method": "A", "primary_topic": topic, "prompt_version": "p",
            "candidate_id": f"{topic}-A-night1-r1-0001", "parent_candidate_id": None, "secondary_tags": [],
            "question": f"{topic} 질문", "answer": answer, "evidence": [], "bundle_id": "b-1", "context": "[E1]\n근거",
            "structure": structure, "generator_version": "generation-1", "validator_version": "validation-3",
            "difficulty": "easy", "state": "released", "state_history": []}


@pytest.mark.parametrize("topic, answer, structure, key_facts", [
    ("numeric", "180일", {"value": "180", "unit": "일"}, ["180일"]),
    ("comparison", "MAR-005 플랫폼 기능 개선, MAR-006 플랫폼 홍보 지원. 답: MAR-006",
     {"entities": ["MAR-005", "MAR-006"], "values": {"MAR-005": "플랫폼 기능 개선", "MAR-006": "플랫폼 홍보 지원"},
      "choice": "MAR-006"}, ["플랫폼 홍보 지원"]),
    ("condition", "인증서를 제출하여야 한다.", {"condition": "설치일 이전까지 인증서를 제출하여야 한다."},
     ["설치일 이전까지 인증서를 제출하여야 한다."]),
    ("table", "2,150", {"row": "인 원", "column": "휴학"}, ["2,150"]),
    ("multi_hop", "제출기한은 1일 이내이며, 2부 제출해야 한다.", {}, ["제출기한은 1일 이내이며, 2부 제출해야 한다."]),
])
def test_golden_release_row_becomes_eval_item(tmp_path, topic, answer, structure, key_facts):
    path = tmp_path / "dev.jsonl"
    path.write_text(json.dumps(_release_row(topic, answer, structure), ensure_ascii=False) + "\n", encoding="utf-8")

    [item] = load_eval_items([str(path)])

    assert {k: item[k] for k in ("id", "reference", "key_facts")} == {
        "id": f"{topic}-A-night1-r1-0001", "reference": answer, "key_facts": key_facts}
