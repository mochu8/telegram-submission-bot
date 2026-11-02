#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""投稿处理器"""

import json
import logging

from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

from config import config
from database.db import SubmissionNotAllowed, db
from utils.auth import review_recipient_ids
from utils.blocking import run_blocking
from utils.helpers import (
    build_submit_intro,
    build_welcome_text,
    escape_html,
    format_review_body,
    format_review_caption,
    format_user_link,
    get_level_emoji,
    get_level_title,
)
from utils.keyboard import (
    build_back_keyboard,
    build_main_keyboard,
    build_review_keyboard,
    build_submit_options_keyboard,
    build_submitting_keyboard,
)
from utils.media import MAX_CAPTION_LENGTH, MAX_MEDIA_ITEMS, MAX_TEXT_LENGTH, send_media_items
from utils.state import clear_submission_draft, clear_user_flow_state
from utils.users import submission_block_message, touch_user

logger = logging.getLogger(__name__)

STATE_IDLE = "idle"
STATE_CHOOSING_TYPE = "choosing_type"
STATE_SUBMITTING = "submitting"


def _remember_text(user_data: dict, plain: str | None, html_value: str | None, *, has_media: bool) -> str:
    """Append text. Returns saved, appended, or kept when the new text would exceed the limit."""
    if not plain:
        return "empty"
    limit = MAX_CAPTION_LENGTH if has_media or user_data.get("media_group") else MAX_TEXT_LENGTH
    existing = user_data.get("text_content") or ""
    if not existing:
        user_data["text_content"] = plain
        if html_value:
            user_data["text_html"] = html_value
        else:
            user_data.pop("text_html", None)
        return "saved"
    if plain == existing:
        return "saved"
    combined = f"{existing}\n{plain}"
    if len(combined) > limit:
        return "kept"
    user_data["text_content"] = combined
    previous_html = user_data.get("text_html")
    addition = html_value or escape_html(plain)
    if previous_html:
        user_data["text_html"] = f"{previous_html}\n{addition}"
    else:
        user_data["text_html"] = f"{escape_html(existing)}\n{addition}"
    return "appended"


async def start_submit_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """开始投稿 - 选择投稿类型"""
    query = update.callback_query
    blocked = await run_blocking(submission_block_message, update.effective_user)
    await query.answer()
    if blocked:
        await query.edit_message_text(blocked)
        return

    await query.edit_message_text(
        build_submit_intro(include_hint=True),
        parse_mode=ParseMode.HTML,
        reply_markup=build_submit_options_keyboard(),
    )


async def submit_type_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """选择投稿类型（实名/匿名）"""
    query = update.callback_query
    user = update.effective_user
    blocked = await run_blocking(submission_block_message, user)
    await query.answer()
    if blocked:
        await query.edit_message_text(blocked)
        return

    is_anonymous = query.data == "submit_anonymous"
    context.user_data["state"] = STATE_SUBMITTING
    context.user_data["is_anonymous"] = is_anonymous
    context.user_data["media_group"] = []
    context.user_data["text_content"] = None
    context.user_data.pop("text_html", None)
    context.user_data["media_group_id"] = None

    submit_type = "🕶️ 匿名投稿" if is_anonymous else "👤 实名投稿"
    await query.edit_message_text(
        (
            f"✅ 已选择：<b>{escape_html(submit_type)}</b>\n\n"
            "请发送您要投稿的内容：\n"
            "• 支持文字、图片、视频、音频、文件\n"
            f"• 支持多图投稿（最多 {MAX_MEDIA_ITEMS} 个）\n"
            f"• 文字不超过 {MAX_TEXT_LENGTH} 个字符，媒体说明不超过 {MAX_CAPTION_LENGTH} 个字符\n"
            "• 发送完成后点击「完成投稿」\n\n"
            "⚠️ 发送 /cancel 可取消投稿"
        ),
        parse_mode=ParseMode.HTML,
        reply_markup=build_submitting_keyboard(),
    )


