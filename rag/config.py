"""공통 설정 — config.yaml 과 .env 를 읽고, 파이프라인 사이에 주고받는 jsonl 파일을 읽고 쓴다."""
from __future__ import annotations

import json
from pathlib import Path

import yaml
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
ARTIFACTS = ROOT / "artifacts"


def load_config() -> dict:
    """.env 의 키(OPENAI_API_KEY, LANGFUSE_*)를 환경 변수로 올리고 config.yaml 을 돌려준다."""
    load_dotenv(ROOT / ".env")
    return yaml.safe_load((ROOT / "config.yaml").read_text(encoding="utf-8"))


def write_jsonl(rows: list[dict], path: Path):
    """임시 파일에 쓴 뒤 바꿔치기해, 쓰는 도중 끊겨도 반쯤 쓰인 파일이 남지 않는다"""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        f.writelines(json.dumps(r, ensure_ascii=False) + "\n" for r in rows)
    tmp.replace(path)


def read_jsonl(path: Path) -> list[dict]:
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def append_jsonl(row: dict, path: Path):
    """체크포인트에 한 줄 덧붙인다 (04 답변 · 05 점수를 하나 끝낼 때마다)"""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")


def read_checkpoint(path: Path) -> list[dict]:
    """체크포인트를 읽는다. 쓰다 끊긴 마지막 줄부터는 버린다 (없으면 빈 목록)"""
    rows = []
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                break
    return rows
