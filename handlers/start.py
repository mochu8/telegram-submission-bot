#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
/start 命令处理器
"""

from telegram import Update
from telegram.ext import ContextTypes
from telegram.constants import ParseMode

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from config import config
from database.db import db
from utils.keyboard import build_main_keyboard


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """处理 /start 命令"""
    user = update.effective_user
    
    # 记录/更新用户
    db.get_or_create_user(
        user_id=user.id,
        username=user.username,
        full_name=user.full_name
    )
    
    # 清除用户状态
    context.user_data.clear()
    
    # 构建欢迎消息
    bot_info = config.bot_info
    welcome_text = f"🤖 *机器人介绍：*\n\nWelcome to {bot_info.get('name', '投稿机器人')}"
    
    # 添加导航链接
    nav_text = "\n"
    for link in config.navigation_links:
        if link.get("enabled", True) and link.get("username"):
            nav_text += f"\n{link['name']}: @{link['username']}"
        elif not link.get("enabled", True):
            placeholder = link.get("placeholder_text", link["name"] + "（筹建中）")
            nav_text += f"\n{placeholder}"
    
    full_message = welcome_text + nav_text
    
    # 构建键盘
    keyboard = build_main_keyboard(
        config.navigation_links,
        config.channel_id,
        config.customer_service
    )
    
    await update.message.reply_text(
        full_message,
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=keyboard
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """处理 /help 命令"""
    help_text = """
🤖 *机器人使用帮助*

*普通用户命令：*
/start - 启动机器人，显示主菜单
/submit - 开始投稿
/mystats - 查看我的投稿统计
/cancel - 取消当前操作
/help - 显示帮助信息

*投稿说明：*
• 支持文字、图片、视频、音频投稿
• 支持多图投稿（最多10张）
• 可选择实名或匿名投稿
• 投稿后等待管理员审核

*注意事项：*
• 请提供真实有效的信息
• 违规投稿可能导致封禁
"""
    
    # 检查是否是管理员
    if config.is_config_admin(update.effective_user.id) or db.is_admin(update.effective_user.id):
        help_text += """
*管理员命令：*
/queue - 查看待审核队列
/stats - 查看总体统计
/ban <用户ID> <原因> - 封禁用户
/unban <用户ID> - 解封用户
/addtag <名称> <emoji> - 添加标签
/addreason <理由> - 添加拒绝理由
"""
    
    await update.message.reply_text(help_text, parse_mode=ParseMode.MARKDOWN)


async def cancel_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """处理 /cancel 命令"""
    context.user_data.clear()
    await update.message.reply_text(
        "✅ 已取消当前操作\n\n发送 /start 返回主菜单"
    )
