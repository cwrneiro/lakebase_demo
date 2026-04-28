export type Decision = 'accepted' | 'dismissed' | 'snoozed'
export type SortKey = 'risk_desc' | 'risk_asc' | 'tenure_desc'

export interface Recommendation {
  recommendation_id: string
  user_id: string
  action_code: string
  action_label: string
  rationale: string | null
  priority: number
  expires_at: string | null
}

export interface Action {
  action_id: string
  user_id: string
  recommendation_id: string | null
  decision: Decision
  notes: string | null
  operator: string
  created_at: string
}

export interface UserSummary {
  user_id: string
  plan_tier: string | null
  region: string | null
  segment: string | null
  churn_risk_score: number | null
  engagement_tier: string | null
  top_recommendation: string | null
  last_action_at: string | null
}

export interface UserListResponse {
  items: UserSummary[]
  total: number
}

export interface UserDetail {
  user_id: string
  plan_tier: string | null
  region: string | null
  segment: string | null
  signup_date: string | null
  churn_risk_score: number | null
  engagement_tier: string | null
  mrr_current: string | null
  subscription_status: string | null
  sessions_30d: number | null
  support_tickets_30d: number | null
  payment_failures_90d: number | null
  days_since_last_event: number | null
  tenure_days: number | null
  last_scored_at: string | null
  recommendations: Recommendation[]
  recent_actions: Action[]
}

export interface ActionCreate {
  recommendation_id?: string | null
  decision: Decision
  notes?: string | null
}

export interface ExplainResponse {
  user_id: string
  rationale: string
  model: string
}

export interface RescoreResponse {
  run_id: number
  run_page_url: string | null
  operator: string | null
}
