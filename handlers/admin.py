#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
管理员命令处理器
"""

from telegram import Update
from telegram.ext import ContextTypes
from telegram.constants import ParseMode

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from config import config
from database.db import db
from utils.keyboard import build_admin_user_keyboard, build_review_keyboard
from utils.helpers import format_user_link, format_datetime


def admin_only(func):
    """管理员权限装饰器"""
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        user = update.effective_user
        if not config.is_config_admin(user.id) and not db.is_admin(user.id):
            await update.message.reply_text("❌ 您没有权限执行此操作")
            return
        return await func(update, context)
    return wrapper


@admin_only
async def queue_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """查看待审核队列"""
    pending_count = db.get_pending_count()
    pending_submissions = db.get_pending_submissions(limit=5)
    
    if not pending_submissions:
        await update.message.reply_text("✅ 当前没有待审核的投稿")
        return
    
    text = f"📋 *待审核队列* ({pending_count} 篇)\n\n"
    
    for sub in pending_submissions:
        user = db.get_user(sub.user_id)
        user_info = "匿名" if sub.is_anonymous else (user.full_name if user else f"ID:{sub.user_id}")
        text += f"• #{sub.id} - {user_info} - {sub.content_type}\n"
    
    if pending_count > 5:
        text += f"\n... 还有 {pending_count - 5} 篇待审核"
    
    text += "\n\n💡 点击下方按钮审核第一篇"
    
    await update.message.reply_text(
        text,
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=build_review_keyboard(pending_submissions[0].id)
    )


@admin_only
async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """查看总体统计"""
    stats = db.get_overall_stats()
    
    # 计算通过率
    if stats['total_submissions'] > 0:
        approval_rate = round(stats['approved'] / stats['total_submissions'] * 100, 1)
    else:
        approval_rate = 0
    
    text = f"""📊 *系统统计*

👥 *总用户数：* {stats['total_users']}
📝 *总投稿数：* {stats['total_submissions']}

*投稿状态分布：*
⏳ 待审核: {stats['pending']}
✅ 已通过: {stats['approved']}
❌ 已拒绝: {stats['rejected']}

📈 *通过率：* {approval_rate}%
"""
    
    await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)


@admin_only
async def ban_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """封禁用户"""
    args = context.args
    
    if not args:
        await update.message.reply_text(
            "用法: `/ban <用户ID> [理由]`\n"
            "例如: `/ban 123456789 违规投稿`",
            parse_mode=ParseMode.MARKDOWN
        )
        return
    
    try:
        target_id = int(args[0])
    except ValueError:
        await update.message.reply_text("❌ 无效的用户ID")
        return
    
    reason = " ".join(args[1:]) if len(args) > 1 else None
    
    # 不能封禁管理员
    if config.is_config_admin(target_id):
        await update.message.reply_text("❌ 不能封禁管理员")
        return
    
    user = update.effective_user
    
    if db.ban_user(target_id, user.id, reason):
        target = db.get_user(target_id)
        target_name = target.full_name if target else f"ID:{target_id}"
        
        await update.message.reply_text(
            f"🔒 *用户已封禁*\n\n"
            f"👤 用户: {target_name}\n"
            f"🆔 ID: `{target_id}`\n"
            f"📝 理由: {reason or '无'}",
            parse_mode=ParseMode.MARKDOWN
        )
        
        # 通知被封禁用户
        try:
            await context.bot.send_message(
                chat_id=target_id,
                text=f"⚠️ *您的账号已被封禁*\n\n"
                     f"📝 原因: {reason or '未说明'}\n\n"
                     f"如有疑问请联系管理员",
                parse_mode=ParseMode.MARKDOWN
            )
        except:
            pass
    else:
        await update.message.reply_text("❌ 封禁失败，用户可能不存在")


@admin_only
async def unban_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """解封用户"""
    args = context.args
    
    if not args:
        await update.message.reply_text(
            "用法: `/unban <用户ID>`\n"
            "例如: `/unban 123456789`",
            parse_mode=ParseMode.MARKDOWN
        )
        return
    
    try:
        target_id = int(args[0])
    except ValueError:
        await update.message.reply_text("❌ 无效的用户ID")
        return
    
    user = update.effective_user
    
    if db.unban_user(target_id, user.id):
        target = db.get_user(target_id)
        target_name = target.full_name if target else f"ID:{target_id}"
        
        await update.message.reply_text(
            f"🔓 *用户已解封*\n\n"
            f"👤 用户: {target_name}\n"
            f"🆔 ID: `{target_id}`",
            parse_mode=ParseMode.MARKDOWN
        )
        
        # 通知被解封用户
        try:
            await context.bot.send_message(
                chat_id=target_id,
                text="🎉 *您的账号已被解封*\n\n现在可以继续使用机器人了。",
                parse_mode=ParseMode.MARKDOWN
            )
        except:
            pass
    else:
        await update.message.reply_text("❌ 解封失败，用户可能不存在")


@admin_only
async def add_tag_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """添加标签"""
    args = context.args
    
    if not args:
        await update.message.reply_text(
            "用法: `/addtag <名称> [emoji]`\n"
            "例如: `/addtag 求助 🆘`",
            parse_mode=ParseMode.MARKDOWN
        )
        return
    
    name = args[0]
    emoji = args[1] if len(args) > 1 else None
    
    tag = db.add_tag(name, emoji)
    if tag:
        await update.message.reply_text(
            f"✅ *标签已添加*\n\n"
            f"🏷️ 名称: {name}\n"
            f"😀 Emoji: {emoji or '无'}",
            parse_mode=ParseMode.MARKDOWN
        )
    else:
        await update.message.reply_text("❌ 标签已存在")


@admin_only
async def add_reason_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """添加拒绝理由"""
    args = context.args
    
    if not args:
        await update.message.reply_text(
            "用法: `/addreason <理由文本>`\n"
            "例如: `/addreason 内容与频道主题不符`",
            parse_mode=ParseMode.MARKDOWN
        )
        return
    
    text = " ".join(args)
    reason = db.add_reject_reason(text)
    
    await update.message.reply_text(
        f"✅ *拒绝理由已添加*\n\n"
        f"📝 理由: {text}",
        parse_mode=ParseMode.MARKDOWN
    )


@admin_only
async def user_info_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """查看用户信息"""
    args = context.args
    
    if not args:
        await update.message.reply_text(
            "用法: `/userinfo <用户ID>`",
            parse_mode=ParseMode.MARKDOWN
        )
        return
    
    try:
        target_id = int(args[0])
    except ValueError:
        await update.message.reply_text("❌ 无效的用户ID")
        return
    
    user = db.get_user(target_id)
    if not user:
        await update.message.reply_text("❌ 用户不存在")
        return
    
    stats = db.get_user_stats(target_id)
    
    from utils.helpers import get_level_title, get_level_emoji
    level = stats['level']
    
    text = f"""👤 *用户信息*

