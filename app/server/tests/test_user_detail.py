"""Tests for GET /api/users/{user_id}."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal


def _user_row() -> tuple:
    """One fake row matching the SELECT in `routes/user_detail.py`."""
    return (
        "u_001",
        "premium",
        "us-west",
        "smb",
        date(2024, 1, 15),
        87,
        "low",
        Decimal("199.00"),
        "active",
        3,
        2,
        1,
        14,
        455,
        datetime(2026, 4, 27, 12, 0, 0),
    )


def _rec_rows() -> list[tuple]:
    return [
        (
            "rec_1",
            "u_001",
            "OUTREACH",
            "Schedule retention call",
            "Engagement dropping; concierge call for premium tier.",
            1,
            datetime(2026, 5, 1, 0, 0, 0),
        )
    ]


def _action_rows() -> list[tuple]:
    return [
        (
            "act_1",
            "u_001",
            "rec_1",
            "accepted",
            "Reached out via email.",
            "operator@example.com",
            datetime(2026, 4, 27, 13, 0, 0),
        )
    ]


def test_get_user_happy_path(client) -> None:
    """GET /api/users/u_001 returns the joined user + scores + recs + actions."""
    cur = client.fake_cursor
    # The route does three executes: user lookup, recs, actions
    cur.fetchone.side_effect = [_user_row()]
    cur.fetchall.side_effect = [_rec_rows(), _action_rows()]

    res = client.get("/api/users/u_001")
    assert res.status_code == 200
    body = res.json()
    assert body["user_id"] == "u_001"
    assert body["plan_tier"] == "premium"
    assert body["churn_risk_score"] == 87
    assert len(body["recommendations"]) == 1
    assert body["recommendations"][0]["action_label"] == "Schedule retention call"
    assert len(body["recent_actions"]) == 1
    assert body["recent_actions"][0]["decision"] == "accepted"


def test_get_user_returns_404_when_missing(client) -> None:
    """An empty `fetchone` from the user lookup triggers 404."""
    cur = client.fake_cursor
    cur.fetchone.return_value = None
    cur.fetchall.return_value = []

    res = client.get("/api/users/u_does_not_exist")
    assert res.status_code == 404
    assert "not found" in res.json()["detail"]
