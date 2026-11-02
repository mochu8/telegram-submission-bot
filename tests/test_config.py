import json

from config import Config


def test_token_env_and_validation(tmp_path, monkeypatch):
    path = tmp_path / "config.json"
    path.write_text(json.dumps({"bot_token": "YOUR_BOT_TOKEN_HERE", "admin_ids": ["42", 7]}))
    cfg = Config(path)
    assert cfg.is_valid_token() is False
    assert cfg.admin_ids == [42, 7]
    assert cfg.is_config_admin(42) is True

    monkeypatch.setenv("BOT_TOKEN", "123456:" + "A" * 35)
    assert cfg.bot_token.startswith("123456:")
    assert cfg.is_valid_token() is True
    assert cfg.is_valid_token("nope") is False


def test_database_path_is_absolute_and_configurable(tmp_path, monkeypatch):
    path = tmp_path / "config.json"
    path.write_text(json.dumps({"database_path": "data/bot.db"}))
    cfg = Config(path)
    assert cfg.database_path == (tmp_path / "data" / "bot.db").resolve()
    assert cfg.database_path.is_absolute()

    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "env.db"))
    assert cfg.database_path == (tmp_path / "env.db").resolve()


def test_invalid_json_is_reported(tmp_path):
    path = tmp_path / "config.json"
    path.write_text("{")
    cfg = Config(path)
    assert cfg.load_error
    assert "JSON" in cfg.load_error
    assert cfg.admin_ids == []
