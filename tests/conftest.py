import pytest

from database.db import Database


@pytest.fixture(autouse=True)
def _clear_runtime_env(monkeypatch):
    monkeypatch.delenv("BOT_TOKEN", raising=False)
    monkeypatch.delenv("DATABASE_PATH", raising=False)


@pytest.fixture
def database(tmp_path):
    instance = Database(tmp_path / "test.db")
    instance.init_db()
    return instance
