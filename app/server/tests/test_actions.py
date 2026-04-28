"""Tests for POST /api/users/{user_id}/actions."""

from __future__ import annotations

from datetime import datetime


def _new_action_row(operator: str) -> tuple:
    """The row returned by the INSERT ... RETURNING in `routes/actions.py`."""
    return (
        "act_new",
        "u_001",
        "rec_1",
        "accepted",
        "Reached out via email.",
        operator,
        datetime(2026, 4, 28, 12, 0, 0),
    )


def test_create_action_happy_path(client) -> None:
    """POST writes the action with the operator from X-Forwarded-Email."""
    cur = client.fake_cursor
    operator = "operator@example.com"
    # First fetchone is the existence check (any non-None tuple); second is
    # the RETURNING from the INSERT.
    cur.fetchone.side_effect = [(1,), _new_action_row(operator)]

    res = client.post(
        "/api/users/u_001/actions",
        json={
            "recommendation_id": "rec_1",
            "decision": "accepted",
            "notes": "Reached out via email.",
        },
        headers={"X-Forwarded-Email": operator},
    )
    assert res.status_code == 201
    body = res.json()
    assert body["decision"] == "accepted"
    assert body["operator"] == operator

    # Two SQL calls: existence check + INSERT. The INSERT's params must
    # include the operator we sent.
    assert cur.execute.call_count == 2
    insert_call = cur.execute.call_args_list[1]
    insert_sql = insert_call.args[0]
    insert_params = insert_call.args[1]
    assert "INSERT INTO user_actions" in insert_sql
    assert insert_params == ("u_001", "rec_1", "accepted", "Reached out via email.", operator)


def test_create_action_uses_local_dev_fallback_operator(client) -> None:
    """Without X-Forwarded-Email header, operator defaults to local-dev."""
    cur = client.fake_cursor
    cur.fetchone.side_effect = [(1,), _new_action_row("local-dev@example.com")]

    res = client.post(
        "/api/users/u_001/actions",
        json={"decision": "dismissed"},
    )
    assert res.status_code == 201
    assert res.json()["operator"] == "local-dev@example.com"

    insert_params = cur.execute.call_args_list[1].args[1]
    # operator is the 5th positional arg in the INSERT params tuple
    assert insert_params[4] == "local-dev@example.com"
