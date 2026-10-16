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

from rag import config, usage
from rag.config import load_config, write_jsonl
from rag.evaluation import evaluation
from rag.generation import generation
from rag.preprocessing import parsing
from rag.validation import validation

TOKENS = {"prompt_tokens": 100, "completion_tokens": 30, "total_tokens": 130,
          "prompt_tokens_details": {"cached_tokens": 40}, "completion_tokens_details": {"reasoning_tokens": 20}}
PRICES = [0.25, 0.025, 2.0]


@pytest.mark.parametrize("public,secret", [("", ""), ("present", ""), ("", "present")])
def test_missing_langfuse_credentials_disable_tracing(monkeypatch, public, secret):
    monkeypatch.setattr(config, "load_dotenv", lambda path: None)
    monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", public)
    monkeypatch.setenv("LANGFUSE_SECRET_KEY", secret)
    monkeypatch.setenv("LANGFUSE_TRACING_ENABLED", "true")
    config.load_config()
    assert config.os.environ["LANGFUSE_TRACING_ENABLED"] == "false"


def test_langfuse_sends_remaining_numeric_scores_and_ignores_metadata_and_nan(monkeypatch):
    client = MagicMock()
    monkeypatch.setattr(evaluation, "get_client", MagicMock(return_value=client))
    evaluation._send_scores([{"trace_id": "trace"}], [{"faithfulness": 0.8, "factual_correctness": 0.9,
                              "chunk_mrr_at_5": float("nan"), "retrieval_settings": "settings"}])
    assert [c.kwargs["name"] for c in client.create_score.call_args_list] == ["faithfulness", "factual_correctness"]
    client.flush.assert_called_once()


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


def _eval_item(item_id: str, question: str) -> dict:
    return {"id": item_id, "question": question, "reference": "정답", "key_facts": ["정답"], "reset_context": False,
            "answerable": True, "primary_topic": None, "evidence": []}


def test_an_eval_set_from_before_answerable_stops_before_any_paid_call(monkeypatch):
    # 옛 eval_set.jsonl 로 04 를 돌리면 답변 파일에도 answerable 이 없어, 05 가 RAGAS 비용을 쓴 뒤에야 KeyError 로 멈췄다.
    generate = MagicMock()
    monkeypatch.setattr(generation, "generate", generate)
    old = {k: v for k, v in _eval_item("q1", "질문").items() if k != "answerable"}

    with pytest.raises(ValueError, match="answerable.*03 검증을 다시 실행"):
        generation.answer_questions([old], MagicMock(), {}, {})
    generate.assert_not_called()


def test_rewrite_and_recent_answer_history_are_preserved_together(monkeypatch):
    rewrite = MagicMock(side_effect=lambda question, cfg: {"question": "검색 " + question})
    generate = MagicMock(side_effect=lambda question, hits, cfg, history:
                         {"answer": "답변 " + question, "input_tokens": 1, "output_tokens": 1})
    monkeypatch.setattr(generation, "rewrite_question", rewrite)
    monkeypatch.setattr(generation, "generate", generate)
    monkeypatch.setattr(generation, "get_client", MagicMock())
    index = MagicMock()
    index.search_with_candidates.return_value = ([], ())
    index.rcfg = {}
    index.chunk_file = "fixture/chunks.jsonl"
    items = [_eval_item(f"q{i}", f"질문 {i}") for i in range(12)]

    rows = generation.answer_questions(items, index, {}, {})

    assert len(rows) == rewrite.call_count == generate.call_count == 12
    for i, call in enumerate(generate.call_args_list):
        assert call.kwargs["history"] == [{"question": r["question"], "answer": r["answer"]}
                                           for r in rows[max(0, i - 10):i]]
        assert index.search_with_candidates.call_args_list[i].kwargs["query"] == "검색 " + items[i]["question"]


