"""실제 콜백 경로와 CSV·비용 계산을 네트워크 호출 없이 검증한다."""
import csv
import json
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import MagicMock

import pandas as pd
import pytest
from langchain_openai import ChatOpenAI
from openai.types.chat import ChatCompletion
from PIL import Image

from rag import usage
from rag.config import load_config, write_jsonl
from rag.evaluation import evaluation
from rag.generation import generation
from rag.preprocessing import parsing

TOKENS = {"prompt_tokens": 100, "completion_tokens": 30, "total_tokens": 130,
          "prompt_tokens_details": {"cached_tokens": 40}, "completion_tokens_details": {"reasoning_tokens": 20}}
PRICES = [0.25, 0.025, 2.0]


def _completion(content: str) -> dict:
    return {"id": "test-response", "created": 0, "object": "chat.completion", "model": "actual-model-snapshot",
            "choices": [{"index": 0, "finish_reason": "stop", "message": {"role": "assistant", "content": content}}],
            "usage": TOKENS}


def _usage_rows(tmp_path):
    with (tmp_path / "api_usage.csv").open(encoding="utf-8", newline="") as file:
        return list(csv.DictReader(file))


def test_cached_input_and_reasoning_costs_with_concurrent_csv_writes(tmp_path):
    def record(i):
        return usage.record_usage("answer", "actual-model-snapshot", TOKENS, PRICES, subject=f"질문 {i}")

    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(record, range(12)))

    assert len(_usage_rows(tmp_path)) == 12
    assert results[0]["cost_usd"] == pytest.approx(0.000076)
    summary, = usage.usage_summary("answer").to_dict("records")
    assert summary["calls"] == 12
    assert summary["input_tokens"] == 1200
    assert summary["cached_input_tokens"] == 480
    assert summary["reasoning_tokens"] == 240
    assert summary["cost_usd"] == pytest.approx(0.000076 * 12)
    assert not (tmp_path / "api_usage.csv").read_bytes().startswith(b"\xef\xbb\xbf")


def test_summary_before_any_call_is_empty_and_creates_no_csv(tmp_path):
    assert usage.usage_summary("ocr").empty
    assert not (tmp_path / "api_usage.csv").exists()


@pytest.mark.parametrize("ocr", [False, True])
def test_ocr_invocation_records_every_image_with_source_without_langfuse(monkeypatch, tmp_path, ocr):
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")

    def fake_generate(self, messages, **kwargs):
        return self._create_chat_result(_completion("예산 100만원"))

    def parse_file(path, pcfg, parser):
        if parser is not None:
            for _ in range(2):
                assert parser._analyze_image(Image.new("RGB", (1, 1))) == "예산 100만원"
        return {"source": path, "records": []}

    monkeypatch.setattr(ChatOpenAI, "_generate", fake_generate)
    monkeypatch.setattr(parsing, "_parse_file", parse_file)
    parsing.parse_documents(["첫째.pdf", "둘째.hwp"], {}, ocr, load_config()["ocr"])

    if not ocr:
        assert not (tmp_path / "api_usage.csv").exists()
        return
    rows = _usage_rows(tmp_path)
    assert [row["subject"] for row in rows] == ["첫째.pdf", "첫째.pdf", "둘째.hwp", "둘째.hwp"]
    assert all(row["stage"] == "ocr" and row["model"] == "actual-model-snapshot" for row in rows)
    assert all(float(row["cost_usd"]) == pytest.approx(0.000076) for row in rows)


@pytest.mark.parametrize("turns", [0, 3, 12])
def test_answer_saves_actual_model_usage_and_recent_history(monkeypatch, tmp_path, turns):
    client = MagicMock()
    client.__enter__.return_value = client
    client.chat.completions.create.return_value = ChatCompletion(**_completion("답변"))
    monkeypatch.setattr(generation.openai, "OpenAI", MagicMock(return_value=client))

    history = [{"question": f"이전 질문 {i}", "answer": f"이전 답변 {i}"} for i in range(turns)]
    result = generation.generate("질문", [], load_config()["llm"], history=history or None)

    assert result["model"] == "actual-model-snapshot"
    assert result["cached_input_tokens"] == 40
    assert result["reasoning_tokens"] == 20
    assert result["cost_usd"] == pytest.approx(0.000076)
    row, = _usage_rows(tmp_path)
    assert row["stage"] == "answer" and row["subject"] == "질문"
    messages = client.chat.completions.create.call_args.kwargs["messages"]
    expected_history = [message for turn in history[-10:] for message in
                        [{"role": "user", "content": turn["question"]},
                         {"role": "assistant", "content": turn["answer"]}]]
    assert messages[1:-1] == expected_history
    assert messages[-1]["content"].startswith("[검색 컨텍스트]\n")


