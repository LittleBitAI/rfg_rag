"""주제별 저장 규약, 공유 카탈로그, 출력 경로 보호.

모든 쓰기는 golden_pipeline/outputs 아래에서만 일어나고, 이미 있는 run 과 release 는 덮어쓰지 않는다.
"""
import hashlib
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from golden_pipeline.schema import ITEM_FIELDS, METHODS, TOPICS, validate_item

PACKAGE = Path(__file__).resolve().parent
OUTPUTS = PACKAGE / "outputs"
CONFIGS = PACKAGE / "configs"
PROMPTS = PACKAGE / "prompts"
STATE_FILES = {"auto_validated": "accepted.jsonl", "rejected": "rejected.jsonl"}


class OutputPathError(ValueError):
    pass


class CatalogError(ValueError):
    pass


def guard(path):
    """golden_pipeline/outputs 밖(data/, artifacts/, eval/ 포함)으로 가는 경로를 막는다."""
    resolved = Path(path).resolve()
    if not resolved.is_relative_to(OUTPUTS.resolve()):
        raise OutputPathError(f"golden_pipeline/outputs 밖으로 쓸 수 없습니다: {resolved}")
    return resolved


def write_run(topic, method, run_id, items, rejects=(), info=None):
    """한 run 의 항목을 상태별 파일로 나눠 쓰고 카탈로그에 등록한다.

    rejects 는 스키마나 주제 구조를 어겨 항목이 되지 못한 생성 출력({bundle_id, reason, raw})이며 rejected.jsonl 에 함께 쓴다.
    info 는 생성 방식이 남기는 실행 정보(모델, 해시, 근거 묶음 등)로 매니페스트의 generation 에 들어간다.
    """
    if method not in METHODS:
        raise ValueError(f"method 는 {METHODS} 중 하나여야 합니다: {method!r}")
    for item in items:
        validate_item(item)
        if (item["primary_topic"], item["method"], item["run_id"]) != (topic, method, run_id):
            raise ValueError(f"{item['candidate_id']} 는 {topic}/{method}/{run_id} 의 항목이 아닙니다")
    run_dir = new_run_dir(topic, method, run_id)
    entries = [_catalog_entry(item) for item in items]
    _check_catalog(entries)
    run_dir.mkdir(parents=True, exist_ok=False)

    _write_jsonl(run_dir / "candidates.jsonl", items)
    for state, name in STATE_FILES.items():
        _write_jsonl(run_dir / name, [item for item in items if item["state"] == state])
    _append_jsonl(run_dir / "rejected.jsonl", rejects)
    _write_json(run_dir / "manifest.json", {
        "run_id": run_id,
        "topic": topic,
        "method": method,
        "created_at": _now(),
        "code_commit": _code_commit(),
        "config_snapshot": snapshot(CONFIGS),
        "prompt_snapshot": snapshot(PROMPTS),
        "counts": {name: _count_lines(run_dir / name) for name in ("candidates.jsonl", *STATE_FILES.values())},
        "generation": info,
    })
    _append_jsonl(OUTPUTS / "catalog.jsonl", entries)
    return run_dir


def run_path(topic, method, run_id):
    return _child(_topic_dir(topic) / "runs" / method, run_id)


def new_run_dir(topic, method, run_id):
    """새 run 이 쓸 디렉터리. run_id 가 경로 한 칸 이름이 아니거나 이미 쓴 run 이면 막는다."""
    run_dir = run_path(topic, method, run_id)
    used = run_dir.exists() or any(
        (entry["topic"], entry["method"], entry["run_id"]) == (topic, method, run_id) for entry in read_catalog()
    )
    if used:
        raise FileExistsError(f"이미 있는 run 입니다: {topic}/{method}/{run_id}")
    return run_dir


