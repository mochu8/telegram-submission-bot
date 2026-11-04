import pytest

from database.db import Database


@pytest.fixture(autouse=True)
def _clear_runtime_env(monkeypatch):
    monkeypatch.delenv("BOT_TOKEN", raising=False)
    monkeypatch.delenv("DATABASE_PATH", raising=False)
    monkeypatch.setenv("MAX_PENDING_SUBMISSIONS", "0")
    monkeypatch.setenv("SUBMISSION_COOLDOWN_SECONDS", "0")
    monkeypatch.setenv("BACKUP_ENABLED", "0")


@pytest.fixture
def database(tmp_path):
    instance = Database(tmp_path / "test.db")
    instance.init_db()
    return instance
