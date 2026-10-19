"""⑤ 평가 — 04 생성의 answers.jsonl 하나를 네 가지로 나눠 채점한다. 나쁜 답이 어디서 왔는지 가르기 위해서다.
  Retrieval    검색이 정답 근거를 가져왔나       context_precision · context_recall · 근거 속 핵심 사실 비율
  Generation   답이 질문에 맞고 핵심을 담았나    answer_relevancy · 답변 속 핵심 사실 비율
  Grounding    답이 검색 근거 안에서만 나왔나    faithfulness
  End-to-End   최종 답이 정답과 맞나, 얼마 들었나  factual_correctness · 지연 시간 · 토큰 · 예상 비용
심판은 evaluation.judge 로 고른다.
  local  로컬 KURE 임베딩 · 리랭커(크로스 인코더)로 같은 지표를 계산한다. API 를 부르지 않아 비용 0원 (기본값)
  ragas  RAGAS + gpt 심판 (유료). 몇 문항씩 채점할 때마다 체크포인트에 저장해, 끊겨도 남은 문항만 채점한다
.env 에 Langfuse 키가 있으면 질문별 점수를 04 생성의 추적(answer-question)에 붙인다.
담당: 평가."""
from __future__ import annotations

import hashlib
import json
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

from ..config import append_jsonl, read_checkpoint, read_jsonl, write_jsonl
from ..retrieval.indexing import Embedder, Reranker
from ..usage import UsageCallback

os.environ.setdefault("RAGAS_DO_NOT_TRACK", "true")  # ragas 사용 통계 전송 끔


_JUDGE_BATCH = 16  # 이 문항 수만큼 채점할 때마다 점수를 저장한다 (끊기면 이 묶음 하나만 다시 채점)


def _judge(cfg: dict, evaluation: str) -> LangchainLLMWrapper:
    ecfg = cfg["evaluation"]
    judge = ChatOpenAI(model=ecfg["judge_model"], max_tokens=int(ecfg["judge_max_tokens"]),
                       reasoning_effort=ecfg["judge_reasoning_effort"], timeout=180, max_retries=3,
                       callbacks=[UsageCallback("judge", ecfg["judge_usd_per_1m_tokens"],
                                                ecfg["judge_reasoning_effort"], evaluation)])
    # 추론 모델은 temperature·n 을 받지 않으므로 RAGAS 가 넣지 못하게 한다
    return LangchainLLMWrapper(judge, bypass_temperature=True, bypass_n=True)


def _score_key(row: dict, metrics: list, ecfg: dict, embeddings) -> str:
    """지표 · 심판 설정 · 문항(질문 · 근거 · 답 · 정답)이 모두 같을 때만 같은 키 — 04 를 다시 돌려 답이 바뀐 문항은 새로 채점한다"""
    key = json.dumps({"metrics": [m.name for m in metrics],
                      "judge": [ecfg["judge_model"], ecfg["judge_reasoning_effort"], ecfg["judge_max_tokens"]],
                      "embeddings": embeddings.model if embeddings else None,
                      "row": [row["question"], row["contexts"], row["answer"], row["reference"]]}, ensure_ascii=False)
    return hashlib.sha1(key.encode()).hexdigest()


def _saved_scores(path: Path) -> dict[str, dict]:
    saved = read_checkpoint(path)
    write_jsonl(saved, path)  # 쓰다 끊긴 마지막 줄을 잘라 내고 그 뒤에 덧붙인다
    return {s["key"]: s["scores"] for s in saved}


