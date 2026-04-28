# Databricks notebook source
# MAGIC %md
# MAGIC # 03 — Score Users
# MAGIC
# MAGIC Heuristic churn-risk scorer (0-100) + 1-3 next-best-action recommendations
# MAGIC per user. No external ML deps so the demo stays reproducible.
# MAGIC
# MAGIC Outputs:
# MAGIC - `${catalog}.scored.user_scores`
# MAGIC - `${catalog}.scored.recommendations`
# MAGIC
# MAGIC Optional: when `include_writeback_signal=true`, decays risk for users
# MAGIC whose recommendations were recently accepted (closes the feedback loop).

# COMMAND ----------

dbutils.widgets.text("catalog", "main")
dbutils.widgets.text("schema_prefix", "lakebase_demo")
dbutils.widgets.text("include_writeback_signal", "false")
CATALOG = dbutils.widgets.get("catalog")
PREFIX = dbutils.widgets.get("schema_prefix")
INCLUDE_WRITEBACK = dbutils.widgets.get("include_writeback_signal").lower() == "true"

CURATED = f"{CATALOG}.{PREFIX}_curated"
SCORED = f"{CATALOG}.{PREFIX}_scored"

# COMMAND ----------

spark.sql(f"CREATE SCHEMA IF NOT EXISTS {SCORED}")

# Build the scorer expression. Weights chosen so a user with high tickets +
# payment failures + recent cancel intent + low engagement scores ~85+, while
# active steady users score ~10-20.
SCORER_SQL = f"""
WITH base AS (
  SELECT
    user_id,
    plan_tier,
    region,
    segment,
    sessions_30d,
    features_used_30d,
    support_tickets_30d,
    cancel_intent_30d,
    payment_failures_90d,
    days_since_last_event,
    tenure_days,
    mrr_current,
    subscription_status
  FROM {CURATED}.user_features
),
scored AS (
  SELECT
    *,
    LEAST(100, GREATEST(0,
      -- Engagement signal (low engagement = higher risk)
      CASE WHEN sessions_30d = 0 THEN 35
           WHEN sessions_30d < 3 THEN 22
           WHEN sessions_30d < 10 THEN 10
           ELSE 0 END
      -- Friction
      + LEAST(20, support_tickets_30d * 6)
      + LEAST(20, payment_failures_90d * 8)
      + cancel_intent_30d * 18
      -- Recency penalty
      + CASE WHEN days_since_last_event >= 14 THEN 12
             WHEN days_since_last_event >= 7  THEN 6
             ELSE 0 END
      -- Already-churned subs
      + CASE WHEN subscription_status = 'churned' THEN 50 ELSE 0 END
    )) AS churn_risk_score
  FROM base
)
SELECT
  user_id,
  plan_tier,
  region,
  segment,
  mrr_current,
  subscription_status,
  sessions_30d,
  features_used_30d,
  support_tickets_30d,
  cancel_intent_30d,
  payment_failures_90d,
  days_since_last_event,
  tenure_days,
  CAST(churn_risk_score AS INT) AS churn_risk_score,
  CASE
    WHEN churn_risk_score >= 70 THEN 'high'
    WHEN churn_risk_score >= 40 THEN 'medium'
    ELSE 'low'
  END AS engagement_tier,
  current_timestamp() AS last_scored_at
FROM scored
"""

# COMMAND ----------

# Apply writeback decay if requested
if INCLUDE_WRITEBACK:
    # Decay risk by 15 points for users whose recommendations were accepted in
    # the last 7 days (capped at 0). This shows the closed loop on stage.
    spark.sql(f"""
    CREATE OR REPLACE TEMP VIEW writeback_decay AS
    SELECT user_id, COUNT(*) * 15 AS decay
    FROM {SCORED}.user_actions_cdc
    WHERE decision = 'accepted'
      AND created_at >= current_timestamp() - INTERVAL 7 DAYS
    GROUP BY user_id
    """)
    SCORER_SQL = f"""
    WITH base AS ({SCORER_SQL})
    SELECT
      b.* EXCEPT (churn_risk_score),
      GREATEST(0, b.churn_risk_score - COALESCE(d.decay, 0)) AS churn_risk_score
    FROM base b
    LEFT JOIN writeback_decay d USING (user_id)
    """

