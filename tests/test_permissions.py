import asyncio
from types import SimpleNamespace

from telegram.ext import Application, CommandHandler, MessageHandler, filters

import handlers.admin as admin
import handlers.review as review
import handlers.submission as submission
from bot import ALLOWED_UPDATES, _register_handlers
from handlers.submission import STATE_SUBMITTING
from utils.auth import admin_only, is_operator


class FakeQuery:
    def __init__(self, data=""):
        self.data = data
        self.alerts = []
        self.edits = []

    async def answer(self, text=None, show_alert=False, **kwargs):
        self.alerts.append({"text": text, "show_alert": show_alert})

    async def edit_message_text(self, text, **kwargs):
        self.edits.append({"text": text, **kwargs})

    async def edit_message_reply_markup(self, reply_markup=None, **kwargs):
        self.edits.append({"markup": reply_markup})


class FakeMessage:
    def __init__(self):
        self.replies = []
        self.text = None
        self.caption = None
        self.caption_html = None
        self.text_html = None
        self.photo = None
        self.video = None
        self.audio = None
        self.document = None
        self.media_group_id = None

    async def reply_text(self, text, **kwargs):
        self.replies.append(text)


def make_update(user_id, data="", with_callback=True):
    message = FakeMessage()
    query = FakeQuery(data) if with_callback else None
    return SimpleNamespace(
        effective_user=SimpleNamespace(id=user_id, username="user", full_name="User"),
        callback_query=query,
        message=message,
        effective_message=message,
    )


ADMIN_CALLBACKS = [
    review.approve_callback,
    review.reject_callback,
    review.tag_select_callback,
    review.confirm_tags_callback,
    review.reject_reason_callback,
    review.custom_reason_callback,
    review.back_to_review_callback,
    admin.ban_user_callback,
    admin.unban_user_callback,
    admin.retired_button_callback,
]


def test_review_callbacks_reject_non_admins(monkeypatch):
    monkeypatch.setattr("utils.auth.is_operator", lambda user_id: False)

    async def run():
        for callback in ADMIN_CALLBACKS:
            update = make_update(4, data="approve_1")
            await callback(update, SimpleNamespace(user_data={}))
            assert update.callback_query.alerts, callback.__name__
            assert "权限" in update.callback_query.alerts[0]["text"]

    asyncio.run(run())


def test_admin_only_allows_and_denies(monkeypatch):
    seen = {}

    @admin_only
    async def handler(update, context):
        seen["user"] = update.effective_user.id

    async def run():
        monkeypatch.setattr("utils.auth.is_operator", lambda user_id: False)
        denied = make_update(3, with_callback=False)
        denied.callback_query = None
        await handler(denied, None)
        assert "user" not in seen
        assert denied.message.replies

        monkeypatch.setattr("utils.auth.is_operator", lambda user_id: True)
        allowed = make_update(9)
        await handler(allowed, None)
        assert seen["user"] == 9
        assert allowed.callback_query.alerts == []

    asyncio.run(run())


def test_is_operator_config_and_role(database, monkeypatch):
    from config import config

    monkeypatch.setattr("utils.auth.db", database)
    monkeypatch.setattr(config, "is_config_admin", lambda user_id: user_id == 9)
    assert is_operator(9) is True

    monkeypatch.setattr(config, "is_config_admin", lambda user_id: False)
    database.get_or_create_user(5, "r", "R")
    assert is_operator(5) is False
    database.update_user_role(5, "admin")
    assert is_operator(5) is True
    assert is_operator(None) is False


class FakeDB:
    def __init__(self, status="pending"):
        self.submission = SimpleNamespace(
            id=15,
            status=status,
            user_id=3,
            media_ids=None,
            media_types=None,
            text_content="hello",
            text_html=None,
            is_anonymous=True,
        )
        self.calls = []

    def get_submission(self, submission_id):
        if submission_id != self.submission.id:
            return None
        return self.submission

    def claim_submission(self, submission_id, reviewer_id):
        self.calls.append(("claim", submission_id, reviewer_id))
        if self.submission.status != "pending":
            return False
        self.submission.status = "publishing"
        return True

    def release_submission_claim(self, submission_id):
        self.calls.append(("release", submission_id))
        self.submission.status = "pending"
        return True

    def finalize_approval(self, submission_id, reviewer_id, tags, published_msg_id):
        self.calls.append(("finalize", submission_id, reviewer_id, tags, published_msg_id))
        self.submission.status = "approved"
        return True

    def reject_submission(self, submission_id, reviewer_id, reason):
        self.calls.append(("reject", submission_id, reason))
        if self.submission.status != "pending":
            return False
        self.submission.status = "rejected"
        return True

    def get_tags_by_ids(self, tag_ids):
        return [SimpleNamespace(id=tag_id, name=f"tag{tag_id}") for tag_id in tag_ids]

    def increment_tag_usage(self, names):
        self.calls.append(("tags", tuple(names)))