def _ragas(rows: list[dict], metrics: list, cfg: dict, evaluation: str, checkpoint: Path,
           embeddings=None) -> list[dict]:
    """RAGAS 채점 → 질문마다 {지표 이름: 점수}. checkpoint 에 저장된 문항은 다시 채점하지 않는다.
    NaN(심판 호출 실패 포함)은 저장하지 않아 다음 실행에서 다시 채점한다."""
    keys = [_score_key(r, metrics, cfg["evaluation"], embeddings) for r in rows]
    scores = _saved_scores(checkpoint)
    todo = [i for i, key in enumerate(keys) if key not in scores]
    print(f"{evaluation}: {len(rows)}문항 중 저장된 점수 {len(rows) - len(todo)}개, 채점할 문항 {len(todo)}개 — {checkpoint}")
    llm = _judge(cfg, evaluation) if todo else None
    emb = LangchainEmbeddingsWrapper(embeddings) if embeddings else None
    for start in range(0, len(todo), _JUDGE_BATCH):
        batch = todo[start:start + _JUDGE_BATCH]
        data = EvaluationDataset.from_list([{"user_input": rows[i]["question"],
                                             "retrieved_contexts": rows[i]["contexts"] or [""],
                                             "response": rows[i]["answer"], "reference": rows[i]["reference"]}
                                            for i in batch])
        for i, s in zip(batch, evaluate(data, metrics=metrics, llm=llm, embeddings=emb, show_progress=False).scores):
            scores[keys[i]] = s
            if not any(math.isnan(v) for v in s.values()):
                append_jsonl({"key": keys[i], "scores": s}, checkpoint)
        print(f"{evaluation} 채점 {start + len(batch)}/{len(todo)}")
    return [scores[key] for key in keys]


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


# ====================================================================================================
# 로컬 심판 — API 없이 RAGAS 와 같은 이름의 지표를 계산한다 (값의 크기는 RAGAS 와 다르므로 서로 비교하지 않는다)
#   문장 지지: 리랭커가 (문장, 근거) 를 관련 있다고 보고(점수 ≥ _SUPPORT_SCORE) 문장 속 숫자가 근거에 모두 있을 때
#   context_recall       정답 문장 중 검색 근거로 지지되는 비율
#   context_precision    검색 근거마다 정답 문장을 지지하나 → 순위를 반영한 평균 정밀도 (RAGAS 와 같은 식)
#   faithfulness         답 문장 중 검색 근거로 지지되는 비율
#   factual_correctness  답 문장이 정답으로 지지되는 비율(정밀도)과 정답 문장이 답으로 지지되는 비율(재현율)의 F1
#   answer_relevancy     질문과 답의 KURE 임베딩 코사인 유사도
# ====================================================================================================
_SUPPORT_SCORE = 0.5  # 리랭커 점수(0~1)가 이 이상이면 문장이 근거와 관련 있다고 본다
_NO_ANSWER = "제공된 문서에서 확인할 수 없습니다"  # 04 답변 프롬프트의 '답 없음' 문장 — 주장이 아니므로 채점하지 않는다
_CITATION = re.compile(r"\[\d+(?:\s*,\s*\d+)*\]")
_LIST_MARK = re.compile(r"^\s*(?:[-*•·>#]+|\d+[.)]|[가-하][.)])\s*")
_SENTENCE_END = re.compile(r"(?<=[.!?。])\s+")
_TABLE_RULE = re.compile(r"^\s*\|?\s*:?-{3,}")
_local_models: dict[tuple[str, str], object] = {}


def _local_model(kind: str, cfg: dict):
    """리랭커 · 임베딩 모델을 한 번만 읽어 네 평가가 같이 쓴다"""
    section = "rerank" if kind == "reranker" else "embedding"
    key = (kind, cfg[section]["model"])
    if key not in _local_models:
        _local_models[key] = Reranker(cfg["rerank"]) if kind == "reranker" else Embedder(cfg["embedding"])
    return _local_models[key]


def _sentences(text: str) -> list[str]:
    """채점할 문장들. 출처 표시 [1] · 목록 기호 · 표 머리글과 구분선 · 너무 짧은 제목과 '답 없음' 문장은 뺀다"""
    lines = _CITATION.sub("", text).splitlines()
    header = {i - 1 for i, line in enumerate(lines) if _TABLE_RULE.match(line)}  # 구분선 바로 윗줄 = 표 머리글
    out = []
    for i, line in enumerate(lines):
        if i in header:
            continue
        for part in _SENTENCE_END.split(line):
            sentence = _LIST_MARK.sub("", part.replace("|", " ").replace("**", "")).strip()
            if len(re.sub(r"\W", "", sentence)) >= 6 and _NO_ANSWER not in sentence:
                out.append(sentence)
    return out


