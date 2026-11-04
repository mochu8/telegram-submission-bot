"""Admin authorization shared by commands and callback queries."""

import functools
import logging

from telegram import Update
from telegram.ext import ContextTypes

from config import config
from database.db import db
from utils.blocking import run_blocking

logger = logging.getLogger(__name__)

DENIED_TEXT = "❌ 您没有权限执行此操作"


def is_operator(user_id: int | None) -> bool:
    """Config admins, database admins, and reviewers can review submissions."""
    if user_id is None:
        return False
    if config.is_config_admin(user_id):
        return True
    return db.is_admin(user_id)


def is_full_admin(user_id: int | None) -> bool:
    """Config admins and role=admin. Reviewers cannot ban, tag, or back up."""
    if user_id is None:
        return False
    if config.is_config_admin(user_id):
        return True
    return db.has_admin_role(user_id)


def is_config_operator(user_id: int | None) -> bool:
    """Only IDs listed in admin_ids can grant roles."""
    return bool(user_id) and config.is_config_admin(user_id)


def review_recipient_ids() -> list[int]:
    """Config admins plus database admins and reviewers."""
    found = set(config.admin_ids)
    found.update(db.list_user_ids_by_roles(("admin", "reviewer")))
    return sorted(item for item in found if item)


def require_access(level: str):
    """level is reviewer, admin, or config. The check is looked up on each call."""

    def decorator(func):
        @functools.wraps(func)
        async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
            user = update.effective_user if update is not None else None
            checks = {
                "reviewer": is_operator,
                "admin": is_full_admin,
                "config": is_config_operator,
            }
            allowed = user is not None and await run_blocking(checks[level], user.id)
            if not allowed:
                logger.warning(
                    "Denied %s action %s for user %s",
                    level,
                    func.__name__,
                    getattr(user, "id", None),
                )
                if update is not None and update.callback_query is not None:
                    await update.callback_query.answer(DENIED_TEXT, show_alert=True)
                elif update is not None and update.effective_message is not None:
                    await update.effective_message.reply_text(DENIED_TEXT)
                return None
            return await func(update, context, *args, **kwargs)

        wrapper.access_level = level
        return wrapper

    return decorator


def admin_only(func):
    """Reviewer-level access for the review flow and the queue."""
    return require_access("reviewer")(func)


def full_admin_only(func):
    """Ban, tags, backups, and recovering stuck rows."""
    return require_access("admin")(func)


def config_admin_only(func):
    """Role changes stay with the IDs in the config file."""
    return require_access("config")(func)
