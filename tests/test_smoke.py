"""Smoke gate: every module under rag/ imports."""

import importlib
import pkgutil
import re
from pathlib import Path

import pytest

import rag

MODULES = sorted(m.name for m in pkgutil.iter_modules(rag.__path__, "rag."))

# requirements.txt 에 적힌 패키지 이름 (하이픈은 밑줄로 바꿔 import 이름과 맞춘다)
REQUIREMENTS = Path(__file__).parents[1] / "requirements.txt"
DEPENDENCIES = {
    re.match(r"[\w.-]+", line).group().replace("-", "_").lower()
    for line in REQUIREMENTS.read_text(encoding="utf-8").splitlines()
    if line.strip() and not line.startswith("#")
}


@pytest.mark.parametrize("name", MODULES)
def test_imports(name):
    try:
        importlib.import_module(name)
    except ModuleNotFoundError as e:
        # requirements.txt 의 패키지 자체가 설치되지 않았을 때만 건너뛴다.
        # 설치된 패키지 안의 없는 하위 모듈(langchain_core.embeddigns 등)은 실제 오류다.
        if e.name in DEPENDENCIES:
            pytest.skip(f"{e.name} not installed")
        raise