def test_publish_is_admin_gated_and_rolls_back(monkeypatch):
    from config import config

    monkeypatch.setitem(config._config, "channel_id", "@channel")

    async def scenario(operator, publish):
        fake = FakeDB()
        monkeypatch.setattr(review, "db", fake)
        monkeypatch.setattr(review, "is_operator", lambda user_id: operator)
        monkeypatch.setattr(review, "_publish_to_channel", publish)
        update = make_update(8)
        context = SimpleNamespace(user_data={}, bot=SimpleNamespace())
        await review.confirm_and_publish(update, context, 15, [])
        return fake, update

    async def run():
        async def unused(*args, **kwargs):
            raise AssertionError("publish should not run")

        fake, update = await scenario(False, unused)
        assert fake.calls == []
        assert any("权限" in (alert["text"] or "") for alert in update.callback_query.alerts)

        async def boom(*args, **kwargs):
            raise RuntimeError("network down")

        fake, update = await scenario(True, boom)
        assert ("claim", 15, 8) in fake.calls
        assert ("release", 15) in fake.calls
        assert not any(call[0] == "finalize" for call in fake.calls)
        assert fake.submission.status == "pending"
        assert any("发布失败" in edit["text"] for edit in update.callback_query.edits)

        async def ok(*args, **kwargs):
            return 42

        sent = []

        async def send_message(**kwargs):
            sent.append(kwargs)

        fake = FakeDB()
        monkeypatch.setattr(review, "db", fake)
        monkeypatch.setattr(review, "is_operator", lambda user_id: True)
        monkeypatch.setattr(review, "_publish_to_channel", ok)
        update = make_update(8)
        context = SimpleNamespace(user_data={}, bot=SimpleNamespace(send_message=send_message))
        await review.confirm_and_publish(update, context, 15, [3])
        assert ("finalize", 15, 8, ["tag3"], 42) in fake.calls
        assert not any(call[0] == "release" for call in fake.calls)
        assert sent and sent[0]["chat_id"] == 3

        fake = FakeDB()
        monkeypatch.setattr(review, "db", fake)

        async def should_not_publish(*args, **kwargs):
            raise AssertionError("second admin must not publish")

        monkeypatch.setattr(review, "_publish_to_channel", should_not_publish)
        fake.submission.status = "publishing"
        update = make_update(9)
        await review.confirm_and_publish(update, SimpleNamespace(user_data={}, bot=None), 15, [])
        assert fake.calls == [("claim", 15, 9)]
        assert any("已被处理" in edit["text"] for edit in update.callback_query.edits)

    asyncio.run(run())


def test_do_reject_blocks_non_admin(monkeypatch):
    fake = FakeDB()
    monkeypatch.setattr(review, "db", fake)
    monkeypatch.setattr(review, "is_operator", lambda user_id: False)

    async def run():
        update = make_update(4)
        result = await review.do_reject(update, SimpleNamespace(user_data={}), 15, "no")
        assert result is False

    asyncio.run(run())
    assert fake.calls == []


def test_resolve_command_recovers_publishing_rows(database, monkeypatch):
    from config import config

    monkeypatch.setattr(admin, "db", database)
    monkeypatch.setattr("utils.auth.db", database)
    monkeypatch.setitem(config._config, "admin_ids", [1])
    database.get_or_create_user(3, "a", "A")
    submission = database.create_submission(3, "text", text_content="stuck")
    assert database.claim_submission(submission.id, 9) is True

    async def run():
        update = make_update(1, with_callback=False)
        context = SimpleNamespace(args=[])
        await admin.stuck_command(update, context)
        assert str(submission.id) in update.message.replies[-1]

        context.args = [str(submission.id), "pending"]
        await admin.resolve_command(update, context)
        assert database.get_submission(submission.id).status == "pending"

        assert database.claim_submission(submission.id, 9) is True
        context.args = [str(submission.id), "approved"]
        await admin.resolve_command(update, context)
        stored = database.get_submission(submission.id)
        assert stored.status == "approved"
        assert database.get_user_stats(3)["approved"] == 1

    asyncio.run(run())


