"""골든 릴리스 행이 주제별 structure 에서 핵심 사실을 뽑아 평가 항목이 되는지 확인한다."""
import json

import pytest

from rag.config import ROOT, read_jsonl
from rag.evaluation.evaluation import _key_fact_ratio
from rag.validation.validation import load_eval_items


def _release_row(topic: str, answer: str, structure: dict, context: str = "[E1]\n근거") -> dict:
    """eval/golden/dev.jsonl 과 같은 필드의 한 행"""
    return {"run_id": "night1-r1", "method": "A", "primary_topic": topic, "prompt_version": "p",
            "candidate_id": f"{topic}-A-night1-r1-0001", "parent_candidate_id": None, "secondary_tags": [],
            "question": f"{topic} 질문", "answer": answer, "evidence": [], "bundle_id": "b-1", "context": context,
            "structure": structure, "generator_version": "generation-1", "validator_version": "validation-3",
            "difficulty": "easy", "state": "released", "state_history": []}


@pytest.mark.parametrize("topic, answer, structure, key_facts", [
    ("numeric", "180일", {"value": "180", "unit": "일"}, ["180일"]),
    ("comparison", "MAR-005 플랫폼 기능 개선, MAR-006 플랫폼 홍보 지원. 답: MAR-006",
     {"entities": ["MAR-005", "MAR-006"], "values": {"MAR-005": "플랫폼 기능 개선", "MAR-006": "플랫폼 홍보 지원"},
      "choice": "MAR-006"}, ["MAR-006"]),
    ("condition", "인증서를 제출하여야 한다.", {"condition": "설치일 이전까지 인증서를 제출하여야 한다."},
     ["설치일 이전까지 인증서를 제출하여야 한다."]),
    ("table", "2,150", {"row": "인 원", "column": "휴학"}, ["2,150"]),
    ("table", "정의 | 개발 방법론 적용", {"row": "상세 설명", "column": "COR-002"}, ["정의", "개발 방법론 적용"]),
])
def test_golden_release_row_becomes_eval_item(tmp_path, topic, answer, structure, key_facts):
    path = tmp_path / "dev.jsonl"
    path.write_text(json.dumps(_release_row(topic, answer, structure), ensure_ascii=False) + "\n", encoding="utf-8")

    [item] = load_eval_items([str(path)])

    assert {k: item[k] for k in ("id", "reference", "key_facts")} == {
        "id": f"{topic}-A-night1-r1-0001", "reference": answer, "key_facts": key_facts}


def test_multi_hop_key_facts_are_context_cells_the_answer_names(tmp_path):
    """근거 단위의 첫 칸(이름)과 질문에 있는 값은 빼고, 답이 언급한 칸 값만 따로따로 사실이 된다"""
    row = _release_row("multi_hop", "요구사항 분류는 '테스트 요구사항'이고 요구사항 명칭은 '단위/통합/성능 시험'이다.", {},
                       "[E1]\n요구사항 분류 | 테스트 요구사항\n\n[E2 · 청크 2]\n요구사항 명칭 | 단위/통합/성능 시험")
    path = tmp_path / "dev.jsonl"
    path.write_text(json.dumps(row, ensure_ascii=False) + "\n", encoding="utf-8")

    [item] = load_eval_items([str(path)])

    assert item["key_facts"] == ["단위/통합/성능 시험", "테스트 요구사항"]


def test_bundled_dev_key_facts_score_the_requested_answer():
    """eval/golden/dev.jsonl 전체: 사실에 'A|B' 로 읽힐 '|' 가 없고, multi_hop 사실은 근거 전체에서 모두 찾힌다"""
    rows = read_jsonl(ROOT / "eval/golden/dev.jsonl")
    items = {it["id"]: it for it in load_eval_items(["eval/golden/dev.jsonl"])}

    assert not [f for it in items.values() for f in it["key_facts"] if "|" in f]
    for row in rows:
        facts = items[row["candidate_id"]]["key_facts"]
        if row["primary_topic"] == "multi_hop" and facts:
            assert _key_fact_ratio(facts, row["context"]) == 1, row["candidate_id"]

    [comparison] = [items[r["candidate_id"]] for r in rows if r["structure"].get("choice") == "MAR-006"]
    assert _key_fact_ratio(comparison["key_facts"], "MAR-006입니다.") == 1
    assert _key_fact_ratio(comparison["key_facts"], "MAR-005가 플랫폼 홍보 지원입니다.") == 0
