"""테스트의 API 사용량 CSV를 실제 artifacts와 분리한다."""
import pytest

from rag import usage


@pytest.fixture(autouse=True)
def isolate_usage_csv(monkeypatch, tmp_path):
    monkeypatch.setattr(usage, "ARTIFACTS", tmp_path)


@pytest.fixture(autouse=True)
def no_langfuse_keys(monkeypatch):
    """테스트는 Langfuse 키가 없는 팀원 환경처럼 돈다.

    load_config 의 load_dotenv 는 이미 있는 환경 변수를 덮지 않으므로 빈 값을 넣어 둔다.
    지우기만 하면 .env 의 실제 키가 되살아나 실제 키로 만든 Langfuse 클라이언트가 프로세스에 남았다.
    """
    for key in ("LANGFUSE_PUBLIC_KEY", "LANGFUSE_SECRET_KEY"):
        monkeypatch.setenv(key, "")
