"""Tests for POST /api/admin/rescore."""

from __future__ import annotations

from unittest.mock import MagicMock


def test_rescore_returns_run_id(client) -> None:
    """POST /api/admin/rescore returns the run_id from `client.jobs.run_now()`."""
    fake_run = MagicMock()
    fake_run.run_id = 99887766
    # The route does `getattr(wait, 'run_id', None)` first; setting it on the
    # returned object directly is the simplest happy-path setup.
    client.fake_workspace.jobs.run_now.return_value = fake_run

    # Always send X-Forwarded-Email so this test passes whether or not the
    # route grows operator auth in the hygiene agent's parallel work.
    res = client.post(
        "/api/admin/rescore",
        headers={"X-Forwarded-Email": "operator@example.com"},
    )
    assert res.status_code == 200
    body = res.json()
    assert body["run_id"] == 99887766
    # job_id from RESCORE_JOB_ID env var (12345) is what we should have
    # asked the SDK to run.
    client.fake_workspace.jobs.run_now.assert_called_once_with(job_id=12345)
