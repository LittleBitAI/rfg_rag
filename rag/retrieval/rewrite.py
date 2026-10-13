"""② 검색 — 원본 질문을 검색에 사용할 질문으로 재작성하고 API 사용량을 기록한다."""
from __future__ import annotations

import time

from langfuse.openai import openai

REWRITE_PROMPT = (
    "공공기관 제안요청서(RFP)를 검색하기 좋은 질문으로 재작성하세요.\n"
    "- 명백한 오타와 한영 자판 오류를 고치고, 문서 검색에 맞는 표현으로 정리하세요.\n"
    "- 원래 의도, 기관명, 사업명, 요구사항 ID, 수치, 기간, 부정 조건과 비교 대상을 보존하세요.\n"
    "- 질문에 없는 사실이나 조건을 추가하지 말고, 답변하거나 잘못된 전제를 임의로 정정하지 마세요.\n"
    "- 이미 명확한 질문은 그대로 두세요.\n"
    "- 설명이나 따옴표 없이 재작성한 질문만 출력하세요."
)


def rewrite_question(question: str, rewrite_cfg: dict) -> dict:
    """검색용 질문·모델·토큰·지연 시간을 반환한다. 출력이 비면 원본 질문으로 검색한다."""
    t0 = time.perf_counter()
    with openai.OpenAI(max_retries=3) as client:
        resp = client.chat.completions.create(
            name="rewrite-question", model=rewrite_cfg["model"],
            max_completion_tokens=int(rewrite_cfg["max_tokens"]),
            reasoning_effort=rewrite_cfg["reasoning_effort"],
            messages=[{"role": "system", "content": REWRITE_PROMPT}, {"role": "user", "content": question}])
    usage = resp.usage
    details = usage.completion_tokens_details
    return {"question": (resp.choices[0].message.content or "").strip() or question, "model": resp.model,
            "input_tokens": usage.prompt_tokens, "output_tokens": usage.completion_tokens,
            "reasoning_tokens": (details.reasoning_tokens if details else 0) or 0,
            "latency_s": round(time.perf_counter() - t0, 2)}
