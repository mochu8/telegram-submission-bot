from types import SimpleNamespace

import utils.helpers as helpers
from utils.helpers import (
    build_publish_bodies,
    build_submit_intro,
    escape_html,
    extract_urls,
    format_review_body,
    format_review_caption,
    format_user_link,
    visible_text,
)
from utils.keyboard import (
    build_admin_user_keyboard,
    build_reject_reasons_keyboard,
    build_review_keyboard,
    build_tags_keyboard,
)
from utils.media import clip_text, group_compatible, send_media_items


def test_review_body_lists_hidden_link_targets():
    html_text = '<a href="https://evil.example/phish">click here</a>'
    urls = extract_urls("click here", html_text)
    assert urls == ["https://evil.example/phish"]
    body = format_review_body("click here", html_text)
    assert "https://evil.example/phish" in body
    assert "click here" in body
    caption = format_review_caption("click here", html_text, limit=1024)
    assert caption is not None
    assert caption.startswith("https://evil.example/phish")


def test_publish_limit_uses_visible_text_not_html_tags():
    html_text = "<b>" + ("字" * 20) + "</b>"
    _html_body, plain = build_publish_bodies(None, html_text, ["标签"], "")
    assert "字" * 20 in plain
    assert "<b>" not in plain
    assert len(plain) < len(html_text) or "<b>" not in plain
    assert visible_text(html_text) == "字" * 20
    assert len(plain) <= 1024


def test_remember_text_appends_instead_of_overwriting():
    from handlers.submission import _remember_text

    data = {}
    assert _remember_text(data, "第一段", "第一段", has_media=False) == "saved"
    assert _remember_text(data, "第二段", "<b>第二段</b>", has_media=False) == "appended"
    assert data["text_content"] == "第一段\n第二段"
    assert "第二段" in data["text_html"]
    data["text_content"] = "x" * 1024
    data["media_group"] = [{"type": "photo"}]
    assert _remember_text(data, "更多", "更多", has_media=True) == "kept"
    assert data["text_content"] == "x" * 1024


def test_submit_intro_does_not_promise_full_anonymity():
    text = build_submit_intro()
    assert "完全匿名" not in text
    assert "记录仍会保留" in text


def test_user_content_is_html_escaped():
    assert escape_html("<b>x</b>") == "&lt;b&gt;x&lt;/b&gt;"
    assert not hasattr(helpers, "escape_markdown")

    link = format_user_link(1, "<admin>", "good_name")
    assert link == '<a href="https://t.me/good_name">&lt;admin&gt;</a>'
    assert format_user_link(5, "a", None) == '<a href="tg://user?id=5">a</a>'
    unsafe = format_user_link(5, "n", "bad name")
    assert "tg://user?id=5" in unsafe
    assert "bad name" not in unsafe

    html_body, plain = build_publish_bodies("a<b>", None, ["x<y>"], "f&f")
    assert "<b>" not in html_body
    assert "a&lt;b&gt;" in html_body
    assert "#x&lt;y&gt;" in html_body
    assert "f&amp;f" in html_body
    assert "a<b>" in plain

    formatted, plain_text = build_publish_bodies("ok", "<b>ok</b>", [], "")
    assert formatted == "<b>ok</b>"
    assert plain_text == "ok"


def test_callback_data_uses_database_ids_and_fits_limit():
    tag = SimpleNamespace(id=7, name="名" * 80, emoji="🏷️", display_name="🏷️ " + ("名" * 80))
    reason = SimpleNamespace(id=3, text="x" * 100)
    tags = build_tags_keyboard([tag], 123456, [7])
    tag_data = tags.inline_keyboard[0][0].callback_data
    assert tag_data == "tag_123456_7"
    assert len(tag_data.encode("utf-8")) <= 64
    assert tags.inline_keyboard[0][0].text.startswith("✓")

    reasons = build_reject_reasons_keyboard([reason], 9)
    reason_data = reasons.inline_keyboard[0][0].callback_data
    assert reason_data == "reason_9_3"
    assert reason_data != "reason_9_0"

    review_data = [
        button.callback_data
        for row in build_review_keyboard(5).inline_keyboard
        for button in row
    ]
    assert review_data == ["approve_5", "reject_5"]

    ban_data = [
        button.callback_data
        for row in build_admin_user_keyboard(4, False).inline_keyboard
        for button in row
    ]
    assert ban_data == ["ban_4"]
    retired = " ".join(review_data + ban_data + [tag_data, reason_data])
    for prefix in ("add_tags_", "edit_", "user_stats_", "user_submissions_", "confirm_publish_"):
        assert prefix not in retired


def test_media_groups_keep_audio_and_documents():
    items = [("p", "photo"), ("v", "video"), ("a", "audio"), ("d", "document")]
    assert group_compatible(items) == [
        [("p", "photo"), ("v", "video")],
        [("a", "audio")],
        [("d", "document")],
    ]
    photos = [(str(index), "photo") for index in range(12)]
    groups = group_compatible(photos)
    assert [len(group) for group in groups] == [10, 2]

    head, rest = clip_text("abcdef", 4)
    assert head == "abc…"
    assert rest == "def"
    assert clip_text("ok", 10) == ("ok", None)


def test_send_media_items_does_not_drop_audio_or_documents():
    import asyncio

    class FakeBot:
        def __init__(self):
            self.calls = []

        async def send_photo(self, **kwargs):
            self.calls.append(("photo", kwargs))
            return SimpleNamespace(message_id=1)

        async def send_audio(self, **kwargs):
            self.calls.append(("audio", kwargs))
            return SimpleNamespace(message_id=2)

        async def send_document(self, **kwargs):
            self.calls.append(("document", kwargs))
            return SimpleNamespace(message_id=3)

        async def send_video(self, **kwargs):
            self.calls.append(("video", kwargs))
            return SimpleNamespace(message_id=4)

        async def send_media_group(self, **kwargs):
            self.calls.append(("group", [type(item).__name__ for item in kwargs["media"]]))
            return [SimpleNamespace(message_id=5)]

    async def run():
        bot = FakeBot()
        messages = await send_media_items(
            bot,
            1,
            ["p1", "p2", "a", "d"],
            ["photo", "photo", "audio", "document"],
            caption="hi",
        )
        assert len(messages) == 3
        kinds = [call[0] for call in bot.calls]
        assert kinds == ["group", "audio", "document"]
        assert bot.calls[0][1] == ["InputMediaPhoto", "InputMediaPhoto"]

    asyncio.run(run())
