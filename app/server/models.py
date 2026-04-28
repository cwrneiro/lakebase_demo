"""Pydantic models exchanged between the FastAPI backend and the React UI."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field

Decision = Literal["accepted", "dismissed", "snoozed"]
SortKey = Literal["risk_desc", "risk_asc", "tenure_desc"]


class Recommendation(BaseModel):
    recommendation_id: str
    user_id: str
    action_code: str
    action_label: str
    rationale: str | None = None
    priority: int
    expires_at: datetime | None = None


class Action(BaseModel):
    action_id: str
    user_id: str
    recommendation_id: str | None = None
    decision: Decision
    notes: str | None = None
    operator: str
    created_at: datetime


class UserSummary(BaseModel):
    """Row in the operator queue list."""

    user_id: str
    plan_tier: str | None = None
    region: str | None = None
    segment: str | None = None
    churn_risk_score: int | None = None
    engagement_tier: str | None = None
    top_recommendation: str | None = None
    last_action_at: datetime | None = None


class UserListResponse(BaseModel):
    items: list[UserSummary]
    total: int


class UserDetail(BaseModel):
    """All score fields plus recommendations and recent actions for one user."""

    # Identity / segmentation (from `users`)
    user_id: str
    plan_tier: str | None = None
    region: str | None = None
    segment: str | None = None
    signup_date: date | None = None

    # Score breakdown (from `user_scores`)
    churn_risk_score: int | None = None
    engagement_tier: str | None = None
    mrr_current: Decimal | None = None
    subscription_status: str | None = None
    sessions_30d: int | None = None
    support_tickets_30d: int | None = None
    payment_failures_90d: int | None = None
    days_since_last_event: int | None = None
    tenure_days: int | None = None
    last_scored_at: datetime | None = None

    recommendations: list[Recommendation] = Field(default_factory=list)
    recent_actions: list[Action] = Field(default_factory=list)


class ActionCreate(BaseModel):
    recommendation_id: str | None = None
    decision: Decision
    notes: str | None = None


class ExplainResponse(BaseModel):
    user_id: str
    rationale: str
    model: str


class RescoreResponse(BaseModel):
    run_id: int
    run_page_url: str | None = None
    operator: str | None = None
