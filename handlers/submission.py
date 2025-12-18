#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
投稿处理器
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
    build_main_keyboard, build_submit_options_keyboard,
    build_submitting_keyboard, build_back_keyboard,
    build_review_keyboard
)
from utils.helpers import format_user_link, truncate_text


# 用户状态常量
STATE_IDLE = 'idle'
STATE_CHOOSING_TYPE = 'choosing_type'
STATE_SUBMITTING = 'submitting'


async def start_submit_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """开始投稿 - 选择投稿类型"""
    query = update.callback_query
    await query.answer()
    
    user = update.effective_user
    
    # 检查用户是否被封禁
    if db.is_user_banned(user.id):
        await query.edit_message_text(
            "❌ 您的账号已被封禁，无法投稿\n\n如有疑问请联系管理员"
        )
        return
    
    # 显示投稿选项
    text = f"""📝 *投稿须知*

{config.submission_rules}

请选择投稿方式：
• *实名投稿*：管理员可看到您的信息
• *匿名投稿*：完全匿名

_(文章内容直接发送至机器人即可)_
"""
    
    await query.edit_message_text(
        text,
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=build_submit_options_keyboard()
    )


async def submit_type_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """选择投稿类型（实名/匿名）"""
    query = update.callback_query
    await query.answer()
    
    user = update.effective_user
    is_anonymous = query.data == "submit_anonymous"
    
    # 设置用户状态
    context.user_data['state'] = STATE_SUBMITTING
    context.user_data['is_anonymous'] = is_anonymous
    context.user_data['media_group'] = []
    context.user_data['text_content'] = None
    context.user_data['media_group_id'] = None
    
    submit_type = "🕶️ 匿名投稿" if is_anonymous else "👤 实名投稿"
    
    text = f"""✅ 已选择：*{submit_type}*

请发送您要投稿的内容：
• 支持文字、图片、视频、音频
• 支持多图投稿（最多10张）
• 可以同时发送图文
• 发送完成后点击「完成投稿」

⚠️ 发送 /cancel 可取消投稿
"""
    
    await query.edit_message_text(
        text,
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=build_submitting_keyboard()
    )