def test_custom_reason_does_not_swallow_an_in_progress_submission(monkeypatch):
    monkeypatch.setattr(review, "is_operator", lambda user_id: True)
    called = []

    async def fake_commit(*args, **kwargs):
        called.append(args)
        return "ok"

    monkeypatch.setattr(review, "commit_rejection", fake_commit)

    async def run():
        update = make_update(1, with_callback=False)
        update.message.text = "我的投稿正文"
        context = SimpleNamespace(
            user_data={
                "state": "submitting",
                "pending_input": {"kind": "reject_reason", "submission_id": 5},
            }
        )
        handled = await review.handle_custom_reason_input(update, context)
        assert handled is False
        assert called == []
        assert "pending_input" not in context.user_data
        assert any("投稿" in reply for reply in update.message.replies)

    asyncio.run(run())


def test_finish_and_type_callbacks_honor_bans(monkeypatch):
    monkeypatch.setattr(submission, "submission_block_message", lambda user: "BANNED")
    created = []
    monkeypatch.setattr(
        submission.db,
        "create_submission",
        lambda **kwargs: created.append(kwargs),
    )

    async def run():
        finish = make_update(2, data="finish_submit")
        context = SimpleNamespace(
            user_data={
                "state": STATE_SUBMITTING,
                "media_group": [],
                "text_content": "hi",
                "text_html": "hi",
                "is_anonymous": False,
            }
        )
        await submission.finish_submit_callback(finish, context)
        assert created == []
        assert any("BANNED" in edit["text"] for edit in finish.callback_query.edits)

        choosing = make_update(2, data="submit_named")
        draft = SimpleNamespace(user_data={})
        await submission.submit_type_callback(choosing, draft)
        assert draft.user_data.get("state") != STATE_SUBMITTING

        incoming = make_update(2, with_callback=False)
        incoming.message.audio = SimpleNamespace(file_id="aud")
        drafting = SimpleNamespace(user_data={"state": STATE_SUBMITTING, "media_group": []})
        await submission.handle_submission_content(incoming, drafting)
        assert drafting.user_data.get("media_group", []) == []
        assert "state" not in drafting.user_data
        assert any("BANNED" in reply for reply in incoming.message.replies)

    asyncio.run(run())


def test_media_limit_and_audio_are_enforced(monkeypatch):
    monkeypatch.setattr(submission, "submission_block_message", lambda user: None)

    async def run():
        update = make_update(2, with_callback=False)
        update.message.audio = SimpleNamespace(file_id="aud")
        context = SimpleNamespace(user_data={"state": STATE_SUBMITTING, "media_group": []})
        await submission.handle_submission_content(update, context)
        assert context.user_data["media_group"] == [{"type": "audio", "file_id": "aud"}]

        update.message.audio = None
        update.message.document = SimpleNamespace(file_id="doc")
        await submission.handle_submission_content(update, context)
        assert context.user_data["media_group"][-1] == {"type": "document", "file_id": "doc"}

        context.user_data["media_group"] = [
            {"type": "photo", "file_id": str(index)} for index in range(10)
        ]
        update.message.document = None
        update.message.audio = SimpleNamespace(file_id="extra")
        await submission.handle_submission_content(update, context)
        assert len(context.user_data["media_group"]) == 10
        assert any("10" in reply for reply in update.message.replies)

        long_caption = make_update(2, with_callback=False)
        long_caption.message.photo = [SimpleNamespace(file_id="p")]
        long_caption.message.caption = "x" * 1025
        fresh = SimpleNamespace(user_data={"state": STATE_SUBMITTING, "media_group": []})
        await submission.handle_submission_content(long_caption, fresh)
        assert fresh.user_data["media_group"] == []
        assert any("1024" in reply for reply in long_caption.message.replies)

    asyncio.run(run())


def test_handlers_are_private_and_updates_are_narrow():
    application = Application.builder().token("123456:" + "A" * 35).build()
    _register_handlers(application)
    registered = [handler for group in application.handlers.values() for handler in group]
    commands = [handler for handler in registered if isinstance(handler, CommandHandler)]
    messages = [handler for handler in registered if isinstance(handler, MessageHandler)]
    assert commands
    assert all(handler.filters == filters.ChatType.PRIVATE for handler in commands)
    assert len(messages) == 1
    assert set(ALLOWED_UPDATES) == {"message", "callback_query"}
    assert application.error_handlers
