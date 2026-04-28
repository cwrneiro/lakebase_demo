# Databricks notebook source
# MAGIC %md
# MAGIC # 03 — Score Users
# MAGIC
# MAGIC Loads the LightGBM churn model registered by `03a_train_churn_model.py`
# MAGIC (UC alias `champion`) and produces a 0-100 churn-risk score per user,
# MAGIC plus 1-3 next-best-action recommendations.
# MAGIC
# MAGIC Outputs:
# MAGIC - `${catalog}.${schema_prefix}_scored.user_scores`
# MAGIC - `${catalog}.${schema_prefix}_scored.recommendations`
# MAGIC
# MAGIC Optional: when `include_writeback_signal=true`, decays risk for users
# MAGIC whose recommendations were recently accepted (closes the feedback loop)
# MAGIC by 15 points per accepted recommendation in the trailing 7 days.

# COMMAND ----------

# MAGIC %pip install --quiet lightgbm mlflow

# COMMAND ----------

dbutils.library.restartPython()

# COMMAND ----------

dbutils.widgets.text("catalog", "main")
dbutils.widgets.text("schema_prefix", "lakebase_demo")
dbutils.widgets.text("include_writeback_signal", "false")
CATALOG = dbutils.widgets.get("catalog")
PREFIX = dbutils.widgets.get("schema_prefix")
INCLUDE_WRITEBACK = dbutils.widgets.get("include_writeback_signal").lower() == "true"

CURATED = f"{CATALOG}.{PREFIX}_curated"
SCORED = f"{CATALOG}.{PREFIX}_scored"
MODEL_URI = f"models:/{CATALOG}.{PREFIX}_curated.churn_model@champion"

# COMMAND ----------

import mlflow
import numpy as np
import pandas as pd

# Use UC for model registry resolution.
mlflow.set_registry_uri("databricks-uc")

spark.sql(f"CREATE SCHEMA IF NOT EXISTS {SCORED}")

# COMMAND ----------

# Pull the feature table into pandas for inference. The training notebook
# (`03a_train_churn_model.py`) uses the same shape so the model's signature
# matches; we just have to apply the same preprocessing (drop identifier +
# label-derived columns, cast string columns to category).
features_pdf = spark.table(f"{CURATED}.user_features").toPandas()
print(f"loaded {len(features_pdf)} feature rows")

DROP_FROM_X = ["user_id", "subscription_status", "signup_date"]
X = features_pdf.drop(columns=[c for c in DROP_FROM_X if c in features_pdf.columns]).copy()
for c in X.columns:
    if X[c].dtype == "object":
        X[c] = X[c].astype("category")
    else:
        X[c] = pd.to_numeric(X[c], errors="coerce").fillna(0)

# COMMAND ----------

# Load the registered model by alias and predict probabilities. `pyfunc`
# returns the raw LightGBM output for binary objectives — that's the
# probability of the positive (churned) class, in [0, 1]. Multiply by 100
# and clip to keep the score range the frontend assumes (UI thresholds:
# <40 low, 40-69 medium, >=70 high).
model = mlflow.pyfunc.load_model(MODEL_URI)
print(f"loaded {MODEL_URI}")

raw_scores = model.predict(X)
# Some flavors return a 2-d array (n, 1) or (n, 2); collapse to 1-d positive
# probabilities for the binary-classifier case.
arr = np.asarray(raw_scores)
if arr.ndim == 2:
    arr = arr[:, -1] if arr.shape[1] > 1 else arr[:, 0]
churn_prob = arr.astype(float)

scores = np.clip(np.round(churn_prob * 100.0), 0, 100).astype(int)

scored_pdf = features_pdf[
    [
        "user_id",
        "plan_tier",
        "region",
        "segment",
        "mrr_current",
        "subscription_status",
        "sessions_30d",
        "features_used_30d",
        "support_tickets_30d",
        "cancel_intent_30d",
        "payment_failures_90d",
        "days_since_last_event",
        "tenure_days",
    ]
].copy()
scored_pdf["churn_risk_score"] = scores

# Persist the model-derived score as a staging table the SQL below joins on.
# Round-tripping through Spark keeps the rest of the pipeline (joins, decay,
# recommendations) on the engine where it scales.
spark.createDataFrame(scored_pdf).createOrReplaceTempView("model_scores")

# COMMAND ----------

# Apply writeback decay if requested. Operates on `churn_risk_score` from the
# model — same column name, same 0-100 range — so the decay logic doesn't care
# whether the score came from the LightGBM model or the previous heuristic.
if INCLUDE_WRITEBACK:
    # Decay risk by 15 points per accepted recommendation in the last 7 days
    # (capped at 0). This shows the closed loop on stage.
    spark.sql(f"""
    CREATE OR REPLACE TEMP VIEW writeback_decay AS
    SELECT user_id, COUNT(*) * 15 AS decay
    FROM {SCORED}.user_actions_cdc
    WHERE decision = 'accepted'
      AND created_at >= current_timestamp() - INTERVAL 7 DAYS
    GROUP BY user_id
    """)
    decay_join_sql = """
      LEFT JOIN writeback_decay d USING (user_id)
    """
    score_expr = "GREATEST(0, m.churn_risk_score - COALESCE(d.decay, 0))"
else:
    decay_join_sql = ""
    score_expr = "m.churn_risk_score"

spark.sql(f"""
CREATE OR REPLACE TABLE {SCORED}.user_scores AS
SELECT
  m.user_id,
  m.plan_tier,
  m.region,
  m.segment,
  m.mrr_current,
  m.subscription_status,
  m.sessions_30d,
  m.features_used_30d,
  m.support_tickets_30d,
  m.cancel_intent_30d,
  m.payment_failures_90d,
  m.days_since_last_event,
  m.tenure_days,
  CAST({score_expr} AS INT) AS churn_risk_score,
  CASE
    WHEN {score_expr} >= 70 THEN 'high'
    WHEN {score_expr} >= 40 THEN 'medium'
    ELSE 'low'
  END AS engagement_tier,
  current_timestamp() AS last_scored_at
FROM model_scores m
{decay_join_sql}
""")
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
# fixed and domain-neutral so the demo translates to any vertical. This block
# is unchanged in shape from the heuristic version — it operates on the final
# `churn_risk_score` column, regardless of how that score was computed.
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
