"""재작성 설정·사용량과 원본 질문을 보존하는 검색·답변 흐름을 확인한다."""
from unittest.mock import MagicMock, call

import pytest
from openai.types.chat import ChatCompletion

from rag.generation import generation
from rag.retrieval import rewrite
from rag.retrieval.retrieval import HybridIndex
from test_retrieval import ranked


@pytest.mark.parametrize("content,details,expected_question,reasoning_tokens", [
    (" 검색용 질문\n", {"reasoning_tokens": 20}, "검색용 질문", 20),
    ("   ", None, "원본 질문", 0),
    (None, {"reasoning_tokens": None}, "원본 질문", 0),
])
def test_rewrite_settings_usage_and_empty_output(monkeypatch, content, details, expected_question, reasoning_tokens):
    response = ChatCompletion(
        id="rewrite-test", created=0, model="rewrite-model-snapshot", object="chat.completion",
        choices=[{"index": 0, "finish_reason": "stop", "message": {"role": "assistant", "content": content}}],
        usage={"prompt_tokens": 100, "completion_tokens": 30, "total_tokens": 130,
               "completion_tokens_details": details})
    client = MagicMock()
    client.__enter__.return_value = client
    client.chat.completions.create.return_value = response
    factory = MagicMock(return_value=client)
    monkeypatch.setattr(rewrite.openai, "OpenAI", factory)
    monkeypatch.setattr(rewrite.time, "perf_counter", MagicMock(side_effect=[10, 10.25]))
    cfg = {"model": "rewrite-model", "max_tokens": 1234, "reasoning_effort": "medium",
           "usd_per_1m_tokens": [0.25, 0.025, 2.0]}

    result = rewrite.rewrite_question("원본 질문", cfg)

    factory.assert_called_once_with(max_retries=3)
    client.chat.completions.create.assert_called_once_with(
        name="rewrite-question", model="rewrite-model", max_completion_tokens=1234, reasoning_effort="medium",
        messages=[{"role": "system", "content": rewrite.REWRITE_PROMPT}, {"role": "user", "content": "원본 질문"}])
    assert result == {"question": expected_question, "model": "rewrite-model-snapshot", "input_tokens": 100,
                      "cached_input_tokens": 0, "output_tokens": 30, "reasoning_tokens": reasoning_tokens,
                      "cost_usd": 0.000085, "latency_s": 0.25}


def test_rewrite_sends_last_ten_turns_as_chat_messages(monkeypatch):
    response = ChatCompletion(
        id="rewrite-test", created=0, model="rewrite-model", object="chat.completion",
        choices=[{"index": 0, "finish_reason": "stop", "message": {"role": "assistant", "content": "검색용 질문"}}],
        usage={"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2})
    client = MagicMock()
    client.__enter__.return_value = client
    client.chat.completions.create.return_value = response
    monkeypatch.setattr(rewrite.openai, "OpenAI", MagicMock(return_value=client))
    cfg = {"model": "rewrite-model", "max_tokens": 10, "reasoning_effort": "low", "usd_per_1m_tokens": [0, 0, 0]}
    history = [{"question": f"질문 {i}", "answer": f"답변 {i}"} for i in range(12)]

    rewrite.rewrite_question("그 사업 예산은?", cfg, history=history)

    messages = client.chat.completions.create.call_args.kwargs["messages"]
    assert messages == ([{"role": "system", "content": rewrite.REWRITE_PROMPT}]
                        + [message for i in range(2, 12) for message in
                           [{"role": "user", "content": f"질문 {i}"}, {"role": "assistant", "content": f"답변 {i}"}]]
                        + [{"role": "user", "content": "그 사업 예산은?"}])


@pytest.mark.parametrize("route",[{}, {"A": {"doc-a"}}, {"A": {"doc-a"}, "B": {"doc-b"}}])
def test_answer_flow_preserves_original_question_without_langfuse_keys(monkeypatch, route):
    for key in ("LANGFUSE_PUBLIC_KEY", "LANGFUSE_SECRET_KEY", "LANGFUSE_BASE_URL"):
        monkeypatch.setenv(key, "")
    item = {"id": "q1", "question": "원본 기관 비교 질문", "reference": "정답", "key_facts": ["근거"],
            "reset_context": False, "answerable": True, "primary_topic": None, "evidence": []}
    rewrite_result = {"question": "검색용 질문", "model": "rewrite-model", "input_tokens": 10,
                      "output_tokens": 5, "reasoning_tokens": 2, "latency_s": 0.1}
    rewrite_fn = MagicMock(return_value=rewrite_result)
    monkeypatch.setattr(generation, "rewrite_question", rewrite_fn)
    hit = {"chunk_id": "c1", "doc_id": "doc-a", "body": "근거", "source": "문서.pdf", "page": 3}
    index = HybridIndex.__new__(HybridIndex)
    index.rcfg = {"token_budget": 2500}
    index.chunk_file = "fixture/chunks.jsonl"
    index.chunks = [hit]
    index.embedder = MagicMock()
    index.embedder.token_counts.return_value = [1]
    index.router = MagicMock()
    index.router.route.return_value = route
    index._rank = MagicMock(return_value=ranked([(0, 1.0)]))
    generate_fn = MagicMock(return_value={"answer": "답변", "input_tokens": 100,
                                          "output_tokens": 50, "reasoning_tokens": 20})
    monkeypatch.setattr(generation, "generate", generate_fn)
    llm_cfg = {"model": "answer-model"}
    rewrite_cfg = {"model": "rewrite-model"}

    row, = generation.answer_questions([item], index, llm_cfg, rewrite_cfg)

    rewrite_fn.assert_called_once_with(item["question"], rewrite_cfg, history=[])
    index.router.route.assert_called_once_with("검색용 질문")
    expected_calls = ([call("검색용 질문", set(), doc_ids) for doc_ids in route.values()] if len(route) > 1
                      else [call("검색용 질문", set(), next(iter(route.values()), None))])
    assert index._rank.call_args_list == expected_calls
    generate_fn.assert_called_once_with(item["question"], [{**hit, "score": 1.0}], llm_cfg, history=[])
    assert row["question"] == item["question"]
    assert row["reference"] == item["reference"]
    assert row["key_facts"] == item["key_facts"]
    assert row["rewrite"] == rewrite_result
    assert row["input_tokens"] == 100
    assert row["contexts"] == ["근거"]
    assert row["context_chunk_ids"] == ["c1"]
    assert row["ranked_candidates"][0]["chunk_id"] == "c1"
    assert row["retrieval_settings"]["stored_rewrites_reused"] is False
    assert row["sources"] == ["문서.pdf p.3"]
    assert row["trace_id"] is None
