"""Conversation state scoped so unrelated flows do not wipe each other."""

SUBMISSION_DRAFT_KEYS = (
    "state",
    "is_anonymous",
    "media_group",
    "text_content",
    "text_html",
    "media_group_id",
)


def clear_submission_draft(user_data: dict) -> None:
    for key in SUBMISSION_DRAFT_KEYS:
        user_data.pop(key, None)


def set_pending_input(user_data: dict, kind: str, **data) -> None:
    """Remember a single text prompt. A new prompt replaces the previous one."""
    user_data["pending_input"] = {"kind": kind, **data}


def peek_pending_input(user_data: dict, kind: str) -> dict | None:
    pending = user_data.get("pending_input")
    if not isinstance(pending, dict) or pending.get("kind") != kind:
        return None
    return pending


def pop_pending_input(user_data: dict, kind: str) -> dict | None:
    pending = peek_pending_input(user_data, kind)
    if pending is None:
        return None
    user_data.pop("pending_input", None)
    return pending


def clear_pending_input(user_data: dict) -> None:
    user_data.pop("pending_input", None)


def review_state(user_data: dict, submission_id: int) -> dict:
    """Tag selection for one submission. Other submissions keep their own state."""
    reviews = user_data.setdefault("reviews", {})
    state = reviews.setdefault(int(submission_id), {})
    state.setdefault("selected_tag_ids", [])
    return state


def clear_review_state(user_data: dict, submission_id: int) -> None:
    reviews = user_data.get("reviews")
    if isinstance(reviews, dict):
        reviews.pop(int(submission_id), None)


def clear_user_flow_state(user_data: dict) -> None:
    """Clear the draft and the active text prompt. Keep per-submission reviews."""
    clear_submission_draft(user_data)
    clear_pending_input(user_data)
