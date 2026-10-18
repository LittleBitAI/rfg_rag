"""A · B · C 비교 실험: 계획 고정(freeze)과 실험 전체의 유료 호출 장부(ledger).

실험은 storage.EXPERIMENT 아래에 카탈로그 · run · 실패 기록을 따로 둔다 (cli --experiment).
장부는 그 실험의 모든 명령 · 방식 · 이어 돌기가 함께 쓰는 하나의 상한이다. run 마다의 한도는 호출 사이에서만 보므로
함께 날아가는 호출 · 끊긴 호출의 비용을 막지 못한다. 장부는 호출을 보내기 전에 최악 비용을 잡아 두고, 돌아온 사용량으로 정산한다.
"""
import json
import math
import threading
import time
import uuid
from collections import Counter
from contextlib import contextmanager
from string import Template

import openai

from golden_pipeline import adoption, evidence, generation, plan, storage, validation
from golden_pipeline.schema import TOPICS

# 주제마다 묶음 10개: train 6 · validation 2 · held-out 2. 몫은 자기 개선과 같은 해시 나눔(adoption.split)으로 정한다.
PARTS = {"train": 6, "validation": 2, "held_out": 2}
BUDGET_FIELDS = ("ceiling_usd", "max_output_tokens", "prices")
# BPE 토큰은 1 바이트 이상이라 입력 토큰 수는 UTF-8 바이트 수를 넘지 않는다. 메시지마다 역할 표시 몫을 더한다.
MESSAGE_OVERHEAD_TOKENS = 16
RETRIES = 8


def freeze(experiment_id, pool_plan_id):
    """큰 계획(pool)에서 주제마다 몫별 PARTS 개를 계획 차례대로 골라 실험 계획 plans/{experiment_id}.json 으로 고정한다.

    몫이 모자란 주제가 있으면 쓰지 않고 멈춘다. 고정 기록(experiments/{id}/freeze.json)에 근거 · 계획 · 프롬프트 ·
    주제 명세의 SHA-256 과 실제 몫별 개수를 남긴다.
    """
    pool, pool_sha = plan.load_plan(pool_plan_id)
    chosen, parts = [], {}
    for topic in TOPICS:
        picked = _stratified([bundle for bundle in pool["bundles"] if bundle["topic"] == topic])
        parts[topic] = {part: [b["bundle_id"] for b in picked if adoption.split(b["bundle_id"]) == part] for part in PARTS}
        short = {part: len(ids) for part, ids in parts[topic].items() if len(ids) < PARTS[part]}
        if short:
            raise ValueError(f"계획 {pool_plan_id} 의 {topic} 묶음이 모자랍니다 (필요 {PARTS}, 찾은 수 {short})")
        chosen += picked
    frozen = {
        **pool, "plan_id": experiment_id, "created_at": storage._now(), "code_commit": storage._code_commit(),
        "stratified_from": {"plan_id": pool_plan_id, "sha256": pool_sha, "parts": PARTS},
        "counts": {topic: sum(PARTS.values()) for topic in TOPICS},
        "planned": {topic: sum(b["topic"] == topic for b in chosen) for topic in TOPICS},
        "coverage": plan._coverage(chosen), "bundles": chosen,
    }
    plan_path = storage._child(storage.OUTPUTS / "plans", f"{experiment_id}.json")
    with plan_path.open("x", encoding="utf-8") as f:
        f.write(json.dumps(frozen, ensure_ascii=False, indent=1) + "\n")
    evidence_manifest = storage._read_json(storage.OUTPUTS / "evidence" / pool["evidence_run"] / "manifest.json")
    record = {
        "experiment": experiment_id, "created_at": frozen["created_at"], "code_commit": frozen["code_commit"],
        "source": {"evidence_run": pool["evidence_run"], "v11_manifest_sha256": pool["v11_manifest_sha256"],
                   "pinned_sha256": evidence_manifest["pinned_sha256"]},
        "pool_plan": {"plan_id": pool_plan_id, "sha256": pool_sha},
        "plan": {"plan_id": experiment_id, "sha256": storage._sha256(plan_path)},
        "topic_specs": pool["topic_specs"], "prompts": storage.snapshot(storage.PROMPTS),
        "part_counts": {topic: {part: len(ids) for part, ids in found.items()} for topic, found in parts.items()},
        "parts": parts,
    }
    root = storage._child(storage.OUTPUTS / "experiments", experiment_id)
    root.mkdir(parents=True, exist_ok=True)
    with (root / "freeze.json").open("x", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False, indent=2) + "\n")
    return root / "freeze.json"


