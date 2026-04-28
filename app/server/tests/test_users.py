"""Tests for GET /api/users."""

from __future__ import annotations

from datetime import datetime


def _two_user_rows() -> list[tuple]:
    """Two fake rows shaped like the SELECT in `routes/users.py`."""
    return [
        (
            "u_001",
            "premium",
            "us-west",
            "smb",
            87,
            "low",
            "Schedule retention call",
            datetime(2026, 4, 20, 12, 0, 0),
        ),
        (
            "u_002",
            "free",
            "us-east",
            "consumer",
            42,
            "medium",
            None,
            None,
        ),
    ]


def test_list_users_happy_path(client) -> None:
    """GET /api/users returns 200 + the expected response shape."""
    cur = client.fake_cursor
    cur.fetchone.return_value = (2,)  # count(*)
    cur.fetchall.return_value = _two_user_rows()

    res = client.get("/api/users")
    assert res.status_code == 200
    body = res.json()
    assert body["total"] == 2
    assert len(body["items"]) == 2
    first = body["items"][0]
    assert first["user_id"] == "u_001"
    assert first["plan_tier"] == "premium"
    assert first["churn_risk_score"] == 87
    assert first["top_recommendation"] == "Schedule retention call"


def test_list_users_accepts_valid_sort(client) -> None:
    """`?sort=risk_asc` is in the SortKey literal and should be accepted."""
    cur = client.fake_cursor
    cur.fetchone.return_value = (0,)
    cur.fetchall.return_value = []

    res = client.get("/api/users?sort=risk_asc")
    assert res.status_code == 200


def test_list_users_rejects_invalid_sort(client) -> None:
    """Invalid sort key is a Pydantic validation error -> 422."""
    res = client.get("/api/users?sort=not_a_real_sort")
    assert res.status_code == 422


def test_list_users_accepts_tier_filter(client) -> None:
    """`?tier=A` builds a WHERE clause and returns 200."""
    cur = client.fake_cursor
    cur.fetchone.return_value = (0,)
    cur.fetchall.return_value = []

    res = client.get("/api/users?tier=A")
    assert res.status_code == 200
    # The count + list SQL should both have been executed; the second call
    # carries the tier param as its first positional arg.
    assert cur.execute.call_count == 2
    list_call_args = cur.execute.call_args_list[1].args
    assert list_call_args[1][0] == "A"