def _claims(text: str) -> list[str]:
    """채점할 문장. 문장 거르기(_sentences)에서 모두 빠지는 짧은 글('180일' · '1식' · '12개월')은 글 전체를 한 문장으로 —
    빼면 짧은 정답의 질문은 검색 · 생성을 잘해도 늘 0점이 된다 (dev 484문항 중 70문항). '답 없음' 문장은 그대로 뺀다"""
    whole = _LIST_MARK.sub("", _CITATION.sub("", text).replace("|", " ").replace("**", "")).strip()
    return _sentences(text) or ([whole] if re.search(r"\w", whole) and _NO_ANSWER not in whole else [])


def _numbers(text: str) -> set[str]:
    """단위까지 맞춘 숫자 · 날짜 토큰 ('3 초' = '3초', '5천만 원' = '5,000만원')"""
    return {token for _, _, token in _semantic_spans(text)}


def _relevance(claims: list[str], passages: list[str], cfg: dict) -> list[list[float]]:
    """claims × passages 리랭커 점수. 문장이 근거에 글자 그대로(띄어쓰기 · 숫자 표기 차이는 무시) 있거나, 근거가 문장으로
    거르면 남지 않는 짧은 값('180일' · '1식')이고 그 값이 문장 안에 있으면 1 — 리랭커는 짧은 글의 관련도를 낮게 매긴다.
    정답이 '180일' 이고 답이 '사업기간은 180일입니다' 이면 그 답 문장은 정답으로 지지된다"""
    reranker = _local_model("reranker", cfg)
    return [[1.0 if _contains(claim, passage) else score
             for passage, score in zip(passages, reranker.scores(claim, passages))] for claim in claims]


def _contains(claim: str, passage: str) -> bool:
    return _key_fact_ratio([claim], passage) == 1 or (not _sentences(passage) and _key_fact_ratio([passage], claim) == 1)


def _supported(claims: list[str], passages: list[str], scores: list[list[float]], question: str) -> list[bool]:
    """질문에 나온 숫자는 근거에 없어도 된다 — '5초가 아니라 3초' 처럼 잘못된 전제를 바로잡는 문장도 지지로 본다"""
    numbers = _numbers(" ".join(passages)) | _numbers(question)
    return [max(row) >= _SUPPORT_SCORE and _numbers(claim) <= numbers for claim, row in zip(claims, scores)]


def _ratio(flags: list[bool]) -> float:
    return sum(flags) / len(flags) if flags else math.nan


def _average_precision(relevant: list[bool]) -> float:
    """순위 k 마다 (상위 k 개 정밀도 × k 번째가 관련 있나) 의 합 / 관련 근거 수 — RAGAS context_precision 과 같은 식"""
    hits, total = 0, 0.0
    for k, is_relevant in enumerate(relevant, 1):
        hits += is_relevant
        total += hits / k if is_relevant else 0.0
    return total / hits if hits else 0.0


def _local_retrieval(row: dict, cfg: dict) -> dict:
    references, contexts = _claims(row["reference"]), [c for c in row["contexts"] if c.strip()]
    if not references or not contexts:
        return {"context_precision": 0.0, "context_recall": 0.0}
    scores = _relevance(references, contexts, cfg)
    relevant = [max(column) >= _SUPPORT_SCORE for column in zip(*scores)]
    return {"context_precision": _average_precision(relevant),
            "context_recall": _ratio(_supported(references, contexts, scores, row["question"]))}


def _local_generation(row: dict, cfg: dict) -> dict:
    if not row["answer"].strip():
        return {"answer_relevancy": 0.0}
    question, answer = _local_model("embedder", cfg).encode([row["question"], row["answer"]])
    return {"answer_relevancy": float(question @ answer)}  # 정규화된 벡터라 내적 = 코사인 유사도


