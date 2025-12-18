#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Telegram 专业级投稿机器人
功能：导航 + 投稿 + 审核 + 用户管理
"""

import logging
from pathlib import Path
from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
)

# 设置路径
import sys
sys.path.insert(0, str(Path(__file__).parent))

# 导入配置和数据库
from config import config
from database.db import db

# 导入处理器
from handlers.start import start_command, help_command, cancel_command
from handlers.submission import (
    start_submit_callback, submit_type_callback,
    handle_submission_content, finish_submit_callback,
    cancel_submit_callback, back_to_main_callback,
    placeholder_callback, submit_command, my_stats_command
)
from handlers.review import (
    approve_callback, reject_callback,
    tag_select_callback, confirm_tags_callback,
    reject_reason_callback, custom_reason_callback,
    back_to_review_callback, handle_custom_reason_input
)
from handlers.admin import (
    queue_command, stats_command, ban_command, unban_command,
    add_tag_command, add_reason_command, user_info_command,
    ban_user_callback, unban_user_callback, handle_ban_reason_input
)

# 日志配置
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)


async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """统一消息处理器"""
    # 优先处理管理员输入
    if await handle_custom_reason_input(update, context):
        return
    
    if await handle_ban_reason_input(update, context):
        return
    
    # 处理投稿内容
    await handle_submission_content(update, context)


def main():
    """主函数"""
    # 检查配置
    if config.bot_token == "YOUR_BOT_TOKEN_HERE":
        print("=" * 60)
        print("❌ 错误：请先配置 Bot Token！")
        print("=" * 60)
        print("\n步骤 1: 在 Telegram 中找 @BotFather")
        print("步骤 2: 发送 /newbot 创建新机器人")
        print("步骤 3: 复制获得的 Token")
        print("步骤 4: 打开 config.json，替换 YOUR_BOT_TOKEN_HERE")
        print("\n" + "=" * 60)
        return
    
    if not config.admin_ids:
        print("=" * 60)
        print("⚠️ 警告：未配置管理员 ID")
        print("=" * 60)
        print("\n步骤 1: 在 Telegram 中找 @userinfobot")
        print("步骤 2: 发送任意消息获取你的用户 ID")
        print("步骤 3: 打开 config.json，在 admin_ids 数组中添加你的 ID")
        print("   例如: \"admin_ids\": [123456789]")
        print("\n" + "=" * 60 + "\n")
    
    # 初始化数据库
    print("🔄 初始化数据库...")
    db.init_db()
    
    # 初始化默认数据
    db.init_default_data(
        config.default_tags,
        config.default_reject_reasons
    )
    print("✅ 数据库初始化完成")
    
    # 创建应用
    application = Application.builder().token(config.bot_token).build()
    
    # ==================== 命令处理器 ====================
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("cancel", cancel_command))
    application.add_handler(CommandHandler("submit", submit_command))
    application.add_handler(CommandHandler("mystats", my_stats_command))
    
    # 管理员命令
    application.add_handler(CommandHandler("queue", queue_command))
    application.add_handler(CommandHandler("stats", stats_command))
    application.add_handler(CommandHandler("ban", ban_command))
    application.add_handler(CommandHandler("unban", unban_command))
    application.add_handler(CommandHandler("addtag", add_tag_command))
    application.add_handler(CommandHandler("addreason", add_reason_command))
    application.add_handler(CommandHandler("userinfo", user_info_command))
    
    # ==================== 回调处理器 ====================
    
    # 导航和投稿
    application.add_handler(CallbackQueryHandler(placeholder_callback, pattern="^placeholder$"))
    application.add_handler(CallbackQueryHandler(start_submit_callback, pattern="^start_submit$"))
    application.add_handler(CallbackQueryHandler(submit_type_callback, pattern="^submit_(named|anonymous)$"))
    application.add_handler(CallbackQueryHandler(finish_submit_callback, pattern="^finish_submit$"))
    application.add_handler(CallbackQueryHandler(cancel_submit_callback, pattern="^cancel_submit$"))
    application.add_handler(CallbackQueryHandler(back_to_main_callback, pattern="^back_to_main$"))
    
    # 审核
    application.add_handler(CallbackQueryHandler(approve_callback, pattern=r"^approve_\d+$"))
    application.add_handler(CallbackQueryHandler(reject_callback, pattern=r"^reject_\d+$"))
    application.add_handler(CallbackQueryHandler(tag_select_callback, pattern=r"^tag_\d+_.+$"))
    application.add_handler(CallbackQueryHandler(confirm_tags_callback, pattern=r"^confirm_tags_\d+$"))
    application.add_handler(CallbackQueryHandler(reject_reason_callback, pattern=r"^reason_\d+_\d+$"))
    application.add_handler(CallbackQueryHandler(custom_reason_callback, pattern=r"^custom_reason_\d+$"))
    application.add_handler(CallbackQueryHandler(back_to_review_callback, pattern=r"^back_review_\d+$"))
    
    # 用户管理
    application.add_handler(CallbackQueryHandler(ban_user_callback, pattern=r"^ban_\d+$"))
    application.add_handler(CallbackQueryHandler(unban_user_callback, pattern=r"^unban_\d+$"))
    
    # ==================== 消息处理器 ====================
    application.add_handler(MessageHandler(
        filters.ALL & ~filters.COMMAND,
        message_handler
    ))
    
    # 启动机器人
    print("=" * 60)
    print("🤖 机器人启动成功！")
    print("=" * 60)
    print(f"📢 频道: {config.channel_id}")
    print(f"👥 管理员数量: {len(config.admin_ids)}")
    print(f"🏷️ 标签数量: {len(db.get_all_tags())}")
    print("=" * 60)
    print("\n按 Ctrl+C 停止机器人\n")
    
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
