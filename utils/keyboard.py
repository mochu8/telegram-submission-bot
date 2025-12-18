#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
键盘生成工具
"""

from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from typing import List, Optional


def build_main_keyboard(navigation_links: list, channel_id: str, 
                        customer_service: dict) -> InlineKeyboardMarkup:
    """构建主菜单键盘"""
    keyboard = []
    
    # 添加导航链接按钮
    for link in navigation_links:
        if link.get("enabled", True) and link.get("username"):
            keyboard.append([
                InlineKeyboardButton(
                    link["name"],
                    url=f"https://t.me/{link['username']}"
                )
            ])
        elif not link.get("enabled", True):
            placeholder = link.get("placeholder_text", link["name"] + "（筹建中）")
            keyboard.append([
                InlineKeyboardButton(placeholder, callback_data="placeholder")
            ])
    
    # 投稿按钮
    keyboard.append([
        InlineKeyboardButton("📝 我要投稿", callback_data="start_submit")
    ])
    
    # 底部按钮行
    bottom_row = []
    if channel_id:
        channel_username = channel_id.replace("@", "")
        bottom_row.append(
            InlineKeyboardButton(
                "📢 订阅频道",
                url=f"https://t.me/{channel_username}"
            )
        )
    
    if customer_service.get("username"):
        bottom_row.append(
            InlineKeyboardButton(
                customer_service.get("name", "联系客服"),
                url=f"https://t.me/{customer_service['username']}"
            )
        )
    
    if bottom_row:
        keyboard.append(bottom_row)
    
    return InlineKeyboardMarkup(keyboard)


def build_submit_options_keyboard() -> InlineKeyboardMarkup:
    """构建投稿选项键盘"""
    keyboard = [
        [
            InlineKeyboardButton("👤 实名投稿", callback_data="submit_named"),
            InlineKeyboardButton("🕶️ 匿名投稿", callback_data="submit_anonymous")
        ],
        [InlineKeyboardButton("❌ 取消", callback_data="cancel_submit")]
    ]
    return InlineKeyboardMarkup(keyboard)


def build_submitting_keyboard() -> InlineKeyboardMarkup:
    """构建投稿中键盘"""
    keyboard = [
        [InlineKeyboardButton("✅ 完成投稿", callback_data="finish_submit")],
        [InlineKeyboardButton("❌ 取消投稿", callback_data="cancel_submit")]
    ]
    return InlineKeyboardMarkup(keyboard)


def build_back_keyboard() -> InlineKeyboardMarkup:
    """构建返回键盘"""
    keyboard = [[InlineKeyboardButton("🏠 返回主菜单", callback_data="back_to_main")]]
    return InlineKeyboardMarkup(keyboard)


def build_review_keyboard(submission_id: int) -> InlineKeyboardMarkup:
    """构建审核键盘"""
    keyboard = [
        [
            InlineKeyboardButton("✅ 通过", callback_data=f"approve_{submission_id}"),
            InlineKeyboardButton("❌ 拒绝", callback_data=f"reject_{submission_id}")
        ],
        [
            InlineKeyboardButton("🏷️ 添加标签", callback_data=f"add_tags_{submission_id}"),
            InlineKeyboardButton("📝 编辑后发布", callback_data=f"edit_{submission_id}")
        ]
    ]
    return InlineKeyboardMarkup(keyboard)


def build_tags_keyboard(tags: list, submission_id: int, 
                        selected: list = None) -> InlineKeyboardMarkup:
    """构建标签选择键盘"""
    if selected is None:
        selected = []
    
    keyboard = []
    row = []
    for tag in tags:
        display = tag.display_name if hasattr(tag, 'display_name') else f"{tag.get('emoji', '')} {tag.get('name', '')}"
        tag_name = tag.name if hasattr(tag, 'name') else tag.get('name', '')
        
        # 标记已选中的标签
        if tag_name in selected:
            display = f"✓ {display}"
        
        row.append(InlineKeyboardButton(
            display,
            callback_data=f"tag_{submission_id}_{tag_name}"
        ))
        
        if len(row) == 2:
            keyboard.append(row)
            row = []
    
    if row:
        keyboard.append(row)
    
    # 确认和取消按钮
    keyboard.append([
        InlineKeyboardButton("✅ 确认标签", callback_data=f"confirm_tags_{submission_id}"),
        InlineKeyboardButton("⬅️ 返回", callback_data=f"back_review_{submission_id}")
    ])
    
    return InlineKeyboardMarkup(keyboard)


def build_reject_reasons_keyboard(reasons: list, 
                                  submission_id: int) -> InlineKeyboardMarkup:
    """构建拒绝理由键盘"""
    keyboard = []
    for i, reason in enumerate(reasons):
        text = reason.text if hasattr(reason, 'text') else reason
        # 截断过长的理由
        display = text[:30] + "..." if len(text) > 30 else text
        keyboard.append([
            InlineKeyboardButton(display, callback_data=f"reason_{submission_id}_{i}")
        ])
    
    # 自定义理由和返回
    keyboard.append([
        InlineKeyboardButton("✏️ 自定义理由", callback_data=f"custom_reason_{submission_id}")
    ])
    keyboard.append([
        InlineKeyboardButton("⬅️ 返回", callback_data=f"back_review_{submission_id}")
    ])
    
    return InlineKeyboardMarkup(keyboard)


def build_confirm_publish_keyboard(submission_id: int) -> InlineKeyboardMarkup:
    """构建确认发布键盘"""
    keyboard = [
        [
            InlineKeyboardButton("✅ 确认发布", callback_data=f"confirm_publish_{submission_id}"),
            InlineKeyboardButton("⬅️ 返回", callback_data=f"back_review_{submission_id}")
        ]
    ]
    return InlineKeyboardMarkup(keyboard)


def build_admin_user_keyboard(user_id: int, is_banned: bool) -> InlineKeyboardMarkup:
    """构建管理员用户操作键盘"""
    keyboard = []
    if is_banned:
        keyboard.append([
            InlineKeyboardButton("🔓 解封用户", callback_data=f"unban_{user_id}")
        ])
    else:
        keyboard.append([
            InlineKeyboardButton("🔒 封禁用户", callback_data=f"ban_{user_id}")
        ])
    
    keyboard.append([
        InlineKeyboardButton("📊 查看统计", callback_data=f"user_stats_{user_id}"),
        InlineKeyboardButton("📜 投稿记录", callback_data=f"user_submissions_{user_id}")
    ])
    
    return InlineKeyboardMarkup(keyboard)
