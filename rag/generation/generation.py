"""④ 생성 — 검색한 청크를 컨텍스트로 gpt 가 답한다.
담당: 생성.  03 검증의 eval_set.jsonl 질문마다 02 검색 → 답변을 만들어 answers.jsonl 로 05 평가에 넘긴다."""
from __future__ import annotations

import time

import openai
from langfuse import observe

SYSTEM_PROMPT = (
    "당신은 공공기관 제안요청서(RFP) 문서 기반 질의응답 도우미입니다.\n"
    "- 반드시 아래 [컨텍스트] 안의 내용만 근거로 답하세요.\n"
    "- 금액·기간·비율·날짜·자격요건·요구사항 ID 는 원문 표기 그대로 인용하세요.\n"
    "- 근거 문장 끝에 [번호] 로 출처를 표시하세요.\n"
    "- 질문에 사실과 다른 전제가 있으면(예: 잘못된 비율·기한) 먼저 '정정:' 으로 바로잡은 뒤 올바른 내용을 답하세요.\n"
    "- 두 사업/기관 비교 질문은 항목별 Markdown 표로 정리하고, 한쪽 문서에 없는 항목은 '문서에 없음'으로 표시하세요.\n"
    "- 요구사항 정리 질문은 요구사항 ID·명칭·핵심 내용을 목록으로 정리하세요.\n"
    "- 질문이 영어로만 되어 있으면 영어로, 그 외에는 한국어로 답하세요.\n"
    "- 컨텍스트에 답이 없으면 '제공된 문서에서 확인할 수 없습니다.' 라고 답하세요."
)


def format_context(hits: list[dict]) -> str:
    """검색 결과 → '[번호] (파일 p.N, 표) 본문' 목록"""
    parts = []
    for i, h in enumerate(hits, 1):
        kind = {"table": "표", "image_caption": "그림"}.get(h["kind"], "본문")
        loc = f"p.{h['page']}" if h["page"] else h["section"][:40]
        parts.append(f"[{i}] ({h['source']} {loc}, {kind})\n{h['body']}")
    return "\n\n".join(parts)


@observe(as_type="generation")
def generate(question: str, hits: list[dict], llm_cfg: dict) -> dict:
    """질문 + 검색 청크 → 답변과 토큰 사용량 (reasoning 토큰은 출력 토큰에 포함되어 과금)"""
    with openai.OpenAI(max_retries=3) as client:
        resp = client.chat.completions.create(
            model=llm_cfg["model"], max_completion_tokens=int(llm_cfg["max_tokens"]),
            reasoning_effort=llm_cfg["reasoning_effort"],
            messages=[{"role": "system", "content": SYSTEM_PROMPT},
                      {"role": "user", "content": f"[컨텍스트]\n{format_context(hits)}\n\n[질문]\n{question}"}])
    usage = resp.usage
    details = usage.completion_tokens_details
    return {"answer": resp.choices[0].message.content or "", "input_tokens": usage.prompt_tokens,
            "output_tokens": usage.completion_tokens, "reasoning_tokens": (details.reasoning_tokens if details else 0) or 0}


def answer_questions(eval_set: list[dict], index, llm_cfg: dict) -> list[dict]:
    """평가 데이터셋 질문마다 검색 → 생성. latency_s = 검색 + 생성 시간"""
    rows = []
    for i, item in enumerate(eval_set, 1):
        t0 = time.perf_counter()
        hits = index.search(item["question"])
        out = generate(item["question"], hits, llm_cfg)
        rows.append({**item, **out, "contexts": [h["body"] for h in hits],
                     "sources": [f"{h['source']} p.{h['page']}" if h["page"] else h["source"] for h in hits],
                     "latency_s": round(time.perf_counter() - t0, 2)})
        print(f"생성 {i}/{len(eval_set)} {item['id']} ({rows[-1]['latency_s']}s)")
    return rows