def test_rewrite_and_recent_answer_history_are_preserved_together(monkeypatch):
    rewrite = MagicMock(side_effect=lambda question, cfg: {"question": "검색 " + question})
    generate = MagicMock(side_effect=lambda question, hits, cfg, history:
                         {"answer": "답변 " + question, "input_tokens": 1, "output_tokens": 1})
    monkeypatch.setattr(generation, "rewrite_question", rewrite)
    monkeypatch.setattr(generation, "generate", generate)
    monkeypatch.setattr(generation, "get_client", MagicMock())
    index = MagicMock()
    index.search.return_value = []
    items = [{"id": f"q{i}", "question": f"질문 {i}"} for i in range(12)]

    rows = generation.answer_questions(items, index, {}, {})

    assert len(rows) == rewrite.call_count == generate.call_count == 12
    for i, call in enumerate(generate.call_args_list):
        assert call.kwargs["history"] == [{"question": r["question"], "answer": r["answer"]}
                                           for r in rows[max(0, i - 10):i]]
        assert index.search.call_args_list[i].kwargs["query"] == "검색 " + items[i]["question"]


def _answer_row() -> dict:
    return {"id": "q1", "question": "질문", "reference": "근거", "key_facts": ["근거"], "answer": "근거",
            "contexts": ["근거"], "trace_id": None, "latency_s": 1.25,
            "input_tokens": 100, "cached_input_tokens": 40, "output_tokens": 30, "reasoning_tokens": 20,
            "cost_usd": 0.000076,
            "rewrite": {"input_tokens": 20, "cached_input_tokens": 0, "output_tokens": 10,
                        "reasoning_tokens": 3, "cost_usd": 0.000025}}


def test_ragas_async_judge_records_each_call_once_and_end_cost_uses_saved_values(monkeypatch, tmp_path):
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    for key in ("LANGFUSE_PUBLIC_KEY", "LANGFUSE_SECRET_KEY", "LANGFUSE_BASE_URL"):
        monkeypatch.delenv(key, raising=False)

    async def fake_agenerate(self, messages, **kwargs):
        prompt = messages[-1].content
        content = ({"claims": ["근거"]} if "ClaimDecompositionOutput" in prompt else
                   {"statements": [{"statement": "근거", "reason": "본문과 일치", "verdict": 1}]})
        return self._create_chat_result(_completion(json.dumps(content, ensure_ascii=False)))

    monkeypatch.setattr(ChatOpenAI, "_agenerate", fake_agenerate)
    answers = tmp_path / "answers.jsonl"
    write_jsonl([_answer_row(), {**_answer_row(), "id": "q2"}], answers)
    cfg = load_config()
    cfg["llm"]["usd_per_1m_tokens"] = [99, 99, 99]

    table = evaluation.evaluate_end_to_end(answers, cfg)

    rows = _usage_rows(tmp_path)
    assert len(rows) == 8  # 질문마다 정답/답변 분해 2회 + 양방향 판정 2회
    assert all(row["stage"] == "judge" and row["evaluation"] == "end_to_end" for row in rows)
    assert sum(float(row["cost_usd"]) for row in rows) == pytest.approx(0.000076 * 8)
    assert table["factual_correctness"].tolist() == [1.0, 1.0, 1.0]
    assert table["cost_usd"].tolist() == [0.000101] * 3
    assert table.loc[0, "answer_cost_usd"] == 0.000076
    assert table.loc[0, "rewrite_cost_usd"] == 0.000025
    assert table.loc[0, "rewrite_reasoning_tokens"] == 3
    pd.testing.assert_frame_equal(pd.read_csv(tmp_path / "end_to_end.csv", keep_default_na=False), table)


@pytest.mark.parametrize("name,score", [
    ("retrieval", {"llm_context_precision_with_reference": 0.5, "context_recall": 1.0}),
    ("generation", {"answer_relevancy": 0.7}),
    ("grounding", {"faithfulness": 0.8}),
    ("end_to_end", {"factual_correctness(mode=f1)": 0.9}),
])
def test_each_evaluation_function_saves_scores_without_notebook(monkeypatch, tmp_path, name, score):
    calculate = MagicMock(return_value=[score])
    monkeypatch.setattr(evaluation, "_ragas", calculate)
    monkeypatch.setattr(evaluation, "Embedder", MagicMock())
    monkeypatch.setattr(evaluation, "_send_scores", MagicMock())
    answers = tmp_path / "answers.jsonl"
    write_jsonl([_answer_row()], answers)

    table = getattr(evaluation, f"evaluate_{name}")(answers, load_config())

    assert calculate.call_args.args[3] == name
    assert table["id"].tolist() == ["q1", "평균"]
    pd.testing.assert_frame_equal(pd.read_csv(tmp_path / f"{name}.csv", keep_default_na=False), table)
