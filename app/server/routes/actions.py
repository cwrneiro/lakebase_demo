"""POST /api/users/{user_id}/actions — operator decision write-back."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Path, Request, Response

from server.db import pool
from server.deps import operator_identity
from server.models import Action, ActionCreate

router = APIRouter()


@router.post("/users/{user_id}/actions", response_model=Action, status_code=201)
def create_action(
    payload: ActionCreate,
    request: Request,
    response: Response,
    user_id: str = Path(..., min_length=1),
    operator: str = Depends(operator_identity),
) -> Action:
    # Optional idempotency: if the client repeats a request with the same
    # `Idempotency-Key` header we return the original row instead of writing a
    # second user_action. Backed by a partial unique index on
    # `user_actions(idempotency_key) WHERE idempotency_key IS NOT NULL`.
    idempotency_key = request.headers.get("Idempotency-Key")

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
                    user_id, recommendation_id, decision, notes, operator, idempotency_key
                )
                VALUES (%s, %s, %s, %s, %s, %s)
                ON CONFLICT (idempotency_key) WHERE idempotency_key IS NOT NULL
                DO NOTHING
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
                    idempotency_key,
                ),
            )
            row = cur.fetchone()

            if row is None:
                # Conflict on idempotency_key: caller is replaying. Return the
                # original row with HTTP 200 so the client sees a successful
                # outcome without a duplicate write.
                assert idempotency_key is not None  # only path that suppresses RETURNING
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
                    WHERE idempotency_key = %s
                    """,
                    (idempotency_key,),
                )
                row = cur.fetchone()
                if row is None:
                    # Should be unreachable: ON CONFLICT fired but the row is
                    # gone. Treat as a server error rather than silently 500ing
                    # on the assert below.
                    raise HTTPException(
                        status_code=500,
                        detail="idempotency conflict but original row not found",
                    )
                response.status_code = 200
        conn.commit()

    return Action(
        action_id=row[0],
        user_id=row[1],
        recommendation_id=row[2],
        decision=row[3],
        notes=row[4],
        operator=row[5],
        created_at=row[6],
    )
