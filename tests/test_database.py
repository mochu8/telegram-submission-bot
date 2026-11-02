import threading
from types import SimpleNamespace

import pytest

from database.db import SubmissionNotAllowed
from database.models import STATUS_APPROVED, STATUS_PENDING, STATUS_PUBLISHING


def test_submission_gate_registers_and_blocks(database, monkeypatch):
    from utils.users import submission_block_message

    monkeypatch.setattr("utils.users.db", database)
    person = SimpleNamespace(id=42, username="bob", full_name="Bob")
    assert submission_block_message(person) is None
    assert database.get_user(42).username == "bob"

    assert database.ban_user(42, admin_id=1, reason="spam") is True
    blocked = submission_block_message(person)
    assert blocked and "封禁" in blocked
    assert database.get_user(42).is_banned is True
    assert database.get_user(42).username == "bob"


def test_ban_unknown_user_creates_a_banned_row(database):
    assert database.get_user(42) is None
    assert database.ban_user(42, admin_id=1, reason="spam") is True

    user = database.get_user(42)
    assert user is not None
    assert user.is_banned is True
    assert user.ban_reason == "spam"
    assert database.is_user_banned(42) is True

    assert database.unban_user(42, admin_id=1) is True
    assert database.is_user_banned(42) is False


def test_get_or_create_does_not_clear_a_ban(database):
    database.get_or_create_user(7, "old", "Old")
    assert database.ban_user(7, 1, "reason") is True

    database.get_or_create_user(7, "new", "New")
    user = database.get_user(7)
    assert user.username == "new"
    assert user.full_name == "New"
    assert user.is_banned is True
    assert user.ban_reason == "reason"


def test_cannot_ban_config_admin_or_reviewer(database, monkeypatch):
    from config import config

    monkeypatch.setattr(config, "is_config_admin", lambda user_id: user_id == 1)
    assert database.ban_user(1, 2, "no") is False
    assert database.get_user(1) is None

    database.get_or_create_user(5, "rev", "Reviewer")
    database.update_user_role(5, "reviewer")
    assert database.ban_user(5, 2, "no") is False
    assert database.is_user_banned(5) is False


def test_create_submission_rejects_banned_and_unknown_users(database):
    with pytest.raises(SubmissionNotAllowed):
        database.create_submission(999, "text", text_content="hi")

    database.get_or_create_user(8, "a", "A")
    database.ban_user(8, 1, "spam")
    with pytest.raises(SubmissionNotAllowed):
        database.create_submission(8, "text", text_content="hi")

    assert database.get_pending_count() == 0
    assert database.get_user_stats(8)["total"] == 0


def test_claim_publish_and_reject_are_single_winners(database):
    database.get_or_create_user(3, "a", "A")
    submission = database.create_submission(3, "text", text_content="hello")

    assert database.claim_submission(submission.id, 10) is True
    assert database.claim_submission(submission.id, 11) is False
    assert database.reject_submission(submission.id, 11, "late") is False
    assert database.get_submission(submission.id).status == STATUS_PUBLISHING

    assert database.release_submission_claim(submission.id) is True
    assert database.get_submission(submission.id).status == STATUS_PENDING
    assert database.claim_submission(submission.id, 10) is True
    assert database.finalize_approval(submission.id, 10, ["新闻"], 55) is True
    assert database.finalize_approval(submission.id, 10, ["新闻"], 55) is False

    stored = database.get_submission(submission.id)
    assert stored.status == STATUS_APPROVED
    assert stored.published_msg_id == 55
    stats = database.get_user_stats(3)
    assert stats["total"] == 1
    assert stats["approved"] == 1

    other = database.create_submission(3, "text", text_content="second")
    assert database.reject_submission(other.id, 10, "因为<b>") is True
    assert database.reject_submission(other.id, 11, "again") is False
    assert database.get_submission(other.id).reject_reason == "因为<b>"
    assert database.get_user_stats(3)["rejected"] == 1


def test_parallel_claims_publish_once(database):
    database.get_or_create_user(4, "a", "A")
    submission = database.create_submission(4, "text", text_content="race")
    barrier = threading.Barrier(2)
    results = []
    errors = []
    lock = threading.Lock()

    def worker(reviewer_id):
        try:
            barrier.wait(timeout=5)
            won = database.claim_submission(submission.id, reviewer_id)
            with lock:
                results.append(won)
        except Exception as exc:  # pragma: no cover - surfaced below
            errors.append(exc)

    threads = [threading.Thread(target=worker, args=(reviewer,)) for reviewer in (10, 11)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=10)

    assert errors == []
    assert sorted(results) == [False, True]
    assert database.get_submission(submission.id).status == STATUS_PUBLISHING


def test_default_data_is_idempotent_and_reasons_use_ids(database):
    tags = [{"name": "分享", "emoji": "📢"}]
    database.init_default_data(tags, ["理由"])
    database.init_default_data(tags, ["理由"])
    assert len(database.get_all_tags()) == 1
    assert len(database.get_all_reject_reasons()) == 1

    first = database.add_reject_reason("A")
    second = database.add_reject_reason("B")
    database.increment_reason_usage(second.id)
    ordered = database.get_all_reject_reasons()
    assert ordered[0].id == second.id
    assert database.get_reject_reason(first.id).text == "A"
