"""Lakebase Postgres connection pool.

Uses the canonical Databricks Apps pattern: a custom `psycopg.Connection`
subclass mints a fresh OAuth credential per physical connection by calling
`WorkspaceClient.postgres.generate_database_credential(endpoint=...)`. The
pool's `max_lifetime=2700` (45 min) guarantees connections are recycled well
before the 1-hour token expires, so no background refresh task is needed.

PG env vars (PGHOST, PGUSER, PGPORT, PGDATABASE) are auto-injected by the App
when a `database` resource is attached. ENDPOINT_NAME is set in the bundle's
`resources/app.yml`.
"""

from __future__ import annotations

import os
from contextlib import asynccontextmanager
from typing import Any

import psycopg
from psycopg_pool import ConnectionPool

from server.config import get_workspace_client


class OAuthConnection(psycopg.Connection):
    """psycopg connection that injects a fresh Lakebase OAuth token at connect time.

    Also sets `search_path` so route SQL can reference synced tables
    (`users`, `user_scores`, ...) without qualifying them — they live in
    `${LAKEBASE_SYNC_SCHEMA}` while the app-owned `user_actions` is in `public`.
    """

    @classmethod
    def connect(cls, conninfo: str = "", **kwargs: Any) -> OAuthConnection:
        endpoint_name = os.environ["ENDPOINT_NAME"]
        w = get_workspace_client()
        credential = w.postgres.generate_database_credential(endpoint=endpoint_name)
        kwargs["password"] = credential.token
        conn = super().connect(conninfo, **kwargs)
        sync_schema = os.environ.get("LAKEBASE_SYNC_SCHEMA", "lakebase_demo_synced")
        # search_path is set per session; public is preserved for user_actions.
        # SET doesn't accept parameters, so we whitelist via regex.
        if not all(c.isalnum() or c == "_" for c in sync_schema):
            raise ValueError(f"unsafe sync_schema: {sync_schema!r}")
        with conn.cursor() as cur:
            cur.execute(f'SET search_path TO "{sync_schema}", public')  # type: ignore[arg-type]
        conn.commit()
        return conn


def _build_conninfo() -> str:
    host = os.environ["PGHOST"]
    port = os.environ.get("PGPORT", "5432")
    database = os.environ["PGDATABASE"]
    user = os.environ["PGUSER"]
    sslmode = os.environ.get("PGSSLMODE", "require")
    return f"dbname={database} user={user} host={host} port={port} sslmode={sslmode}"


# Pool is constructed at import time but not opened. The FastAPI lifespan
# explicitly calls `pool.open(wait=True, timeout=30.0)` so a misconfigured DB
# fails the app boot loudly instead of silently hanging requests.
pool: ConnectionPool = ConnectionPool(
    conninfo=_build_conninfo(),
    connection_class=OAuthConnection,
    min_size=1,
    max_size=10,
    max_lifetime=2700,  # 45 min: recycle before the 1h OAuth token expires
    open=False,
)


@asynccontextmanager
async def pool_lifespan():
    """Async context manager that opens/closes the pool. Used by FastAPI lifespan."""
    pool.open(wait=True, timeout=30.0)
    try:
        yield pool
    finally:
        pool.close()
