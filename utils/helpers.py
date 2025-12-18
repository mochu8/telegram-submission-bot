#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
辅助函数
"""

import json
from datetime import datetime
from typing import Optional


def format_user_link(user_id: int, full_name: str, 
                     username: str = None) -> str:
    """格式化用户链接"""
    if username:
        return f"[{full_name}](https://t.me/{username})"
    return f"[{full_name}](tg://user?id={user_id})"


def format_datetime(dt: datetime) -> str:
    """格式化日期时间"""
    if dt is None:
        return "N/A"
    return dt.strftime("%Y-%m-%d %H:%M:%S")


def format_time_ago(dt: datetime) -> str:
    """格式化相对时间"""
    if dt is None:
        return "N/A"
    
    now = datetime.utcnow()
    diff = now - dt
    
    seconds = diff.total_seconds()
    if seconds < 60:
        return "刚刚"
    elif seconds < 3600:
        minutes = int(seconds / 60)
        return f"{minutes} 分钟前"
    elif seconds < 86400:
        hours = int(seconds / 3600)
        return f"{hours} 小时前"
    else:
        days = int(seconds / 86400)
        return f"{days} 天前"


def truncate_text(text: str, max_length: int = 100) -> str:
    """截断文本"""
    if text is None:
        return ""
    if len(text) <= max_length:
        return text
    return text[:max_length - 3] + "..."


def escape_markdown(text: str) -> str:
    """转义 Markdown 特殊字符"""
    if text is None:
        return ""
    special_chars = ['_', '*', '[', ']', '(', ')', '~', '`', '>', '#', '+', '-', '=', '|', '{', '}', '.', '!']
    for char in special_chars:
        text = text.replace(char, f'\\{char}')
    return text


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
        10: "至尊"
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
        10: "🏆"
    }
    return emojis.get(level, "🌱")


def format_submission_info(submission, user=None, show_user: bool = True) -> str:
    """格式化投稿信息"""
    lines = []
    
    lines.append(f"📋 *投稿 #{submission.id}*")
    lines.append("")
    
    if show_user and user and not submission.is_anonymous:
        user_link = format_user_link(user.id, user.full_name or "用户", user.username)
        lines.append(f"👤 投稿者: {user_link}")
        lines.append(f"🆔 用户ID: `{user.id}`")
    elif submission.is_anonymous:
        lines.append("👤 投稿者: *匿名用户*")
    
    lines.append(f"📅 时间: {format_time_ago(submission.created_at)}")
    lines.append(f"📁 类型: {get_content_type_name(submission.content_type)}")
    
    if submission.tags:
        try:
            tags = json.loads(submission.tags)
            if tags:
                lines.append(f"🏷️ 标签: {', '.join(tags)}")
        except:
            pass
    
    status_emoji = {
        'pending': '⏳',
        'approved': '✅',
        'rejected': '❌'
    }
    status_name = {
        'pending': '待审核',
        'approved': '已通过',
        'rejected': '已拒绝'
    }
    lines.append(f"📊 状态: {status_emoji.get(submission.status, '❓')} {status_name.get(submission.status, '未知')}")
    
    return "\n".join(lines)


def get_content_type_name(content_type: str) -> str:
    """获取内容类型名称"""
    types = {
        'text': '📝 纯文字',
        'photo': '🖼️ 图片',
        'video': '🎬 视频',
        'audio': '🎵 音频',
        'document': '📄 文件',
        'media_group': '🖼️ 多图'
    }
    return types.get(content_type, content_type)
