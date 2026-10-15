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
from decimal import Decimal
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


_DIGITS = r"\d+(?:,\d{3})*(?:\.\d+)?"
_UNITS = "원|초|분|시간|개월|년|월|일|명|개|건|회|%|조|항|호|차|점|장|단계"
# '글자-' 바로 뒤 숫자는 SFR-009 같은 식별자의 일부라 수량이 아니다 — 'SFR-009\n분류' 가 9분이 되지 않게
_NUMBER = re.compile(rf"(?<![\d.,])(?<![^\W\d_]-){_DIGITS}(?:\s*[억만천백](?:\s*{_DIGITS})?)*(?:\s*(?:{_UNITS}))?")
_NUMBER_PART = re.compile(rf"({_DIGITS})?([억만천백])|({_DIGITS})")
_MULTIPLIERS = {"억": 100_000_000, "만": 10_000, "천": 1_000, "백": 100}
_TIME = r"(?:\d{1,2}:\d{2}|(?:오전|오후)\s*\d{1,2}시(?:\s*\d{1,2}분)?)"
_DATE = re.compile(r"(?<!\d)(?P<year>\d{4})[.\-년]\s*(?P<month>\d{1,2})[.\-월]\s*"
                   r"(?P<day>\d{1,2})(?:일)?(?!\d)(?:\s*\([월화수목금토일](?:요일)?\))?"
                   rf"(?:\s*(?P<time>{_TIME}))?")


def _parse_number(value: str) -> str:
    total = Decimal(0)
    section = Decimal(0)
    for match in _NUMBER_PART.finditer(value):
        digits, scale, plain = match.groups()
        number = Decimal((digits or plain or "1").replace(",", ""))
        multiplier = _MULTIPLIERS.get(scale, 1)
        if multiplier >= 10_000:
            total += (section + (number if digits else 0)) * multiplier
            section = Decimal(0)
        else:
            section += number * multiplier
    return _number_token(total + section, re.sub(rf"{_DIGITS}|[억만천백\s]", "", value))


def _number_token(value: Decimal, unit: str) -> str:
    return f"⟦number:{value.normalize()}:{unit}⟧"


def _parse_time(value: str) -> str:
    hour, *minutes = map(int, re.findall(r"\d+", value))
    if "오전" in value or "오후" in value:
        hour = hour % 12 + (12 if "오후" in value else 0)
    return f"⟦time:{hour:02}:{minutes[0] if minutes else 0:02}⟧"


def _date_spans(match: re.Match) -> list[tuple[int, int, str]]:
    # 날짜를 년·월·일 숫자로 풀어 '3월 10일' 같은 부분 날짜 사실도 맞게 한다
    token = "".join(_number_token(Decimal(match[name]), unit)
                    for name, unit in (("year", "년"), ("month", "월"), ("day", "일")))
    end = match.start("time") if match["time"] else match.end()
    spans = [(match.start(), end, token)]
    if match["time"]:
        spans.append((match.start("time"), match.end(), _parse_time(match["time"])))
    return spans


def _number_spans(text: str, start: int, end: int) -> list[tuple[int, int, str]]:
    return [(m.start(), m.end(), _parse_number(m[0])) for m in _NUMBER.finditer(text, start, end)]


def _semantic_spans(text: str) -> list[tuple[int, int, str]]:
    spans = []
    start = 0
    for match in _DATE.finditer(text):
        spans.extend(_number_spans(text, start, match.start()))
        spans.extend(_date_spans(match))
        start = match.end()
    spans.extend(_number_spans(text, start, len(text)))
    return spans


def _plain_text(text: str, start: int, end: int) -> tuple[str, list[tuple[int, int]]]:
    chars, positions = [], []
    for i in range(start, end):
        if text[i].isspace() or text[i] == ",":
            continue
        lowered = text[i].lower()  # 'İ' 처럼 소문자가 두 글자가 되기도 해서 글자마다 위치를 남긴다
        chars.append(lowered)
        positions.extend([(i, i + 1)] * len(lowered))
    return "".join(chars), positions


def _canonical_text(text: str) -> tuple[str, list[tuple[int, int]]]:
    parts, positions = [], []
    cursor = 0
    for start, end, token in _semantic_spans(text):
        plain, offsets = _plain_text(text, cursor, start)
        parts.extend((plain, token))
        positions.extend(offsets)
        positions.extend([(start, end)] * len(token))
        cursor = end
    plain, offsets = _plain_text(text, cursor, len(text))
    parts.append(plain)
    positions.extend(offsets)
    return "".join(parts), positions


def _negated(text: str, start: int, end: int) -> bool:
    if start > 0 and text[start - 1] in "미불비" or re.search(r"않|제외|없", text[end:end + 6]):
        return True
    # '별도' 는 '부가세 별도' 처럼 말이 끝날 때만 부정이다. '별도 시건장치' · '별도로' 처럼 뒤를 꾸미면 '따로' 다
    separate = re.search(r"별도", text[end:end + 6])
    return separate is not None and not re.match(r"\s*\w", text[end + separate.end():])


def _fact_pattern(fact: str) -> str:
    """사실을 검색 패턴으로. 억·만 등으로 줄인 단위 없는 금액('1,000만')만 본문 쪽 '원'을 허용한다"""
    parts, cursor = [], 0
    for start, end, token in _semantic_spans(fact):
        parts.append(re.escape(_plain_text(fact, cursor, start)[0]))
        if token.endswith(":⟧") and re.search("[억만천백]", fact[start:end]):
            parts.append(re.escape(token[:-1]) + "(?:원)?⟧")
        else:
            parts.append(re.escape(token))
        cursor = end
    parts.append(re.escape(_plain_text(fact, cursor, len(fact))[0]))
    # 식별자 숫자는 글자 그대로 찾으므로 앞뒤에 숫자가 더 붙으면 다른 값이다 (SFR-009 ≠ SFR-0091)
    return ("(?<!\\d)" if fact[:1].isdigit() else "") + "".join(parts) + ("(?!\\d)" if fact[-1:].isdigit() else "")


def _fact_matches(fact: str, hay: str, positions: list[tuple[int, int]], text: str) -> bool:
    pattern = _fact_pattern(fact)
    if not re.search(r"\d", fact):
        hay, positions = _plain_text(text, 0, len(text))
    for match in re.finditer(pattern, hay):
        if not pattern or not _negated(text, positions[match.start()][0], positions[match.end() - 1][1]):
            return True
    return False


def _key_fact_ratio(facts: list[str], text: str) -> float:
    """핵심 사실 중 text 에 들어 있는 비율. 'A|B' 는 둘 중 하나만 있어도 맞음"""
    hay, positions = _canonical_text(text)
    return sum(any(_fact_matches(alt, hay, positions, text) for alt in str(f).split("|"))
               for f in facts) / len(facts)


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
