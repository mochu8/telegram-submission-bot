"""Send submission media without dropping audio or documents."""

import logging

from telegram import InputMediaAudio, InputMediaDocument, InputMediaPhoto, InputMediaVideo

logger = logging.getLogger(__name__)

MAX_MEDIA_ITEMS = 10
MAX_CAPTION_LENGTH = 1024
MAX_TEXT_LENGTH = 4096

_INPUT_TYPES = {
    "photo": InputMediaPhoto,
    "video": InputMediaVideo,
    "audio": InputMediaAudio,
    "document": InputMediaDocument,
}

_VISUAL = {"photo", "video"}


def media_category(media_type: str) -> str:
    if media_type in _VISUAL:
        return "visual"
    return media_type


def group_compatible(items: list[tuple[str, str]]) -> list[list[tuple[str, str]]]:
    """Group items Telegram accepts in one album, preserving order.

    Photos and videos can share an album. Audio only groups with audio, and
    documents only group with documents. Albums are capped at 10 items.
    """
    groups: list[list[tuple[str, str]]] = []
    current: list[tuple[str, str]] = []
    current_category = None
    for item in items:
        _file_id, media_type = item
        category = media_category(media_type)
        if current and (category != current_category or len(current) >= MAX_MEDIA_ITEMS):
            groups.append(current)
            current = []
        current.append(item)
        current_category = category
    if current:
        groups.append(current)
    return groups


def clip_text(text: str | None, limit: int) -> tuple[str, str | None]:
    """Fit text to a Telegram limit and return the remainder instead of dropping it."""
    if not text:
        return "", None
    if len(text) <= limit:
        return text, None
    head = text[: limit - 1] + "…"
    rest = text[limit - 1 :]
    if len(rest) > MAX_TEXT_LENGTH:
        logger.warning(
            "Truncating overflow text from %s to %s characters",
            len(rest),
            MAX_TEXT_LENGTH,
        )
        rest = rest[: MAX_TEXT_LENGTH - 1] + "…"
    return head, rest


async def send_single_media(bot, chat_id, file_id, media_type, caption=None, parse_mode=None):
    kwargs = {"chat_id": chat_id}
    if caption:
        kwargs["caption"] = caption
        if parse_mode:
            kwargs["parse_mode"] = parse_mode
    if media_type == "photo":
        return await bot.send_photo(photo=file_id, **kwargs)
    if media_type == "video":
        return await bot.send_video(video=file_id, **kwargs)
    if media_type == "audio":
        return await bot.send_audio(audio=file_id, **kwargs)
    if media_type == "document":
        return await bot.send_document(document=file_id, **kwargs)
    raise ValueError(f"unsupported media type: {media_type}")


async def send_media_items(bot, chat_id, file_ids, media_types, caption=None, parse_mode=None):
    """Send every item. Mixed albums are split so audio and documents are not skipped."""
    items = list(zip(file_ids, media_types))
    if not items:
        return []

    messages = []
    first_group = True
    for group in group_compatible(items):
        group_caption = caption if first_group else None
        unsupported = any(media_type not in _INPUT_TYPES for _file_id, media_type in group)
        if unsupported or len(group) == 1:
            for index, (file_id, media_type) in enumerate(group):
                cap = group_caption if index == 0 else None
                message = await send_single_media(
                    bot,
                    chat_id,
                    file_id,
                    media_type,
                    caption=cap,
                    parse_mode=parse_mode,
                )
                if message is not None:
                    messages.append(message)
        else:
            media = []
            for index, (file_id, media_type) in enumerate(group):
                cap = group_caption if index == 0 else None
                media_cls = _INPUT_TYPES[media_type]
                media_kwargs = {"media": file_id}
                if cap:
                    media_kwargs["caption"] = cap
                    if parse_mode:
                        media_kwargs["parse_mode"] = parse_mode
                media.append(media_cls(**media_kwargs))
            sent = await bot.send_media_group(chat_id=chat_id, media=media)
            messages.extend(sent or [])
        first_group = False
    return messages
