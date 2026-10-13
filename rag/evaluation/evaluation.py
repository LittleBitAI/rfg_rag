"""⑤ 평가 — 04 생성의 answers.jsonl 하나를 네 가지로 나눠 채점한다. 나쁜 답이 어디서 왔는지 가르기 위해서다.
  Retrieval    검색이 정답 근거를 가져왔나       context_precision · context_recall · 근거 속 핵심 사실 비율
  Generation   답이 질문에 맞고 핵심을 담았나    answer_relevancy · 답변 속 핵심 사실 비율
  Grounding    답이 검색 근거 안에서만 나왔나    faithfulness
  End-to-End   최종 답이 정답과 맞나, 얼마 들었나  factual_correctness · 지연 시간 · 토큰 · 예상 비용
.env 에 Langfuse 키가 있으면 질문별 점수를 04 생성의 추적(answer-question)에 붙인다.
담당: 평가."""
from __future__ import annotations

import math
import os
import re
from pathlib import Path

import pandas as pd
from langchain_openai import ChatOpenAI
from langfuse import get_client
from ragas import EvaluationDataset, evaluate
from ragas.embeddings import LangchainEmbeddingsWrapper
from ragas.llms import LangchainLLMWrapper
from ragas.metrics import (FactualCorrectness, Faithfulness, LLMContextPrecisionWithReference, LLMContextRecall,
                           ResponseRelevancy)

from ..config import read_jsonl
from ..retrieval.indexing import Embedder
from ..usage import UsageCallback

os.environ.setdefault("RAGAS_DO_NOT_TRACK", "true")  # ragas 사용 통계 전송 끔


def _ragas(rows: list[dict], metrics: list, cfg: dict, evaluation: str, embeddings=None) -> list[dict]:
    """RAGAS 채점 → 질문마다 {지표 이름: 점수}"""
    ecfg = cfg["evaluation"]
    judge = ChatOpenAI(model=ecfg["judge_model"], max_tokens=int(ecfg["judge_max_tokens"]),
                       reasoning_effort=ecfg["judge_reasoning_effort"], timeout=180, max_retries=3,
                       callbacks=[UsageCallback("judge", ecfg["judge_usd_per_1m_tokens"], evaluation)])
    # 추론 모델은 temperature·n 을 받지 않으므로 RAGAS 가 넣지 못하게 한다
    llm = LangchainLLMWrapper(judge, bypass_temperature=True, bypass_n=True)
    data = EvaluationDataset.from_list([{"user_input": r["question"], "retrieved_contexts": r["contexts"] or [""],
                                         "response": r["answer"], "reference": r["reference"]} for r in rows])
    emb = LangchainEmbeddingsWrapper(embeddings) if embeddings else None
    return evaluate(data, metrics=metrics, llm=llm, embeddings=emb).scores


def _norm(s: str) -> str:
    return re.sub(r"[\s,]", "", s).lower()


def _key_fact_ratio(facts: list[str], text: str) -> float:
    """핵심 사실 중 text 에 들어 있는 비율. 'A|B' 는 둘 중 하나만 있어도 맞음"""
    hay = _norm(text)
    return sum(any(_norm(alt) in hay for alt in str(f).split("|")) for f in facts) / len(facts)


def _send_scores(rows: list[dict], scores: list[dict]):
    """질문별 점수를 그 질문의 Langfuse 추적에 붙인다. trace_id 가 없으면(키 없이 생성한 답) 보내지 않는다"""
    langfuse = get_client()
    for r, s in zip(rows, scores):
        if not r["trace_id"]:
            continue
        for name, value in s.items():
            if not math.isnan(value):
                langfuse.create_score(trace_id=r["trace_id"], name=name, value=value, data_type="NUMERIC")
    langfuse.flush()