def test_reset_context_from_eval_yaml_clears_history_before_that_question(monkeypatch, tmp_path):
    generate = MagicMock(side_effect=lambda question, hits, cfg, history:
                         {"answer": "답변 " + question, "input_tokens": 1, "output_tokens": 1})
    monkeypatch.setattr(generation, "rewrite_question", lambda question, cfg: {"question": question})
    monkeypatch.setattr(generation, "generate", generate)
    monkeypatch.setattr(generation, "get_client", MagicMock())
    index = MagicMock()
    index.search_with_candidates.return_value = ([], ())
    index.rcfg = {}
    index.chunk_file = "fixture/chunks.jsonl"
    questions = tmp_path / "eval_questions.yaml"
    questions.write_text("- {id: q0, question: 질문 0, reference: 정답, must_include: [정답]}\n"
                         "- {id: q1, question: 질문 1, reference: 정답, must_include: [정답], reset_context: true}\n"
                         "- {id: q2, question: 질문 2, reference: 정답, must_include: [정답]}\n", encoding="utf-8")
    items, _ = validation.check_eval_items(validation.load_eval_items([str(questions)]))
    items = [{**item, "evidence": []} for item in items]

    generation.answer_questions(items, index, {}, {})

    histories = [call.kwargs["history"] for call in generate.call_args_list]
    assert histories == [[], [], [{"question": "질문 1", "answer": "답변 질문 1"}]]


def _answer_row() -> dict:
    return {"id": "q1", "question": "질문", "reference": "근거", "key_facts": ["근거"], "answer": "근거",
            "answerable": True, "contexts": ["근거"], "trace_id": None, "latency_s": 1.25,
            "input_tokens": 100, "cached_input_tokens": 40, "output_tokens": 30, "reasoning_tokens": 20,
            "cost_usd": 0.000076, "primary_topic": "numeric",
            "evidence": [{"doc_id": "d1", "chunk_id": "c1"}],
            "ranked_candidates": [{"chunk_id": "c1", "doc_id": "d1", "fused_rank": 1,
                                   "dense_rank": 1, "dense_score": 0.7, "bm25_rank": 1,
                                   "bm25_score": 2.0, "exact_code_match": False}],
            "context_chunk_ids": ["c1"],
            "retrieval_settings": {"dense_weight": 0.6, "candidate_k": 50, "token_budget": 2500,
                                   "chunk_file": "fixture/chunks.jsonl", "k_values": [5, 10, 20],
                                   "stored_rewrites_reused": False},
            "rewrite": {"question": "재작성 질문", "input_tokens": 20, "cached_input_tokens": 0, "output_tokens": 10,
                        "reasoning_tokens": 3, "cost_usd": 0.000025}}


@pytest.mark.parametrize("name,metric,calls_per_question", [
    ("grounding", "faithfulness", 2), ("end_to_end", "factual_correctness", 4)])
def test_ragas_async_judges_record_each_call_once_and_keep_saved_costs(monkeypatch, tmp_path, name, metric, calls_per_question):
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")

    async def fake_agenerate(self, messages, **kwargs):
        prompt = messages[-1].content
        if "ClaimDecompositionOutput" in prompt:
            content = {"claims": ["근거"]}
        elif "StatementGeneratorOutput" in prompt:
            content = {"statements": ["근거"]}
        else:
            content = {"statements": [{"statement": "근거", "reason": "본문과 일치", "verdict": 1}]}
        return self._create_chat_result(_completion(json.dumps(content, ensure_ascii=False)))

    monkeypatch.setattr(ChatOpenAI, "_agenerate", fake_agenerate)
    answers = tmp_path / "answers.jsonl"
    write_jsonl([_answer_row(), {**_answer_row(), "id": "q2"}], answers)
    cfg = load_config()
    cfg["llm"]["usd_per_1m_tokens"] = [99, 99, 99]

    table = getattr(evaluation, f"evaluate_{name}")(answers, cfg)

    rows = _usage_rows(tmp_path)
    assert len(rows) == 2 * calls_per_question
    assert all(row["stage"] == "judge" and row["evaluation"] == name for row in rows)
    assert sum(float(row["cost_usd"]) for row in rows) == pytest.approx(0.000076 * 2 * calls_per_question)
    assert table[metric].tolist() == [1.0, 1.0, 1.0]
    if name == "end_to_end":
        assert table["cost_usd"].tolist() == [0.000101] * 3
        assert table.loc[0, "answer_cost_usd"] == 0.000076
        assert table.loc[0, "rewrite_cost_usd"] == 0.000025
        assert table.loc[0, "rewrite_reasoning_tokens"] == 3
    pd.testing.assert_frame_equal(pd.read_csv(tmp_path / f"{name}.csv", keep_default_na=False), table)


