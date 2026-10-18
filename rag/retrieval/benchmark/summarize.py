"""튜닝 가중치를 동결한 뒤 동일 validation 질문의 결과를 집계한다."""
from __future__ import annotations

import gzip
import json

import numpy as np
import pandas as pd

from rag.config import read_jsonl
from rag.evaluation.ir import ir_scores

from .common import OUT, RECORD, WEIGHTS, models, save_json
from .prepare import freeze_inputs
from .run import measurement_files


def load_results(path):
    with gzip.open(path, "rt", encoding="utf-8") as stream:
        return [json.loads(line) for line in stream]


def config_name(mode, sparse, weight):
    return f"{mode}-{sparse}-{weight:.1f}"


def scored_rows(rows, questions):
    return [{**row, "scores": score_fields(row, questions)} for row in rows]


def score_fields(row, questions):
    scores = ir_scores({**questions[row["id"]], **row})
    return {key: value if np.isfinite(value) else None for key, value in scores.items()}


def choose_weights(spec, results, questions):
    choices = {}
    for sparse in (["kiwi", "whitespace"] if spec["key"] == "kure" else ["kiwi"]):
        for mode in ("isolated", "integrated"):
            means = {}
            for weight in WEIGHTS:
                rows = load_results(results / spec["key"] / f"{config_name(mode, sparse, weight)}.jsonl.gz")
                tuning = [score_fields(r, questions)["chunk_fused_recall_at_10"] for r in rows
                          if r["partition"] == "tuning" and r["route"] == "ordinary"
                          and r["chunk_label_state"] == "fully_labelled"]
                assert tuning
                means[weight] = float(np.mean(tuning))
            winner = min(WEIGHTS, key=lambda w: (-means[w], abs(w - 0.6), w))
            choices[f"{mode}-{sparse}"] = {"weight": winner, "tuning_chunk_recall_at_10": means[winner],
                                           "grid_tuning_means": {str(k): v for k, v in means.items()}}
    return choices


def selections(spec, choices):
    configs = [("dense", "kiwi", 1.0, "diagnostic"), ("kiwi_hybrid_fixed", "kiwi", 0.6, "fixed")]
    if spec["key"] == "kure":
        configs += [("kiwi_bm25", "kiwi", 0.0, "baseline"), ("whitespace_bm25", "whitespace", 0.0, "baseline"),
                    ("whitespace_hybrid_fixed", "whitespace", 0.6, "fixed")]
    for mode in ("isolated", "integrated"):
        for label, sparse, weight, selection in configs:
            yield mode, label, sparse, weight, selection
        for sparse in (["kiwi", "whitespace"] if spec["key"] == "kure" else ["kiwi"]):
            yield mode, f"{sparse}_hybrid_tuned", sparse, choices[f"{mode}-{sparse}"]["weight"], "tuned"


def quality_groups(rows, metadata):
    table = pd.DataFrame([{**{k: v for k, v in r.items() if k not in ("scores", "ranked_candidates")}, **r["scores"]}
                          for r in rows])
    metrics = list(rows[0]["scores"])
    for partition in ("tuning", "validation", "all_dev"):
        part = table if partition == "all_dev" else table[table.partition == partition]
        for route in ("ordinary", "filter"):
            routed = part[part.route == route]
            for topic in ["ALL", *sorted(routed.primary_topic.unique())]:
                topic_rows = routed if topic == "ALL" else routed[routed.primary_topic == topic]
                for group in ("ALL", "single_evidence", "multi_evidence", "exact_code_questions"):
                    selected = select_group(topic_rows, group)
                    if selected.empty and (topic != "ALL" or group != "ALL"):
                        continue
                    yield quality_row(selected, metadata, partition, route, topic, group, metrics)


def select_group(table, group):
    if group == "ALL":
        return table
    if group == "exact_code_questions":
        return table[table.code_query]
    return table[table.coverage_group == group]


def quality_row(selected, metadata, partition, route, topic, group, metrics):
    row = {**metadata, "partition": partition, "route": route, "topic": topic, "group": group, "questions": len(selected)}
    for level in ("doc", "chunk"):
        states = selected[f"{level}_label_state"]
        denominator = states.isin(["fully_labelled", "partly_labelled", "unlabelled"]).sum()
        excluded = states.isin(["partly_labelled", "unlabelled"]).sum()
        row[f"{level}_eligible"] = int((states == "fully_labelled").sum())
        row[f"{level}_mapping_exclusion_rate"] = excluded / denominator if denominator else None
    for metric in metrics:
        row[metric] = pd.to_numeric(selected[metric]).mean()
    return row


