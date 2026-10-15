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


def test_bundled_dev_key_facts_score_the_requested_answer():
    """eval/golden/dev.jsonl: 표 칸 구분선 ' | ' 가 'A|B' 로 읽히지 않고, multi_hop 사실은 근거 전체에서 모두 찾히며,
    항목 이름이 아닌 첫 칸 값과 수량은 정답 꼴 그대로 남는다. 행 번호는 dev.jsonl 의 줄 번호"""
    rows = read_jsonl(ROOT / "eval/golden/dev.jsonl")
    items = {it["id"]: it for it in load_eval_items(["eval/golden/dev.jsonl"])}
    facts = {n: items[row["candidate_id"]]["key_facts"] for n, row in enumerate(rows, 1)}

    assert not [f for fs in facts.values() for f in fs if " | " in f]
    for n, row in enumerate(rows, 1):
        if row["primary_topic"] == "multi_hop" and facts[n]:
            assert _key_fact_ratio(facts[n], row["context"]) == 1, n

    assert _key_fact_ratio(facts[270], "MAR-006입니다.") == 1
    assert _key_fact_ratio(facts[270], "MAR-005가 플랫폼 홍보 지원입니다.") == 0
    assert facts[333] == ["DAR-002", "DAR-003", "DB 설계 요구사항", "데이터 분석 요구사항"]
    assert facts[336] == ["PER-002", "성능 요구사항"]
    assert facts[335] == ["47|47개", "SFR-상담-001"]
    assert _key_fact_ratio(facts[335], rows[335 - 1]["answer"]) == 1
    assert facts[362] == []  # 2024 는 날짜 2024.12.27 의 일부일 뿐 수량이 아니다
    # 한 칸 속 글머리 항목도 따로 사실이 된다 — 산출물만 답하면 만점이 아니다
    assert facts[393] == ["실행계획서", "클라우드 거버넌스 및 운영/관리 프로세스 수립",
                          "클라우드 기반 가상 데스크톱(VDI) 및 원격 학습 환경 구축 방안",
                          "클라우드 보안 및 데이터 보호 정책/가이드라인 마련", "클라우드 전환 로드맵 및 전략 수립"]
    assert _key_fact_ratio(facts[393], "실행계획서") == 0.2
    assert facts[379] == ["SFR-003", "지도기반 통계결과 가시화", "지도기반 통계결과 출력(인쇄, 다운로드)"]  # 한 줄 속 ' o '
    assert facts[348] == ["4", "6", "참여기술인력 현황 : 특, 고, 중, 초급 기술자 보유"]  # 행 번호 꼴 4 도 값
    assert facts[387] == []  # 표준화 항목을 바꿔 말한 정답 — 분류 하나로 만점이 나지 않게 뺀다
