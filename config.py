#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""配置管理模块"""

import json
import os
import re
from pathlib import Path

TOKEN_RE = re.compile(r"^[0-9]+:[A-Za-z0-9_-]{30,}$")
PLACEHOLDER_TOKENS = {"", "YOUR_BOT_TOKEN_HERE", "在这里填入你的 Bot Token"}


class Config:
    """配置类"""

    def __init__(self, config_path: str | Path | None = None):
        if config_path is None:
            config_path = Path(__file__).resolve().parent / "config.json"
        self.config_path = Path(config_path)
        self.load_error: str | None = None
        self._config: dict = {}
        self.reload()

    def _load_config(self) -> dict:
        """加载配置文件"""
        if not self.config_path.exists():
            return {}
        try:
            with open(self.config_path, "r", encoding="utf-8") as handle:
                data = json.load(handle)
        except json.JSONDecodeError as exc:
            raise ValueError(f"配置文件不是合法 JSON: {self.config_path} ({exc})") from exc
        if not isinstance(data, dict):
            raise ValueError(f"配置文件的根必须是 JSON 对象: {self.config_path}")
        return data

    def reload(self):
        """重新加载配置"""
        try:
            self._config = self._load_config()
            self.load_error = None
        except ValueError as exc:
            self._config = {}
            self.load_error = str(exc)

    def _mapping(self, key: str) -> dict:
        value = self._config.get(key) or {}
        return value if isinstance(value, dict) else {}

    def _sequence(self, key: str) -> list:
        value = self._config.get(key) or []
        return value if isinstance(value, list) else []

    @property
    def bot_token(self) -> str:
        env_token = os.environ.get("BOT_TOKEN", "").strip()
        if env_token:
            return env_token
        return str(self._config.get("bot_token", "")).strip()

    def is_valid_token(self, token: str | None = None) -> bool:
        """Reject blank, placeholder, and malformed BotFather tokens."""
        value = self.bot_token if token is None else token.strip()
        if value in PLACEHOLDER_TOKENS:
            return False
        return TOKEN_RE.fullmatch(value) is not None

    @property
    def admin_ids(self) -> list[int]:
        ids = []
        for item in self._sequence("admin_ids"):
            try:
                ids.append(int(item))
            except (TypeError, ValueError):
                continue
        return ids

    @property
    def channel_id(self) -> str:
        value = self._config.get("channel_id") or ""
        return value if isinstance(value, str) else str(value)

    @property
    def channel_name(self) -> str:
        value = self._config.get("channel_name") or ""
        return value if isinstance(value, str) else str(value)

    @property
    def bot_info(self) -> dict:
        return self._mapping("bot_info")

    @property
    def navigation_links(self) -> list:
        return self._sequence("navigation_links")

    @property
    def customer_service(self) -> dict:
        return self._mapping("customer_service")

    @property
    def submission_rules(self) -> str:
        value = self._config.get("submission_rules") or ""
        return value if isinstance(value, str) else str(value)

    @property
    def default_tags(self) -> list:
        return self._sequence("default_tags")

    @property
    def default_reject_reasons(self) -> list:
        return self._sequence("default_reject_reasons")

    @property
    def database_path(self) -> Path:
        """Absolute SQLite path. Relative paths are based on the config file directory."""
        raw = os.environ.get("DATABASE_PATH") or self._config.get("database_path") or "bot.db"
        path = Path(str(raw)).expanduser()
        if path.is_absolute():
            return path.resolve()
        return (self.config_path.resolve().parent / path).resolve()

    def is_config_admin(self, user_id: int) -> bool:
        """检查是否是配置文件中的管理员"""
        return user_id in self.admin_ids

    def get_footer_text(self) -> str:
        """获取尾部信息文本"""
        footer_config = self._mapping("footer")
        if not footer_config.get("enabled", False):
            return ""

        parts = []
        for item in footer_config.get("links", []) or []:
            if not isinstance(item, dict):
                continue
            if item.get("enabled", True) and item.get("username"):
                name = item.get("name", "")
                username = item["username"]
                parts.append(f"{name} @{username}")

        return " ".join(parts)


config = Config()
