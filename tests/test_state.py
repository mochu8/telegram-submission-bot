from utils.state import (
    clear_review_state,
    clear_user_flow_state,
    review_state,
    set_pending_input,
)


def test_review_state_is_scoped_per_submission():
    data = {"state": "submitting", "text_content": "draft"}
    set_pending_input(data, "ban_reason", target_id=4)
    review_state(data, 1)["selected_tag_ids"].append(3)
    review_state(data, 2)["selected_tag_ids"].append(4)

    assert review_state(data, 1)["selected_tag_ids"] == [3]
    assert review_state(data, 2)["selected_tag_ids"] == [4]

    clear_review_state(data, 1)
    assert 1 not in data["reviews"]
    assert data["reviews"][2]["selected_tag_ids"] == [4]

    clear_user_flow_state(data)
    assert "state" not in data
    assert "text_content" not in data
    assert "pending_input" not in data
    assert data["reviews"][2]["selected_tag_ids"] == [4]
