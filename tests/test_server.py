"""질문 화면 API: 이전 대화를 최근 10턴으로 잘라 answer_question 에 넘기고 답변 · 출처를 돌려준다."""
from frontend import server


def test_ask_trims_history_and_returns_answer_and_sources(monkeypatch):
    calls = []

    def fake_answer_question(item, index, llm_cfg, rewrite_cfg, history=None):
        calls.append({"item": item, "history": history})
        return {**item, "answer": "답 [1]", "sources": ["a.pdf p.3"], "contexts": ["본문"], "latency_s": 1.0}

    monkeypatch.setattr(server, "answer_question", fake_answer_question)
    turns = [{"question": f"q{i}", "answer": f"a{i}"} for i in range(12)]
    req = server.AskRequest(question="그 사업 예산은?", history=turns)

    out = server.ask(req, index=None, cfg={"llm": {}, "rewrite": {}})

    assert out == {"answer": "답 [1]", "sources": ["a.pdf p.3"], "contexts": ["본문"]}
    assert calls[0]["history"] == turns[2:]
    assert calls[0]["item"]["question"] == "그 사업 예산은?"
    assert calls[0]["item"]["id"].startswith("web-")
