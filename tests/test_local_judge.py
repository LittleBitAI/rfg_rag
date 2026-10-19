"""로컬 심판: API 없이 RAGAS 와 같은 열 이름의 점수를 계산한다 (모델은 가짜로 바꿔 규칙만 확인)."""
from unittest.mock import MagicMock

import numpy as np
import pytest

from rag.config import load_config, write_jsonl
from rag.evaluation import evaluation


class _FakeReranker:
    """질문 문장의 첫 낱말이 근거에 있으면 관련(1.0), 없으면 무관(0.0)"""

    def scores(self, query, texts):
        return [1.0 if query.split()[0] in text else 0.0 for text in texts]


class _FakeEmbedder:
    def encode(self, texts):
        return np.array([[1.0, 0.0], [0.6, 0.8]])


def _row(**fields) -> dict:
    return {"id": "q1", "question": "질문", "reference": "", "key_facts": ["없는 사실"], "answerable": True, "answer": "", "contexts": [],
            "trace_id": None, "latency_s": 1.0, "input_tokens": 1, "output_tokens": 1, "cached_input_tokens": 0,
            "reasoning_tokens": 0, "cost_usd": 0.0,
            "rewrite": {"input_tokens": 1, "output_tokens": 1, "cached_input_tokens": 0, "reasoning_tokens": 0,
                        "cost_usd": 0.0}, **fields}


@pytest.mark.parametrize("name,row,expected", [
    # 출처 [1] · 목록 기호 · '답 없음' 문장 · 짧은 제목은 빼고, 숫자가 근거와 다른 문장(5초)은 지지되지 않음
    ("grounding", _row(answer="응답 시간은 3초입니다 [1].\n- 응답 시간은 5초입니다.\n제공된 문서에서 확인할 수 없습니다.\n## 요약",
                       contexts=["응답 시간은 3 초 이내", "무관한 내용"]),
     {"faithfulness": 0.5}),
    # 정답 두 문장 중 100명은 근거(200명)에 없어 재현율 0.5, 관련 근거가 2·3위라 평균 정밀도 (1/2 + 2/3) / 2
    ("retrieval", _row(reference="응답 시간은 3초입니다. 동시접속은 100명입니다.",
                       contexts=["무관한 내용", "응답 시간 3초", "동시접속은 200명"]),
     {"context_precision": pytest.approx((1 / 2 + 2 / 3) / 2, abs=1e-4), "context_recall": 0.5}),
    # 답의 두 번째 문장은 정답에 없어 정밀도 0.5, 정답 문장은 답에 있어 재현율 1 → F1 2/3
    ("end_to_end", _row(reference="하자보수 기간은 1년입니다.", answer="하자보수 기간은 1년입니다. 추가로 교육을 2회 실시합니다."),
     {"factual_correctness": pytest.approx(2 / 3, abs=1e-4)}),
    # 짧은 정답('180일')도 채점한다 — 근거에 글자 그대로 있으면 리랭커 점수가 낮아도 지지 (예전엔 문장에서 빠져 늘 0점)
    ("retrieval", _row(reference="180일", contexts=["무관한 내용", "사업기간 : 착수일로부터 180 일"]),
     {"context_precision": 0.5, "context_recall": 1.0}),
    ("end_to_end", _row(reference="180일", answer="180일"), {"factual_correctness": 1.0}),
    # 짧은 정답이 답 문장 안에 있으면 지지 (리랭커 점수는 0) — 근거에 없는 둘째 문장만 정밀도에서 빠진다
    ("end_to_end", _row(reference="180일", answer="사업기간은 착수일로부터 180 일입니다. 추가로 교육을 2회 실시합니다."),
     {"factual_correctness": pytest.approx(2 / 3, abs=1e-4)}),
    ("generation", _row(answer="답변"), {"answer_relevancy": pytest.approx(0.6)}),
    ("generation", _row(answer=" "), {"answer_relevancy": 0.0}),
])
def test_local_judge_scores_without_any_api_call(monkeypatch, tmp_path, name, row, expected):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setattr(evaluation, "_judge", MagicMock(side_effect=AssertionError("API 심판을 부르면 안 됨")))
    monkeypatch.setattr(evaluation, "_local_model",
                        lambda kind, cfg: _FakeReranker() if kind == "reranker" else _FakeEmbedder())
    answers = tmp_path / "answers.jsonl"
    write_jsonl([row], answers)
    cfg = load_config()
    assert cfg["evaluation"]["judge"] == "local"

    table = getattr(evaluation, f"evaluate_{name}")(answers, cfg)

    assert {column: table.loc[0, column] for column in expected} == expected  # 표는 소수 넷째 자리로 반올림
    assert (tmp_path / f"{name}.csv").exists()
    assert not (tmp_path / "checkpoints").exists()


def test_local_faithfulness_is_nan_when_answer_has_no_claim():
    row = _row(answer="제공된 문서에서 확인할 수 없습니다.", contexts=["근거"])
    assert np.isnan(evaluation._local_grounding(row, load_config())["faithfulness"])


def test_local_grounding_skips_table_header_and_accepts_corrected_premise_numbers(monkeypatch):
    monkeypatch.setattr(evaluation, "_local_model", lambda kind, cfg: _FakeReranker())
    row = _row(question="응답 시간이 5초인가요?", contexts=["응답시간은 3초 이내, 동시접속 500명"],
               answer="응답시간은 5초가 아니라 3초입니다.\n| 요구 항목 이름 | 사업별 기준 |\n|---|---|\n| 동시접속 | 500명 |")

    assert evaluation._local_grounding(row, load_config())["faithfulness"] == 1.0
