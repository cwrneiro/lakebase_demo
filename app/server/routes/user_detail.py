"""GET /api/users/{user_id} — full detail view for one user."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Path

from server.db import pool
from server.models import Action, Recommendation, UserDetail

router = APIRouter()


@router.get("/users/{user_id}", response_model=UserDetail)
def get_user(user_id: str = Path(..., min_length=1)) -> UserDetail:
    with pool.connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT u.user_id,
                       u.plan_tier,
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

            cur.execute(
                """
                SELECT recommendation_id,
                       user_id,
                       action_code,
                       action_label,
                       rationale,
                       priority,
                       expires_at
                  FROM recommendations
                 WHERE user_id = %s
                 ORDER BY priority ASC
                """,
                (user_id,),
            )
            rec_rows = cur.fetchall()

            cur.execute(
                """
                SELECT action_id::text,
                       user_id,
                       recommendation_id,
                       decision,
                       notes,
                       operator,
                       created_at
                  FROM user_actions
                 WHERE user_id = %s
                 ORDER BY created_at DESC
                 LIMIT 20
                """,
                (user_id,),
            )
            act_rows = cur.fetchall()

    recommendations = [
        Recommendation(
            recommendation_id=r[0],
            user_id=r[1],
            action_code=r[2],
            action_label=r[3],
            rationale=r[4],
            priority=r[5],
            expires_at=r[6],
        )
        for r in rec_rows
    ]
    actions = [
        Action(
            action_id=a[0],
            user_id=a[1],
            recommendation_id=a[2],
            decision=a[3],
            notes=a[4],
            operator=a[5],
            created_at=a[6],
        )
        for a in act_rows
    ]

    return UserDetail(
        user_id=row[0],
        plan_tier=row[1],
        region=row[2],
        segment=row[3],
        signup_date=row[4],
        churn_risk_score=row[5],
        engagement_tier=row[6],
        mrr_current=row[7],
        subscription_status=row[8],
        sessions_30d=row[9],
        support_tickets_30d=row[10],
        payment_failures_90d=row[11],
        days_since_last_event=row[12],
        tenure_days=row[13],
        last_scored_at=row[14],
        recommendations=recommendations,
        recent_actions=actions,
    )
