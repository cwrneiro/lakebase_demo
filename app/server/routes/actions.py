"""POST /api/users/{user_id}/actions — operator decision write-back."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Path

from server.db import pool
from server.deps import operator_identity
from server.models import Action, ActionCreate

router = APIRouter()


@router.post("/users/{user_id}/actions", response_model=Action, status_code=201)
def create_action(
    payload: ActionCreate,
    user_id: str = Path(..., min_length=1),
    operator: str = Depends(operator_identity),
) -> Action:
    # Confirm the user exists so we don't accumulate orphaned writebacks. The
    # `users` table is a synced read-only mirror of UC, so this is safe to
    # query on the hot path.
    with pool.connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT 1 FROM users WHERE user_id = %s", (user_id,))
            if cur.fetchone() is None:
                raise HTTPException(status_code=404, detail=f"user {user_id!r} not found")

            cur.execute(
                """
                INSERT INTO user_actions (
                    user_id, recommendation_id, decision, notes, operator
                )
                VALUES (%s, %s, %s, %s, %s)
                RETURNING action_id::text,
                          user_id,
                          recommendation_id,
                          decision,
                          notes,
                          operator,
                          created_at
                """,
                (
                    user_id,
                    payload.recommendation_id,
                    payload.decision,
                    payload.notes,
                    operator,
                ),
            )
            row = cur.fetchone()
        conn.commit()

    assert row is not None  # RETURNING guarantees one row
    return Action(
        action_id=row[0],
        user_id=row[1],
        recommendation_id=row[2],
        decision=row[3],
        notes=row[4],
        operator=row[5],
        created_at=row[6],
    )
