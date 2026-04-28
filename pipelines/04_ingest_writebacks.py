# Databricks notebook source
# MAGIC %md
# MAGIC # 04 — Ingest Writebacks (Lakebase → UC)
# MAGIC
# MAGIC Pulls newly-written rows from Lakebase `user_actions` (the operator
# MAGIC writeback table) into `${catalog}.scored.user_actions_cdc` for closed-loop
# MAGIC learning. Runs every minute via the `writeback_ingest_job`.
# MAGIC
# MAGIC Uses the workspace SP credentials (the job's run-as identity) to mint a
# MAGIC short-lived OAuth token, then connects with `psycopg`.

# COMMAND ----------

# MAGIC %pip install --quiet "psycopg[binary]" "databricks-sdk>=0.81.0"

# COMMAND ----------

dbutils.library.restartPython()

# COMMAND ----------

dbutils.widgets.text("catalog", "main")
dbutils.widgets.text("schema_prefix", "lakebase_demo")
dbutils.widgets.text("lakebase_project_id", "lakebase-demo")
dbutils.widgets.text("lakebase_database", "app")

CATALOG = dbutils.widgets.get("catalog")
PREFIX = dbutils.widgets.get("schema_prefix")
PROJECT_ID = dbutils.widgets.get("lakebase_project_id")
DATABASE = dbutils.widgets.get("lakebase_database")
SCORED = f"{CATALOG}.{PREFIX}_scored"

ENDPOINT_PATH = f"projects/{PROJECT_ID}/branches/production/endpoints/primary"

# COMMAND ----------

import psycopg
from databricks.sdk import WorkspaceClient
from pyspark.sql import functions as F
from pyspark.sql.types import (
    StringType,
    StructField,
    StructType,
    TimestampType,
)

w = WorkspaceClient()

# Ensure target table exists
spark.sql(f"""
CREATE TABLE IF NOT EXISTS {SCORED}.user_actions_cdc (
  action_id STRING,
  user_id STRING,
  recommendation_id STRING,
  decision STRING,
  notes STRING,
  operator STRING,
  created_at TIMESTAMP
) USING DELTA
""")

# COMMAND ----------

# High-watermark: last created_at we have in UC
hw_row = spark.sql(
    f"SELECT MAX(created_at) AS hw FROM {SCORED}.user_actions_cdc"
).collect()[0]
high_watermark = hw_row["hw"]
print(f"high watermark: {high_watermark}")

# COMMAND ----------

# Get connection details
endpoints_resp = list(w.postgres.list_endpoints(parent=f"projects/{PROJECT_ID}/branches/production"))
host = endpoints_resp[0].status.hosts.host
cred = w.postgres.generate_database_credential(endpoint=ENDPOINT_PATH)
token = cred.token
me = w.current_user.me().user_name

conninfo = (
    f"host={host} port=5432 dbname={DATABASE} "
    f"user={me} sslmode=require"
)

# COMMAND ----------

# Pull new rows
where_clause = "WHERE created_at > %s" if high_watermark is not None else ""
params = (high_watermark,) if high_watermark is not None else ()

new_rows = []
with psycopg.connect(conninfo, password=token) as conn:
    with conn.cursor() as cur:
        cur.execute(
            f"""
            SELECT
              action_id::text,
              user_id,
              recommendation_id,
              decision,
              notes,
              operator,
              created_at
            FROM user_actions
            {where_clause}
            ORDER BY created_at
            """,
            params,
        )
        new_rows = cur.fetchall()

print(f"new rows: {len(new_rows)}")

# COMMAND ----------

if new_rows:
    schema = StructType([
        StructField("action_id", StringType(), False),
        StructField("user_id", StringType(), False),
        StructField("recommendation_id", StringType(), True),
        StructField("decision", StringType(), False),
        StructField("notes", StringType(), True),
        StructField("operator", StringType(), False),
        StructField("created_at", TimestampType(), False),
    ])
    sdf = spark.createDataFrame(new_rows, schema=schema)
    (sdf.write.mode("append").saveAsTable(f"{SCORED}.user_actions_cdc"))
    print(f"appended {sdf.count()} rows to {SCORED}.user_actions_cdc")
else:
    print("no new rows; nothing to do")
