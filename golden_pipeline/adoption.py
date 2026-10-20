"""RRSI 의 채택 하한과 held-out. 자기 개선 loop 가 예방 규칙을 무조건 더하지 않고, 도움이 된다고 잰 것만 쓰게 한다.

계획의 묶음은 id 해시로 셋으로 나뉘어 늘 같은 몫에 든다.
train 은 지금처럼 출시용 후보를 만든다. validation 은 새 정책을 채택할지 정하는 데만 쓰고,
held-out 은 어떤 결정에도 쓰지 않고 loop 끝에 규칙 없는 정책과 채택한 정책의 차이를 잰다.
"""
import hashlib
import random

from golden_pipeline import storage

# 해시 몫(0~99)이 끝값보다 작은 첫 몫: train 60%, validation 20%, held-out 20%.
SPLITS = (("train", 60), ("validation", 80), ("held_out", 100))
RESAMPLES = 1000
SEED = 20261015
# 한쪽 95%: 짝지은 통과 차이 평균의 부트스트랩 5 백분위가 0 보다 커야 채택한다.
FLOOR_QUANTILE = 0.05


def split(bundle_id):
    bucket = int(hashlib.sha256(bundle_id.encode("utf-8")).hexdigest(), 16) % 100
    return next(name for name, end in SPLITS if bucket < end)


def passes(topic, run_id):
    """A run 이 부른 묶음마다 통과(auto_validated) 항목이 있으면 1, 없으면 0. 후보가 되지 못한 출력도 0 이다."""
    run_dir = storage.run_path(topic, "A", run_id)
    sent = storage._read_json(run_dir / "manifest.json")["generation"]["bundle_ids"]
    accepted = {item["bundle_id"] for item in storage.read_validated(topic, "A", run_id)}
    return {bundle: int(bundle in accepted) for bundle in sent}


def paired_gain(new, old):
    """같은 묶음에서 (새 정책 통과 - 기존 정책 통과) 의 평균과, 그 평균을 묶음으로 다시 뽑은 부트스트랩 하한.

    묶음마다 난이도가 달라 두 정책의 통과율만 견주면 묶음 구성의 차이가 정책의 차이로 보인다. 그래서 같은 묶음끼리 짝짓는다.
    """
    diffs = [new[bundle] - old[bundle] for bundle in sorted(old)]
    rng = random.Random(SEED)
    means = sorted(sum(rng.choices(diffs, k=len(diffs))) / len(diffs) for _ in range(RESAMPLES))
    return sum(diffs) / len(diffs), means[int(FLOOR_QUANTILE * RESAMPLES)]


def settings():
    """나눔 · 하한을 정하는 값. loop 를 시작할 때 고정해, 도중에 바뀌면 멈춘다."""
    # start.json 에서 읽은 값과 견주므로 JSON 이 되돌려 주는 꼴(리스트)로 낸다.
    return {"splits": [list(pair) for pair in SPLITS], "resamples": RESAMPLES, "seed": SEED,
            "floor_quantile": FLOOR_QUANTILE}
