"""로컬 심판: API 없이 RAGAS 와 같은 열 이름의 점수를 계산한다 (리랭커는 가짜로 바꿔 규칙만 확인)."""
import math
from unittest.mock import MagicMock

import pytest

from rag.config import load_config, write_jsonl
from rag.evaluation import evaluation
from test_usage import _answer_row


class _FakeReranker:
    """질문 문장의 첫 낱말이 근거에 있으면 관련(1.0), 없으면 무관(0.0)"""

    def scores(self, query, texts):
        return [1.0 if query.split()[0] in text else 0.0 for text in texts]


@pytest.fixture(autouse=True)
def fake_reranker(monkeypatch):
    """모델만 가짜로 — _local_model 이 실제 config 에서 리랭커 설정을 찾는 길은 그대로 탄다"""
    monkeypatch.setattr(evaluation, "_rerankers", {})
    monkeypatch.setattr(evaluation, "Reranker", lambda rerank_cfg: _FakeReranker())


def _row(**fields) -> dict:
    return {"question": "질문", "reference": "", "answer": "", "contexts": [], **fields}


@pytest.mark.parametrize("name,row,expected", [
    # 출처 [1] · 목록 기호 · '답 없음' 문장 · 짧은 제목은 빼고, 숫자가 근거와 다른 문장(5초)은 지지되지 않음
    ("grounding", _row(answer="응답 시간은 3초입니다 [1].\n- 응답 시간은 5초입니다.\n제공된 문서에서 확인할 수 없습니다.\n## 요약",
                       contexts=["응답 시간은 3 초 이내", "무관한 내용"]), {"faithfulness": 0.5}),
    # 답의 두 번째 문장은 정답에 없어 정밀도 0.5, 정답 문장은 답에 있어 재현율 1 → F1 2/3
    ("end_to_end", _row(reference="하자보수 기간은 1년입니다.", answer="하자보수 기간은 1년입니다. 추가로 교육을 2회 실시합니다."),
     {"factual_correctness": pytest.approx(2 / 3)}),
    # 짧은 정답('180일')도 채점한다 — 예전엔 문장 거르기에서 빠져 늘 0점
    ("end_to_end", _row(reference="180일", answer="180일"), {"factual_correctness": 1.0}),
    # 짧은 정답이 답 문장 안에 있으면 리랭커 점수(0)와 상관없이 지지 — 근거에 없는 둘째 문장만 정밀도에서 빠진다
    ("end_to_end", _row(reference="180일", answer="사업기간은 착수일로부터 180 일입니다. 추가로 교육을 2회 실시합니다."),
     {"factual_correctness": pytest.approx(2 / 3)}),
    # 답 없음 질문에 바르게 거절하면 만점, 정답이 있는데 거절하면 0점
    ("end_to_end", _row(reference="제공된 문서에서 확인할 수 없습니다.", answer="제공된 문서에서 확인할 수 없습니다."),
     {"factual_correctness": 1.0}),
    ("end_to_end", _row(reference="180일", answer="제공된 문서에서 확인할 수 없습니다."), {"factual_correctness": 0.0}),
])
def test_local_judge_scores(name, row, expected):
    local = evaluation._local_grounding if name == "grounding" else evaluation._local_end_to_end
    assert local(row, load_config()) == expected


def test_local_faithfulness_is_nan_when_answer_has_no_claim():
    row = _row(answer="제공된 문서에서 확인할 수 없습니다.", contexts=["근거"])
    assert math.isnan(evaluation._local_grounding(row, load_config())["faithfulness"])


def test_local_grounding_skips_table_header_and_accepts_corrected_premise_numbers():
    row = _row(question="응답 시간이 5초인가요?", contexts=["응답시간은 3초 이내, 동시접속 500명"],
               answer="응답시간은 5초가 아니라 3초입니다.\n| 요구 항목 이름 | 사업별 기준 |\n|---|---|\n| 동시접속 | 500명 |")
    assert evaluation._local_grounding(row, load_config())["faithfulness"] == 1.0


@pytest.mark.parametrize("name,column", [("grounding", "faithfulness"), ("end_to_end", "factual_correctness")])
def test_local_judge_writes_the_same_columns_without_any_api_call(monkeypatch, tmp_path, name, column):
    monkeypatch.setattr(evaluation, "_ragas", MagicMock(side_effect=AssertionError("API 심판을 부르면 안 됨")))
    answers = tmp_path / "answers.jsonl"
    write_jsonl([_answer_row()], answers)
    cfg = load_config()
    cfg["evaluation"]["judge"] = "local"

    table = getattr(evaluation, f"evaluate_{name}")(answers, cfg)

    assert table.loc[0, column] == 1.0  # 답 '근거' 가 근거 · 정답 '근거' 에 글자 그대로 있다
    assert not (tmp_path / "checkpoints").exists()
