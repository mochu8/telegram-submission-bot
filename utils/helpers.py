#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""辅助函数"""

import html
import json
import logging
import re
from datetime import datetime, timezone

from config import config
from utils.timeutil import utcnow

logger = logging.getLogger(__name__)

_USERNAME_RE = re.compile(r"[A-Za-z0-9_]{1,32}")


def escape_html(text) -> str:
    """Escape text for Telegram HTML parse mode."""
    if text is None:
        return ""
    return html.escape(str(text), quote=True)


def format_user_link(user_id: int, full_name: str, username: str = None) -> str:
    """HTML link to a user. The visible name is always escaped."""
    name = escape_html(full_name or "用户")
    if username and _USERNAME_RE.fullmatch(username):
        return f'<a href="https://t.me/{username}">{name}</a>'
    return f'<a href="tg://user?id={int(user_id)}">{name}</a>'


def format_datetime(dt: datetime) -> str:
    """格式化日期时间"""
    if dt is None:
        return "N/A"
    return dt.strftime("%Y-%m-%d %H:%M:%S")


def format_time_ago(dt: datetime) -> str:
    """格式化相对时间"""
    if dt is None:
        return "N/A"
    if dt.tzinfo is not None:
        dt = dt.astimezone(timezone.utc).replace(tzinfo=None)

    seconds = (utcnow() - dt).total_seconds()
    if seconds < 60:
        return "刚刚"
    if seconds < 3600:
        return f"{int(seconds / 60)} 分钟前"
    if seconds < 86400:
        return f"{int(seconds / 3600)} 小时前"
    return f"{int(seconds / 86400)} 天前"


def truncate_text(text: str, max_length: int = 100) -> str:
    """截断文本"""
    if text is None:
        return ""
    if len(text) <= max_length:
        return text
    return text[: max_length - 3] + "..."


def get_level_title(level: int) -> str:
    """获取等级称号"""
    titles = {
        0: "新手",
        1: "入门",
        2: "活跃",
        3: "热心",
        4: "资深",
        5: "专家",
        6: "大师",
        7: "传奇",
        8: "史诗",
        9: "神话",
        10: "至尊",
    }
    return titles.get(level, "未知")


def get_level_emoji(level: int) -> str:
    """获取等级图标"""
    emojis = {
        0: "🌱",
        1: "🌿",
        2: "🌲",
        3: "⭐",
        4: "⭐⭐",
        5: "🌟",
        6: "🌟🌟",
        7: "💫",
        8: "👑",
        9: "👑👑",
        10: "🏆",
    }
    return emojis.get(level, "🌱")


def build_welcome_text() -> str:
    """主菜单文案。配置里的名称都按纯文本转义。"""
    bot_info = config.bot_info or {}
    name = escape_html(bot_info.get("name") or "投稿机器人")
    lines = ["🤖 <b>机器人介绍：</b>", "", f"Welcome to {name}", ""]
    for link in config.navigation_links:
        if not isinstance(link, dict):
            continue
        if link.get("enabled", True) and link.get("username"):
            lines.append(
                f"{escape_html(link.get('name', ''))}: @{escape_html(link['username'])}"
            )
        elif not link.get("enabled", True):
            placeholder = link.get("placeholder_text") or f"{link.get('name', '')}（筹建中）"
            lines.append(escape_html(placeholder))
    return "\n".join(lines).rstrip()


def build_submit_intro(include_hint: bool = False) -> str:
    """投稿说明。规则文本按纯文本转义，避免破坏 HTML。"""
    rules = escape_html(config.submission_rules)
    hint = "\n\n<i>(文章内容直接发送至机器人即可)</i>" if include_hint else ""
    return (
        "📝 <b>投稿须知</b>\n\n"
        f"{rules}\n\n"
        "请选择投稿方式：\n"
        "• <b>实名投稿</b>：管理员可看到您的信息\n"
        "• <b>匿名投稿</b>：完全匿名"
        f"{hint}"
    )


def build_publish_bodies(text_content, text_html, tags, footer) -> tuple[str, str]:
    """Return (html, plain) channel text. User text is escaped unless it is Telegram HTML."""
    tags = list(tags or [])
    html_parts: list[str] = []
    plain_parts: list[str] = []
    if tags:
        html_parts.append(" ".join(f"#{escape_html(tag)}" for tag in tags) + "：")
        plain_parts.append(" ".join(f"#{tag}" for tag in tags) + "：")
    if text_html:
        html_parts.append(text_html)
    elif text_content:
        html_parts.append(escape_html(text_content))
    if text_content:
        plain_parts.append(text_content)
    elif text_html:
        plain_parts.append(text_html)

    html_body = "".join(html_parts)
    plain_body = "".join(plain_parts)
    if footer:
        separator = "\n\n" if html_body else ""
        html_body = f"{html_body}{separator}{escape_html(footer)}"
        plain_separator = "\n\n" if plain_body else ""
        plain_body = f"{plain_body}{plain_separator}{footer}"
    return html_body, plain_body


def format_submission_info(submission, user=None, show_user: bool = True) -> str:
    """格式化投稿信息（HTML）"""
    lines = [f"📋 <b>投稿 #{submission.id}</b>", ""]

    if show_user and user and not submission.is_anonymous:
        user_link = format_user_link(user.id, user.full_name or "用户", user.username)
        lines.append(f"👤 投稿者: {user_link}")
        lines.append(f"🆔 用户ID: <code>{int(user.id)}</code>")
    elif submission.is_anonymous:
        lines.append("👤 投稿者: <b>匿名用户</b>")

    lines.append(f"📅 时间: {escape_html(format_time_ago(submission.created_at))}")
    lines.append(f"📁 类型: {escape_html(get_content_type_name(submission.content_type))}")

    if submission.tags:
        try:
            tags = json.loads(submission.tags)
        except (TypeError, ValueError):
            logger.warning("Ignoring invalid tags on submission %s", submission.id)
            tags = None
        if tags:
            lines.append(f"🏷️ 标签: {escape_html(', '.join(str(tag) for tag in tags))}")

    status_emoji = {
        "pending": "⏳",
        "publishing": "🔄",
        "approved": "✅",
        "rejected": "❌",
    }
    status_name = {
        "pending": "待审核",
        "publishing": "发布中",
        "approved": "已通过",
        "rejected": "已拒绝",
    }
    lines.append(
        f"📊 状态: {status_emoji.get(submission.status, '❓')} "
        f"{status_name.get(submission.status, '未知')}"
    )
    return "\n".join(lines)


def get_content_type_name(content_type: str) -> str:
    """获取内容类型名称"""
    types = {
        "text": "📝 纯文字",
        "photo": "🖼️ 图片",
        "video": "🎬 视频",
        "audio": "🎵 音频",
        "document": "📄 文件",
        "media_group": "🖼️ 多图",
    }
    return types.get(content_type, content_type)