def unvalidated_run(topic, method, run_id):
    """검증할 run 의 디렉터리. 없는 run 이거나 이미 검증한 run 이면 막는다 (검증 결과를 덮어쓰지 않는다)."""
    run_dir = run_path(topic, method, run_id)
    if not (run_dir / "candidates.jsonl").exists():
        raise FileNotFoundError(f"없는 run 입니다: {topic}/{method}/{run_id}")
    if (run_dir / "validation.json").exists():
        raise FileExistsError(f"이미 검증한 run 입니다: {topic}/{method}/{run_id}")
    return run_dir


def write_validation(topic, method, run_id, items, info):
    """검증한 항목을 run 의 상태 파일에 쓰고 검증 기록(validation.json)을 남긴다.

    생성 때 비워 둔 accepted.jsonl 을 채우고, 거절 항목은 rejected.jsonl 뒤에 붙인다.
    항목은 candidates.jsonl 의 기록에서 상태만 나아간 것이어야 한다. 파일별 SHA-256 은 출시 때 다시 확인한다.
    """
    run_dir = unvalidated_run(topic, method, run_id)
    if _count_lines(run_dir / "accepted.jsonl"):
        raise FileExistsError(f"accepted.jsonl 이 비어 있지 않습니다: {topic}/{method}/{run_id}")
    candidates = {record["candidate_id"] for record in _read_jsonl(run_dir / "candidates.jsonl")}
    return _record_validation(run_dir, items, candidates, run_dir / "validation.json", info)


def continue_validation(topic, method, run_id, items, info):
    """한도에 닿아 끝난 검증의 pending 후보만 검증한 항목을 상태 파일 뒤에 붙이고, 이어 쓴 검증 기록을 남긴다.

    기록은 validation-2.json, validation-3.json ... 이고 앞 기록의 SHA-256 을 continues 에 남긴다.
    이어 쓰기 전에 상태 파일이 마지막 기록과 같은지 본다. 그래야 출시 때 마지막 기록 하나로 앞의 검증까지 확인된다.
    """
    read_validated(topic, method, run_id)
    run_dir = run_path(topic, method, run_id)
    records = validation_records(run_dir)
    last = records[-1]
    pending = set(_read_json(last)["pending"])
    info = {**info, "continues": {"file": last.name, "sha256": _sha256(last)}}
    return _record_validation(run_dir, items, pending, run_dir / f"validation-{len(records) + 1}.json", info)


def validation_records(run_dir):
    """run 의 검증 기록을 쓴 차례로: validation.json, 이어서 검증한 validation-2.json, validation-3.json ...

    이어 쓴 기록마다 continues 가 바로 앞 기록의 SHA-256 과 같은지 본다. 마지막 기록만 상태 파일과 대조하므로,
    이 사슬이 없으면 앞 기록(비용 · 판정 수)이 바뀌어도 보고서 · 출시본이 그대로 읽는다.
    """
    records, path = [], Path(run_dir) / "validation.json"
    while path.exists():
        if records:
            link = {"file": records[-1].name, "sha256": _sha256(records[-1])}
            if _read_json(path).get("continues") != link:
                raise CatalogError(f"{path.name} 이 이은 {records[-1].name} 가 바뀌었습니다: {Path(run_dir).name}")
        records.append(path)
        path = Path(run_dir) / f"validation-{len(records) + 1}.json"
    return records


def _record_validation(run_dir, items, allowed, record_path, info):
    """allowed 후보를 검증한 항목을 상태별 파일 뒤에 붙이고 검증 기록을 쓴다."""
    originals = {record["candidate_id"]: record for record in _read_jsonl(run_dir / "candidates.jsonl")}
    for item in items:
        validate_item(item)
        if item["state"] == "candidate" or item["candidate_id"] not in allowed:
            raise ValueError(f"{item['candidate_id']} 는 {run_dir.name} 에서 검증할 후보가 아닙니다")
        _require_same_record(originals[item["candidate_id"]], item)

    for state, name in STATE_FILES.items():
        with guard(run_dir / name).open("a", encoding="utf-8") as f:
            f.writelines(json.dumps(item, ensure_ascii=False) + "\n" for item in items if item["state"] == state)
    with guard(record_path).open("x", encoding="utf-8") as f:
        f.write(json.dumps({
            **info,
            "counts": {state: sum(item["state"] == state for item in items) for state in STATE_FILES},
            "files": {name: _sha256(run_dir / name) for name in STATE_FILES.values()},
        }, ensure_ascii=False, indent=2) + "\n")
    return run_dir


