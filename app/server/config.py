"""Dual-mode auth helpers for the Databricks App.

In Databricks Apps the runtime injects service principal credentials and a
bare-hostname `DATABRICKS_HOST`. Locally we use a CLI profile (the
`DATABRICKS_PROFILE` env var) and rely on the SDK to assemble the host URL.
"""

from __future__ import annotations

import os

from databricks.sdk import WorkspaceClient

# Databricks Apps runtime sets DATABRICKS_APP_NAME. Treat its presence as the
# canonical signal that we are running inside the App container.
IS_DATABRICKS_APP: bool = bool(os.environ.get("DATABRICKS_APP_NAME"))


def get_workspace_client() -> WorkspaceClient:
    """Return a WorkspaceClient authenticated for the current environment.

    - In Databricks Apps: defaults pick up the auto-injected service principal.
    - Locally: reads the configured CLI profile (DATABRICKS_PROFILE).
    """
    if IS_DATABRICKS_APP:
        return WorkspaceClient()
    profile = os.environ.get("DATABRICKS_PROFILE", "DEFAULT")
    return WorkspaceClient(profile=profile)


def get_workspace_host() -> str:
    """Return the workspace host URL with an `https://` scheme."""
    if IS_DATABRICKS_APP:
        host = os.environ.get("DATABRICKS_HOST", "")
        if host and not host.startswith("http"):
            host = f"https://{host}"
        return host
    return get_workspace_client().config.host


def get_oauth_token() -> str | None:
    """Return an OAuth bearer token for the current identity, if available.

    Prefers the SDK's `config.token` (set when using PAT auth); falls back to
    `config.authenticate()`, which returns an `Authorization: Bearer <token>`
    header for OAuth/U2M flows.
    """
    cfg = get_workspace_client().config
    if cfg.token:
        return cfg.token
    auth_headers = cfg.authenticate()
    if auth_headers and "Authorization" in auth_headers:
        return auth_headers["Authorization"].replace("Bearer ", "")
    return None
