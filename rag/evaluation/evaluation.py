"""⑤ 평가 — 04 생성의 answers.jsonl 하나를 네 가지로 나눠 채점한다. 나쁜 답이 어디서 왔는지 가르기 위해서다.
  Retrieval    검색이 정답 근거를 가져왔나       Recall@k · MRR@k · Evidence Coverage · 문자열 일치
  Generation   답이 핵심을 담았나              답변 속 핵심 사실 문자열 일치
  Grounding    답이 검색 근거 안에서만 나왔나    faithfulness
  End-to-End   최종 답이 정답과 맞나, 얼마 들었나  factual_correctness · 지연 시간 · 토큰 · 예상 비용
.env 에 Langfuse 키가 있으면 질문별 점수를 04 생성의 추적(answer-question)에 붙인다.
RAGAS 점수는 몇 문항씩 채점할 때마다 체크포인트에 저장해, 끊겨도 남은 문항만 채점한다.
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
from ragas.llms import LangchainLLMWrapper
from ragas.metrics import FactualCorrectness, Faithfulness

from ..config import append_jsonl, read_checkpoint, read_jsonl, write_jsonl
from ..retrieval.retrieval import retrieval_fields
from ..usage import UsageCallback
from .ir import coverage_group, exclusion_report, ir_scores, label_state

os.environ.setdefault("RAGAS_DO_NOT_TRACK", "true")  # ragas 사용 통계 전송 끔


_JUDGE_BATCH = 16  # 이 문항 수만큼 채점할 때마다 점수를 저장한다 (끊기면 이 묶음 하나만 다시 채점)


def _judge(ecfg: dict, evaluation: str) -> LangchainLLMWrapper:
    judge = ChatOpenAI(model=ecfg["judge_model"], max_tokens=int(ecfg["judge_max_tokens"]),
                       reasoning_effort=ecfg["judge_reasoning_effort"], timeout=180, max_retries=3,
                       callbacks=[UsageCallback("judge", ecfg["judge_usd_per_1m_tokens"], evaluation)])
    # 추론 모델은 temperature·n 을 받지 않으므로 RAGAS 가 넣지 못하게 한다
    return LangchainLLMWrapper(judge, bypass_temperature=True, bypass_n=True)


def _score_key(row: dict, metrics: list, ecfg: dict) -> str:
    """지표 · 심판 설정 · 문항(질문 · 근거 · 답 · 정답)이 모두 같을 때만 같은 키 — 04 를 다시 돌려 답이 바뀐 문항은 새로 채점한다"""
    key = json.dumps({"metrics": [m.name for m in metrics],
                      "judge": [ecfg["judge_model"], ecfg["judge_reasoning_effort"], ecfg["judge_max_tokens"]],
                      "row": [row["question"], row["contexts"], row["answer"], row["reference"]]}, ensure_ascii=False)
    return hashlib.sha1(key.encode()).hexdigest()


def _saved_scores(path: Path) -> dict[str, dict]:
    saved = read_checkpoint(path)
    write_jsonl(saved, path)  # 쓰다 끊긴 마지막 줄을 잘라 내고 그 뒤에 덧붙인다
    return {s["key"]: s["scores"] for s in saved}


def _ragas(rows: list[dict], metrics: list, cfg: dict, evaluation: str, checkpoint: Path) -> list[dict]:
    """RAGAS 채점 → 질문마다 {지표 이름: 점수}. checkpoint 에 저장된 문항은 다시 채점하지 않는다.
    NaN(심판 호출 실패 포함)은 저장하지 않아 다음 실행에서 다시 채점한다."""
    keys = [_score_key(r, metrics, cfg["evaluation"]) for r in rows]
    scores = _saved_scores(checkpoint)
    todo = [i for i, key in enumerate(keys) if key not in scores]
    print(f"{evaluation}: {len(rows)}문항 중 저장된 점수 {len(rows) - len(todo)}개, 채점할 문항 {len(todo)}개 — {checkpoint}")
    llm = _judge(cfg["evaluation"], evaluation) if todo else None
    for start in range(0, len(todo), _JUDGE_BATCH):
        batch = todo[start:start + _JUDGE_BATCH]
        data = EvaluationDataset.from_list([{"user_input": rows[i]["question"],
                                             "retrieved_contexts": rows[i]["contexts"] or [""],
                                             "response": rows[i]["answer"], "reference": rows[i]["reference"]}
                                            for i in batch])
        for i, s in zip(batch, evaluate(data, metrics=metrics, llm=llm).scores):
            scores[keys[i]] = s
            if not any(math.isnan(v) for v in s.values()):
                append_jsonl({"key": keys[i], "scores": s}, checkpoint)
    return [scores[key] for key in keys]


def _checkpoint(answers_path: Path, evaluation: str) -> Path:
    """평가별 점수 체크포인트 — answers.jsonl 옆 checkpoints/judge/<평가>.jsonl"""
    return answers_path.with_name("checkpoints") / "judge" / f"{evaluation}.jsonl"


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
    if not any(r["trace_id"] for r in rows):
        return
    langfuse = get_client()
    for r, s in zip(rows, scores):
        if not r["trace_id"]:
            continue
        for name, value in s.items():
            if isinstance(value, (int, float)) and not math.isnan(value):
                langfuse.create_score(trace_id=r["trace_id"], name=name, value=value, data_type="NUMERIC")
    langfuse.flush()


def _table(rows: list[dict], scores: list[dict], path: Path) -> pd.DataFrame:
    """질문별 표 + 맨 아래 '평균' 행을 반환하고 CSV로 자동 저장한다."""
    df = pd.DataFrame([{"id": r["id"], "question": r["question"], **s} for r, s in zip(rows, scores)])
    mean = df.mean(numeric_only=True).to_frame().T.assign(id="평균", question="")
    table = pd.concat([df, mean], ignore_index=True).round(
        {name: 8 if name.endswith("cost_usd") else 4 for name, value in scores[0].items()
         if isinstance(value, (int, float))})
    table.to_csv(path, index=False, encoding="utf-8")
    return table


# JSON으로 저장된 04 출력 중 05가 소비하는 필드만 검사한다. 생산자의 추가 메타데이터는 보존한다.
_NUMERIC_TYPES = (int, float)
_NULLABLE_TEXT = (str, type(None))
_USAGE_FIELDS = {"input_tokens": int, "output_tokens": int, "cached_input_tokens": int,
                 "reasoning_tokens": int, "cost_usd": _NUMERIC_TYPES}
ANSWER_FIELDS = {
    "id": str, "question": str, "reference": str, "key_facts": [str], "answerable": bool,
    "answer": str, "contexts": [str], "trace_id": _NULLABLE_TEXT, "latency_s": _NUMERIC_TYPES,
    **_USAGE_FIELDS, "primary_topic": _NULLABLE_TEXT, "context_chunk_ids": [str],
    "rewrite": {"question": str, **_USAGE_FIELDS},
    "retrieval_settings": {"dense_weight": _NUMERIC_TYPES, "candidate_k": int, "token_budget": int,
                           "chunk_file": str, "k_values": [int], "stored_rewrites_reused": bool},
    "ranked_candidates": [{"chunk_id": str, "doc_id": str, "fused_rank": int,
                           "dense_score": (*_NUMERIC_TYPES, type(None)), "dense_rank": (int, type(None)),
                           "bm25_score": (*_NUMERIC_TYPES, type(None)), "bm25_rank": (int, type(None)),
                           "exact_code_match": bool}],
    "evidence": [{"doc_id": _NULLABLE_TEXT, "chunk_id": _NULLABLE_TEXT}],
}


def _invalid_record_fields(record, fields: dict, prefix: str) -> list[str]:
    if not isinstance(record, dict):
        return [prefix]
    invalid = []
    for field, expected in fields.items():
        path = f"{prefix}.{field}"
        invalid.extend([path] if field not in record else _invalid_field_value(record[field], expected, path))
    return invalid


def _invalid_list_items(value, expected: list, prefix: str) -> list[str]:
    if not isinstance(value, list):
        return [prefix]
    return [field for i, item in enumerate(value) for field in _invalid_field_value(item, expected[0], f"{prefix}[{i}]")]


def _invalid_field_value(value, expected, prefix: str) -> list[str]:
    if isinstance(expected, dict):
        return _invalid_record_fields(value, expected, prefix)
    if isinstance(expected, list):
        return _invalid_list_items(value, expected, prefix)
    types = expected if isinstance(expected, tuple) else (expected,)
    # bool은 int의 하위 클래스지만 토큰·비용·순위의 숫자로 허용하지 않는다.
    if type(value) not in types:
        return [prefix]
    return [prefix] if type(value) is float and not math.isfinite(value) else []


def _read_answers(answers_path: Path) -> list[dict]:
    """모든 행의 필수 값·자료형을 검사한 뒤 반환한다. 잘못된 값은 유료 호출 전에 멈춘다."""
    answers = read_jsonl(answers_path)
    invalid = [field for i, row in enumerate(answers, 1) for field in _invalid_record_fields(row, ANSWER_FIELDS, f"row[{i}]")]
    if invalid:
        raise ValueError(f"{answers_path} 에 {invalid} 필드가 없거나 형식이 잘못되었습니다. "
                         "03 → 02 설정 셀 → 04 를 다시 실행해 답변 파일을 만드세요")
    return answers


def evaluate_retrieval(answers_path: Path, cfg: dict) -> pd.DataFrame:
    """Retrieval: API 없이 패킹 전 순위와 LLM에 보낸 청크를 평가한다."""
    rows = _read_answers(answers_path)
    scores = [{**ir_scores(r), "key_facts_in_context": _key_fact_ratio(r["key_facts"], " ".join(r["contexts"]))
               if r["answerable"] and r["key_facts"] else math.nan,
               "primary_topic": r["primary_topic"], "coverage_group": coverage_group(r),
               "doc_label_state": label_state(r, "doc"), "chunk_label_state": label_state(r, "chunk"),
               "retrieval_settings": json.dumps(r["retrieval_settings"], ensure_ascii=False)} for r in rows]
    _send_scores(rows, scores)
    exclusion_report(rows).to_csv(answers_path.with_name("retrieval_exclusions.csv"), index=False, encoding="utf-8")
    return _table(rows, scores, answers_path.with_name("retrieval.csv"))


def rerun_retrieval(answers_path: Path, output_path: Path, index) -> list[dict]:
    """저장된 재작성 질문으로 검색만 다시 한다. 재작성·생성·심판 API 호출은 없다."""
    rows = _read_answers(answers_path)
    rescored = []
    for row in rows:
        hits, fields = retrieval_fields(index, row["question"], row["rewrite"]["question"], reused=True)
        rescored.append({**row, **fields, "contexts": [h["body"] for h in hits],
                         "sources": [f"{h['source']} p.{h['page']}" if h["page"] else h["source"] for h in hits],
                         "trace_id": None})
    write_jsonl(rescored, output_path)
    return rescored


def evaluate_generation(answers_path: Path, cfg: dict) -> pd.DataFrame:
    """Generation: 정답의 핵심 사실 문자열이 답변에 포함되는 비율."""
    rows = _read_answers(answers_path)
    scores = [{"key_facts_in_answer": _key_fact_ratio(r["key_facts"], r["answer"])
               if r["key_facts"] else math.nan} for r in rows]
    _send_scores(rows, scores)
    return _table(rows, scores, answers_path.with_name("generation.csv"))


def evaluate_grounding(answers_path: Path, cfg: dict) -> pd.DataFrame:
    """Grounding: 답의 주장들이 검색한 청크로 뒷받침되나 (낮으면 환각)"""
    rows = _read_answers(answers_path)
    ragas = _ragas(rows, [Faithfulness()], cfg, "grounding", _checkpoint(answers_path, "grounding"))
    scores = [{"faithfulness": s["faithfulness"]} for s in ragas]
    _send_scores(rows, scores)
    return _table(rows, scores, answers_path.with_name("grounding.csv"))


def evaluate_end_to_end(answers_path: Path, cfg: dict) -> pd.DataFrame:
    """End-to-End: 최종 답이 정답과 사실이 맞는지 + 질문당 지연 시간·토큰·예상 비용(USD)"""
    rows = _read_answers(answers_path)
    ragas = _ragas(rows, [FactualCorrectness()], cfg, "end_to_end", _checkpoint(answers_path, "end_to_end"))
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
