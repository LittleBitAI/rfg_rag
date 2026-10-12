"""스모크 게이트: rag/ 아래 모든 모듈이 import 되는지 확인한다."""

import importlib
import pkgutil

import pytest

import rag

MODULES = sorted(m.name for m in pkgutil.iter_modules(rag.__path__, "rag."))


# requirements.txt 가 설치된 .venv 에서 돈다. 없는 모듈은 어떤 것이든 실패다.
@pytest.mark.parametrize("name", MODULES)
def test_imports(name):
    importlib.import_module(name)
