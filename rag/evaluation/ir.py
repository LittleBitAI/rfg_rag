"""골든 문서·청크 라벨로 API 없이 검색 순위와 실제 컨텍스트를 평가한다."""
from __future__ import annotations

import math

import pandas as pd

K_VALUES = (5, 10, 20)
COMPONENTS = ("fused", "dense", "bm25")


def recall_at_k(ranking: list[str], gold: set[str], k: int) -> float:
    return len(set(ranking[:k]) & gold) / len(gold)


def mrr_at_k(ranking: list[str], gold: set[str], k: int) -> float:
    return next((1 / rank for rank, value in enumerate(ranking[:k], 1) if value in gold), 0.0)


def evidence_coverage(sent: list[str], gold: set[str]) -> dict:
    coverage = len(set(sent) & gold) / len(gold)
    return {"evidence_coverage": coverage, "full_evidence_coverage": float(coverage == 1)}


def label_state(row: dict, level: str) -> str:
    if not row["answerable"]:
        return "unanswerable"
    evidence = row["evidence"]
    if not evidence:
        return "no_golden_evidence"
    count = sum(bool(e[f"{level}_id"]) for e in evidence)
    if count == len(evidence):
        return "fully_labelled"
    return "partly_labelled" if count else "unlabelled"


def _ranking(candidates: list[dict], component: str, level: str) -> list[str]:
    rank = f"{component}_rank"
    return [c[f"{level}_id"] for c in sorted((c for c in candidates if c[rank] is not None),
                                            key=lambda c: c[rank])]


def ir_scores(row: dict) -> dict:
    scores = {}
    for level in ("doc", "chunk"):
        gold = {e[f"{level}_id"] for e in row["evidence"]}
        eligible = label_state(row, level) == "fully_labelled"
        for component in COMPONENTS:
            ranking = _ranking(row["ranked_candidates"], component, level)
            for k in K_VALUES:
                scores[f"{level}_{component}_recall_at_{k}"] = recall_at_k(ranking, gold, k) if eligible else math.nan
                if component == "fused":
                    scores[f"{level}_mrr_at_{k}"] = mrr_at_k(ranking, gold, k) if eligible else math.nan
        exact = {c[f"{level}_id"] for c in row["ranked_candidates"] if c["exact_code_match"]}
        scores[f"{level}_exact_code_recall"] = len(exact & gold) / len(gold) if eligible else math.nan
    gold = {e["chunk_id"] for e in row["evidence"]}
    coverage = evidence_coverage(row["context_chunk_ids"], gold) if label_state(row, "chunk") == "fully_labelled" else {
        "evidence_coverage": math.nan, "full_evidence_coverage": math.nan}
    return {**scores, **coverage}


def coverage_group(row: dict) -> str:
    return "multi_evidence" if row["primary_topic"] in ("multi_hop", "comparison") or len(row["evidence"]) > 1 else "single_evidence"


def exclusion_report(rows: list[dict]) -> pd.DataFrame:
    report = []
    for topic in ["ALL", *sorted({r["primary_topic"] or "yaml" for r in rows})]:
        selected = rows if topic == "ALL" else [r for r in rows if (r["primary_topic"] or "yaml") == topic]
        for level in ("doc", "chunk"):
            states = [label_state(r, level) for r in selected]
            counts = {state: states.count(state) for state in (
                "fully_labelled", "partly_labelled", "unlabelled", "unanswerable", "no_golden_evidence")}
            eligible = counts["fully_labelled"] + counts["partly_labelled"] + counts["unlabelled"]
            report.append({"primary_topic": topic, "level": level, "questions": len(selected), **counts,
                           "mapping_exclusion_rate": (counts["partly_labelled"] + counts["unlabelled"]) / eligible
                           if eligible else math.nan})
    return pd.DataFrame(report)


def component_table(table: pd.DataFrame, level: str) -> pd.DataFrame:
    """문서·청크 각각 한 표에서 세 순위와 코드 집합을 비교한다."""
    questions = table[table["id"] != "평균"]
    rows = [{"component": component, **{f"Recall@{k}": questions[f"{level}_{component}_recall_at_{k}"].mean()
                                      for k in K_VALUES}} for component in COMPONENTS]
    rows.append({"component": "exact_code_membership", "Recall (membership)": questions[f"{level}_exact_code_recall"].mean()})
    for k in K_VALUES:
        rows[0][f"MRR@{k}"] = questions[f"{level}_mrr_at_{k}"].mean()
    states = questions[f"{level}_label_state"]
    mapped = states.isin(["fully_labelled", "partly_labelled", "unlabelled"])
    excluded = states.isin(["partly_labelled", "unlabelled"]).sum()
    return pd.DataFrame(rows).assign(scored_questions=(states == "fully_labelled").sum(),
                                    mapping_exclusion_rate=excluded / mapped.sum() if mapped.any() else math.nan)


def coverage_table(table: pd.DataFrame) -> pd.DataFrame:
    """실제 컨텍스트의 근거 포함률을 단일·다중 근거로 나누고 분모를 표시한다."""
    questions = table[table["id"] != "평균"]
    return questions.groupby("coverage_group").agg(
        questions=("id", "size"), scored_questions=("evidence_coverage", "count"),
        evidence_coverage=("evidence_coverage", "mean"), full_evidence_coverage=("full_evidence_coverage", "mean"))
