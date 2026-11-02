#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""管理员命令处理器"""

import logging

from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

from config import config
from database.db import db
from utils.auth import admin_only, is_operator
from utils.helpers import escape_html, format_datetime, get_level_emoji, get_level_title
from utils.keyboard import build_admin_user_keyboard, build_review_keyboard
from utils.state import peek_pending_input, pop_pending_input, set_pending_input

logger = logging.getLogger(__name__)


def _target_name(user, target_id: int) -> str:
    if user is not None and user.full_name:
        return escape_html(user.full_name)
    return f"ID:{int(target_id)}"


async def _notify(bot, chat_id: int, text: str) -> None:
    try:
        await bot.send_message(chat_id=chat_id, text=text, parse_mode=ParseMode.HTML)
    except Exception:
        logger.warning("Failed to notify user %s", chat_id, exc_info=True)


@admin_only
async def queue_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """查看待审核队列"""
    pending_count = db.get_pending_count()
    pending_submissions = db.get_pending_submissions(limit=5)

    if not pending_submissions:
        await update.message.reply_text("✅ 当前没有待审核的投稿")
        return

    lines = [f"📋 <b>待审核队列</b> ({pending_count} 篇)", ""]
    for sub in pending_submissions:
        user = db.get_user(sub.user_id)
        if sub.is_anonymous:
            user_info = "匿名"
        elif user is not None and user.full_name:
            user_info = escape_html(user.full_name)
        else:
            user_info = f"ID:{sub.user_id}"
        lines.append(f"• #{sub.id} - {user_info} - {escape_html(sub.content_type)}")

    if pending_count > 5:
        lines.append(f"\n... 还有 {pending_count - 5} 篇待审核")
    lines.append("\n💡 点击下方按钮审核第一篇")

    await update.message.reply_text(
        "\n".join(lines),
        parse_mode=ParseMode.HTML,
        reply_markup=build_review_keyboard(pending_submissions[0].id),
    )


@admin_only
async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """查看总体统计"""
    stats = db.get_overall_stats()
    if stats["total_submissions"] > 0:
        approval_rate = round(stats["approved"] / stats["total_submissions"] * 100, 1)
    else:
        approval_rate = 0

    publishing_line = ""
    if stats["publishing"]:
        publishing_line = f"🔄 发布中: {stats['publishing']}\n"

    text = (
        "📊 <b>系统统计</b>\n\n"
        f"👥 <b>总用户数：</b> {stats['total_users']}\n"
        f"📝 <b>总投稿数：</b> {stats['total_submissions']}\n\n"
        "<b>投稿状态分布：</b>\n"
        f"⏳ 待审核: {stats['pending']}\n"
        f"{publishing_line}"
        f"✅ 已通过: {stats['approved']}\n"
        f"❌ 已拒绝: {stats['rejected']}\n\n"
        f"📈 <b>通过率：</b> {approval_rate}%"
    )
    await update.message.reply_text(text, parse_mode=ParseMode.HTML)


@admin_only
async def ban_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """封禁用户"""
    args = context.args or []
    if not args:
        await update.message.reply_text(
            "用法: <code>/ban &lt;用户ID&gt; [理由]</code>\n例如: <code>/ban 123456789 违规投稿</code>",
            parse_mode=ParseMode.HTML,
        )
        return

    try:
        target_id = int(args[0])
    except ValueError:
        await update.message.reply_text("❌ 无效的用户ID")
        return

    reason = " ".join(args[1:]) if len(args) > 1 else None
    if config.is_config_admin(target_id) or db.is_admin(target_id):
        await update.message.reply_text("❌ 不能封禁管理员")
        return

    if not db.ban_user(target_id, update.effective_user.id, reason):
        await update.message.reply_text("❌ 封禁失败，对方可能是管理员")
        return

    target = db.get_user(target_id)
    await update.message.reply_text(
        (
            "🔒 <b>用户已封禁</b>\n\n"
            f"👤 用户: {_target_name(target, target_id)}\n"
            f"🆔 ID: <code>{target_id}</code>\n"
            f"📝 理由: {escape_html(reason or '无')}"
        ),
        parse_mode=ParseMode.HTML,
    )
    await _notify(
        context.bot,
        target_id,
        (
            "⚠️ <b>您的账号已被封禁</b>\n\n"
            f"📝 原因: {escape_html(reason or '未说明')}\n\n"
            "如有疑问请联系管理员"
        ),
    )