@pytest.mark.parametrize("name,score", [
    ("retrieval", {}),
    ("generation", {}),
    ("grounding", {"faithfulness": 0.8}),
    ("end_to_end", {"factual_correctness(mode=f1)": 0.9}),
])
def test_each_evaluation_function_saves_scores_without_notebook(monkeypatch, tmp_path, name, score):
    calculate = MagicMock(return_value=[score])
    monkeypatch.setattr(evaluation, "_ragas", calculate)
    monkeypatch.setattr(evaluation, "_send_scores", MagicMock())
    answers = tmp_path / "answers.jsonl"
    row = {**_answer_row(), "key_facts": ["3초", "포함"],
           "contexts": ["3 초, 부가세 포함"], "answer": "13초, 부가세 불포함"}
    write_jsonl([row], answers)

    table = getattr(evaluation, f"evaluate_{name}")(answers, load_config())

    if name in ("grounding", "end_to_end"):
        assert calculate.call_args.args[3] == name
    else:
        calculate.assert_not_called()
    assert table["id"].tolist() == ["q1", "평균"]
    if name in ("retrieval", "generation"):
        column, expected = {"retrieval": ("key_facts_in_context", 1),
                            "generation": ("key_facts_in_answer", 0)}[name]
        assert table[column].tolist() == [expected, expected]
    pd.testing.assert_frame_equal(pd.read_csv(tmp_path / f"{name}.csv"), table.replace("", float("nan")))


@pytest.mark.parametrize("name", ["retrieval", "generation", "grounding", "end_to_end"])
@pytest.mark.parametrize("field", ["answerable", "rewrite", "ranked_candidates", "context_chunk_ids", "retrieval_settings"])
def test_incomplete_answers_stop_before_ragas_is_paid(monkeypatch, tmp_path, name, field):
    # 옛 answers.jsonl 은 RAGAS 채점을 다 산 뒤 KeyError: 'answerable' 로 멈추고 CSV 도 남기지 않았다.
    calculate = MagicMock()
    monkeypatch.setattr(evaluation, "_ragas", calculate)
    answers = tmp_path / "answers.jsonl"
    write_jsonl([{k: v for k, v in _answer_row().items() if k != field}], answers)

    with pytest.raises(ValueError, match=field + r".*03 → 02 설정 셀 → 04"):
        getattr(evaluation, f"evaluate_{name}")(answers, load_config())
    calculate.assert_not_called()


def test_correct_refusal_keeps_answer_string_match_and_excludes_retrieval(tmp_path):
    answers = tmp_path / "answers.jsonl"
    refusal = {**_answer_row(), "id": "q2", "answerable": False, "key_facts": ["확인할 수 없"],
               "reference": "제공된 문서에서 확인할 수 없습니다.", "answer": "제공된 문서에서 확인할 수 없습니다.",
               "contexts": ["다른 사업의 본문"]}
    write_jsonl([_answer_row(), refusal], answers)

    table = evaluation.evaluate_retrieval(answers, load_config()).set_index("id")

    for column in ["chunk_fused_recall_at_5", "doc_mrr_at_5", "key_facts_in_context", "evidence_coverage"]:
        assert pd.isna(table.loc["q2", column])
        assert table.loc["평균", column] == table.loc["q1", column]
    assert evaluation.evaluate_generation(answers, {}).set_index("id").loc["q2", "key_facts_in_answer"] == 1
