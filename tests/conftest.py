"""테스트의 API 사용량 CSV를 실제 artifacts와 분리한다."""
import pytest

from rag import usage


@pytest.fixture(autouse=True)
def isolate_usage_csv(monkeypatch, tmp_path):
    monkeypatch.setattr(usage, "ARTIFACTS", tmp_path)