async def handle_submission_content(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """处理用户发送的投稿内容"""
    user = update.effective_user
    message = update.message
    if user is None or message is None:
        return

    blocked = await run_blocking(submission_block_message, user)
    if blocked:
        clear_submission_draft(context.user_data)
        await message.reply_text(blocked)
        return

    if context.user_data.get("state") != STATE_SUBMITTING:
        await message.reply_text(
            "请先点击「📝 我要投稿」开始投稿\n\n发送 /start 返回主菜单",
            reply_markup=build_back_keyboard(),
        )
        return

    if message.text and len(message.text) > MAX_TEXT_LENGTH:
        await message.reply_text(
            f"文字不能超过 {MAX_TEXT_LENGTH} 个字符，请缩短后重新发送。",
            reply_markup=build_submitting_keyboard(),
        )
        return

    if message.caption and len(message.caption) > MAX_CAPTION_LENGTH:
        await message.reply_text(
            f"媒体说明不能超过 {MAX_CAPTION_LENGTH} 个字符，请缩短后重新发送。",
            reply_markup=build_submitting_keyboard(),
        )
        return

    if message.media_group_id:
        context.user_data["media_group_id"] = message.media_group_id

    media_item = extract_media_info(message)
    if media_item:
        media_group = context.user_data.setdefault("media_group", [])
        if len(media_group) >= MAX_MEDIA_ITEMS:
            await message.reply_text(
                f"最多只能投稿 {MAX_MEDIA_ITEMS} 个媒体文件。",
                reply_markup=build_submitting_keyboard(),
            )
            return
        media_group.append(media_item)
        remembered = _remember_text(
            context.user_data,
            message.caption,
            message.caption_html,
            has_media=True,
        )
        if message.media_group_id and remembered != "kept":
            return
        note = _text_memory_note(remembered)
        await message.reply_text(
            f"✅ 已收到 {len(media_group)} 个媒体文件{note}\n\n继续发送更多内容，或点击「完成投稿」",
            reply_markup=build_submitting_keyboard(),
        )
        return

    if message.text:
        remembered = _remember_text(
            context.user_data,
            message.text,
            message.text_html,
            has_media=False,
        )
        note = _text_memory_note(remembered)
        await message.reply_text(
            f"✅ 已收到文字内容{note}\n\n可以继续发送图片/视频/音频/文件，或点击「完成投稿」",
            reply_markup=build_submitting_keyboard(),
        )
        return

    await message.reply_text(
        "暂不支持这种消息类型。请发送文字、图片、视频、音频或文件。",
        reply_markup=build_submitting_keyboard(),
    )


def _text_memory_note(remembered: str) -> str:
    if remembered == "appended":
        return "\n已把这段文字接到之前的内容后面。"
    if remembered == "kept":
        return "\n已保留之前的文字。加上这段后会超过长度限制，所以没有写入。"
    return ""


def extract_media_info(message) -> dict | None:
    """提取消息中的媒体信息"""
    if message.photo:
        return {"type": "photo", "file_id": message.photo[-1].file_id}
    if message.video:
        return {"type": "video", "file_id": message.video.file_id}
    if message.audio:
        return {"type": "audio", "file_id": message.audio.file_id}
    if message.document:
        return {"type": "document", "file_id": message.document.file_id}
    return None


async def finish_submit_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """完成投稿"""
    query = update.callback_query
    user = update.effective_user
    blocked = await run_blocking(submission_block_message, user)
    if blocked:
        clear_submission_draft(context.user_data)
        await query.answer()
        await query.edit_message_text(blocked)
        return

    media_group = list(context.user_data.get("media_group") or [])
    text_content = context.user_data.get("text_content")
    is_anonymous = context.user_data.get("is_anonymous", False)

    if not media_group and not text_content:
        await query.answer("❌ 请先发送投稿内容", show_alert=True)
        return
    if len(media_group) > MAX_MEDIA_ITEMS:
        await query.answer(f"最多只能投稿 {MAX_MEDIA_ITEMS} 个媒体文件", show_alert=True)
        return
    if media_group and text_content and len(text_content) > MAX_CAPTION_LENGTH:
        await query.answer(
            f"带媒体时文字不能超过 {MAX_CAPTION_LENGTH} 个字符，请缩短后再完成",
            show_alert=True,
        )
        return
    if not media_group and text_content and len(text_content) > MAX_TEXT_LENGTH:
        await query.answer(f"文字不能超过 {MAX_TEXT_LENGTH} 个字符", show_alert=True)
        return

    await query.answer()
    if len(media_group) > 1:
        content_type = "media_group"
    elif len(media_group) == 1:
        content_type = media_group[0]["type"]
    else:
        content_type = "text"

    try:
        submission = await run_blocking(
            db.create_submission,
            user_id=user.id,
            content_type=content_type,
            text_content=text_content,
            text_html=context.user_data.get("text_html"),
            media_ids=[item["file_id"] for item in media_group] or None,
            media_types=[item["type"] for item in media_group] or None,
            is_anonymous=is_anonymous,
        )
    except SubmissionNotAllowed as exc:
        logger.info("Refused to store a submission for user %s: %s", user.id, exc)
        clear_submission_draft(context.user_data)
        detail = str(exc)
        if detail.startswith("user "):
            detail = await run_blocking(submission_block_message, user) or "请先发送 /start 后再投稿"
        await query.edit_message_text(detail)
        return

    clear_submission_draft(context.user_data)
    await query.edit_message_text(
        (
            "✅ <b>投稿成功！</b>\n\n"
            f"投稿编号：<code>#{submission.id}</code>\n"
            f"投稿类型：{'匿名' if is_anonymous else '实名'}\n"
            "状态：⏳ 等待审核\n\n"
            "我们会尽快审核您的投稿，请耐心等待。"
        ),
        parse_mode=ParseMode.HTML,
        reply_markup=build_back_keyboard(),
    )
    await notify_admins_new_submission(context, submission, user)


async def notify_admins_new_submission(context: ContextTypes.DEFAULT_TYPE, submission, user):
    """通知管理员有新投稿"""
    admin_ids = review_recipient_ids()
    if not admin_ids:
        return

    if submission.is_anonymous:
        user_info = "👤 <b>匿名用户</b>"
    else:
        user_link = format_user_link(user.id, user.full_name or "用户", user.username)
        user_info = f"👤 投稿者: {user_link}\n🆔 用户ID: <code>{int(user.id)}</code>"

    body = format_review_body(submission.text_content, submission.text_html)
    if body:
        body += "\n\n"

    text = (
        f"📨 <b>新投稿 #{submission.id}</b>\n\n"
        f"{user_info}\n"
        f"📁 类型: {escape_html(submission.content_type)}\n"
        "⏰ 时间: 刚刚\n\n"
        f"{'─' * 20}\n\n"
        f"{body}"
    )

    for admin_id in admin_ids:
        try:
            sent = await context.bot.send_message(
                chat_id=admin_id,
                text=text,
                parse_mode=ParseMode.HTML,
                reply_markup=build_review_keyboard(submission.id),
            )
            if sent is not None:
                await run_blocking(db.add_review_notice, submission.id, admin_id, sent.message_id)
            if not submission.media_ids:
                continue
            media_ids = json.loads(submission.media_ids)
            if submission.media_types:
                media_types = json.loads(submission.media_types)
            else:
                media_types = ["photo"] * len(media_ids)
            caption = format_review_caption(
                submission.text_content,
                submission.text_html,
                MAX_CAPTION_LENGTH,
            )
            await send_media_items(
                context.bot,
                admin_id,
                media_ids,
                media_types,
                caption=caption,
            )
        except Exception:
            logger.warning("通知管理员 %s 失败", admin_id, exc_info=True)


async def cancel_submit_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """取消投稿"""
    await back_to_main_callback(update, context, answer_text="已取消投稿")


async def back_to_main_callback(update: Update, context: ContextTypes.DEFAULT_TYPE,
                                answer_text: str | None = None):
    """返回主菜单"""
    query = update.callback_query
    await run_blocking(touch_user, update.effective_user)
    clear_user_flow_state(context.user_data)
    if query is None:
        return

    await query.answer(answer_text)
    await query.edit_message_text(
        build_welcome_text(),
        parse_mode=ParseMode.HTML,
        reply_markup=build_main_keyboard(
            config.navigation_links,
            config.channel_id,
            config.customer_service,
        ),
    )


async def placeholder_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """占位按钮点击"""
    await run_blocking(touch_user, update.effective_user)
    await update.callback_query.answer("该功能正在筹建中，敬请期待！", show_alert=True)


async def submit_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """处理 /submit 命令"""
    blocked = await run_blocking(submission_block_message, update.effective_user)
    if blocked:
        await update.message.reply_text(blocked)
        return

    await update.message.reply_text(
        build_submit_intro(),
        parse_mode=ParseMode.HTML,
        reply_markup=build_submit_options_keyboard(),
    )


async def my_submissions_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """查看自己的投稿和状态。"""
    user = update.effective_user
    await run_blocking(touch_user, user)
    rows = await run_blocking(db.get_user_submissions, user.id, limit=10)
    if not rows:
        await update.message.reply_text("你还没有投稿。")
        return
    status_name = {
        "pending": "待审核",
        "publishing": "发布中",
        "approved": "已通过",
        "rejected": "已拒绝",
    }
    lines = ["<b>我的投稿</b>", ""]
    for sub in rows:
        kind = "匿名" if sub.is_anonymous else "实名"
        lines.append(
            f"#{sub.id} {status_name.get(sub.status, escape_html(sub.status))} · {kind}"
        )
    await update.message.reply_text("\n".join(lines), parse_mode=ParseMode.HTML)


async def my_stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """查看我的投稿统计"""
    user = update.effective_user
    await run_blocking(touch_user, user)
    stats = await run_blocking(db.get_user_stats, user.id)
    if not stats:
        await update.message.reply_text("📊 您还没有投稿记录")
        return

    level = stats["level"]
    text = (
        "📊 <b>我的投稿统计</b>\n\n"
        f"{get_level_emoji(level)} <b>等级：</b> Lv.{level} {escape_html(get_level_title(level))}\n\n"
        f"📝 <b>总投稿：</b> {stats['total']} 篇\n"
        f"✅ <b>已通过：</b> {stats['approved']} 篇\n"
        f"❌ <b>已拒绝：</b> {stats['rejected']} 篇\n"
        f"⏳ <b>待审核：</b> {stats['pending']} 篇\n\n"
        f"📈 <b>通过率：</b> {stats['approval_rate']}%"
    )
    await update.message.reply_text(text, parse_mode=ParseMode.HTML)