spark.sql(f"CREATE OR REPLACE TABLE {SCORED}.user_scores AS {SCORER_SQL}")
spark.sql(f"ALTER TABLE {SCORED}.user_scores ALTER COLUMN user_id SET NOT NULL")
try:
    spark.sql(
        f"ALTER TABLE {SCORED}.user_scores "
        f"ADD CONSTRAINT user_scores_pk PRIMARY KEY (user_id)"
    )
except Exception as e:
    print(f"user_scores_pk: {e}")
print(f"{SCORED}.user_scores:", spark.table(f"{SCORED}.user_scores").count())

# COMMAND ----------

# Build recommendations: 1-3 per user, ordered by priority. Action vocabulary is
# fixed and domain-neutral so the demo translates to any vertical.
spark.sql(f"""
CREATE OR REPLACE TABLE {SCORED}.recommendations AS
WITH ranked AS (
  SELECT
    user_id,
    churn_risk_score,
    engagement_tier,
    payment_failures_90d,
    support_tickets_30d,
    cancel_intent_30d,
    days_since_last_event,
    plan_tier
  FROM {SCORED}.user_scores
),
candidates AS (
  -- Each row = a candidate recommendation. Filter on per-user fit.
  SELECT user_id, 'WAIVE_FEE' AS action_code, 'Waive next billing fee' AS action_label,
         'Recent payment failure detected' AS rationale, 1 AS priority
  FROM ranked WHERE payment_failures_90d > 0
  UNION ALL
  SELECT user_id, 'SCHEDULE_CHECKIN', 'Schedule check-in call',
         'High cancellation signal in last 30 days', 1
  FROM ranked WHERE cancel_intent_30d > 0
  UNION ALL
  SELECT user_id, 'OFFER_DISCOUNT', 'Offer 20% retention discount',
         'High churn risk with established tenure', 2
  FROM ranked WHERE churn_risk_score >= 60
  UNION ALL
  SELECT user_id, 'SUPPORT_FOLLOWUP', 'Follow up on open support ticket',
         'Multiple support tickets in last 30 days', 2
  FROM ranked WHERE support_tickets_30d >= 2
  UNION ALL
  SELECT user_id, 'REENGAGEMENT_EMAIL', 'Send reengagement email sequence',
         'No activity in 14+ days', 3
  FROM ranked WHERE days_since_last_event >= 14
  UNION ALL
  SELECT user_id, 'UPSELL_PREMIUM', 'Offer premium upgrade',
         'High engagement, room to grow', 3
  FROM ranked WHERE engagement_tier = 'low' AND plan_tier = 'basic' AND churn_risk_score < 40
)
SELECT
  uuid() AS recommendation_id,
  user_id,
  action_code,
  action_label,
  rationale,
  priority,
  current_timestamp() + INTERVAL 14 DAYS AS expires_at
FROM (
  SELECT *,
    ROW_NUMBER() OVER (PARTITION BY user_id ORDER BY priority) AS rn
  FROM candidates
)
WHERE rn <= 3
""")
spark.sql(
    f"ALTER TABLE {SCORED}.recommendations "
    f"ALTER COLUMN recommendation_id SET NOT NULL"
)
try:
    spark.sql(
        f"ALTER TABLE {SCORED}.recommendations "
        f"ADD CONSTRAINT recommendations_pk PRIMARY KEY (recommendation_id)"
    )
except Exception as e:
    print(f"recommendations_pk: {e}")
print(f"{SCORED}.recommendations:", spark.table(f"{SCORED}.recommendations").count())
