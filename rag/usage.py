"""API 응답의 사용량과 예상 비용을 Langfuse 키 없이 로컬 CSV에 기록한다."""
from __future__ import annotations

import csv
from datetime import datetime, timezone
from threading import Lock

import pandas as pd
from langchain_core.callbacks import BaseCallbackHandler

from .config import ARTIFACTS

_CSV_LOCK = Lock()


def record_usage(stage: str, model: str, tokens: dict, prices: list[float],
                 subject: str = "", evaluation: str = "") -> dict:
    """캐시 입력은 입력에, 추론 토큰은 출력에 포함되므로 비용에 두 번 더하지 않는다."""
    cached = (tokens.get("prompt_tokens_details") or {}).get("cached_tokens") or 0
    reasoning = (tokens.get("completion_tokens_details") or {}).get("reasoning_tokens") or 0
    usd_in, usd_cached, usd_out = prices
    usage = {"model": model, "input_tokens": tokens["prompt_tokens"], "cached_input_tokens": cached,
             "output_tokens": tokens["completion_tokens"], "reasoning_tokens": reasoning,
             "cost_usd": ((tokens["prompt_tokens"] - cached) * usd_in + cached * usd_cached
                          + tokens["completion_tokens"] * usd_out) / 1e6}
    row = {"timestamp": datetime.now(timezone.utc).isoformat(), "stage": stage,
           "evaluation": evaluation, "subject": subject, **usage}
    path = ARTIFACTS / "api_usage.csv"
    with _CSV_LOCK:
        path.parent.mkdir(parents=True, exist_ok=True)
        needs_header = not path.exists()
        with path.open("a", encoding="utf-8", newline="") as file:
            writer = csv.DictWriter(file, fieldnames=list(row))
            if needs_header:
                writer.writeheader()
            writer.writerow(row)
    return usage


class UsageCallback(BaseCallbackHandler):
    """OCR와 RAGAS의 실제 LLM 호출마다 기록한다. RAGAS의 재시도도 소비량에 포함한다."""

    raise_error = True

    def __init__(self, stage: str, prices: list[float], evaluation: str = ""):
        self.stage, self.prices, self.evaluation = stage, prices, evaluation
        self.subject = ""

    def on_llm_end(self, response, **kwargs):
        output = response.llm_output
        record_usage(self.stage, output["model_name"], output["token_usage"], self.prices,
                     subject=self.subject, evaluation=self.evaluation)


def usage_summary(stage: str) -> pd.DataFrame:
    """해당 단계의 누적 호출 수·토큰·비용. API 호출 전에는 빈 표를 반환한다."""
    totals = ["input_tokens", "cached_input_tokens", "output_tokens", "reasoning_tokens", "cost_usd"]
    groups = ["stage", "evaluation", "model"]
    path = ARTIFACTS / "api_usage.csv"
    if not path.exists():
        return pd.DataFrame(columns=[*groups, "calls", *totals])
    rows = pd.read_csv(path, keep_default_na=False)
    rows = rows[rows["stage"] == stage]
    aggregations = {"calls": ("stage", "size"), **{name: (name, "sum") for name in totals}}
    return rows.groupby(groups).agg(**aggregations).reset_index()