def pro_packets(experiment_id):
    """주제마다 Pro 채팅에 그대로 붙여 넣을 C 프롬프트(prompts/C.txt)와 빈 sidecar 를 experiments/{id}/pro 에 쓴다.

    묶음은 A · B 가 받는 것과 같은 train 묶음과 같은 컨텍스트다. 프롬프트는 B 처럼 고정 글에 주제 명세만 넣고,
    A 의 예방 규칙 · A · B 의 답 · 검증 결과는 넣지 않는다.
    """
    root = storage._child(storage.OUTPUTS / "experiments", experiment_id)
    record = storage._read_json(root / "freeze.json")
    planned, sha = plan.load_plan(experiment_id)
    current = {"계획": sha, "prompts/C.txt": storage._sha256(storage.PROMPTS / "C.txt"),
               **{f"주제 명세 {topic}": plan.topic_spec(topic)[1] for topic in TOPICS}}
    frozen = {"계획": record["plan"]["sha256"], "prompts/C.txt": record["prompts"]["C.txt"],
              **{f"주제 명세 {topic}": record["topic_specs"][topic] for topic in TOPICS}}
    changed = [name for name in current if current[name] != frozen[name]]
    if changed:
        raise ValueError(f"실험 {experiment_id} 를 고정한 뒤 바뀌었습니다: {changed}")
    template = Template((storage.PROMPTS / "C.txt").read_text(encoding="utf-8"))
    folder = root / "pro"
    folder.mkdir(exist_ok=True)
    for topic in TOPICS:
        spec, _ = plan.topic_spec(topic)
        train = record["parts"][topic]["train"]
        bundles = [bundle for bundle in planned["bundles"] if bundle["bundle_id"] in train]
        text = template.substitute(
            topic=topic, requires=spec["requires"], structure=json.dumps(spec["structure"], ensure_ascii=False),
            count=len(bundles), bundles="\n\n".join(f"=== 근거 묶음 bundle_id: {b['bundle_id']} ===\n{b['context']}" for b in bundles))
        with (folder / f"{topic}.txt").open("x", encoding="utf-8") as f:
            f.write(text)
        with (folder / f"{topic}.sidecar.json").open("x", encoding="utf-8") as f:
            f.write(json.dumps({name: "" for name in generation.SIDECAR}, ensure_ascii=False, indent=2) + "\n")
    return folder


def _stratified(bundles):
    left, picked = dict(PARTS), []
    for bundle in bundles:
        part = adoption.split(bundle["bundle_id"])
        if left[part]:
            picked.append(bundle)
            left[part] -= 1
    return picked


def budget(experiment_id):
    """사람이 승인한 실험 예산 configs/experiments/{id}.json: 상한(USD), 호출마다 최대 출력 토큰(추론 포함), 모델별 단가."""
    path = storage.CONFIGS / "experiments" / f"{experiment_id}.json"
    if not path.exists():
        raise ValueError(f"승인된 실험 예산이 없어 유료 호출을 하지 않습니다: {path}")
    data = storage._read_json(path)
    if set(data) != set(BUDGET_FIELDS):
        raise ValueError(f"실험 예산은 정확히 {BUDGET_FIELDS} 를 가져야 합니다: {path}")
    # 출력 상한 0 은 출력 비용을 잡지 않고 API 에도 상한을 보내지 않으며, 음수 단가는 잡아 둔 비용을 줄여 상한을 풀어 버린다.
    prices = data["prices"]
    valid = (_positive(data["ceiling_usd"]) and type(data["max_output_tokens"]) is int and data["max_output_tokens"] > 0
             and isinstance(prices, dict) and prices
             and all(isinstance(pair, list) and len(pair) == 2 and all(map(_positive, pair)) for pair in prices.values()))
    if not valid:
        raise ValueError(f"실험 예산의 상한 · 단가는 0 보다 큰 수, 출력 상한은 1 이상의 정수여야 합니다: {path}")
    return data


def _positive(value):
    return generation._is_number(value) and math.isfinite(value) and value > 0


