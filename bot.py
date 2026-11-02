#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Telegram 投稿机器人
功能：导航 + 投稿 + 审核 + 用户管理
"""

import logging

from telegram import Update
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from config import config
from database.db import db
from handlers.admin import (
    add_reason_command,
    add_tag_command,
    ban_command,
    ban_user_callback,
    handle_ban_reason_input,
    queue_command,
    retired_button_callback,
    stats_command,
    unban_command,
    unban_user_callback,
    user_info_command,
)
from handlers.review import (
    approve_callback,
    back_to_review_callback,
    confirm_tags_callback,
    custom_reason_callback,
    handle_custom_reason_input,
    reject_callback,
    reject_reason_callback,
    tag_select_callback,
)
from handlers.start import cancel_command, help_command, start_command
from handlers.submission import (
    back_to_main_callback,
    cancel_submit_callback,
    finish_submit_callback,
    handle_submission_content,
    my_stats_command,
    placeholder_callback,
    start_submit_callback,
    submit_command,
    submit_type_callback,
)

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

RETIRED_BUTTONS = r"^(add_tags|edit|user_stats|user_submissions|confirm_publish)_\d+$"
ALLOWED_UPDATES = [Update.MESSAGE, Update.CALLBACK_QUERY]


async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """私聊里的非命令消息：管理员输入优先，其余视为投稿内容。"""
    if update.message is None:
        return
    if await handle_custom_reason_input(update, context):
        return
    if await handle_ban_reason_input(update, context):
        return
    await handle_submission_content(update, context)


async def on_error(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.error("处理更新时出现未捕获的异常", exc_info=context.error)


def _register_handlers(application: Application) -> None:
    private = filters.ChatType.PRIVATE
    commands = {
        "start": start_command,
        "help": help_command,
        "cancel": cancel_command,
        "submit": submit_command,
        "mystats": my_stats_command,
        "queue": queue_command,
        "stats": stats_command,
        "ban": ban_command,
        "unban": unban_command,
        "addtag": add_tag_command,
        "addreason": add_reason_command,
        "userinfo": user_info_command,
    }
    for name, callback in commands.items():
        application.add_handler(CommandHandler(name, callback, filters=private))

    application.add_handler(CallbackQueryHandler(placeholder_callback, pattern="^placeholder$"))
    application.add_handler(CallbackQueryHandler(start_submit_callback, pattern="^start_submit$"))
    application.add_handler(
        CallbackQueryHandler(submit_type_callback, pattern="^submit_(named|anonymous)$")
    )
    application.add_handler(CallbackQueryHandler(finish_submit_callback, pattern="^finish_submit$"))
    application.add_handler(CallbackQueryHandler(cancel_submit_callback, pattern="^cancel_submit$"))
    application.add_handler(CallbackQueryHandler(back_to_main_callback, pattern="^back_to_main$"))

    application.add_handler(CallbackQueryHandler(approve_callback, pattern=r"^approve_\d+$"))
    application.add_handler(CallbackQueryHandler(reject_callback, pattern=r"^reject_\d+$"))
    application.add_handler(CallbackQueryHandler(tag_select_callback, pattern=r"^tag_\d+_\d+$"))
    application.add_handler(
        CallbackQueryHandler(confirm_tags_callback, pattern=r"^confirm_tags_\d+$")
    )
    application.add_handler(
        CallbackQueryHandler(reject_reason_callback, pattern=r"^reason_\d+_\d+$")
    )
    application.add_handler(
        CallbackQueryHandler(custom_reason_callback, pattern=r"^custom_reason_\d+$")
    )
    application.add_handler(
        CallbackQueryHandler(back_to_review_callback, pattern=r"^back_review_\d+$")
    )
    application.add_handler(CallbackQueryHandler(ban_user_callback, pattern=r"^ban_\d+$"))
    application.add_handler(CallbackQueryHandler(unban_user_callback, pattern=r"^unban_\d+$"))
    application.add_handler(CallbackQueryHandler(retired_button_callback, pattern=RETIRED_BUTTONS))

    application.add_handler(MessageHandler(private & ~filters.COMMAND, message_handler))
    application.add_error_handler(on_error)


def main() -> int:
    """主函数"""
    if config.load_error:
        logger.error("%s", config.load_error)
        return 1
    if not config.is_valid_token():
        logger.error(
            "Bot token 无效。请设置环境变量 BOT_TOKEN，或把 config.example.json "
            "复制为 config.json 后填写 bot_token。Token 从 @BotFather 获取。"
        )
        return 1
    if not config.admin_ids:
        logger.warning(
            "未配置 admin_ids。在 config.json 中加入管理员的 Telegram 用户 ID，"
            "否则没有人可以审核投稿。"
        )

    logger.info("初始化数据库 %s", config.database_path)
    db.configure(config.database_path)
    db.init_db()
    db.init_default_data(config.default_tags, config.default_reject_reasons)
    logger.info(
        "数据库就绪，频道=%s，管理员=%s，标签=%s",
        config.channel_id or "(未设置)",
        len(config.admin_ids),
        len(db.get_all_tags()),
    )

    application = Application.builder().token(config.bot_token).build()
    _register_handlers(application)
    application.run_polling(allowed_updates=ALLOWED_UPDATES)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
