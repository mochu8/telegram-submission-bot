#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""审核处理器"""

import json
import logging

from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

from config import config
from database.db import db
from utils.auth import DENIED_TEXT, admin_only, is_operator
from utils.helpers import build_publish_bodies, escape_html
from utils.keyboard import (
    build_reject_reasons_keyboard,
    build_review_keyboard,
    build_tags_keyboard,
)
from utils.media import (
    MAX_CAPTION_LENGTH,
    MAX_TEXT_LENGTH,
    clip_text,
    send_media_items,
)
from utils.state import (
    clear_review_state,
    peek_pending_input,
    pop_pending_input,
    review_state,
    set_pending_input,
)

logger = logging.getLogger(__name__)


def _tag_names(tag_ids) -> list[str]:
    ids = []
    for tag_id in tag_ids or []:
        try:
            ids.append(int(tag_id))
        except (TypeError, ValueError):
            continue
    return [tag.name for tag in db.get_tags_by_ids(ids)]


def _rejection_admin_text(submission_id: int, reason: str) -> str:
    return (
        f"❌ <b>投稿 #{int(submission_id)} 已拒绝</b>\n\n"
        f"📝 理由: {escape_html(reason)}"
    )


def _rejection_user_text(submission_id: int, reason: str) -> str:
    return (
        f"😔 <b>您的投稿 #{int(submission_id)} 未通过审核</b>\n\n"
        f"📝 原因: {escape_html(reason)}\n\n"
        "您可以根据反馈修改后重新投稿。"
    )


async def _answer_denied(query) -> None:
    if query is None:
        return
    try:
        await query.answer(DENIED_TEXT, show_alert=True)
    except Exception:
        logger.warning("Could not answer unauthorized callback", exc_info=True)


async def _notify_rejection(context, submission, submission_id: int, reason: str) -> None:
    try:
        await context.bot.send_message(
            chat_id=submission.user_id,
            text=_rejection_user_text(submission_id, reason),
            parse_mode=ParseMode.HTML,
        )
    except Exception:
        logger.warning(
            "Failed to notify submitter %s about rejection of %s",
            submission.user_id,
            submission_id,
            exc_info=True,
        )


async def commit_rejection(context, reviewer, submission_id: int, reason: str) -> str:
    """Apply a rejection. Returns forbidden, missing, handled, or ok."""
    if reviewer is None or not is_operator(reviewer.id):
        logger.warning(
            "Blocked non-admin rejection of submission %s by %s",
            submission_id,
            getattr(reviewer, "id", None),
        )
        return "forbidden"
    submission = db.get_submission(submission_id)
    if submission is None:
        clear_review_state(context.user_data, submission_id)
        return "missing"
    if not db.reject_submission(submission_id, reviewer.id, reason):
        clear_review_state(context.user_data, submission_id)
        return "handled"
    clear_review_state(context.user_data, submission_id)
    await _notify_rejection(context, submission, submission_id, reason)
    return "ok"


@admin_only
async def approve_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """通过投稿"""
    query = update.callback_query
    await query.answer()

    submission_id = int(query.data.replace("approve_", ""))
    state = review_state(context.user_data, submission_id)
    state["selected_tag_ids"] = []

    tags = db.get_all_tags()
    if tags:
        await query.edit_message_reply_markup(
            reply_markup=build_tags_keyboard(tags, submission_id, [])
        )
        return
    await confirm_and_publish(update, context, submission_id, [])


@admin_only
async def tag_select_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """选择标签"""
    query = update.callback_query
    await query.answer()

    _prefix, submission_raw, tag_raw = query.data.split("_")
    submission_id = int(submission_raw)
    tag_id = int(tag_raw)

    state = review_state(context.user_data, submission_id)
    selected = state["selected_tag_ids"]
    if tag_id in selected:
        selected.remove(tag_id)
    else:
        selected.append(tag_id)

    await query.edit_message_reply_markup(
        reply_markup=build_tags_keyboard(db.get_all_tags(), submission_id, selected)
    )