@contextmanager
def ledger(experiment_id):
    """실험 장부를 연다. 두 명령이 한 장부를 함께 쓰면 서로의 잡아 둔 비용을 보지 못하므로 잠금 파일로 하나만 연다.

    강제 종료로 잠금이 남으면, 다른 명령이 돌지 않는지 확인하고 지운다. 그때 정산되지 않은 호출은 장부에 잡아 둔 채 남는다.
    """
    root = storage.state_root()
    root.mkdir(parents=True, exist_ok=True)
    lock = root / "ledger.lock"
    lock.open("x").close()
    try:
        yield Ledger(root / "ledger.jsonl", budget(experiment_id))
    finally:
        lock.unlink()


def committed(path):
    """장부의 확정 비용: 정산한 호출의 비용 + 정산하지 못한 호출(보내는 중 · 끊김 · 오류)의 잡아 둔 비용."""
    reserved, spent = {}, 0.0
    for row in storage._read_jsonl(path) if path.exists() else []:
        if row["event"] == "reserve":
            reserved[row["id"]] = row["reserved_usd"]
        elif row["event"] == "settled":
            spent += row["cost_usd"]
            reserved.pop(row["id"])
        elif row["event"] == "rate_limited":
            reserved.pop(row["id"])
    return spent + sum(reserved.values())


class Ledger:
    def __init__(self, path, settings):
        self.path, self.settings, self.lock = path, settings, threading.Lock()
        self.committed = committed(path)

    def guard(self, send):
        """send(model, reasoning_effort, messages, max_output_tokens) 를 장부 안에서 부르는 client.

        429 는 처리하지 않은 요청이라 잡아 둔 비용을 풀고 다시 보낸다. 연결 오류 · 시간 초과 · 5xx 는 청구됐을 수 있어
        잡아 둔 비용을 그대로 두고, 새로 잡아 다시 보낸다. 그 밖의 오류는 잡아 둔 채 멈춘다.
        """
        def call(model, reasoning_effort, messages):
            for attempt in range(RETRIES):
                call_id, reserved = self._reserve(model, messages)
                try:
                    response = send(model, reasoning_effort, messages, self.settings["max_output_tokens"])
                except openai.RateLimitError as error:
                    self._close(call_id, "rate_limited", -reserved, {"error": str(error)[:200]})
                except (openai.APIConnectionError, openai.InternalServerError) as error:
                    self._close(call_id, "uncertain", 0.0, {"error": f"{type(error).__name__}: {str(error)[:200]}"})
                else:
                    cost = self._cost(model, response["input_tokens"], response["output_tokens"])
                    usage = {key: response[key] for key in ("input_tokens", "output_tokens")}
                    self._close(call_id, "settled", cost - reserved, {**usage, "model_reported": response["model"], "cost_usd": cost})
                    return response
                time.sleep(2 ** attempt)
            raise RuntimeError(f"API 호출이 {RETRIES} 번 모두 실패했습니다")
        return call

    def _reserve(self, model, messages):
        tokens = sum(len(m["content"].encode("utf-8")) + MESSAGE_OVERHEAD_TOKENS for m in messages)
        reserved = self._cost(model, tokens, self.settings["max_output_tokens"])
        call_id = uuid.uuid4().hex
        with self.lock:
            if self.committed + reserved > self.settings["ceiling_usd"]:
                raise generation.BudgetExceeded(f"실험 상한 {self.settings['ceiling_usd']} USD: 확정 {self.committed:.4f} + 이번 호출 최대 {reserved:.4f}")
            self.committed += reserved
            storage._append_jsonl(self.path, [{"id": call_id, "event": "reserve", "at": storage._now(), "model": model,
                                               "reserved_usd": reserved}])
        return call_id, reserved

    def _close(self, call_id, event, change, details):
        with self.lock:
            self.committed += change
            storage._append_jsonl(self.path, [{"id": call_id, "event": event, "at": storage._now(), **details}])

    def _cost(self, model, tokens_in, tokens_out):
        if model not in self.settings["prices"]:
            raise ValueError(f"승인된 실험 예산에 {model} 단가가 없습니다")
        price_in, price_out = self.settings["prices"][model]
        return (tokens_in * price_in + tokens_out * price_out) / 1_000_000


