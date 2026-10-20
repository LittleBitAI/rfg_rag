"""실제 릴리스 대신 합성 행으로 주제별 핵심 사실 추출 회귀를 검사한다."""
import json

import pytest

from rag.evaluation.evaluation import _key_fact_ratio
from rag.validation.validation import load_eval_items


def _release_row(topic: str, answer: str, structure: dict, context: str = "[E1]\n합성 근거") -> dict:
    return {"run_id": "synthetic-run", "method": "A", "primary_topic": topic, "prompt_version": "synthetic",
            "candidate_id": f"synthetic-{topic}", "parent_candidate_id": None, "secondary_tags": [],
            "question": f"{topic} 합성 질문", "answer": answer, "evidence": [], "bundle_id": "synthetic-bundle",
            "context": context, "structure": structure, "generator_version": "generation-1",
            "validator_version": "validation-3", "difficulty": "easy", "state": "released", "state_history": []}


@pytest.mark.parametrize("topic, answer, structure, key_facts", [
    ("numeric", "83일", {"value": "83", "unit": "일"}, ["83일"]),
    ("comparison", "TEST-701 합성 검색, TEST-702 합성 저장. 답: TEST-702",
     {"entities": ["TEST-701", "TEST-702"], "values": {"TEST-701": "합성 검색", "TEST-702": "합성 저장"},
      "choice": "TEST-702"}, ["TEST-702"]),
    ("condition", "가상 확인서를 제출한다.", {"condition": "가상 확인서를 제출한다."}, ["가상 확인서를 제출한다."]),
    ("table", "8,731", {"row": "합성 행", "column": "합성 열"}, ["8,731"]),
    ("table", "가상 정의 | 합성 처리", {"row": "합성 설명", "column": "TEST-703"}, ["가상 정의", "합성 처리"]),
    ("unanswerable", "합성 문서에서 확인할 수 없습니다.", {"attribute": "합성 장치", "key_terms": ["합성"]}, ["확인할 수 없"]),
    ("false_premise", "가상 기간은 13개월이 아니라 29개월입니다.", {"stated": "13개월", "actual": "29개월"}, ["29개월"]),
])
def test_golden_release_row_becomes_eval_item(tmp_path, topic, answer, structure, key_facts):
    path = tmp_path / "dev.jsonl"
    path.write_text(json.dumps(_release_row(topic, answer, structure), ensure_ascii=False) + "\n", encoding="utf-8")
    [item] = load_eval_items([str(path)])
    assert {k: item[k] for k in ("id", "reference", "key_facts", "answerable")} == {
        "id": f"synthetic-{topic}", "reference": answer, "key_facts": key_facts,
        "answerable": topic != "unanswerable"}
    assert _key_fact_ratio(item["key_facts"], answer) == 1
    if topic == "comparison":
        assert _key_fact_ratio(key_facts, "TEST-701이 정답입니다.") == 0
    if topic == "table" and len(key_facts) > 1:
        assert _key_fact_ratio(key_facts, key_facts[0]) == 0.5


@pytest.mark.parametrize("context, answer, question, expected", [
    ("식별자 | TEST-981\n분류\n\n[E2]\n항목 | 합성 분류", "코드: TEST-981; 분류: 합성 분류", "코드와 분류는?", ["TEST-981", "합성 분류"]),
    ("가상\n항목 | 합성 내용", "가상 항목: 합성 내용", "표의 세부 값은?", ["합성 내용"]),
    ("합성 문서는 잠금 보관함에 둔다", "합성 문서는 잠금 보관함에 둔다", "보관 규칙은?", ["합성 문서는 잠금 보관함에 둔다"]),
    ("TEST-811 | 가상 설계\n\n[E2]\nTEST-812 | 합성 분석", "TEST-811: 가상 설계; TEST-812: 합성 분석", "각 식별자와 내용은?",
     ["TEST-811", "TEST-812", "가상 설계", "합성 분석"]),
    ("31 | TEST-815", "수량: 31개; 코드: TEST-815", "수량과 코드는?", ["31|31개", "TEST-815"]),
    ("2031 | 설명", "2031.05.09에 공고되었다", "날짜는?", []),
    ("가상 | 가상 설계 규약", "분류: 가상; 명칭: 가상 설계 규약", "분류와 명칭은?", ["가상", "가상 설계 규약"]),
    ("결과물 | 합성 보고문\n\n[E2]\n세부 내용 | ○ 가상 연결 구조 구성 ○ 합성 보관 절차 수립 ○ 가상 접근 정책 작성 ○ 합성 이행 계획 작성",
     "결과물: 합성 보고문; 내용: 가상 연결 구조 구성; 합성 보관 절차 수립; 가상 접근 정책 작성; 합성 이행 계획 작성", "결과물과 내용은?",
     ["합성 보고문", "가상 연결 구조 구성", "합성 보관 절차 수립", "가상 접근 정책 작성", "합성 이행 계획 작성"]),
    ("세부 내용 | ○ 합성 교환 기능 - 가상 정보 수집", "내용: 합성 교환 기능; 가상 정보 수집", "세부 내용은?", ["합성 교환 기능", "가상 정보 수집"]),
    ("9 | 13 | 합성 전문 담당 인원", "번호: 9; 인원: 13; 명칭: 합성 전문 담당 인원", "번호와 인원과 명칭은?", ["9", "13", "합성 전문 담당 인원"]),
    ("가상 | 합성 저장", "가상 사업에 매우 특수한 새로운 방식을 적용하여 안정성을 보장한다", "어떻게 처리하나?", []),
    ("요구분류 | 처리", "요구분류: 처리", "지도기반 처리 기능의 요구분류는?", []),
])
def test_synthetic_multi_hop_facts_preserve_scoring_regressions(tmp_path, context, answer, question, expected):
    row = _release_row("multi_hop", answer, {}, "[E1]\n" + context)
    row["question"] = question
    # 반복 항목명과 첫 칸의 숫자를 구별하려면 서로 다른 문서의 합성 표가 필요하다.
    labels = ["결과물 | 다른 값", "세부 내용 | 다른 값", "요구분류 | 다른 값", "가상\n항목 | 다른 값", "9 | 다른 값"]
    support = [{**_release_row("table", "다른 값", {}, "[E1]\n" + label),
                "candidate_id": f"support-{i}-{j}", "evidence": [{"doc_sha": f"synthetic-doc-{i}"}]}
               for i in range(3) for j, label in enumerate(labels)]
    path = tmp_path / "synthetic.jsonl"
    path.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in [row, *support]), encoding="utf-8")
    [item, *_] = load_eval_items([str(path)])
    assert item["key_facts"] == sorted(expected)
    if expected:
        assert _key_fact_ratio(expected, answer) == _key_fact_ratio(expected, context) == 1
        if len(expected) == 5:
            assert _key_fact_ratio(expected, "합성 보고문") == 0.2
