"""Smoke gate: every module under rag/ imports."""

import importlib
import pkgutil

import pytest

import rag

MODULES = sorted(m.name for m in pkgutil.iter_modules(rag.__path__, "rag."))


@pytest.mark.parametrize("name", MODULES)
def test_imports(name):
    try:
        importlib.import_module(name)
    except ModuleNotFoundError as e:
        # A missing third-party package means requirements.txt isn't installed here;
        # a missing rag.* module is a real break.
        if e.name and not e.name.startswith("rag"):
            pytest.skip(f"{e.name} not installed")
        raise