🆔 ID: `{user.id}`
📛 用户名: @{user.username or '无'}
📝 昵称: {user.full_name or '无'}
📅 注册时间: {format_datetime(user.created_at)}

{get_level_emoji(level)} *等级：* Lv.{level} {get_level_title(level)}
🔐 *角色：* {user.role}
🚫 *封禁状态：* {'是' if user.is_banned else '否'}

*投稿统计：*
📝 总投稿: {stats['total']}
✅ 已通过: {stats['approved']}
❌ 已拒绝: {stats['rejected']}
📈 通过率: {stats['approval_rate']}%
"""
    
    if user.is_banned:
        text += f"\n📝 *封禁原因：* {user.ban_reason or '未说明'}"
    
    await update.message.reply_text(
        text,
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=build_admin_user_keyboard(target_id, user.is_banned)
    )


async def ban_user_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """通过按钮封禁用户"""
    query = update.callback_query
    user = update.effective_user
    
    if not config.is_config_admin(user.id) and not db.is_admin(user.id):
        await query.answer("❌ 您没有权限", show_alert=True)
        return
    
    await query.answer()
    
    target_id = int(query.data.replace("ban_", ""))
    
    # 存储状态，等待输入封禁理由
    context.user_data['banning_user'] = target_id
    
    await query.edit_message_text(
        f"请输入封禁用户 `{target_id}` 的理由：\n\n"
        f"直接发送文字，或发送 /cancel 取消",
        parse_mode=ParseMode.MARKDOWN
    )


async def unban_user_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """通过按钮解封用户"""
    query = update.callback_query
    user = update.effective_user
    
    if not config.is_config_admin(user.id) and not db.is_admin(user.id):
        await query.answer("❌ 您没有权限", show_alert=True)
        return
    
    await query.answer()
    
    target_id = int(query.data.replace("unban_", ""))
    
    if db.unban_user(target_id, user.id):
        target = db.get_user(target_id)
        target_name = target.full_name if target else f"ID:{target_id}"
        
        await query.edit_message_text(
            f"🔓 *用户已解封*\n\n"
            f"👤 用户: {target_name}\n"
            f"🆔 ID: `{target_id}`",
            parse_mode=ParseMode.MARKDOWN
        )
    else:
        await query.edit_message_text("❌ 解封失败")


async def handle_ban_reason_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """处理封禁理由输入"""
    user = update.effective_user
    message = update.message
    
    target_id = context.user_data.get('banning_user')
    if not target_id:
        return False
    
    if not config.is_config_admin(user.id) and not db.is_admin(user.id):
        return False
    
    reason = message.text
    del context.user_data['banning_user']
    
    if db.ban_user(target_id, user.id, reason):
        target = db.get_user(target_id)
        target_name = target.full_name if target else f"ID:{target_id}"
        
        await message.reply_text(
            f"🔒 *用户已封禁*\n\n"
            f"👤 用户: {target_name}\n"
            f"🆔 ID: `{target_id}`\n"
            f"📝 理由: {reason}",
            parse_mode=ParseMode.MARKDOWN
        )
        
        # 通知被封禁用户
        try:
            await context.bot.send_message(
                chat_id=target_id,
                text=f"⚠️ *您的账号已被封禁*\n\n"
                     f"📝 原因: {reason}\n\n"
                     f"如有疑问请联系管理员",
                parse_mode=ParseMode.MARKDOWN
            )
        except:
            pass
    else:
        await message.reply_text("❌ 封禁失败")
    
    return True