@admin_only
async def unban_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """解封用户"""
    args = context.args or []
    if not args:
        await update.message.reply_text(
            "用法: <code>/unban &lt;用户ID&gt;</code>\n例如: <code>/unban 123456789</code>",
            parse_mode=ParseMode.HTML,
        )
        return

    try:
        target_id = int(args[0])
    except ValueError:
        await update.message.reply_text("❌ 无效的用户ID")
        return

    if not db.unban_user(target_id, update.effective_user.id):
        await update.message.reply_text("❌ 解封失败，用户可能不存在")
        return

    target = db.get_user(target_id)
    await update.message.reply_text(
        (
            "🔓 <b>用户已解封</b>\n\n"
            f"👤 用户: {_target_name(target, target_id)}\n"
            f"🆔 ID: <code>{target_id}</code>"
        ),
        parse_mode=ParseMode.HTML,
    )
    await _notify(
        context.bot,
        target_id,
        "🎉 <b>您的账号已被解封</b>\n\n现在可以继续使用机器人了。",
    )


@admin_only
async def add_tag_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """添加标签"""
    args = context.args or []
    if not args:
        await update.message.reply_text(
            "用法: <code>/addtag &lt;名称&gt; [emoji]</code>\n例如: <code>/addtag 求助 🆘</code>",
            parse_mode=ParseMode.HTML,
        )
        return

    name = args[0]
    emoji = args[1] if len(args) > 1 else None
    tag = db.add_tag(name, emoji)
    if tag is None:
        await update.message.reply_text("❌ 标签已存在")
        return

    await update.message.reply_text(
        (
            "✅ <b>标签已添加</b>\n\n"
            f"🏷️ 名称: {escape_html(name)}\n"
            f"😀 Emoji: {escape_html(emoji or '无')}"
        ),
        parse_mode=ParseMode.HTML,
    )


@admin_only
async def add_reason_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """添加拒绝理由"""
    args = context.args or []
    if not args:
        await update.message.reply_text(
            "用法: <code>/addreason &lt;理由文本&gt;</code>\n例如: <code>/addreason 内容与频道主题不符</code>",
            parse_mode=ParseMode.HTML,
        )
        return

    text = " ".join(args)
    db.add_reject_reason(text)
    await update.message.reply_text(
        f"✅ <b>拒绝理由已添加</b>\n\n📝 理由: {escape_html(text)}",
        parse_mode=ParseMode.HTML,
    )


@admin_only
async def user_info_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """查看用户信息"""
    args = context.args or []
    if not args:
        await update.message.reply_text(
            "用法: <code>/userinfo &lt;用户ID&gt;</code>",
            parse_mode=ParseMode.HTML,
        )
        return

    try:
        target_id = int(args[0])
    except ValueError:
        await update.message.reply_text("❌ 无效的用户ID")
        return

    user = db.get_user(target_id)
    if user is None:
        await update.message.reply_text("❌ 用户不存在")
        return

    stats = db.get_user_stats(target_id)
    level = stats["level"]
    username = f"@{escape_html(user.username)}" if user.username else "无"
    text = (
        "👤 <b>用户信息</b>\n\n"
        f"🆔 ID: <code>{user.id}</code>\n"
        f"📛 用户名: {username}\n"
        f"📝 昵称: {escape_html(user.full_name or '无')}\n"
        f"📅 注册时间: {escape_html(format_datetime(user.created_at))}\n\n"
        f"{get_level_emoji(level)} <b>等级：</b> Lv.{level} {escape_html(get_level_title(level))}\n"
        f"🔐 <b>角色：</b> {escape_html(user.role)}\n"
        f"🚫 <b>封禁状态：</b> {'是' if user.is_banned else '否'}\n\n"
        "<b>投稿统计：</b>\n"
        f"📝 总投稿: {stats['total']}\n"
        f"✅ 已通过: {stats['approved']}\n"
        f"❌ 已拒绝: {stats['rejected']}\n"
        f"📈 通过率: {stats['approval_rate']}%"
    )
    if user.is_banned:
        text += f"\n📝 <b>封禁原因：</b> {escape_html(user.ban_reason or '未说明')}"

    await update.message.reply_text(
        text,
        parse_mode=ParseMode.HTML,
        reply_markup=build_admin_user_keyboard(target_id, user.is_banned),
    )


@admin_only
async def ban_user_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """通过按钮封禁用户"""
    query = update.callback_query
    target_id = int(query.data.replace("ban_", ""))
    if config.is_config_admin(target_id) or db.is_admin(target_id):
        await query.answer("不能封禁管理员", show_alert=True)
        return

    await query.answer()
    set_pending_input(context.user_data, "ban_reason", target_id=target_id)
    await query.edit_message_text(
        (
            f"请输入封禁用户 <code>{target_id}</code> 的理由：\n\n"
            "直接发送文字，或发送 /cancel 取消"
        ),
        parse_mode=ParseMode.HTML,
    )