def _local_grounding(row: dict, cfg: dict) -> dict:
    """답에 채점할 문장이 없으면(빈 답 · '답 없음'만) RAGAS 처럼 NaN"""
    claims, contexts = _claims(row["answer"]), [c for c in row["contexts"] if c.strip()]
    if not claims or not contexts:
        return {"faithfulness": math.nan if not claims else 0.0}
    scores = _relevance(claims, contexts, cfg)
    return {"faithfulness": _ratio(_supported(claims, contexts, scores, row["question"]))}


def _windows(sentences: list[str], size: int = 3) -> list[str]:
    """이어진 문장 size 개씩 묶는다 — 정답 한 문장의 내용이 답의 여러 문장에 나뉘어 있어도 지지로 본다"""
    return [" ".join(sentences[i:i + size]) for i in range(max(1, len(sentences) - size + 1))]


def _local_end_to_end(row: dict, cfg: dict) -> dict:
    answer, references = _claims(row["answer"]), _claims(row["reference"])
    if not answer or not references:
        return {"factual_correctness": 0.0}
    reference = [" ".join(references)]
    precision = _ratio(_supported(answer, reference, _relevance(answer, reference, cfg), row["question"]))
    windows = _windows(answer)
    recall = _ratio(_supported(references, windows, _relevance(references, windows, cfg), row["question"]))
    return {"factual_correctness": 2 * precision * recall / (precision + recall) if precision + recall else 0.0}


_LOCAL = {"retrieval": _local_retrieval, "generation": _local_generation,
          "grounding": _local_grounding, "end_to_end": _local_end_to_end}
# RAGAS 지표와 결과 이름 → 표 열 이름
_RAGAS = {"retrieval": (lambda: [LLMContextPrecisionWithReference(), LLMContextRecall()],
                        {"llm_context_precision_with_reference": "context_precision",
                         "context_recall": "context_recall"}),
          "generation": (lambda: [ResponseRelevancy()], {"answer_relevancy": "answer_relevancy"}),
          "grounding": (lambda: [Faithfulness()], {"faithfulness": "faithfulness"}),
          "end_to_end": (lambda: [FactualCorrectness()], {"factual_correctness(mode=f1)": "factual_correctness"})}


def _judge_scores(rows: list[dict], cfg: dict, evaluation: str, answers_path: Path) -> list[dict]:
    """질문마다 {표 열 이름: 점수}. judge 가 local 이면 API 를 부르지 않는다"""
    if cfg["evaluation"]["judge"] == "local":
        print(f"{evaluation}: 로컬 심판으로 {len(rows)}문항 채점 (API 호출 없음)")
        return [_LOCAL[evaluation](r, cfg) for r in rows]
    metrics, names = _RAGAS[evaluation]
    embeddings = Embedder(cfg["embedding"]) if evaluation == "generation" else None
    scores = _ragas(rows, metrics(), cfg, evaluation, _checkpoint(answers_path, evaluation), embeddings)
    return [{column: s[name] for name, column in names.items()} for s in scores]


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


# 05 의 네 평가가 답변 파일 한 행에서 읽는 필드
ANSWER_FIELDS = ("id", "question", "reference", "key_facts", "answerable", "answer", "contexts", "trace_id", "latency_s",
                 "input_tokens", "output_tokens", "cached_input_tokens", "reasoning_tokens", "cost_usd", "rewrite")


def _read_answers(answers_path: Path) -> list[dict]:
    """답변 파일을 읽고, 평가가 읽을 필드가 빠진 행이 있으면 RAGAS 호출(유료) 전에 멈춘다"""
    answers = read_jsonl(answers_path)
    missing = sorted({field for r in answers for field in ANSWER_FIELDS if field not in r})
    if missing:
        raise ValueError(f"{answers_path} 에 {missing} 필드가 없습니다. 03 → 02 설정 셀 → 04 를 다시 실행해 답변 파일을 만드세요")
    return answers