def latency_groups(table, metadata):
    for partition in ("tuning", "validation", "all_dev"):
        for route in ("ordinary", "filter"):
            part = table[table.route == route]
            if partition != "all_dev":
                part = part[part.partition == partition]
            for pass_id in ("ALL", 0, 1, 2):
                selected = part if pass_id == "ALL" else part[part["pass"] == pass_id]
                yield {**metadata, "partition": partition, "route": route, "pass": pass_id,
                       "samples": len(selected), "p50_ms": selected.milliseconds.quantile(0.5),
                       "p90_ms": selected.milliseconds.quantile(0.9), "mean_ms": selected.milliseconds.mean(),
                       "min_ms": selected.milliseconds.min(), "max_ms": selected.milliseconds.max()}


def paired_differences(validation):
    table = pd.DataFrame(validation)
    families = {"dense": "dense", "kiwi_hybrid_fixed": "kiwi_hybrid_fixed",
                "whitespace_hybrid_fixed": "kiwi_hybrid_fixed", "kiwi_hybrid_tuned": "kiwi_hybrid_tuned",
                "whitespace_hybrid_tuned": "kiwi_hybrid_tuned", "kiwi_bm25": "kiwi_bm25",
                "whitespace_bm25": "kiwi_bm25"}
    baseline = table[(table.model == "kure") & table.label.isin(set(families.values()))].rename(
        columns={"label": "baseline_label"})
    table["baseline_label"] = table.label.map(families)
    metrics = [c for c in table if "_fused_recall_at_" in c or "_mrr_at_" in c
               or c in ("evidence_coverage", "full_evidence_coverage")]
    paired = table.merge(baseline, on=["id", "mode", "baseline_label"], suffixes=("", "_kure"), validate="many_to_one")
    paired = pd.concat([paired, paired.assign(primary_topic="ALL")], ignore_index=True)
    records = []
    for keys, selected in paired.groupby(["model", "mode", "label", "baseline_label", "route", "primary_topic"], dropna=False):
        meta = dict(zip(["model", "mode", "label", "baseline_label", "route", "topic"], keys))
        for metric in metrics:
            diff = pd.to_numeric(selected[metric]) - pd.to_numeric(selected[f"{metric}_kure"])
            values = diff.dropna()
            records.append({**meta, "metric": metric, "paired_questions": len(values),
                            "mean_difference": values.mean(), "improved": int((values > 0).sum()),
                            "tied": int((values == 0).sum()), "regressed": int((values < 0).sum())})
    return records


def collect_model(spec, choices):
    quality, latency, validation = [], [], []
    questions = {row["id"]: row for row in read_jsonl(RECORD / "questions.jsonl")}
    for mode, label, sparse, weight, selection in selections(spec, choices):
        name = config_name(mode, sparse, weight)
        metadata = {"model": spec["key"], "mode": mode, "label": label, "dense_weight": weight, "selection": selection}
        rows = scored_rows(load_results(OUT / spec["key"] / f"{name}.jsonl.gz"), questions)
        quality.extend(quality_groups(rows, metadata))
        times = pd.read_json(OUT / spec["key"] / f"{name}-latency.jsonl", lines=True)
        latency.extend(latency_groups(times, metadata))
        for row in rows:
            if row["partition"] == "validation":
                validation.append({**metadata, **{k: row[k] for k in ("id", "route", "primary_topic", "coverage_group")}, **row["scores"]})
    return quality, latency, validation


def export_raw(spec):
    import shutil

    target = RECORD / "results" / spec["key"]
    target.mkdir(parents=True, exist_ok=True)
    source = OUT / spec["key"]
    for name in [*measurement_files(spec), "complete.json"]:
        shutil.copyfile(source / name, target / name)


def summarize():
    from .verify import verify_completion, verify_record

    manifest = freeze_inputs()
    specs = models()
    resources = [verify_completion(OUT / spec["key"], spec, manifest) for spec in specs]
    questions = {row["id"]: row for row in read_jsonl(RECORD / "questions.jsonl")}
    choices = {s["key"]: choose_weights(s, OUT, questions) for s in specs}
    choice_path = RECORD / "chosen_weights.json"
    if choice_path.exists():
        assert json.loads(choice_path.read_text(encoding="utf-8")) == choices, "Frozen tuning choices changed"
    else:
        save_json(choices, choice_path)
    quality, latency, validation = [], [], []
    for spec in specs:
        q, t, v = collect_model(spec, choices[spec["key"]])
        quality.extend(q)
        latency.extend(t)
        validation.extend(v)
        export_raw(spec)
    pd.DataFrame(quality).to_csv(RECORD / "quality.csv", index=False, encoding="utf-8")
    pd.DataFrame(latency).to_csv(RECORD / "latency.csv", index=False, encoding="utf-8")
    pd.DataFrame(validation).to_csv(RECORD / "validation_per_question.csv", index=False, encoding="utf-8")
    pd.DataFrame(paired_differences(validation)).to_csv(RECORD / "paired_differences.csv", index=False, encoding="utf-8")
    save_json(resources, RECORD / "resources.json")
    verify_record(RECORD)
    print("SUMMARIZED all seven models; choices frozen before validation aggregation", flush=True)
