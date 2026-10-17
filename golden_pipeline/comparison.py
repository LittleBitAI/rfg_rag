"""비교 실험의 결과: 주제 · 방식별 지표와 비용, 장부 대조, 눈가림 사람 검토 표본과 그 판정 (API 호출 없음).

첫 시도 비교는 A 의 round 1 · B · C 가 같은 train 묶음에 묶음마다 한 번 낸 출력이다.
A 의 round 2 · 3 은 출력을 더 내므로 첫 시도와 따로, 누적 커버리지와 더 든 비용으로 보고한다.
모든 비율은 분자 · 분모를 함께 남기고, 잴 수 없는 값은 0 이 아니라 None 이나 unobserved 로 둔다.
"""
import csv
import json
import random
from collections import Counter

from golden_pipeline import experiment, improvement, plan, report, storage, validation
from golden_pipeline.generation import UNOBSERVED

LOOP, B_RUN, C_RUN = "a1", "b1", "c1"
RUBRIC = ("evidence_support", "answer_correct", "topic_fit", "useful")
# 방식 · 주제마다 검토할 출력 수와 층. 검증을 통과한 것과 거절된 것을 하나씩, 없으면 남은 층에서 채운다.
PER_CELL = 2
STRATA = ("auto_validated", "rejected", "candidate")
SEED = 20261018


def compare(experiment_id):
    """주제마다 · 전체의 지표, 비용, 장부 대조, 사람 판정을 모은 결과."""
    storage.EXPERIMENT = experiment_id
    record = storage._read_json(storage.state_root() / "freeze.json")
    topics = {topic: _topic(topic, record) for topic in record["parts"]}
    result = {"experiment": experiment_id, "created_at": storage._now(), "topics": topics,
              "overall": _overall(topics), "ledger": experiment.usage(experiment_id)}
    result["reconciliation"] = _reconcile(topics, result["ledger"])
    result["human"] = _human(experiment_id)
    return result


def _topic(topic, record):
    assigned = record["parts"][topic]["train"]
    rounds = _checked_runs(topic, record)["A"]
    first = {"A": [f"{LOOP}-r1"], "B": [B_RUN], "C": [C_RUN]}
    methods = {method: _method(topic, method, runs, set(assigned)) for method, runs in first.items()}
    full = _method(topic, "A", rounds, set(assigned)) if rounds else None
    loop_report = improvement._loop_path(topic, LOOP) / "report.json"
    loop = storage._read_json(loop_report) if loop_report.exists() else None
    return {"assigned": len(assigned), "first_attempt": methods, "a_full": full,
            "a_loop": loop and {key: loop[key] for key in ("stop_reason", "held_out", "calls", "cost_usd")},
            "costs": _costs(topic, methods, full, loop)}


def _method(topic, method, runs, assigned):
    """runs 의 생성 출력으로 잰 지표. run 이 없으면 measured False."""
    if not runs or not all(_exists(topic, method, run_id) for run_id in runs):
        return {"measured": False, "runs": runs}
    outputs = report._collect(topic, method, runs)["outputs"]
    valid = [output for output in outputs if output["state"] == "auto_validated"]
    return {
        "measured": True, "runs": runs,
        "usable_bundle_coverage": _ratio(len({o["bundle_id"] for o in valid} & assigned), len(assigned)),
        "output_acceptance": _ratio(len(valid), len(outputs)),
        "delivery_completeness": _ratio(len({o["bundle_id"] for o in outputs} & assigned), len(assigned)),
        "rejections": dict(Counter(o["code"] for o in outputs if o["state"] in ("rejected", "not_item"))),
        "pending": sum(o["state"] == "candidate" for o in outputs),
        "unique_valid_questions": len(_valid_questions(topic, method, runs)),
    }


