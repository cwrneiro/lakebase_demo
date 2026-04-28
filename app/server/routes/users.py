"""GET /api/users — paginated, sortable, optionally tier-filtered queue."""

from __future__ import annotations

from fastapi import APIRouter, Query

from server.db import pool
from server.models import SortKey, UserListResponse, UserSummary

router = APIRouter()

# Whitelist sort keys so we can interpolate them into the SQL safely.
_SORT_SQL: dict[str, str] = {
    "risk_desc": "s.churn_risk_score DESC NULLS LAST, u.user_id ASC",
    "risk_asc": "s.churn_risk_score ASC NULLS LAST, u.user_id ASC",
    "tenure_desc": "s.tenure_days DESC NULLS LAST, u.user_id ASC",
}


@router.get("/users", response_model=UserListResponse)
def list_users(
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    sort: SortKey = Query(default="risk_desc"),
    tier: str | None = Query(default=None, description="Optional plan_tier filter"),
) -> UserListResponse:
    order_by = _SORT_SQL[sort]

    where_clauses: list[str] = []
    params: list[object] = []
    if tier:
        where_clauses.append("u.plan_tier = %s")
        params.append(tier)
    where_sql = ("WHERE " + " AND ".join(where_clauses)) if where_clauses else ""

    # Top recommendation per user: priority ASC = highest priority first.
    # Most-recent action per user: created_at DESC.
    list_sql = f"""
        WITH top_rec AS (
            SELECT DISTINCT ON (user_id)
                   user_id, action_label, priority
              FROM recommendations
             ORDER BY user_id, priority ASC
        ),
        last_act AS (
            SELECT DISTINCT ON (user_id)
                   user_id, created_at
              FROM user_actions
             ORDER BY user_id, created_at DESC
        )
        SELECT u.user_id,
               u.plan_tier,
               u.region,
               u.segment,
               s.churn_risk_score,
               s.engagement_tier,
               r.action_label AS top_recommendation,
               a.created_at   AS last_action_at
          FROM users u
          LEFT JOIN user_scores    s ON s.user_id = u.user_id
          LEFT JOIN top_rec        r ON r.user_id = u.user_id
          LEFT JOIN last_act       a ON a.user_id = u.user_id
          {where_sql}
         ORDER BY {order_by}
         LIMIT %s OFFSET %s
    """

    count_sql = f"SELECT count(*) FROM users u {where_sql}"

    with pool.connection() as conn:
        with conn.cursor() as cur:
            cur.execute(count_sql, params)
            total_row = cur.fetchone()
            total = int(total_row[0]) if total_row else 0

            cur.execute(list_sql, [*params, limit, offset])
            rows = cur.fetchall()

    items = [
        UserSummary(
            user_id=row[0],
            plan_tier=row[1],
            region=row[2],
            segment=row[3],
            churn_risk_score=row[4],
            engagement_tier=row[5],
            top_recommendation=row[6],
            last_action_at=row[7],
        )
        for row in rows
    ]
    return UserListResponse(items=items, total=total)
