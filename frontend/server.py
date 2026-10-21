"""질문 화면의 API — 04 생성과 같은 설정으로 answer_question 을 감싼다.
대화 기록은 화면(브라우저 탭)이 갖고 질문마다 보내므로 서버는 대화 상태를 갖지 않는다.
저장소 최상위에서 실행: .venv\\Scripts\\python -m uvicorn frontend.server:app --port 8767"""
from __future__ import annotations

import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI
from pydantic import BaseModel

from rag.config import ARTIFACTS, load_config, read_jsonl
from rag.generation.generation import answer_question
from rag.retrieval.retrieval import HybridIndex

HISTORY_TURNS = 10  # 04 의 answer_questions 와 같은 대화 창


class Turn(BaseModel):
    question: str
    answer: str


class AskRequest(BaseModel):
    question: str
    history: list[Turn] = []


def ask(req: AskRequest, index, cfg: dict) -> dict:
    """질문 하나에 답하고 화면에 필요한 답변 · 출처 · 청크 본문만 돌려준다."""
    item = {"id": f"web-{uuid.uuid4()}", "question": req.question}
    history = [turn.model_dump() for turn in req.history[-HISTORY_TURNS:]]
    row = answer_question(item, index, cfg["llm"], cfg["rewrite"], history=history)
    return {"answer": row["answer"], "sources": row["sources"], "contexts": row["contexts"]}


@asynccontextmanager
async def lifespan(app: FastAPI):
    # 04_generation.ipynb 와 똑같이 config.yaml 위에 02 가 저장한 검색 설정을 덮는다
    cfg = load_config()
    retrieval_settings, = read_jsonl(ARTIFACTS / "retrieval_settings.jsonl")
    cfg.update(retrieval_settings)
    app.state.cfg = cfg
    app.state.index = HybridIndex(ARTIFACTS, cfg)
    yield


app = FastAPI(lifespan=lifespan)


@app.post("/api/ask")
def ask_endpoint(req: AskRequest) -> dict:
    return ask(req, app.state.index, app.state.cfg)