def _checked_runs(topic, record):
    """주제의 비교 run (A loop 의 round 전부 · B · C) 이 고정한 실험 정의로 만들어졌는지 보고 돌려준다. 어긋나면 견줄 수 없어 멈춘다.

    계획 · 그 SHA-256 · 주제 명세, A · B 의 생성 프롬프트, 검증기 · 판정기 프롬프트가 고정 기록과 같아야 하고,
    출력이 train 몫 밖의 고정 묶음을 가리키지 않아야 하며, A · B 의 생성 설정과 세 방식의 검증 설정이 같아야 한다 (한도 · 예산은 빼고).
    """
    runs = {"A": [run_dir.name for run_dir in improvement._rounds(topic, LOOP)] if _exists(topic, "A", f"{LOOP}-r1") else [],
            "B": [B_RUN] if _exists(topic, "B", B_RUN) else [], "C": [C_RUN] if _exists(topic, "C", C_RUN) else []}
    settings = {"생성": set(), "검증": set()}
    for method, run_ids in runs.items():
        for run_id in run_ids:
            generated, checked = _check_run(topic, method, run_id, record)
            settings["생성"].update(generated)
            settings["검증"].update(checked)
    mixed = [name for name, found in settings.items() if len(found) > 1]
    if mixed:
        raise ValueError(f"{topic} 의 방식들이 서로 다른 {mixed} 설정으로 돌았습니다")
    return runs


def _check_run(topic, method, run_id, record):
    """run 하나가 고정 기록과 맞는지 보고, (생성 설정, 검증 설정들) 을 돌려준다."""
    run_dir = storage.run_path(topic, method, run_id)
    where = f"{topic}/{method}/{run_id}"
    generated = storage._read_json(run_dir / "manifest.json")["generation"]
    pinned = (record["plan"]["plan_id"], record["plan"]["sha256"], record["topic_specs"][topic])
    if (generated["plan_id"], generated["plan_sha256"], generated["topic_spec_sha256"]) != pinned:
        raise ValueError(f"{where} 는 고정한 계획 · 주제 명세로 만든 run 이 아닙니다")
    outside = {bundle_id for part, ids in record["parts"][topic].items() if part != "train" for bundle_id in ids}
    stray = sorted({output["bundle_id"] for output in report._outputs(topic, method, run_id, run_dir)} & outside)
    if stray:
        raise ValueError(f"{where} 에 train 몫이 아닌 묶음의 출력이 있습니다: {stray}")
    checked = [storage._read_json(path) for path in storage.validation_records(run_dir)]
    # C 는 웹에서 만들어 생성 프롬프트 기록이 없다. C 의 프롬프트는 pro-packets 가 고정 기록과 맞춰 본다.
    prompts = {(generated["prompt_file"], generated["prompt_sha256"])} if method != "C" else set()
    prompts |= {(name, row[key]) for row in checked
                for name, key in (("validator.txt", "prompt_sha256"), ("judge.txt", "judge_prompt_sha256"))}
    changed = sorted(name for name, sha in prompts if record["prompts"].get(name) != sha)
    if changed:
        raise ValueError(f"{where} 가 고정한 뒤 바뀐 프롬프트로 돌았습니다: {changed}")
    return ([_priced(generated["run_config"])] if method != "C" else []), [_priced(row["run_config"]) for row in checked]


def _priced(config):
    return tuple(sorted((key, value) for key, value in config.items() if key not in ("max_calls", "budget_usd")))


def _valid_questions(topic, method, runs):
    return {validation._norm(item["question"]) for run_id in runs if storage.validation_records(storage.run_path(topic, method, run_id))
            for item in storage.read_validated(topic, method, run_id)}


def _costs(topic, methods, full, loop):
    """방식마다 생성 · 검증 비용과 유일한 유효 질문당 비용. C 의 생성 비용은 웹이라 관측할 수 없다."""
    costs = {}
    for method, measured in methods.items():
        if not measured["measured"]:
            continue
        data = report._collect(topic, method, measured["runs"])
        generation = sum(g["cost_usd"] for g in data["generation"]) if method != "C" else UNOBSERVED
        checked = sum(record["cost_usd"] for record in data["validation"])
        total = UNOBSERVED if method == "C" else generation + checked
        costs[method] = {"generation_usd": generation, "validation_usd": checked, "total_usd": total,
                         "per_unique_valid_question": _per(total, measured["unique_valid_questions"])}
    if full and loop:
        # A 의 전 과정: round 2 · 3, 채택을 재는 validation run, held-out run, 다시 부른 호출까지 loop 장부(calls.jsonl)의 전부.
        costs["A_full"] = {"total_usd": loop["cost_usd"], "calls": loop["calls"],
                           "per_unique_valid_question": _per(loop["cost_usd"], full["unique_valid_questions"])}
    return costs


def _per(total, valid):
    if total == UNOBSERVED:
        return {"numerator": UNOBSERVED, "denominator": valid, "value": UNOBSERVED}
    return _ratio(total, valid)


