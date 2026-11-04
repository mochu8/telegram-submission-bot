"""Registration and the ban gate used by every submission entry point."""

import logging

from database.db import db

logger = logging.getLogger(__name__)

BANNED_TEXT = "❌ 您的账号已被封禁，无法投稿\n\n如有疑问请联系管理员"


def touch_user(tg_user):
    """Create or refresh the local user row for a Telegram user."""
    if tg_user is None:
        return None
    return db.get_or_create_user(
        user_id=tg_user.id,
        username=getattr(tg_user, "username", None),
        full_name=getattr(tg_user, "full_name", None),
    )


def submission_block_message(tg_user) -> str | None:
    """Register the user and return an error when they are not allowed to submit."""
    record = touch_user(tg_user)
    if record is not None and record.is_banned:
        logger.info("Blocked banned user %s from submitting", tg_user.id)
        return BANNED_TEXT
    return None
