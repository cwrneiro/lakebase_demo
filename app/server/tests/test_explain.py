"""Tests for POST /api/users/{user_id}/explain."""

from __future__ import annotations

import os
from datetime import date, datetime
from decimal import Decimal
from unittest.mock import MagicMock, patch


def _user_score_row() -> tuple:
    """Row returned by the SELECT in `routes/explain.py`."""
    return (
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


def test_explain_returns_503_when_disabled(client) -> None:
    """When ENABLE_LLM_EXPLAIN is false the route should fail closed."""
    with patch.dict(os.environ, {"ENABLE_LLM_EXPLAIN": "false"}):
        res = client.post("/api/users/u_001/explain")
    assert res.status_code == 503
    assert "disabled" in res.json()["detail"].lower()


def test_explain_happy_path(client) -> None:
    """Mock the OpenAI client so the route returns the rationale + model name."""
    cur = client.fake_cursor
    cur.fetchone.return_value = _user_score_row()

    fake_completion = MagicMock()
    fake_completion.choices = [MagicMock()]
    fake_completion.choices[0].message.content = (
        "User has high churn risk driven by recent payment failures and "
        "declining sessions. Recommend a retention call before next billing."
    )

    fake_client = MagicMock()
    fake_client.chat.completions.create.return_value = fake_completion

    with patch("server.llm.OpenAI", return_value=fake_client), patch(
        "server.llm.get_oauth_token", return_value="fake-token"
    ), patch("server.llm.get_workspace_host", return_value="https://example.databricks.com"):
        res = client.post("/api/users/u_001/explain")

    assert res.status_code == 200
    body = res.json()
    assert body["user_id"] == "u_001"
    assert "churn risk" in body["rationale"]
    assert body["model"] == os.environ.get("SERVING_ENDPOINT", "databricks-claude-sonnet-4-5")