def _overall(topics):
    """주제를 합친 지표: 분자와 분모를 각각 더한다. 어느 주제에서 잴 수 없었던 방식은 그 주제를 빼고 셋 수를 남긴다."""
    overall = {}
    for method in ("A", "B", "C", "A_full"):
        cells = [t["a_full"] if method == "A_full" else t["first_attempt"][method] for t in topics.values()]
        measured = [cell for cell in cells if cell and cell["measured"]]
        overall[method] = {"topics_measured": len(measured), **{
            name: _ratio(sum(c[name]["numerator"] for c in measured), sum(c[name]["denominator"] for c in measured))
            for name in ("usable_bundle_coverage", "output_acceptance", "delivery_completeness")}}
        overall[method]["pending"] = sum(c["pending"] for c in measured)
        overall[method]["rejections"] = dict(sum((Counter(c["rejections"]) for c in measured), Counter()))
    return overall


def _reconcile(topics, ledger):
    """장부에서 정산한 비용과 run 기록에 남은 비용(A loop 전부, B 생성 · 검증, C 검증)의 차이."""
    recorded = 0.0
    for topic in topics.values():
        costs = topic["costs"]
        recorded += costs["A_full"]["total_usd"] if "A_full" in costs else 0.0
        recorded += costs["B"]["total_usd"] if "B" in costs else 0.0
        recorded += costs["C"]["validation_usd"] if "C" in costs else 0.0
    return {"ledger_settled_usd": ledger["settled_usd"], "run_records_usd": recorded,
            "difference_usd": ledger["settled_usd"] - recorded, "ledger_committed_usd": ledger["committed_usd"],
            "ceiling_usd": experiment.budget(storage.EXPERIMENT)["ceiling_usd"]}


def review_packets(experiment_id):
    """방식 · 주제마다 첫 시도 출력 PER_CELL 개를 STRATA 차례로 고른 눈가림 검토 표본을 experiments/{id}/review 에 쓴다.

    방식 · run · 판정은 key.json 에만 두고, 검토지에는 주제 · 질문 · 답 · 인용 근거만 보인다. 항목이 되지 못한 출력은
    질문 · 답이 없어 표본에 넣지 않는다. 표본은 거절을 일부러 넣은 것이라 전체 품질의 추정이 아니다.
    """
    storage.EXPERIMENT = experiment_id
    record = storage._read_json(storage.state_root() / "freeze.json")
    planned, _ = plan.load_plan(record["plan"]["plan_id"])
    bundles = {bundle["bundle_id"]: bundle for bundle in planned["bundles"]}
    rng = random.Random(SEED)
    chosen = []
    # 고정 기록의 주제 차례는 schema.TOPICS 차례다 (freeze).
    for topic in record["parts"]:
        _checked_runs(topic, record)
        for method, run_id in (("A", f"{LOOP}-r1"), ("B", B_RUN), ("C", C_RUN)):
            if _exists(topic, method, run_id):
                chosen += [{"topic": topic, "method": method, "run_id": run_id, **pick} for pick in _sample(topic, method, run_id, rng)]
    rng.shuffle(chosen)
    for n, entry in enumerate(chosen, 1):
        entry["review_id"] = f"R{n:02d}"
    folder = storage.state_root() / "review"
    folder.mkdir()
    storage._write_json(folder / "key.json", {"seed": SEED, "per_cell": PER_CELL, "strata": STRATA,
                                              "entries": [{k: e[k] for k in ("review_id", "topic", "method", "run_id", "candidate_id", "stratum")} for e in chosen]})
    (folder / "packet.md").write_text(_packet(chosen, bundles), encoding="utf-8")
    with (folder / "judgments.csv").open("x", encoding="utf-8-sig", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["review_id", *RUBRIC, "note"])
        writer.writerows([entry["review_id"], *[""] * len(RUBRIC), ""] for entry in chosen)
    return folder


def _sample(topic, method, run_id, rng):
    """run 의 항목을 판정 상태(층)별로 나눠, 층마다 하나씩 STRATA 차례로 PER_CELL 개가 될 때까지 고른다."""
    run_dir = storage.run_path(topic, method, run_id)
    latest = {row["candidate_id"]: row for name in ("candidates.jsonl", "accepted.jsonl", "rejected.jsonl")
              for row in storage._read_jsonl(run_dir / name) if "candidate_id" in row}
    strata = {stratum: sorted((i for i in latest.values() if i["state"] == stratum), key=lambda i: i["candidate_id"])
              for stratum in STRATA}
    picks = []
    while len(picks) < PER_CELL and any(strata.values()):
        for stratum in STRATA:
            if strata[stratum] and len(picks) < PER_CELL:
                item = strata[stratum].pop(rng.randrange(len(strata[stratum])))
                picks.append({"candidate_id": item["candidate_id"], "stratum": stratum, "item": item})
    return picks