def _table(rows: list[dict], scores: list[dict], path: Path) -> pd.DataFrame:
    """질문별 표 + 맨 아래 '평균' 행을 반환하고 CSV로 자동 저장한다."""
    df = pd.DataFrame([{"id": r["id"], "question": r["question"], **s} for r, s in zip(rows, scores)])
    mean = df.mean(numeric_only=True).to_frame().T.assign(id="평균", question="")
    table = pd.concat([df, mean], ignore_index=True).round(
        {name: 8 if name.endswith("cost_usd") else 4 for name in scores[0]})
    table.to_csv(path, index=False, encoding="utf-8")
    return table


def evaluate_retrieval(answers_path: Path, cfg: dict) -> pd.DataFrame:
    """Retrieval: 검색한 청크가 정답에 필요한 내용을 담았나"""
    rows = read_jsonl(answers_path)
    ragas = _ragas(rows, [LLMContextPrecisionWithReference(), LLMContextRecall()], cfg, "retrieval")
    scores = [{"context_precision": s["llm_context_precision_with_reference"], "context_recall": s["context_recall"],
               "key_facts_in_context": _key_fact_ratio(r["key_facts"], " ".join(r["contexts"]))}
              for r, s in zip(rows, ragas)]
    _send_scores(rows, scores)
    return _table(rows, scores, answers_path.with_name("retrieval.csv"))


def evaluate_generation(answers_path: Path, cfg: dict) -> pd.DataFrame:
    """Generation: 답이 질문에 맞게 핵심 사실을 담았나 (answer_relevancy 는 KURE 임베딩으로 계산)"""
    rows = read_jsonl(answers_path)
    ragas = _ragas(rows, [ResponseRelevancy()], cfg, "generation", embeddings=Embedder(cfg["embedding"]))
    scores = [{"answer_relevancy": s["answer_relevancy"], "key_facts_in_answer": _key_fact_ratio(r["key_facts"], r["answer"])}
              for r, s in zip(rows, ragas)]
    _send_scores(rows, scores)
    return _table(rows, scores, answers_path.with_name("generation.csv"))


def evaluate_grounding(answers_path: Path, cfg: dict) -> pd.DataFrame:
    """Grounding: 답의 주장들이 검색한 청크로 뒷받침되나 (낮으면 환각)"""
    rows = read_jsonl(answers_path)
    ragas = _ragas(rows, [Faithfulness()], cfg, "grounding")
    scores = [{"faithfulness": s["faithfulness"]} for s in ragas]
    _send_scores(rows, scores)
    return _table(rows, scores, answers_path.with_name("grounding.csv"))


def evaluate_end_to_end(answers_path: Path, cfg: dict) -> pd.DataFrame:
    """End-to-End: 최종 답이 정답과 사실이 맞는지 + 질문당 지연 시간·토큰·예상 비용(USD)"""
    rows = read_jsonl(answers_path)
    ragas = _ragas(rows, [FactualCorrectness()], cfg, "end_to_end")
    # 지연 시간 · 토큰 · 비용은 추적에 이미 있으므로 점수로는 factual_correctness 만 보낸다
    _send_scores(rows, [{"factual_correctness": s["factual_correctness(mode=f1)"]} for s in ragas])
    scores = [{"factual_correctness": s["factual_correctness(mode=f1)"], "latency_s": r["latency_s"],
               "input_tokens": r["input_tokens"], "output_tokens": r["output_tokens"],
               "cached_input_tokens": r["cached_input_tokens"], "reasoning_tokens": r["reasoning_tokens"],
               "rewrite_input_tokens": r["rewrite"]["input_tokens"],
               "rewrite_output_tokens": r["rewrite"]["output_tokens"],
               "rewrite_cached_input_tokens": r["rewrite"]["cached_input_tokens"],
               "rewrite_reasoning_tokens": r["rewrite"]["reasoning_tokens"],
               "answer_cost_usd": r["cost_usd"], "rewrite_cost_usd": r["rewrite"]["cost_usd"],
               "cost_usd": r["cost_usd"] + r["rewrite"]["cost_usd"]}
              for r, s in zip(rows, ragas)]
    return _table(rows, scores, answers_path.with_name("end_to_end.csv"))