async def handle_submission_content(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """处理用户发送的投稿内容"""
    user = update.effective_user
    message = update.message
    
    # 检查用户是否在投稿状态
    if context.user_data.get('state') != STATE_SUBMITTING:
        await message.reply_text(
            "请先点击「📝 我要投稿」开始投稿\n\n发送 /start 返回主菜单",
            reply_markup=build_back_keyboard()
        )
        return
    
    # 检查是否是媒体组的一部分
    if message.media_group_id:
        # 处理媒体组
        if context.user_data.get('media_group_id') != message.media_group_id:
            context.user_data['media_group_id'] = message.media_group_id
            context.user_data['media_group'] = []
        
        # 添加到媒体组
        media_item = extract_media_info(message)
        if media_item:
            context.user_data['media_group'].append(media_item)
        
        # 保存文字内容（如果有）- 使用 HTML 格式保留样式
        if message.caption:
            context.user_data['text_content'] = message.caption
            context.user_data['text_html'] = message.caption_html if message.caption_html else message.caption
        
        return  # 等待更多媒体组消息
    
    # 处理单独的消息
    media_item = extract_media_info(message)
    
    if media_item:
        # 添加到媒体列表
        if 'media_group' not in context.user_data:
            context.user_data['media_group'] = []
        context.user_data['media_group'].append(media_item)
        
        # 保存文字内容 - 使用 HTML 格式保留样式
        if message.caption:
            context.user_data['text_content'] = message.caption
            context.user_data['text_html'] = message.caption_html if message.caption_html else message.caption
        
        count = len(context.user_data['media_group'])
        await message.reply_text(
            f"✅ 已收到 {count} 个媒体文件\n\n继续发送更多内容，或点击「完成投稿」",
            reply_markup=build_submitting_keyboard()
        )
    elif message.text:
        # 纯文字内容 - 使用 HTML 格式保留样式
        context.user_data['text_content'] = message.text
        context.user_data['text_html'] = message.text_html if message.text_html else message.text
        await message.reply_text(
            "✅ 已收到文字内容\n\n可以继续发送图片/视频，或点击「完成投稿」",
            reply_markup=build_submitting_keyboard()
        )


def extract_media_info(message) -> dict:
    """提取消息中的媒体信息"""
    if message.photo:
        # 获取最高质量的图片
        photo = message.photo[-1]
        return {
            'type': 'photo',
            'file_id': photo.file_id
        }
    elif message.video:
        return {
            'type': 'video',
            'file_id': message.video.file_id
        }
    elif message.audio:
        return {
            'type': 'audio',
            'file_id': message.audio.file_id
        }
    elif message.document:
        return {
            'type': 'document',
            'file_id': message.document.file_id
        }
    return None


async def finish_submit_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """完成投稿"""
    query = update.callback_query
    await query.answer()
    
    user = update.effective_user
    
    # 检查是否有内容
    media_group = context.user_data.get('media_group', [])
    text_content = context.user_data.get('text_content')
    is_anonymous = context.user_data.get('is_anonymous', False)
    
    if not media_group and not text_content:
        await query.answer("❌ 请先发送投稿内容", show_alert=True)
        return
    
    # 确定内容类型
    if len(media_group) > 1:
        content_type = 'media_group'
    elif len(media_group) == 1:
        content_type = media_group[0]['type']
    else:
        content_type = 'text'
    
    # 提取媒体ID和类型
    media_ids = [m['file_id'] for m in media_group] if media_group else None
    media_types = [m['type'] for m in media_group] if media_group else None
    
    # 获取 HTML 格式的内容（保留富文本格式）
    text_html = context.user_data.get('text_html')
    
    # 创建投稿记录
    submission = db.create_submission(
        user_id=user.id,
        content_type=content_type,
        text_content=text_content,
        text_html=text_html,
        media_ids=media_ids,
        media_types=media_types,
        is_anonymous=is_anonymous
    )
    
    # 清除用户状态
    context.user_data.clear()
    
    # 通知用户
    await query.edit_message_text(
        f"✅ *投稿成功！*\n\n"
        f"投稿编号：`#{submission.id}`\n"
        f"投稿类型：{'匿名' if is_anonymous else '实名'}\n"
        f"状态：⏳ 等待审核\n\n"
        f"我们会尽快审核您的投稿，请耐心等待。",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=build_back_keyboard()
    )
    
    # 通知管理员
    await notify_admins_new_submission(context, submission, user)


async def notify_admins_new_submission(context: ContextTypes.DEFAULT_TYPE, 
                                       submission, user):
    """通知管理员有新投稿"""
    admin_ids = config.admin_ids
    
    if not admin_ids:
        return
    
    # 构建通知消息
    if submission.is_anonymous:
        user_info = "👤 *匿名用户*"
    else:
        user_link = format_user_link(user.id, user.full_name or "用户", user.username)
        user_info = f"👤 投稿者: {user_link}\n🆔 用户ID: `{user.id}`"
    
    text = (
        f"📨 *新投稿 #{submission.id}*\n\n"
        f"{user_info}\n"
        f"📁 类型: {submission.content_type}\n"
        f"⏰ 时间: 刚刚\n\n"
        f"{'─' * 20}\n\n"
    )
    
    if submission.text_content:
        text += f"📝 内容：\n{truncate_text(submission.text_content, 500)}\n\n"
    
    # 发送给所有管理员
    for admin_id in admin_ids:
        try:
            # 先发送信息和审核按钮
            await context.bot.send_message(
                chat_id=admin_id,
                text=text,
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=build_review_keyboard(submission.id)
            )
            
            # 发送媒体内容
            if submission.media_ids:
                media_ids = json.loads(submission.media_ids)
                media_types = json.loads(submission.media_types) if submission.media_types else ['photo'] * len(media_ids)
                
                if len(media_ids) == 1:
                    # 单个媒体
                    await send_single_media(context, admin_id, media_ids[0], 
                                           media_types[0], submission.text_content)
                else:
                    # 多个媒体
                    await send_media_group(context, admin_id, media_ids, 
                                          media_types, submission.text_content)
        except Exception as e:
            print(f"通知管理员 {admin_id} 失败: {e}")


async def send_single_media(context, chat_id, file_id, media_type, caption=None):
    """发送单个媒体"""
    if media_type == 'photo':
        await context.bot.send_photo(chat_id=chat_id, photo=file_id, caption=caption)
    elif media_type == 'video':
        await context.bot.send_video(chat_id=chat_id, video=file_id, caption=caption)
    elif media_type == 'audio':
        await context.bot.send_audio(chat_id=chat_id, audio=file_id, caption=caption)
    elif media_type == 'document':
        await context.bot.send_document(chat_id=chat_id, document=file_id, caption=caption)


async def send_media_group(context, chat_id, file_ids, media_types, caption=None):
    """发送媒体组"""
    media = []
    for i, (file_id, media_type) in enumerate(zip(file_ids, media_types)):
        # 只在第一个媒体上添加标题
        cap = caption if i == 0 else None
        
        if media_type == 'photo':
            media.append(InputMediaPhoto(media=file_id, caption=cap))
        elif media_type == 'video':
            media.append(InputMediaVideo(media=file_id, caption=cap))
    
    if media:
        await context.bot.send_media_group(chat_id=chat_id, media=media)


async def cancel_submit_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """取消投稿"""
    query = update.callback_query
    await query.answer("已取消投稿")
    
    context.user_data.clear()
    
    # 返回主菜单
    await back_to_main_callback(update, context)


async def back_to_main_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """返回主菜单"""
    query = update.callback_query
    if query:
        await query.answer()
    
    user = update.effective_user
    context.user_data.clear()
    
    # 构建欢迎消息
    bot_info = config.bot_info
    welcome_text = f"🤖 *机器人介绍：*\n\nWelcome to {bot_info.get('name', '投稿机器人')}"
    
    nav_text = "\n"
    for link in config.navigation_links:
        if link.get("enabled", True) and link.get("username"):
            nav_text += f"\n{link['name']}: @{link['username']}"
        elif not link.get("enabled", True):
            placeholder = link.get("placeholder_text", link["name"] + "（筹建中）")
            nav_text += f"\n{placeholder}"
    
    full_message = welcome_text + nav_text
    
    keyboard = build_main_keyboard(
        config.navigation_links,
        config.channel_id,
        config.customer_service
    )
    
    if query:
        await query.edit_message_text(
            full_message,
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=keyboard
        )


async def placeholder_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """占位按钮点击"""
    query = update.callback_query
    await query.answer("该功能正在筹建中，敬请期待！", show_alert=True)


async def submit_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """处理 /submit 命令"""
    user = update.effective_user
    
    # 检查用户是否被封禁
    if db.is_user_banned(user.id):
        await update.message.reply_text(
            "❌ 您的账号已被封禁，无法投稿\n\n如有疑问请联系管理员"
        )
        return
    
    text = f"""📝 *投稿须知*

{config.submission_rules}

请选择投稿方式：
• *实名投稿*：管理员可看到您的信息
• *匿名投稿*：完全匿名
"""
    
    await update.message.reply_text(
        text,
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=build_submit_options_keyboard()
    )


async def my_stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """查看我的投稿统计"""
    user = update.effective_user
    stats = db.get_user_stats(user.id)
    
    if not stats:
        await update.message.reply_text("📊 您还没有投稿记录")
        return
    
    from utils.helpers import get_level_title, get_level_emoji
    
    level = stats['level']
    level_title = get_level_title(level)
    level_emoji = get_level_emoji(level)
    
    text = f"""📊 *我的投稿统计*

{level_emoji} *等级：* Lv.{level} {level_title}

📝 *总投稿：* {stats['total']} 篇
✅ *已通过：* {stats['approved']} 篇
❌ *已拒绝：* {stats['rejected']} 篇
⏳ *待审核：* {stats['pending']} 篇

📈 *通过率：* {stats['approval_rate']}%
"""
    await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)
