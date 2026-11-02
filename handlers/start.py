#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""/start 命令处理器"""

from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

from config import config
from utils.auth import is_operator
from utils.helpers import build_welcome_text
from utils.keyboard import build_main_keyboard
from utils.state import clear_user_flow_state
from utils.users import touch_user


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """处理 /start 命令"""
    touch_user(update.effective_user)
    clear_user_flow_state(context.user_data)

    await update.message.reply_text(
        build_welcome_text(),
        parse_mode=ParseMode.HTML,
        reply_markup=build_main_keyboard(
            config.navigation_links,
            config.channel_id,
            config.customer_service,
        ),
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """处理 /help 命令"""
    touch_user(update.effective_user)
    help_text = (
        "🤖 <b>机器人使用帮助</b>\n\n"
        "<b>普通用户命令：</b>\n"
        "/start - 启动机器人，显示主菜单\n"
        "/submit - 开始投稿\n"
        "/mystats - 查看我的投稿统计\n"
        "/cancel - 取消当前操作\n"
        "/help - 显示帮助信息\n\n"
        "<b>投稿说明：</b>\n"
        "• 支持文字、图片、视频、音频和文件投稿\n"
        "• 支持多媒体投稿（最多 10 个）\n"
        "• 可选择实名或匿名投稿\n"
        "• 投稿后等待管理员审核\n\n"
        "<b>注意事项：</b>\n"
        "• 请提供真实有效的信息\n"
        "• 违规投稿可能导致封禁"
    )

    if is_operator(update.effective_user.id):
        help_text += (
            "\n\n<b>管理员命令：</b>\n"
            "/queue - 查看待审核队列\n"
            "/stats - 查看总体统计\n"
            "/ban &lt;用户ID&gt; &lt;原因&gt; - 封禁用户\n"
            "/unban &lt;用户ID&gt; - 解封用户\n"
            "/userinfo &lt;用户ID&gt; - 查看用户信息\n"
            "/addtag &lt;名称&gt; &lt;emoji&gt; - 添加标签\n"
            "/addreason &lt;理由&gt; - 添加拒绝理由"
        )

    await update.message.reply_text(help_text, parse_mode=ParseMode.HTML)


async def cancel_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """处理 /cancel 命令"""
    touch_user(update.effective_user)
    clear_user_flow_state(context.user_data)
    await update.message.reply_text("✅ 已取消当前操作\n\n发送 /start 返回主菜单")