def _unanswerable_as_nan(rows: list[dict], scores: list[dict], names: tuple[str, ...]) -> list[dict]:
    """답이 문서에 없는 질문(answerable False)에서 names 지표를 NaN 으로 — 평균 · Langfuse 에서 빠진다.
    그 질문은 찾아 올 정답 근거가 없고 맞는 답이 거절 문장('확인할 수 없습니다')이라, 이 지표들은 잘 해도 0 이 나온다"""
    return [s if r["answerable"] else {**s, **dict.fromkeys(names, math.nan)} for r, s in zip(rows, scores)]


def _checkpoint(answers_path: Path, evaluation: str) -> Path:
    """평가별 점수 체크포인트 — answers.jsonl 옆 checkpoints/judge/<평가>.jsonl"""
    return answers_path.with_name("checkpoints") / "judge" / f"{evaluation}.jsonl"


def evaluate_retrieval(answers_path: Path, cfg: dict) -> pd.DataFrame:
    """Retrieval: 검색한 청크가 정답에 필요한 내용을 담았나"""
    rows = _read_answers(answers_path)
    judged = _judge_scores(rows, cfg, "retrieval", answers_path)
    scores = [{**j, "key_facts_in_context": _key_fact_ratio(r["key_facts"], " ".join(r["contexts"]))}
              for r, j in zip(rows, judged)]
    scores = _unanswerable_as_nan(rows, scores, ("context_precision", "context_recall", "key_facts_in_context"))
    _send_scores(rows, scores)
    return _table(rows, scores, answers_path.with_name("retrieval.csv"))


def evaluate_generation(answers_path: Path, cfg: dict) -> pd.DataFrame:
    """Generation: 답이 질문에 맞게 핵심 사실을 담았나 (answer_relevancy 는 KURE 임베딩으로 계산)"""
    rows = _read_answers(answers_path)
    judged = _judge_scores(rows, cfg, "generation", answers_path)
    scores = [{**j, "key_facts_in_answer": _key_fact_ratio(r["key_facts"], r["answer"])} for r, j in zip(rows, judged)]
    # answer_relevancy 는 얼버무린 답(거절 포함)을 0 으로 매긴다. 거절이 정답인 질문에서는 뺀다
    scores = _unanswerable_as_nan(rows, scores, ("answer_relevancy",))
    _send_scores(rows, scores)
    return _table(rows, scores, answers_path.with_name("generation.csv"))


def evaluate_grounding(answers_path: Path, cfg: dict) -> pd.DataFrame:
    """Grounding: 답의 주장들이 검색한 청크로 뒷받침되나 (낮으면 환각)"""
    rows = _read_answers(answers_path)
    scores = _judge_scores(rows, cfg, "grounding", answers_path)
    _send_scores(rows, scores)
    return _table(rows, scores, answers_path.with_name("grounding.csv"))


def evaluate_end_to_end(answers_path: Path, cfg: dict) -> pd.DataFrame:
    """End-to-End: 최종 답이 정답과 사실이 맞는지 + 질문당 지연 시간·토큰·예상 비용(USD)"""
    rows = _read_answers(answers_path)
    judged = _judge_scores(rows, cfg, "end_to_end", answers_path)
    # 지연 시간 · 토큰 · 비용은 추적에 이미 있으므로 점수로는 factual_correctness 만 보낸다
    _send_scores(rows, judged)
    scores = [{**j, "latency_s": r["latency_s"],
               "input_tokens": r["input_tokens"], "output_tokens": r["output_tokens"],
               "cached_input_tokens": r["cached_input_tokens"], "reasoning_tokens": r["reasoning_tokens"],
               "rewrite_input_tokens": r["rewrite"]["input_tokens"],
               "rewrite_output_tokens": r["rewrite"]["output_tokens"],
               "rewrite_cached_input_tokens": r["rewrite"]["cached_input_tokens"],
               "rewrite_reasoning_tokens": r["rewrite"]["reasoning_tokens"],
               "answer_cost_usd": r["cost_usd"], "rewrite_cost_usd": r["rewrite"]["cost_usd"],
               "cost_usd": r["cost_usd"] + r["rewrite"]["cost_usd"]}
              for r, j in zip(rows, judged)]
    return _table(rows, scores, answers_path.with_name("end_to_end.csv"))
