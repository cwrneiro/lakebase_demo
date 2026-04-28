# Databricks notebook source
# MAGIC %md
# MAGIC # 02 — Compute Features
# MAGIC
# MAGIC Aggregates `${catalog}.raw.events` + `subscriptions` + `users` into
# MAGIC `${catalog}.curated.user_features`, one row per user.

# COMMAND ----------

dbutils.widgets.text("catalog", "main")
dbutils.widgets.text("schema_prefix", "lakebase_demo")
CATALOG = dbutils.widgets.get("catalog")
PREFIX = dbutils.widgets.get("schema_prefix")
RAW = f"{CATALOG}.{PREFIX}_raw"
CURATED = f"{CATALOG}.{PREFIX}_curated"

# COMMAND ----------

spark.sql(f"CREATE SCHEMA IF NOT EXISTS {CURATED}")

spark.sql(f"""
CREATE OR REPLACE TABLE {CURATED}.user_features AS
WITH ev_30d AS (
  SELECT
    user_id,
    COUNT_IF(event_type = 'login') AS sessions_30d,
    COUNT(DISTINCT CASE WHEN event_type = 'feature_use' THEN event_id END) AS features_used_30d,
    COUNT_IF(event_type = 'support_ticket') AS support_tickets_30d,
    COUNT_IF(event_type = 'cancel_intent') AS cancel_intent_30d,
    MAX(event_ts) AS last_event_ts
  FROM {RAW}.events
  WHERE event_ts >= current_timestamp() - INTERVAL 30 DAYS
  GROUP BY user_id
),
ev_90d AS (
  SELECT
    user_id,
    COUNT_IF(event_type = 'payment_failure') AS payment_failures_90d
  FROM {RAW}.events
  WHERE event_ts >= current_timestamp() - INTERVAL 90 DAYS
  GROUP BY user_id
),
ev_all AS (
  SELECT
    user_id,
    MAX(event_ts) AS last_event_all_ts,
    COUNT_IF(event_type = 'login') AS lifetime_logins
  FROM {RAW}.events
  GROUP BY user_id
)
SELECT
  u.user_id,
  u.plan_tier,
  u.region,
  u.segment,
  u.signup_date,
  COALESCE(ev30.sessions_30d, 0) AS sessions_30d,
  COALESCE(ev30.features_used_30d, 0) AS features_used_30d,
  COALESCE(ev30.support_tickets_30d, 0) AS support_tickets_30d,
  COALESCE(ev30.cancel_intent_30d, 0) AS cancel_intent_30d,
  COALESCE(ev90.payment_failures_90d, 0) AS payment_failures_90d,
  DATEDIFF(current_date(), CAST(eva.last_event_all_ts AS DATE)) AS days_since_last_event,
  DATEDIFF(current_date(), u.signup_date) AS tenure_days,
  eva.lifetime_logins,
  s.mrr_usd AS mrr_current,
  s.status AS subscription_status
FROM {RAW}.users u
LEFT JOIN ev_30d ev30 USING (user_id)
LEFT JOIN ev_90d ev90 USING (user_id)
LEFT JOIN ev_all eva USING (user_id)
LEFT JOIN {RAW}.subscriptions s USING (user_id)
""")

n = spark.table(f"{CURATED}.user_features").count()
print(f"{CURATED}.user_features: {n} rows")

# Synced tables need a primary key on the source UC table.
spark.sql(f"ALTER TABLE {CURATED}.user_features ALTER COLUMN user_id SET NOT NULL")
try:
    spark.sql(
        f"ALTER TABLE {CURATED}.user_features "
        f"ADD CONSTRAINT user_features_pk PRIMARY KEY (user_id)"
    )
except Exception as e:
    print(f"user_features_pk: {e}")
