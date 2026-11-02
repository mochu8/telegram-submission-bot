"""Admin authorization shared by commands and callback queries."""

import functools
import logging

from telegram import Update
from telegram.ext import ContextTypes

from config import config
from database.db import db

logger = logging.getLogger(__name__)

DENIED_TEXT = "❌ 您没有权限执行此操作"


def is_operator(user_id: int | None) -> bool:
    """True for config admins and for users with an admin or reviewer role."""
    if user_id is None:
        return False
    if config.is_config_admin(user_id):
        return True
    return db.is_admin(user_id)


def admin_only(func):
    """Reject non-admins before a command or callback runs."""

    @functools.wraps(func)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
        user = update.effective_user if update is not None else None
        if user is None or not is_operator(user.id):
            logger.warning(
                "Denied admin action %s for user %s",
                func.__name__,
                getattr(user, "id", None),
            )
            if update is not None and update.callback_query is not None:
                await update.callback_query.answer(DENIED_TEXT, show_alert=True)
            elif update is not None and update.effective_message is not None:
                await update.effective_message.reply_text(DENIED_TEXT)
            return None
        return await func(update, context, *args, **kwargs)

    return wrapper