@admin_only
async def confirm_tags_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """确认标签并发布"""
    query = update.callback_query
    await query.answer()

    submission_id = int(query.data.replace("confirm_tags_", ""))
    selected = list(review_state(context.user_data, submission_id).get("selected_tag_ids", []))
    await confirm_and_publish(update, context, submission_id, selected)


async def _publish_to_channel(context, submission, tags: list[str]) -> int | None:
    html_text, plain_text = build_publish_bodies(
        submission.text_content,
        submission.text_html,
        tags,
        config.get_footer_text(),
    )
    has_media = bool(submission.media_ids) and submission.media_ids not in ("null", "[]")
    limit = MAX_CAPTION_LENGTH if has_media else MAX_TEXT_LENGTH
    extra = None
    if not html_text:
        primary = None
    elif len(html_text) <= limit:
        primary = html_text
    else:
        head, rest = clip_text(plain_text, limit)
        primary = escape_html(head)
        extra = escape_html(rest) if rest else None
        logger.info("Clipped channel text for submission %s to %s characters", submission.id, limit)

    if has_media:
        media_ids = json.loads(submission.media_ids)
        if submission.media_types:
            media_types = json.loads(submission.media_types)
        else:
            media_types = ["photo"] * len(media_ids)
        if not media_ids:
            raise RuntimeError("投稿没有可发布的媒体")
        messages = await send_media_items(
            context.bot,
            config.channel_id,
            media_ids,
            media_types,
            caption=primary,
            parse_mode=ParseMode.HTML if primary else None,
        )
        published_id = messages[0].message_id if messages else None
    else:
        message = await context.bot.send_message(
            chat_id=config.channel_id,
            text=primary or "（空投稿）",
            parse_mode=ParseMode.HTML,
        )
        published_id = message.message_id

    if extra:
        try:
            await context.bot.send_message(
                chat_id=config.channel_id,
                text=extra,
                parse_mode=ParseMode.HTML,
            )
        except Exception:
            logger.exception(
                "Submission %s was published but the overflow text was not",
                submission.id,
            )
    return published_id


async def confirm_and_publish(update: Update, context: ContextTypes.DEFAULT_TYPE,
                              submission_id: int, tag_ids: list):
    """确认并发布到频道。调用前会再次确认管理员身份。"""
    query = update.callback_query
    user = update.effective_user

    if user is None or not is_operator(user.id):
        logger.warning(
            "Blocked non-admin publish of submission %s by %s",
            submission_id,
            getattr(user, "id", None),
        )
        await _answer_denied(query)
        return

    if query is None:
        logger.warning("confirm_and_publish called without a callback query")
        return

    submission = db.get_submission(submission_id)
    if submission is None:
        clear_review_state(context.user_data, submission_id)
        await query.edit_message_text("❌ 投稿不存在")
        return

    if not config.channel_id:
        await query.edit_message_text("❌ 未配置 channel_id，无法发布")
        return

    if not db.claim_submission(submission_id, user.id):
        clear_review_state(context.user_data, submission_id)
        await query.edit_message_text("❌ 该投稿已被处理")
        return

    tags = _tag_names(tag_ids)
    try:
        published_msg_id = await _publish_to_channel(context, submission, tags)
    except Exception as exc:
        logger.exception("Publishing submission %s failed", submission_id)
        db.release_submission_claim(submission_id)
        await query.edit_message_text(
            f"❌ 发布失败: {escape_html(str(exc))}",
            parse_mode=ParseMode.HTML,
        )
        return

    if published_msg_id is None:
        logger.error("Channel publish of submission %s produced no message", submission_id)
        db.release_submission_claim(submission_id)
        await query.edit_message_text("❌ 发布失败: 频道没有返回消息")
        return

    if not db.finalize_approval(submission_id, user.id, tags, published_msg_id):
        logger.error(
            "Published submission %s as message %s but failed to mark it approved",
            submission_id,
            published_msg_id,
        )
        await query.edit_message_text("❌ 已发布到频道，但写入审核结果失败，请检查日志")
        return

    if tags:
        db.increment_tag_usage(tags)
    clear_review_state(context.user_data, submission_id)

    await query.edit_message_text(
        (
            f"✅ <b>投稿 #{submission_id} 已通过并发布</b>\n\n"
            f"🏷️ 标签: {escape_html(', '.join(tags) if tags else '无')}\n"
            f"📢 已发布到: {escape_html(config.channel_id)}"
        ),
        parse_mode=ParseMode.HTML,
    )
    try:
        await context.bot.send_message(
            chat_id=submission.user_id,
            text=(
                f"🎉 <b>恭喜！您的投稿 #{submission_id} 已通过审核！</b>\n\n"
                f"您的投稿已发布到 {escape_html(config.channel_name)} 频道。\n"
                "感谢您的投稿！"
            ),
            parse_mode=ParseMode.HTML,
        )
    except Exception:
        logger.warning(
            "Failed to notify submitter %s about approval of %s",
            submission.user_id,
            submission_id,
            exc_info=True,
        )


