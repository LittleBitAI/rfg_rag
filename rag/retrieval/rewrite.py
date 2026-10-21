"""② 검색 — 원본 질문을 검색에 사용할 질문으로 재작성하고 API 사용량을 기록한다."""
from __future__ import annotations

import time

from langfuse.openai import openai

from ..usage import record_usage

REWRITE_PROMPT = (
    "공공기관 제안요청서(RFP)를 검색하기 좋은 질문으로 재작성하세요.\n"
    "- [이전 대화]가 함께 오면 [재작성할 질문]만 재작성하세요. 이전 답변을 이어 쓰거나 질문에 답하지 마세요.\n"
    "- 기관명이나 사업명 없이 이어서 묻는 질문('사업 기간은?', '그 사업 예산은?')은 "
    "[이전 대화]가 가리키는 기관명·사업명을 넣으세요.\n"
    "- 명백한 오타와 한영 자판 오류를 고치고, 문서 검색에 맞는 표현으로 정리하세요.\n"
    "- 사업의 비용 · 가격 · 금액 · 예산을 묻는 질문은 제안요청서가 쓰는 낱말인 '사업예산(사업비)'으로 쓰세요.\n"
    "- 사업 전반을 묻는 질문('사업에 대해 알려줘')은 '사업개요(사업명·사업기간·사업예산)'를 묻는 질문으로 쓰세요.\n"
    "- 사업 내용을 자세히 묻거나 사업을 평가·분석해 달라는 질문은 '사업개요, 추진배경, 사업목표, 사업범위'를 묻는 질문으로 쓰고, "
    "'평가해 달라' 같은 요청 낱말은 빼세요. 제안서 평가 기준·배점을 묻는 질문은 그대로 두세요.\n"
    "- 원래 의도, 기관명, 사업명, 요구사항 ID, 수치, 기간, 부정 조건과 비교 대상을 보존하세요.\n"
    "- 질문과 [이전 대화]에 없는 사실이나 조건을 추가하지 말고, 답변하거나 잘못된 전제를 임의로 정정하지 마세요.\n"
    "- 이미 명확한 질문은 그대로 두세요.\n"
    "- 설명이나 따옴표 없이 재작성한 질문만 출력하세요."
)


def _with_history(question: str, history: list[dict]) -> str:
    if not history:
        return question
    turns = "\n\n".join(f"질문: {turn['question']}\n답변: {turn['answer']}" for turn in history)
    return f"[이전 대화]\n{turns}\n\n[재작성할 질문]\n{question}"


def rewrite_question(question: str, rewrite_cfg: dict, history: list[dict] | None = None) -> dict:
    """검색용 질문·모델·토큰·지연 시간을 반환한다. 출력이 비면 원본 질문으로 검색한다.
    최근 10개 대화를 함께 보내 '그 사업' 같은 지시어를 앞서 나온 사업명으로 풀게 한다.
    대화는 assistant 차례가 아니라 인용한 글로 보낸다 — 이전 답변이 assistant 차례로 오면 모델이 재작성 대신
    그 답변을 이어 써, 답 문장이 검색어가 됐다."""
    messages = [{"role": "system", "content": REWRITE_PROMPT},
                {"role": "user", "content": _with_history(question, (history or [])[-10:])}]
    prices = rewrite_cfg["usd_per_1m_tokens"]
    t0 = time.perf_counter()
    with openai.OpenAI(max_retries=3) as client:
        resp = client.chat.completions.create(
            name="rewrite-question", model=rewrite_cfg["model"],
            max_completion_tokens=int(rewrite_cfg["max_tokens"]),
            reasoning_effort=rewrite_cfg["reasoning_effort"],
            messages=messages)
    usage = record_usage("rewrite", resp.model, resp.usage.model_dump(), prices, rewrite_cfg["reasoning_effort"],
                         subject=question)
    return {"question": (resp.choices[0].message.content or "").strip() or question, **usage,
            "latency_s": round(time.perf_counter() - t0, 2)}