def read_validated(topic, method, run_id):
    """검증한 run 의 auto_validated 항목. 상태 파일이 마지막 검증 기록과 다르면 막는다."""
    run_dir = run_path(topic, method, run_id)
    records = validation_records(run_dir)
    if not records:
        raise FileNotFoundError(f"검증하지 않은 run 입니다: {topic}/{method}/{run_id}")
    record = _read_json(records[-1])
    changed = [name for name, sha in record["files"].items() if _sha256(run_dir / name) != sha]
    if changed:
        raise CatalogError(f"{topic}/{method}/{run_id} 의 {changed} 가 검증 기록({records[-1].name})과 다릅니다")
    return _read_jsonl(run_dir / "accepted.jsonl")


def write_release(topic, version, items, runs, info=None):
    """출시 상태 항목을 releases/{version}/golden.jsonl 과 출시 매니페스트로 쓴다.

    매니페스트에는 입력 run 전부의 파일 SHA-256 을 남긴다. 항목이 모두 빠진 run 도 실패 기록의 출처이기 때문이다.
    """
    for item in items:
        validate_item(item)
        if item["state"] != "released" or item["primary_topic"] != topic:
            raise ValueError(f"{item['candidate_id']} 는 {topic} 의 출시 상태 항목이 아닙니다")
    ids = [item["candidate_id"] for item in items]
    if len(set(ids)) != len(ids):
        raise ValueError("같은 항목이 출시본에 두 번 들어 있습니다")
    originals = _registered_records(topic, ids)
    for item in items:
        _require_same_record(originals[item["candidate_id"]], item)
    release_dir = _child(_topic_dir(topic) / "releases", version)
    release_dir.mkdir(parents=True, exist_ok=False)

    golden = release_dir / "golden.jsonl"
    _write_jsonl(golden, items)
    runs = set(runs) | {(item["method"], item["run_id"]) for item in items}
    _write_json(release_dir / "manifest.json", {
        "version": version,
        "topic": topic,
        "created_at": _now(),
        "code_commit": _code_commit(),
        "count": len(items),
        "golden_sha256": _sha256(golden),
        "runs": [f"{method}/{run_id}" for method, run_id in sorted(runs)],
        "sources": {f"{method}/{run_id}": _run_hashes(topic, method, run_id) for method, run_id in sorted(runs)},
        "release": info,
    })
    return release_dir


def read_catalog():
    path = guard(OUTPUTS / "catalog.jsonl")
    return _read_jsonl(path) if path.exists() else []


def evidence_group(item):
    """같은 근거 묶음을 가리키는 항목은 같은 키를 갖는다 (근거 순서와 무관)."""
    refs = sorted(json.dumps(ref, sort_keys=True, ensure_ascii=False) for ref in item["evidence"])
    return hashlib.sha256("\n".join(refs).encode("utf-8")).hexdigest()


def snapshot(directory):
    """디렉터리 안 파일마다 SHA-256 을 기록한다. run 이 어떤 설정·프롬프트로 돌았는지 남기기 위해서다."""
    return {
        path.relative_to(directory).as_posix(): _sha256(path)
        for path in sorted(Path(directory).rglob("*"))
        if path.is_file()
    }


def _check_catalog(entries):
    """항목은 카탈로그에 한 번만, 근거 묶음은 한 주제에만 속한다."""
    seen = set()
    owner = {}
    for entry in read_catalog():
        seen.add(entry["candidate_id"])
        owner.setdefault(entry["evidence_group"], entry["topic"])
    for entry in entries:
        if entry["candidate_id"] in seen:
            raise CatalogError(f"이미 등록된 항목입니다: {entry['candidate_id']}")
        if owner.setdefault(entry["evidence_group"], entry["topic"]) != entry["topic"]:
            raise CatalogError(
                f"{entry['candidate_id']} 의 근거 묶음은 이미 {owner[entry['evidence_group']]} 주제 소유입니다"
            )
        seen.add(entry["candidate_id"])


