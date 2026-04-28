# Databricks notebook source
# MAGIC %md
# MAGIC # 01 — Generate Synthetic Data
# MAGIC
# MAGIC Generates ~5k users, ~500k events, and ~5k subscriptions for a generic B2C
# MAGIC subscription product. Output: `${catalog}.raw.{users,events,subscriptions}`.
# MAGIC
# MAGIC Idempotent: tables are overwritten on each run.

# COMMAND ----------

# MAGIC %pip install --quiet mimesis polars

# COMMAND ----------

dbutils.library.restartPython()

# COMMAND ----------

dbutils.widgets.text("catalog", "main")
dbutils.widgets.text("schema_prefix", "lakebase_demo")
CATALOG = dbutils.widgets.get("catalog")
PREFIX = dbutils.widgets.get("schema_prefix")
RAW = f"{CATALOG}.{PREFIX}_raw"

N_USERS = 5_000
EVENTS_PER_USER_AVG = 100
SEED = 42

# COMMAND ----------

import random
import uuid
from datetime import datetime, timedelta, timezone

import polars as pl
from mimesis import Generic, Person
from mimesis.locales import Locale

random.seed(SEED)
gen = Generic(locale=Locale.EN, seed=SEED)
person = Person(locale=Locale.EN, seed=SEED)

PLAN_TIERS = ["basic", "standard", "premium"]
PLAN_MRR = {"basic": 9.99, "standard": 24.99, "premium": 49.99}
REGIONS = ["NA", "EU", "LATAM", "APAC"]
AGE_BANDS = ["18-24", "25-34", "35-44", "45-54", "55-64", "65+"]
SEGMENTS = ["individual", "family", "business"]

EVENT_TYPES_WEIGHTED = [
    ("login", 0.55),
    ("feature_use", 0.30),
    ("support_ticket", 0.04),
    ("payment_failure", 0.02),
    ("cancel_intent", 0.02),
    ("plan_change", 0.07),
]

now = datetime.now(timezone.utc)

# COMMAND ----------

# Build users
users = []
for _ in range(N_USERS):
    signup = now - timedelta(days=random.randint(15, 1200))
    users.append(
        {
            "user_id": str(uuid.uuid4()),
            "signup_date": signup.date(),
            "plan_tier": random.choices(PLAN_TIERS, weights=[0.5, 0.35, 0.15])[0],
            "region": random.choice(REGIONS),
            "age_band": random.choice(AGE_BANDS),
            "segment": random.choices(SEGMENTS, weights=[0.7, 0.2, 0.1])[0],
        }
    )

users_df = pl.DataFrame(users)
print(f"users: {len(users_df)}")

# COMMAND ----------

# Build subscriptions
subs = []
for u in users:
    plan = u["plan_tier"]
    started = datetime.combine(u["signup_date"], datetime.min.time(), tzinfo=timezone.utc)
    status = random.choices(["active", "paused", "churned"], weights=[0.78, 0.07, 0.15])[0]
    ended = None
    if status == "churned":
        ended = started + timedelta(days=random.randint(30, 900))
        if ended > now:
            ended = now - timedelta(days=random.randint(1, 60))
    subs.append(
        {
            "user_id": u["user_id"],
            "plan": plan,
            "mrr_usd": PLAN_MRR[plan],
            "status": status,
            "started_at": started,
            "ended_at": ended,
        }
    )

subs_df = pl.DataFrame(subs)
print(f"subscriptions: {len(subs_df)}")

# COMMAND ----------

# Build events (skewed: more events for engaged users, fewer for at-risk)
event_types = [t for t, _ in EVENT_TYPES_WEIGHTED]
event_weights = [w for _, w in EVENT_TYPES_WEIGHTED]

events = []
for u in users:
    # Vary intensity per user — creates risk signal
    intensity = max(0.05, random.gauss(1.0, 0.5))
    n_events = max(0, int(EVENTS_PER_USER_AVG * intensity))
    signup = datetime.combine(u["signup_date"], datetime.min.time(), tzinfo=timezone.utc)
    days_active = max(1, (now - signup).days)
    for _ in range(n_events):
        ts = signup + timedelta(
            seconds=random.randint(0, days_active * 86400),
        )
        event_type = random.choices(event_types, weights=event_weights)[0]
        events.append(
            {
                "event_id": str(uuid.uuid4()),
                "user_id": u["user_id"],
                "event_ts": ts,
                "event_type": event_type,
            }
        )

events_df = pl.DataFrame(events)
print(f"events: {len(events_df)}")

# COMMAND ----------

# Write to UC. Use spark.createDataFrame(<polars>.to_pandas()) since pyspark on
# serverless may not have direct polars adapter; pandas conversion is reliable.
def write_uc(pdf: pl.DataFrame, table: str) -> None:
    sdf = spark.createDataFrame(pdf.to_pandas())
    full = f"{RAW}.{table}"
    (
        sdf.write
        .mode("overwrite")
        .option("overwriteSchema", "true")
        .saveAsTable(full)
    )
    print(f"wrote {full}: {sdf.count()} rows")

# Synced tables in Lakebase need primary keys — declare them on the UC tables.
spark.sql(f"CREATE SCHEMA IF NOT EXISTS {RAW}")

write_uc(users_df, "users")
spark.sql(f"ALTER TABLE {RAW}.users ALTER COLUMN user_id SET NOT NULL")
# PK may already exist on re-runs; tolerate that
try:
    spark.sql(f"ALTER TABLE {RAW}.users ADD CONSTRAINT users_pk PRIMARY KEY (user_id)")
except Exception as e:
    print(f"users_pk: {e}")

write_uc(subs_df, "subscriptions")
write_uc(events_df, "events")
