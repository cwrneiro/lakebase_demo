"""FastAPI dependencies."""

from __future__ import annotations

from fastapi import Header


def operator_identity(
    x_forwarded_email: str | None = Header(default=None, alias="X-Forwarded-Email"),
    x_forwarded_user: str | None = Header(default=None, alias="X-Forwarded-User"),
) -> str:
    """Resolve the operator email/identity for write-back attribution.

    Databricks Apps forwards the authenticated user's identity in
    `X-Forwarded-Email` (and `X-Forwarded-User` as a fallback). When running
    locally without a proxy, attribute writes to a stable placeholder so we
    never store empty operators (the DB column is NOT NULL).
    """
    if x_forwarded_email:
        return x_forwarded_email
    if x_forwarded_user:
        return x_forwarded_user
    return "local-dev@example.com"
