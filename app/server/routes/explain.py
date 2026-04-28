"""POST /api/users/{user_id}/explain — Foundation Model rationale panel."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Path

from server.db import pool
from server.llm import explain_score, get_serving_endpoint, is_llm_enabled
from server.models import ExplainResponse

router = APIRouter()


@router.post("/users/{user_id}/explain", response_model=ExplainResponse)
def explain_user(user_id: str = Path(..., min_length=1)) -> ExplainResponse:
    if not is_llm_enabled():
        raise HTTPException(
            status_code=503,
            detail="LLM explain panel is disabled (set ENABLE_LLM_EXPLAIN=true to enable).",
        )

    with pool.connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT u.plan_tier,
                       u.region,
                       u.segment,
                       u.signup_date,
                       s.churn_risk_score,
                       s.engagement_tier,
                       s.mrr_current,
                       s.subscription_status,
                       s.sessions_30d,
                       s.support_tickets_30d,
                       s.payment_failures_90d,
                       s.days_since_last_event,
                       s.tenure_days,
                       s.last_scored_at
                  FROM users u
                  LEFT JOIN user_scores s ON s.user_id = u.user_id
                 WHERE u.user_id = %s
                """,
                (user_id,),
            )
            row = cur.fetchone()
            if row is None:
                raise HTTPException(status_code=404, detail=f"user {user_id!r} not found")

    context = {
        "plan_tier": row[0],
        "region": row[1],
        "segment": row[2],
        "signup_date": row[3].isoformat() if row[3] is not None else None,
        "churn_risk_score": row[4],
        "engagement_tier": row[5],
        "mrr_current": str(row[6]) if row[6] is not None else None,
        "subscription_status": row[7],
        "sessions_30d": row[8],
        "support_tickets_30d": row[9],
        "payment_failures_90d": row[10],
        "days_since_last_event": row[11],
        "tenure_days": row[12],
        "last_scored_at": row[13].isoformat() if row[13] is not None else None,
    }

    try:
        rationale = explain_score(context)
    except Exception as exc:  # pragma: no cover -- propagate as a clean 502
        raise HTTPException(
            status_code=502,
            detail=f"Foundation Model API call failed: {exc}",
        ) from exc

    return ExplainResponse(user_id=user_id, rationale=rationale, model=get_serving_endpoint())