def estimate(experiment_id, price_in, price_out):
    """고정한 실험 계획과 지난 A run 의 실제 토큰 기록으로 주제별 호출 수 · 비용을 어림한다 (API 호출 없음).

    expected 는 지난 기록의 평균(호출당 토큰, 출력당 검증 호출, 통과율)이고, high 는 A 의 세 round 가 train 묶음을 모두
    다시 부르고 held-out 까지 재며, 호출마다 출력이 지난 기록의 99 백분위이고, unanswerable 출력마다 대상 문서 묶음을 모두 읽을 때다.
    """
    planned, _ = plan.load_plan(experiment_id)
    batches = _unanswerable_batches(planned)
    rows = {}
    for topic in TOPICS:
        seen = _history(topic)
        passed = seen["passed"] / seen["outputs"]
        # A: round 1 은 train 6 묶음, round 2 · 3 은 통과하지 못한 묶음. round 2 · 3 의 채택마다 validation 2 묶음, 처음엔 v0 도.
        a_expected = 6 * (1 + (1 - passed) + (1 - passed) ** 2) + 6
        gen = {"expected": 6 + a_expected, "high": 6 + 18 + 6 + 4}
        per_output = {"expected": seen["val_calls"] / seen["outputs"], "high": seen["val_calls"] / seen["outputs"]}
        if topic == "unanswerable":
            per_output["high"] = max(per_output["high"], sum(batches) / len(batches))
        rows[topic] = {}
        for case in ("expected", "high"):
            out_gen, out_val = (seen["gen_out"], seen["val_out"]) if case == "expected" else (seen["gen_out_p99"], seen["val_out_p99"])
            val = (gen[case] + 6) * per_output[case]
            usd = (gen[case] * (seen["gen_in"] * price_in + out_gen * price_out)
                   + val * (seen["val_in"] * price_in + out_val * price_out)) / 1_000_000
            rows[topic][case] = {"generation_calls": round(gen[case], 1), "validation_calls": round(val, 1), "usd": round(usd, 4)}
        rows[topic]["history"] = {**seen, "pass_rate": round(passed, 3)}
    total = {case: round(sum(row[case]["usd"] for row in rows.values()), 4) for case in ("expected", "high")}
    return {"plan": experiment_id, "prices": [price_in, price_out], "unanswerable_batches": batches, "topics": rows, "total_usd": total}


def _history(topic):
    """그 주제의 지난 A run (실험 밖 outputs/goldens) 에서: 생성 · 검증 호출당 평균 토큰과 출력 99 백분위, 출력 수, 통과 수, 검증 호출 수."""
    gen, val, outputs, passed = [], [], 0, 0
    for run_dir in sorted((storage.OUTPUTS / "goldens" / topic / "runs" / "A").iterdir()):
        records = storage.validation_records(run_dir)
        if not records:
            continue
        calls = storage._read_json(run_dir / "manifest.json")["generation"]["calls"]
        gen += calls
        outputs += len(calls)
        passed += storage._count_lines(run_dir / "accepted.jsonl")
        val += [call for record in records for call in storage._read_json(record)["calls"]]

    def mean(rows, key):
        return sum(row[key] for row in rows) / len(rows)

    def p99(rows):
        return sorted(row["output_tokens"] for row in rows)[int(0.99 * (len(rows) - 1))]
    return {"outputs": outputs, "passed": passed, "val_calls": len(val),
            "gen_in": mean(gen, "input_tokens"), "gen_out": mean(gen, "output_tokens"), "gen_out_p99": p99(gen),
            "val_in": mean(val, "input_tokens"), "val_out": mean(val, "output_tokens"), "val_out_p99": p99(val)}


def _unanswerable_batches(planned):
    """unanswerable 묶음마다 검증기가 읽을 대상 문서 묶음 수 (validation.document_batches)."""
    bundles = [bundle for bundle in planned["bundles"] if bundle["topic"] == "unanswerable"]
    run_dir = storage.OUTPUTS / "evidence" / planned["evidence_run"]
    found = plan.document_units(run_dir, evidence.PACKAGE, {bundle["doc_sha"] for bundle in bundles})
    return [len(validation.document_batches(found[bundle["doc_sha"]])) for bundle in bundles]


def usage(experiment_id):
    """장부 요약: 정산 · 429 · 불확실 · 정산 없는 호출 수, 정산 비용, 확정 비용(불확실 몫 포함)."""
    path = storage._child(storage.OUTPUTS / "experiments", experiment_id) / "ledger.jsonl"
    rows = storage._read_jsonl(path) if path.exists() else []
    events = Counter(row["event"] for row in rows)
    closed = {row["id"] for row in rows if row["event"] in ("settled", "rate_limited")}
    open_ids = {row["id"] for row in rows if row["event"] == "reserve"} - closed
    return {"events": dict(events), "unsettled": len(open_ids),
            "settled_usd": sum(row["cost_usd"] for row in rows if row["event"] == "settled"),
            "committed_usd": committed(path)}
