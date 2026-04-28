"""Shared pytest fixtures for the FastAPI backend tests.

The real app boots with:
- `server.db.pool` — a module-level psycopg ConnectionPool constructed at
  import time, requiring PG* env vars and an OAuth token at first connect.
- `server.config.get_workspace_client()` — an authenticated SDK client.

For tests we replace both with `MagicMock`s so routes never touch a real DB
or the Databricks API. PG env vars are seeded before import so the pool
constructor in `server.db` doesn't blow up.
"""

from __future__ import annotations

import os
import sys
from collections.abc import Iterator
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# --- Path / env setup (must run before importing the app) -------------------
# `app/app.py` and `server/*.py` use bare imports like `from server.db import
# pool`, so the `app/` directory must be on sys.path.
_APP_DIR = Path(__file__).resolve().parents[2]
if str(_APP_DIR) not in sys.path:
    sys.path.insert(0, str(_APP_DIR))

# `server.db` reads PGHOST/PGUSER/PGDATABASE at import time when constructing
# the pool. We set safe placeholders; the pool itself is replaced with a
# MagicMock in fixtures, so these are never used to dial out.
os.environ.setdefault("PGHOST", "localhost")
os.environ.setdefault("PGPORT", "5432")
os.environ.setdefault("PGUSER", "test")
os.environ.setdefault("PGDATABASE", "test")
os.environ.setdefault("ENDPOINT_NAME", "test-endpoint")
os.environ["LAKEBASE_SYNC_SCHEMA"] = "lakebase_demo_synced"
os.environ["RESCORE_JOB_ID"] = "12345"
os.environ["ENABLE_LLM_EXPLAIN"] = "true"
os.environ.setdefault("DATABRICKS_HOST", "https://example.databricks.com")


def _make_pool_mock(cursor: MagicMock) -> MagicMock:
    """Build a MagicMock pool whose context-manager chain yields `cursor`."""
    conn = MagicMock(name="connection")
    pool = MagicMock(name="pool")
    # `with pool.connection() as conn:` -> conn
    pool.connection.return_value.__enter__.return_value = conn
    pool.connection.return_value.__exit__.return_value = False
    # `with conn.cursor() as cur:` -> cursor
    conn.cursor.return_value.__enter__.return_value = cursor
    conn.cursor.return_value.__exit__.return_value = False
    conn.commit = MagicMock()
    return pool


@pytest.fixture
def mock_cursor() -> MagicMock:
    """A fresh MagicMock cursor — tests configure fetchone/fetchall on this."""
    return MagicMock(name="cursor")


@pytest.fixture
def mock_workspace_client() -> MagicMock:
    """A MagicMock WorkspaceClient injected by the `client` fixture."""
    return MagicMock(name="WorkspaceClient")


@pytest.fixture
def client(mock_cursor: MagicMock, mock_workspace_client: MagicMock) -> Iterator:
    """A FastAPI TestClient with the DB pool and WorkspaceClient stubbed out."""
    from fastapi.testclient import TestClient

    # Import the FastAPI app and the modules that bind `pool` at import time.
    import app as app_module
    import server.db as db_module
    from server.routes import actions, admin, explain, user_detail, users

    fake_pool = _make_pool_mock(mock_cursor)

    patches = [
        # Patch the canonical pool object so anything that re-resolves it sees
        # the mock; also patch each module that already imported it by name.
        patch.object(db_module, "pool", fake_pool),
        patch.object(app_module, "pool", fake_pool),
        patch.object(users, "pool", fake_pool),
        patch.object(user_detail, "pool", fake_pool),
        patch.object(actions, "pool", fake_pool),
        patch.object(explain, "pool", fake_pool),
        # Routes that authenticate against Databricks (admin.rescore, explain
        # via llm.get_llm_client) go through `get_workspace_client()`. Patch
        # both the canonical name and any module-local re-import.
        patch("server.config.get_workspace_client", return_value=mock_workspace_client),
        patch.object(admin, "get_workspace_client", return_value=mock_workspace_client),
    ]
    for p in patches:
        p.start()
    try:
        # `TestClient` as a context manager triggers FastAPI's lifespan, which
        # calls pool.open()/close() — those are mock methods now, so harmless.
        with TestClient(app_module.app) as test_client:
            test_client.fake_pool = fake_pool  # type: ignore[attr-defined]
            test_client.fake_cursor = mock_cursor  # type: ignore[attr-defined]
            test_client.fake_workspace = mock_workspace_client  # type: ignore[attr-defined]
            yield test_client
    finally:
        for p in patches:
            p.stop()
