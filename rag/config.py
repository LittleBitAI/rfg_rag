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
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.writelines(json.dumps(r, ensure_ascii=False) + "\n" for r in rows)


def read_jsonl(path: Path) -> list[dict]:
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]