def _packet(chosen, bundles):
    lines = ["# 눈가림 검토지", "",
             "출력마다 네 가지를 Y 또는 N 으로 `judgments.csv` 에 적습니다. 어느 방식이 만든 출력인지는 보이지 않습니다.", "",
             "- `evidence_support`: 답이 아래 인용 근거로 뒷받침된다",
             "- `answer_correct`: 답이 질문에 맞는 정답이다 (unanswerable 은 거절 문장이 맞는 답인지, false_premise 는 틀린 전제를 바로잡는지)",
             "- `topic_fit`: 질문이 적힌 주제 유형에 맞다",
             "- `useful`: RFP 를 읽는 사람이 실제로 물을 만한 쓸모 있는 질문이다", ""]
    for entry in sorted(chosen, key=lambda e: e["review_id"]):
        item = entry["item"]
        units = validation.evidence_units(item, bundles[item["bundle_id"]])
        lines += [f"## {entry['review_id']} · 주제 {entry['topic']}", "", f"질문: {item['question']}", "",
                  f"답: {item['answer']}", "", "인용 근거:", "", "```"]
        lines += [f"[{unit['label']}]\n{unit['text']}" for unit in units] + ["```", ""]
    return "\n".join(lines)


def _human(experiment_id):
    """사람 판정: 방식 · 주제 · 층마다 네 검사를 모두 통과한 출력 / 검토한 출력. 판정 파일이 없거나 빈 칸이면 잴 수 없다."""
    folder = storage.state_root() / "review"
    if not (folder / "judgments.csv").exists():
        return {"measured": False, "reason": "검토 표본이 없습니다"}
    key = {entry["review_id"]: entry for entry in storage._read_json(folder / "key.json")["entries"]}
    with (folder / "judgments.csv").open(encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
    # 빠진 행은 표본을 줄이고 겹친 행은 한 출력을 두 번 세므로, 표본의 모든 출력을 꼭 한 번씩 판정했을 때만 잰다.
    ids = Counter(row["review_id"] for row in rows)
    if set(ids) != set(key) or max(ids.values(), default=0) > 1:
        return {"measured": False, "reason": "판정 행이 표본과 하나씩 맞지 않습니다",
                "missing": sorted(set(key) - set(ids)), "unknown": sorted(set(ids) - set(key)),
                "duplicated": sorted(review_id for review_id, n in ids.items() if n > 1)}
    if any(row[name].strip().upper() not in ("Y", "N") for row in rows for name in RUBRIC):
        return {"measured": False, "reason": "판정에 Y · N 이 아닌 칸이 있습니다"}
    cells = {}
    for row in rows:
        entry = key[row["review_id"]]
        passed = all(row[name].strip().upper() == "Y" for name in RUBRIC)
        for cell in ((entry["method"], "all"), (entry["method"], entry["topic"]), (entry["method"], f"stratum:{entry['stratum']}")):
            cells.setdefault(cell, [0, 0])
            cells[cell] = [cells[cell][0] + passed, cells[cell][1] + 1]
    return {"measured": True, "cells": {f"{m} · {scope}": _ratio(*pair) for (m, scope), pair in sorted(cells.items())},
            "checks": {name: dict(Counter(f"{key[r['review_id']]['method']}:{r[name].strip().upper()}" for r in rows))
                       for name in RUBRIC}}


def _exists(topic, method, run_id):
    return (storage.run_path(topic, method, run_id) / "manifest.json").exists()


def _ratio(numerator, denominator):
    return {"numerator": numerator, "denominator": denominator,
            "value": numerator / denominator if denominator else None}


def write(experiment_id):
    """compare 결과를 experiments/{id}/comparison.json 에 쓴다 (다시 쓰면 덮어씀: 판정이 들어올 때마다 다시 잰다)."""
    result = compare(experiment_id)
    path = storage.state_root() / "comparison.json"
    storage._write_json(path, result)
    return json.dumps({"overall": result["overall"], "reconciliation": result["reconciliation"],
                       "human": result["human"]}, ensure_ascii=False, indent=2)