@admin_only
async def reject_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """拒绝投稿 - 显示拒绝理由"""
    query = update.callback_query
    await query.answer()

    submission_id = int(query.data.replace("reject_", ""))
    reasons = db.get_all_reject_reasons()
    if not reasons:
        for text in config.default_reject_reasons:
            db.add_reject_reason(text)
        reasons = db.get_all_reject_reasons()

    await query.edit_message_reply_markup(
        reply_markup=build_reject_reasons_keyboard(reasons, submission_id)
    )


@admin_only
async def reject_reason_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """选择拒绝理由"""
    query = update.callback_query
    _prefix, submission_raw, reason_raw = query.data.split("_")
    submission_id = int(submission_raw)
    reason_id = int(reason_raw)

    reason = db.get_reject_reason(reason_id)
    if reason is None:
        await query.answer("理由不存在", show_alert=True)
        return

    await query.answer()
    if await do_reject(update, context, submission_id, reason.text):
        db.increment_reason_usage(reason.id)


@admin_only
async def custom_reason_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """自定义拒绝理由"""
    query = update.callback_query
    await query.answer()

    submission_id = int(query.data.replace("custom_reason_", ""))
    set_pending_input(context.user_data, "reject_reason", submission_id=submission_id)
    await query.edit_message_text(
        f"📝 请输入拒绝理由（针对投稿 #{submission_id}）：\n\n"
        "直接发送文字即可，或发送 /cancel 取消"
    )


async def handle_custom_reason_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """处理自定义拒绝理由输入"""
    pending = peek_pending_input(context.user_data, "reject_reason")
    if not pending:
        return False

    user = update.effective_user
    message = update.message
    if user is None or message is None or not is_operator(user.id):
        return False

    if not message.text or not message.text.strip():
        await message.reply_text("请发送文字理由，或发送 /cancel 取消")
        return True

    pop_pending_input(context.user_data, "reject_reason")
    submission_id = int(pending["submission_id"])
    reason_text = message.text.strip()
    result = await commit_rejection(context, user, submission_id, reason_text)
    if result == "forbidden":
        return False
    if result != "ok":
        await message.reply_text("❌ 投稿不存在或已被处理")
        return True

    await message.reply_text(
        _rejection_admin_text(submission_id, reason_text),
        parse_mode=ParseMode.HTML,
    )
    return True


async def do_reject(update: Update, context: ContextTypes.DEFAULT_TYPE,
                    submission_id: int, reason: str):
    """执行拒绝操作，并再次确认调用者是管理员。"""
    query = update.callback_query
    result = await commit_rejection(context, update.effective_user, submission_id, reason)
    if result == "forbidden":
        await _answer_denied(query)
        return False
    if query is None:
        return result == "ok"
    if result != "ok":
        await query.edit_message_text("❌ 投稿不存在或已被处理")
        return False
    await query.edit_message_text(
        _rejection_admin_text(submission_id, reason),
        parse_mode=ParseMode.HTML,
    )
    return True


@admin_only
async def back_to_review_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """返回审核界面"""
    query = update.callback_query
    await query.answer()

    submission_id = int(query.data.replace("back_review_", ""))
    state = review_state(context.user_data, submission_id)
    state["selected_tag_ids"] = []
    await query.edit_message_reply_markup(reply_markup=build_review_keyboard(submission_id))
