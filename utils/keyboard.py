#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""键盘生成工具"""

from telegram import InlineKeyboardButton, InlineKeyboardMarkup


def build_main_keyboard(navigation_links: list, channel_id: str, customer_service: dict):
    """构建主菜单键盘"""
    keyboard = []

    for link in navigation_links:
        if not isinstance(link, dict):
            continue
        if link.get("enabled", True) and link.get("username"):
            keyboard.append(
                [InlineKeyboardButton(link["name"], url=f"https://t.me/{link['username']}")]
            )
        elif not link.get("enabled", True):
            placeholder = link.get("placeholder_text", link.get("name", "") + "（筹建中）")
            keyboard.append([InlineKeyboardButton(placeholder, callback_data="placeholder")])

    keyboard.append([InlineKeyboardButton("📝 我要投稿", callback_data="start_submit")])

    bottom_row = []
    if channel_id:
        channel_username = channel_id.replace("@", "")
        bottom_row.append(
            InlineKeyboardButton("📢 订阅频道", url=f"https://t.me/{channel_username}")
        )

    if customer_service.get("username"):
        bottom_row.append(
            InlineKeyboardButton(
                customer_service.get("name", "联系客服"),
                url=f"https://t.me/{customer_service['username']}",
            )
        )

    if bottom_row:
        keyboard.append(bottom_row)

    return InlineKeyboardMarkup(keyboard)


def build_submit_options_keyboard():
    """构建投稿选项键盘"""
    keyboard = [
        [
            InlineKeyboardButton("👤 实名投稿", callback_data="submit_named"),
            InlineKeyboardButton("🕶️ 匿名投稿", callback_data="submit_anonymous"),
        ],
        [InlineKeyboardButton("❌ 取消", callback_data="cancel_submit")],
    ]
    return InlineKeyboardMarkup(keyboard)


def build_submitting_keyboard():
    """构建投稿中键盘"""
    keyboard = [
        [InlineKeyboardButton("✅ 完成投稿", callback_data="finish_submit")],
        [InlineKeyboardButton("❌ 取消投稿", callback_data="cancel_submit")],
    ]
    return InlineKeyboardMarkup(keyboard)


def build_back_keyboard():
    """构建返回键盘"""
    keyboard = [[InlineKeyboardButton("🏠 返回主菜单", callback_data="back_to_main")]]
    return InlineKeyboardMarkup(keyboard)


def build_review_keyboard(submission_id: int):
    """审核操作。通过之后再选标签，不再放没有处理器的按钮。"""
    keyboard = [
        [
            InlineKeyboardButton("✅ 通过", callback_data=f"approve_{int(submission_id)}"),
            InlineKeyboardButton("❌ 拒绝", callback_data=f"reject_{int(submission_id)}"),
        ]
    ]
    return InlineKeyboardMarkup(keyboard)


def _tag_id(tag):
    if hasattr(tag, "id"):
        return tag.id
    if isinstance(tag, dict):
        return tag.get("id")
    return None


def _tag_label(tag) -> str:
    if hasattr(tag, "display_name"):
        return tag.display_name
    if isinstance(tag, dict):
        emoji = tag.get("emoji") or ""
        name = tag.get("name", "")
        return f"{emoji} {name}".strip()
    return str(tag)


def build_tags_keyboard(tags: list, submission_id: int, selected: list | None = None):
    """标签按钮使用标签的数据库 id，避免把名称放进 64 字节的 callback_data。"""
    if selected is None:
        selected = []
    selected_ids = set(selected)

    keyboard = []
    row = []
    for tag in tags:
        tag_id = _tag_id(tag)
        if tag_id is None:
            continue
        display = _tag_label(tag)
        if tag_id in selected_ids:
            display = f"✓ {display}"
        row.append(
            InlineKeyboardButton(
                display,
                callback_data=f"tag_{int(submission_id)}_{int(tag_id)}",
            )
        )
        if len(row) == 2:
            keyboard.append(row)
            row = []

    if row:
        keyboard.append(row)

    keyboard.append(
        [
            InlineKeyboardButton("✅ 确认标签", callback_data=f"confirm_tags_{int(submission_id)}"),
            InlineKeyboardButton("⬅️ 返回", callback_data=f"back_review_{int(submission_id)}"),
        ]
    )
    return InlineKeyboardMarkup(keyboard)


def build_reject_reasons_keyboard(reasons: list, submission_id: int):
    """拒绝理由按钮使用理由的数据库 id，而不是会变化的列表下标。"""
    keyboard = []
    for reason in reasons:
        reason_id = reason.id if hasattr(reason, "id") else reason.get("id")
        text = reason.text if hasattr(reason, "text") else reason.get("text", str(reason))
        display = text[:30] + "..." if len(text) > 30 else text
        keyboard.append(
            [
                InlineKeyboardButton(
                    display,
                    callback_data=f"reason_{int(submission_id)}_{int(reason_id)}",
                )
            ]
        )

    keyboard.append(
        [InlineKeyboardButton("✏️ 自定义理由", callback_data=f"custom_reason_{int(submission_id)}")]
    )
    keyboard.append(
        [InlineKeyboardButton("⬅️ 返回", callback_data=f"back_review_{int(submission_id)}")]
    )
    return InlineKeyboardMarkup(keyboard)


def build_admin_user_keyboard(user_id: int, is_banned: bool):
    """用户操作只保留有处理器的封禁/解封按钮。"""
    if is_banned:
        row = [InlineKeyboardButton("🔓 解封用户", callback_data=f"unban_{int(user_id)}")]
    else:
        row = [InlineKeyboardButton("🔒 封禁用户", callback_data=f"ban_{int(user_id)}")]
    return InlineKeyboardMarkup([row])
