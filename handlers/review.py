#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
审核处理器
"""

import json
from telegram import Update, InputMediaPhoto, InputMediaVideo
from telegram.ext import ContextTypes
from telegram.constants import ParseMode

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from config import config
from database.db import db
from utils.keyboard import (
    build_review_keyboard, build_tags_keyboard,
    build_reject_reasons_keyboard, build_confirm_publish_keyboard
)
from utils.helpers import format_submission_info, format_user_link


async def approve_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """通过投稿"""
    query = update.callback_query
    user = update.effective_user
    
    # 检查权限
    if not config.is_config_admin(user.id) and not db.is_admin(user.id):
        await query.answer("❌ 您没有权限执行此操作", show_alert=True)
        return
    
    await query.answer()
    
    # 解析投稿ID
    submission_id = int(query.data.replace("approve_", ""))
    
    # 存储投稿ID，等待选择标签
    context.user_data['reviewing_submission_id'] = submission_id
    context.user_data['selected_tags'] = []
    
    # 显示标签选择
    tags = db.get_all_tags()
    if tags:
        await query.edit_message_reply_markup(
            reply_markup=build_tags_keyboard(tags, submission_id, [])
        )
    else:
        # 没有标签，直接发布
        await confirm_and_publish(update, context, submission_id, [])


async def tag_select_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """选择标签"""
    query = update.callback_query
    await query.answer()
    
    # 解析数据：tag_submissionId_tagName
    parts = query.data.split("_", 2)
    submission_id = int(parts[1])
    tag_name = parts[2]
    
    # 切换标签选中状态
    selected = context.user_data.get('selected_tags', [])
    if tag_name in selected:
        selected.remove(tag_name)
    else:
        selected.append(tag_name)
    context.user_data['selected_tags'] = selected
    
    # 更新键盘显示
    tags = db.get_all_tags()
    await query.edit_message_reply_markup(
        reply_markup=build_tags_keyboard(tags, submission_id, selected)
    )


async def confirm_tags_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """确认标签并发布"""
    query = update.callback_query
    await query.answer()
    
    # 解析投稿ID
    submission_id = int(query.data.replace("confirm_tags_", ""))
    selected_tags = context.user_data.get('selected_tags', [])
    
    await confirm_and_publish(update, context, submission_id, selected_tags)


async def confirm_and_publish(update: Update, context: ContextTypes.DEFAULT_TYPE,
                              submission_id: int, tags: list):
    """确认并发布到频道"""
    query = update.callback_query
    user = update.effective_user
    
    # 获取投稿信息
    submission = db.get_submission(submission_id)
    if not submission:
        await query.edit_message_text("❌ 投稿不存在")
        return
    
    if submission.status != 'pending':
        await query.edit_message_text("❌ 该投稿已被处理")
        return
    
    # 发布到频道
    channel_id = config.channel_id
    published_msg_id = None
    
    try:
        # 构建发布内容（优先使用HTML格式以保留富文本样式）
        publish_text = ""
        
        # 构建标签（格式：#标签：内容）
        if tags:
            tag_str = " ".join([f"#{tag}" for tag in tags])
            publish_text = f"{tag_str}："
        
        # 添加投稿内容 - 优先使用HTML格式
        content_text = submission.text_html if submission.text_html else submission.text_content
        if content_text:
            publish_text += content_text
        
        # 添加尾部信息
        footer = config.get_footer_text()
        if footer:
            publish_text += f"\n\n{footer}"
        
        # 发送到频道（使用 HTML 模式以支持富文本）
        if submission.media_ids:
            media_ids = json.loads(submission.media_ids)
            media_types = json.loads(submission.media_types) if submission.media_types else ['photo'] * len(media_ids)
            
            if len(media_ids) == 1:
                # 单个媒体
                msg = await send_single_media_to_channel(
                    context, channel_id, media_ids[0], 
                    media_types[0], publish_text
                )
                published_msg_id = msg.message_id if msg else None
            else:
                # 多个媒体
                msgs = await send_media_group_to_channel(
                    context, channel_id, media_ids, 
                    media_types, publish_text
                )
                published_msg_id = msgs[0].message_id if msgs else None
        else:
            # 纯文字
            msg = await context.bot.send_message(
                chat_id=channel_id,
                text=publish_text,
                parse_mode=ParseMode.HTML
            )
            published_msg_id = msg.message_id
        
        # 更新数据库
        db.approve_submission(submission_id, user.id, tags, published_msg_id)
        
        # 增加标签使用次数
        if tags:
            db.increment_tag_usage(tags)
        
        # 通知管理员
        await query.edit_message_text(
            f"✅ *投稿 #{submission_id} 已通过并发布*\n\n"
            f"🏷️ 标签: {', '.join(tags) if tags else '无'}\n"
            f"📢 已发布到: {channel_id}",
            parse_mode=ParseMode.MARKDOWN
        )
        
        # 通知投稿者
        try:
            submitter = db.get_user(submission.user_id)
            await context.bot.send_message(
                chat_id=submission.user_id,
                text=f"🎉 *恭喜！您的投稿 #{submission_id} 已通过审核！*\n\n"
                     f"您的投稿已发布到 {config.channel_name} 频道。\n"
                     f"感谢您的投稿！",
                parse_mode=ParseMode.MARKDOWN
            )
        except:
            pass
    
    except Exception as e:
        await query.edit_message_text(f"❌ 发布失败: {str(e)}")
    
    # 清除用户状态
    context.user_data.clear()


async def send_single_media_to_channel(context, channel_id, file_id, 
                                       media_type, caption=None):
    """发送单个媒体到频道"""
    if media_type == 'photo':
        return await context.bot.send_photo(chat_id=channel_id, photo=file_id, caption=caption, parse_mode=ParseMode.HTML)
    elif media_type == 'video':
        return await context.bot.send_video(chat_id=channel_id, video=file_id, caption=caption, parse_mode=ParseMode.HTML)
    elif media_type == 'audio':
        return await context.bot.send_audio(chat_id=channel_id, audio=file_id, caption=caption, parse_mode=ParseMode.HTML)
    elif media_type == 'document':
        return await context.bot.send_document(chat_id=channel_id, document=file_id, caption=caption, parse_mode=ParseMode.HTML)
    return None


async def send_media_group_to_channel(context, channel_id, file_ids, 
                                      media_types, caption=None):
    """发送媒体组到频道"""
    media = []
    for i, (file_id, media_type) in enumerate(zip(file_ids, media_types)):
        cap = caption if i == 0 else None
        # 使用 HTML 解析模式以支持富文本格式
        if media_type == 'photo':
            media.append(InputMediaPhoto(media=file_id, caption=cap, parse_mode=ParseMode.HTML if cap else None))
        elif media_type == 'video':
            media.append(InputMediaVideo(media=file_id, caption=cap, parse_mode=ParseMode.HTML if cap else None))
    
    if media:
        return await context.bot.send_media_group(chat_id=channel_id, media=media)
    return None


async def reject_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """拒绝投稿 - 显示拒绝理由"""
    query = update.callback_query
    user = update.effective_user
    
    # 检查权限
    if not config.is_config_admin(user.id) and not db.is_admin(user.id):
        await query.answer("❌ 您没有权限执行此操作", show_alert=True)
        return
    
    await query.answer()
    
    # 解析投稿ID
    submission_id = int(query.data.replace("reject_", ""))
    
    # 获取拒绝理由列表
    reasons = db.get_all_reject_reasons()
    default_reasons = config.default_reject_reasons
    
    # 如果数据库没有理由，使用默认理由
    if not reasons:
        for text in default_reasons:
            db.add_reject_reason(text)
        reasons = db.get_all_reject_reasons()
    
    await query.edit_message_reply_markup(
        reply_markup=build_reject_reasons_keyboard(reasons, submission_id)
    )


async def reject_reason_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """选择拒绝理由"""
    query = update.callback_query
    await query.answer()
    
    # 解析数据：reason_submissionId_reasonIndex
    parts = query.data.split("_")
    submission_id = int(parts[1])
    reason_index = int(parts[2])
    
    # 获取理由
    reasons = db.get_all_reject_reasons()
    if reason_index >= len(reasons):
        await query.answer("理由不存在", show_alert=True)
        return
    
    reason = reasons[reason_index]
    reason_text = reason.text if hasattr(reason, 'text') else reason
    
    # 执行拒绝
    await do_reject(update, context, submission_id, reason_text)
    
    # 增加理由使用次数
    if hasattr(reason, 'id'):
        db.increment_reason_usage(reason.id)


async def custom_reason_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """自定义拒绝理由"""
    query = update.callback_query
    await query.answer()
    
    # 解析投稿ID
    submission_id = int(query.data.replace("custom_reason_", ""))
    
    # 存储状态，等待用户输入
    context.user_data['awaiting_custom_reason'] = submission_id
    
    await query.edit_message_text(
        f"📝 请输入拒绝理由（针对投稿 #{submission_id}）：\n\n"
        f"直接发送文字即可，或发送 /cancel 取消"
    )


async def handle_custom_reason_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """处理自定义拒绝理由输入"""
    user = update.effective_user
    message = update.message
    
    submission_id = context.user_data.get('awaiting_custom_reason')
    if not submission_id:
        return False  # 不是在输入自定义理由
    
    # 检查权限
    if not config.is_config_admin(user.id) and not db.is_admin(user.id):
        return False
    
    reason_text = message.text
    
    # 清除状态
    del context.user_data['awaiting_custom_reason']
    
    # 执行拒绝
    submission = db.get_submission(submission_id)
    if not submission or submission.status != 'pending':
        await message.reply_text("❌ 投稿不存在或已被处理")
        return True
    
    db.reject_submission(submission_id, user.id, reason_text)
    
    await message.reply_text(
        f"❌ *投稿 #{submission_id} 已拒绝*\n\n"
        f"📝 理由: {reason_text}",
        parse_mode=ParseMode.MARKDOWN
    )
    
    # 通知投稿者
    try:
        await context.bot.send_message(
            chat_id=submission.user_id,
            text=f"😔 *您的投稿 #{submission_id} 未通过审核*\n\n"
                 f"📝 原因: {reason_text}\n\n"
                 f"您可以根据反馈修改后重新投稿。",
            parse_mode=ParseMode.MARKDOWN
        )
    except:
        pass
    
    return True


async def do_reject(update: Update, context: ContextTypes.DEFAULT_TYPE,
                    submission_id: int, reason: str):
    """执行拒绝操作"""
    query = update.callback_query
    user = update.effective_user
    
    # 获取投稿
    submission = db.get_submission(submission_id)
    if not submission:
        await query.edit_message_text("❌ 投稿不存在")
        return
    
    if submission.status != 'pending':
        await query.edit_message_text("❌ 该投稿已被处理")
        return
    
    # 更新数据库
    db.reject_submission(submission_id, user.id, reason)
    
    # 通知管理员
    await query.edit_message_text(
        f"❌ *投稿 #{submission_id} 已拒绝*\n\n"
        f"📝 理由: {reason}",
        parse_mode=ParseMode.MARKDOWN
    )
    
    # 通知投稿者
    try:
        await context.bot.send_message(
            chat_id=submission.user_id,
            text=f"😔 *您的投稿 #{submission_id} 未通过审核*\n\n"
                 f"📝 原因: {reason}\n\n"
                 f"您可以根据反馈修改后重新投稿。",
            parse_mode=ParseMode.MARKDOWN
        )
    except:
        pass


async def back_to_review_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """返回审核界面"""
    query = update.callback_query
    await query.answer()
    
    # 解析投稿ID
    submission_id = int(query.data.replace("back_review_", ""))
    
    # 清除选中的标签
    context.user_data['selected_tags'] = []
    
    # 显示审核按钮
    await query.edit_message_reply_markup(
        reply_markup=build_review_keyboard(submission_id)
    )
