"""④ 생성 — 검색한 청크와 이전 대화를 컨텍스트로 GPT가 답한다.
담당: 생성. 03 검증의 eval_set.jsonl 질문마다 02 검색 → 답변을 만들어
answers.jsonl로 05 평가에 넘긴다.
.env에 Langfuse 키가 있으면 질문마다 추적 하나가 남는다."""
from __future__ import annotations

import time

from langfuse import get_client, observe
from langfuse.openai import openai

SYSTEM_PROMPT = (
    "당신은 공공기관 제안요청서(RFP) 문서 기반 질의응답 도우미입니다.\n"
    "- 반드시 현재 질문은 [검색 컨텍스트] 안의 내용만 근거로 답하세요.\n"
    "- [이전 대화]는 현재 질문을 이해하는 데만 활용하고, 문서의 사실을 확인하는 근거로 쓰지 마세요.\n"
    "- 금액·기간·비율·날짜·자격요건·요구사항 ID는 원문 표기 그대로 인용하세요.\n"
    "- 근거 문장 끝에 [번호]로 출처를 표시하세요.\n"
    "- 질문에 사실과 다른 전제가 있으면(예: 잘못된 비율·기한) 먼저 '정정:'으로 바로잡은 뒤 올바른 내용을 답하세요.\n"
    "- 두 사업/기관 비교 질문은 항목별 Markdown 표로 정리하고, 한쪽 문서에 없는 항목은 '문서에 없음'으로 표시하세요.\n"
    "- 요구사항 정리 질문은 요구사항 ID·명칭·핵심 내용을 목록으로 정리하세요.\n"
    "- 질문이 영어로만 되어 있으면 영어로, 그 외에는 한국어로 답하세요.\n"
    "- 검색 컨텍스트에 답이 없으면 '제공된 문서에서 확인할 수 없습니다.'라고 답하세요."
)


def format_context(hits: list[dict]) -> str:
    """검색 결과를 '[번호] (파일 p.N, 표) 본문' 목록으로 변환."""
    parts = []
    for i, h in enumerate(hits, 1):
        kind = {"table": "표", "image_caption": "그림"}.get(h["kind"], "본문")
        loc = f"p.{h['page']}" if h["page"] else h["section"][:40]
        parts.append(f"[{i}] ({h['source']} {loc}, {kind})\n{h['body']}")
    return "\n\n".join(parts) or "(검색된 문서 청크가 없습니다.)"


def format_history(history: list[dict]) -> str:
    """이전 질문·답변 목록을 프롬프트용 문자열로 변환."""
    if not history:
        return "(이전 대화가 없습니다.)"

    return "\n\n".join(
        f"[대화 {i}]\n질문: {turn['question']}\n답변: {turn['answer']}"
        for i, turn in enumerate(history, 1)
    )


def generate(question: str, hits: list[dict], llm_cfg: dict, history: list[dict] | None = None) -> dict:
    """검색 청크와 이전 대화를 사용해 답변 및 토큰 사용량을 생성."""
    history = history or []
    
    messages = [{"role": "system", "content":SYSTEM_PROMPT}]
    
    # 최대 10개 대화 (이전 질문 10개, 답변 10개, 총 20개 메세지)
    for turn in history[-10]:
        messages.append({"role": "user", "content": turn["question"]})
        messages.append({"role": "assistant", "content": turn["answer"]})
    
    messages.append({
        "role" : "user",
        "content": f"[컨덱스트]\n{format_context(hits)}\n\n[질문]\n{question}"
    })

    with openai.OpenAI(max_retries=3) as client:
        resp = client.chat.completions.create(
            name="generate-answer", model=llm_cfg["model"], max_completion_tokens=int(llm_cfg["max_tokens"]),
            reasoning_effort=llm_cfg["reasoning_effort"],
            messages=messages)

    usage = resp.usage
    details = usage.completion_tokens_details
    return {"answer": resp.choices[0].message.content or "", "input_tokens": usage.prompt_tokens,
        "output_tokens": usage.completion_tokens, "reasoning_tokens": ((details.reasoning_tokens if details else 0) or 0),}


# 입력·출력에서 검색 색인 객체를 캡처하지 않는다.
@observe(name="answer-question", capture_input=False, capture_output=False)
def answer_question(item: dict, index, llm_cfg: dict, history: list[dict] | None = None) -> dict:
    """질문 하나를 검색하고, 직전 대화 기록을 참고해 답변한다."""
    t0 = time.perf_counter()
    hits = index.search(item["question"])
    out = generate(item["question"], hits, llm_cfg, history=history)

    langfuse = get_client()
    langfuse.update_current_span(input=item["question"], output=out["answer"],
        metadata={
            "eval_id": item["id"],
            "history_turns": len(history or []),
        },
    )

    return {**item, **out, "contexts": [h["body"] for h in hits],
        "sources": [
            f"{h['source']} p.{h['page']}" if h["page"] else h["source"] for h in hits],
        "latency_s": round(time.perf_counter() - t0, 2),
        "trace_id": langfuse.get_current_trace_id(),
    }


def answer_questions(eval_set: list[dict], index, llm_cfg: dict, history_window: int = 10) -> list[dict]:
    """질문을 순서대로 처리하며 직전 history_window개의 Q&A를 전달한다.

    테스트용 대화 기록은 이 함수 실행 중에만 유지된다.
    eval_set의 순서가 대화 순서가 되며, 이전 질문과 생성된 답변을 사용한다.
    """
    rows = []
    history = []

    for i, item in enumerate(eval_set, 1):
        row = answer_question(item, index, llm_cfg, history=history[-history_window])
        rows.append(row)

        # 다음 질문에서 이전 대화로 사용할 수 있도록 Q&A를 추가한다.
        history.append({
            "question": item["question"],
            "answer": row["answer"],
        })

        print(f"생성 {i}/{len(eval_set)} {item['id']} ({row['latency_s']}s)")

    return rows