def _registered_records(topic, ids):
    """카탈로그가 가리키는 run 의 candidates.jsonl 에서 각 항목의 원래 기록을 읽는다."""
    entries = {entry["candidate_id"]: entry for entry in read_catalog() if entry["topic"] == topic}
    unknown = [candidate_id for candidate_id in ids if candidate_id not in entries]
    if unknown:
        raise CatalogError(f"카탈로그에 {topic} 항목으로 등록되지 않았습니다: {unknown}")
    runs = {(entries[candidate_id]["method"], entries[candidate_id]["run_id"]) for candidate_id in ids}
    records = {}
    for method, run_id in runs:
        path = guard(_topic_dir(topic) / "runs" / method / run_id / "candidates.jsonl")
        records.update((record["candidate_id"], record) for record in _read_jsonl(path))
    return records


def _require_same_record(original, item):
    """출시 항목은 run 에 등록된 기록에서 상태만 더 나아간 것이어야 한다.

    질문·답·근거·방법·run 을 바꿔 끼우면 카탈로그의 근거 묶음 소유와 출시 매니페스트의 원본 run 이 거짓이 된다.
    """
    progress = ("state", "state_history", "validator_version", "difficulty")
    changed = [name for name in ITEM_FIELDS if name not in progress and item[name] != original[name]]
    history = original["state_history"]
    if item["state_history"][:len(history)] != history:
        changed.append("state_history")
    changed += [name for name in progress[2:] if original[name] not in (None, item[name])]
    if changed:
        raise CatalogError(
            f"{item['candidate_id']} 가 run {original['method']}/{original['run_id']} 에 등록된 기록과 다릅니다: {changed}"
        )


def _run_hashes(topic, method, run_id):
    """출시본의 원본 run 파일별 SHA-256. 검증 기록(validation.json 과 이어 쓴 기록)도 모두 넣는다."""
    run_dir = run_path(topic, method, run_id)
    names = ("candidates.jsonl", *STATE_FILES.values(), "manifest.json")
    return {name: _sha256(run_dir / name) for name in (*names, *(path.name for path in validation_records(run_dir)))}


def _catalog_entry(item):
    return {
        "candidate_id": item["candidate_id"],
        "topic": item["primary_topic"],
        "evidence_group": evidence_group(item),
        "method": item["method"],
        "run_id": item["run_id"],
    }


def _topic_dir(topic):
    if topic not in TOPICS:
        raise ValueError(f"topic 은 {TOPICS} 중 하나여야 합니다: {topic!r}")
    return guard(OUTPUTS / "goldens" / topic)


def _child(parent, name):
    """name 이 경로 한 칸일 때만 parent 아래 경로를 돌려준다 ('..' 나 '/' 로 빠져나가지 못하게)."""
    path = guard(Path(parent) / name)
    if path.parent != Path(parent).resolve():
        raise OutputPathError(f"경로 한 칸 이름이 아닙니다: {name!r}")
    return path


def _code_commit():
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=PACKAGE, capture_output=True, text=True, check=True
    )
    return result.stdout.strip()


def _now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _count_lines(path):
    with path.open(encoding="utf-8") as f:
        return sum(1 for _ in f)


def _read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _read_jsonl(path):
    with path.open(encoding="utf-8") as f:
        return [json.loads(line) for line in f]


def _write_json(path, data):
    guard(path).write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _write_jsonl(path, rows):
    with guard(path).open("x", encoding="utf-8") as f:
        f.writelines(json.dumps(row, ensure_ascii=False) + "\n" for row in rows)


def _append_jsonl(path, rows):
    # ponytail: 잠금 없는 추가 쓰기. 여러 run 을 동시에 돌리게 되면 파일 잠금을 넣는다.
    with guard(path).open("a", encoding="utf-8") as f:
        f.writelines(json.dumps(row, ensure_ascii=False) + "\n" for row in rows)