@admin_only
async def unban_user_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """通过按钮解封用户"""
    query = update.callback_query
    await query.answer()

    target_id = int(query.data.replace("unban_", ""))
    if not db.unban_user(target_id, update.effective_user.id):
        await query.edit_message_text("❌ 解封失败")
        return

    target = db.get_user(target_id)
    await query.edit_message_text(
        (
            "🔓 <b>用户已解封</b>\n\n"
            f"👤 用户: {_target_name(target, target_id)}\n"
            f"🆔 ID: <code>{target_id}</code>"
        ),
        parse_mode=ParseMode.HTML,
    )
    await _notify(
        context.bot,
        target_id,
        "🎉 <b>您的账号已被解封</b>\n\n现在可以继续使用机器人了。",
    )


async def handle_ban_reason_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """处理封禁理由输入"""
    pending = peek_pending_input(context.user_data, "ban_reason")
    if not pending:
        return False

    user = update.effective_user
    message = update.message
    if user is None or message is None or not is_operator(user.id):
        return False

    if context.user_data.get("state") == "submitting":
        pop_pending_input(context.user_data, "ban_reason")
        await message.reply_text(
            "你正在投稿，已取消未完成的封禁理由。这条消息会按投稿内容处理。\n"
            "如需封禁，请先发送 /cancel 结束投稿。"
        )
        return False

    if not message.text or not message.text.strip():
        await message.reply_text("请发送文字理由，或发送 /cancel 取消")
        return True

    reason = message.text.strip()
    target_id = int(pending["target_id"])
    if config.is_config_admin(target_id) or db.is_admin(target_id):
        pop_pending_input(context.user_data, "ban_reason")
        await message.reply_text("❌ 不能封禁管理员")
        return True

    pop_pending_input(context.user_data, "ban_reason")
    if not db.ban_user(target_id, user.id, reason):
        await message.reply_text("❌ 封禁失败")
        return True

    target = db.get_user(target_id)
    await message.reply_text(
        (
            "🔒 <b>用户已封禁</b>\n\n"
            f"👤 用户: {_target_name(target, target_id)}\n"
            f"🆔 ID: <code>{target_id}</code>\n"
            f"📝 理由: {escape_html(reason)}"
        ),
        parse_mode=ParseMode.HTML,
    )
    await _notify(
        context.bot,
        target_id,
        (
            "⚠️ <b>您的账号已被封禁</b>\n\n"
            f"📝 原因: {escape_html(reason)}\n\n"
            "如有疑问请联系管理员"
        ),
    )
    return True


@admin_only
async def stuck_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """列出卡在发布中的投稿。"""
    rows = db.list_publishing_submissions()
    if not rows:
        await update.message.reply_text("没有卡在发布中的投稿。")
        return
    lines = ["<b>发布中的投稿</b>", ""]
    for sub in rows:
        lines.append(
            f"#{sub.id} 投稿人 <code>{sub.user_id}</code> "
            f"审核人 <code>{sub.reviewer_id or '无'}</code>"
        )
    lines.append("")
    lines.append("退回待审核：<code>/resolve 编号 pending</code>")
    lines.append("确认已发出、不再发布：<code>/resolve 编号 approved</code>")
    await update.message.reply_text("\n".join(lines), parse_mode=ParseMode.HTML)


@admin_only
async def resolve_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """把卡在 publishing 的投稿退回待审核，或标成已通过且不再发送。"""
    args = context.args or []
    if len(args) != 2:
        await update.message.reply_text(
            "用法: <code>/resolve &lt;投稿编号&gt; pending|approved</code>",
            parse_mode=ParseMode.HTML,
        )
        return
    try:
        submission_id = int(args[0])
    except ValueError:
        await update.message.reply_text("❌ 无效的投稿编号")
        return
    action = args[1].lower()
    submission = db.get_submission(submission_id)
    if submission is None:
        await update.message.reply_text("❌ 投稿不存在")
        return
    if submission.status != "publishing":
        await update.message.reply_text("❌ 只有状态为发布中的投稿可以这样处理")
        return
    actor_id = update.effective_user.id
    if action == "pending":
        ok = db.release_submission_claim(submission_id)
        text = f"投稿 #{submission_id} 已退回待审核。请先确认频道里没有这条消息。"
    elif action == "approved":
        ok = db.finalize_approval(submission_id, actor_id, None, submission.published_msg_id)
        text = (
            f"投稿 #{submission_id} 已标成通过，不会再次发到频道。"
            "如果频道里实际上没有这条消息，请不要用 approved。"
        )
    else:
        await update.message.reply_text("❌ 第二个参数只能是 pending 或 approved")
        return
    if not ok:
        await update.message.reply_text("❌ 处理失败，状态可能已经变了")
        return
    await update.message.reply_text(text)


@admin_only
async def retired_button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """旧键盘上已删除的按钮。只提示，不执行任何写操作。"""
    await update.callback_query.answer("该按钮已停用，请使用最新消息上的按钮", show_alert=True)
