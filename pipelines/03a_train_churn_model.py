# Databricks notebook source
# MAGIC %md
# MAGIC # 03a — Train Churn Model (LightGBM + MLflow + UC Registry)
# MAGIC
# MAGIC Trains a LightGBM binary classifier on `${catalog}.${schema_prefix}_curated.user_features`
# MAGIC and registers the resulting model under
# MAGIC `${catalog}.${schema_prefix}_curated.churn_model` in the Unity Catalog
# MAGIC model registry, with the `champion` alias pointing at the new version.
# MAGIC
# MAGIC The downstream notebook `03_score_users.py` loads
# MAGIC `models:/<catalog>.<schema_prefix>_curated.churn_model@champion` to
# MAGIC produce churn-risk scores in place of the previous SQL heuristic.
# MAGIC
# MAGIC ### Honest caveat about the label
# MAGIC The training label is `subscriptions.status == 'churned'` from the
# MAGIC synthetic-data generator (`pipelines/01_generate_synthetic_data.py`).
# MAGIC That status is sampled randomly with fixed weights — it is NOT a
# MAGIC ground-truth churn outcome derived from feature behavior. A production
# MAGIC model would train on actual historical churn outcomes (e.g. users whose
# MAGIC subscriptions ended in a labelling window after a feature snapshot).
# MAGIC The demo value of this notebook is the architecture (training notebook
# MAGIC → MLflow → UC registry → loaded-by-alias at scoring time), not the
# MAGIC predictive accuracy of the resulting model.

# COMMAND ----------

# MAGIC %pip install --quiet lightgbm mlflow

# COMMAND ----------

dbutils.library.restartPython()

# COMMAND ----------

dbutils.widgets.text("catalog", "main")
dbutils.widgets.text("schema_prefix", "lakebase_demo")
CATALOG = dbutils.widgets.get("catalog")
PREFIX = dbutils.widgets.get("schema_prefix")
CURATED = f"{CATALOG}.{PREFIX}_curated"
MODEL_NAME = f"{CATALOG}.{PREFIX}_curated.churn_model"
MODEL_ALIAS = "champion"

# COMMAND ----------

import lightgbm as lgb
import mlflow
import mlflow.lightgbm
import pandas as pd
from sklearn.metrics import classification_report, roc_auc_score
from sklearn.model_selection import train_test_split

# Use the workspace's default tracking URI (already configured in the runtime).
# Point the model registry at Unity Catalog so `register_model` lands under
# the three-level name `<catalog>.<schema>.<model>`.
mlflow.set_registry_uri("databricks-uc")

# COMMAND ----------

# Load features. The label comes from `subscription_status` which mirrors
# `subscriptions.status` from the raw layer — see the caveat at the top of
# this notebook.
features_sdf = spark.table(f"{CURATED}.user_features")
pdf = features_sdf.toPandas()
print(f"loaded {len(pdf)} feature rows from {CURATED}.user_features")

# Binary target: 1 when the subscription has churned, 0 otherwise (active/paused).
pdf["label"] = (pdf["subscription_status"] == "churned").astype(int)
positive_rate = pdf["label"].mean()
print(f"positive (churned) rate: {positive_rate:.3f}")

# COMMAND ----------

# Build X / y. Drop user_id (identifier, not predictive) and drop the columns
# we used to derive the label (status) plus pure-identifier date columns.
DROP_COLS = ["user_id", "subscription_status", "label", "signup_date"]
y = pdf["label"].values
X = pdf.drop(columns=[c for c in DROP_COLS if c in pdf.columns]).copy()

# Categorical handling: low-cardinality string columns (plan_tier, region,
# segment) get LightGBM's native categorical support via pandas `category`
# dtype. Numeric columns are passed through.
categorical_cols = [c for c in X.columns if X[c].dtype == "object"]
for c in categorical_cols:
    X[c] = X[c].astype("category")

# Coerce any remaining object columns (none expected) and fill numeric NaNs.
numeric_cols = [c for c in X.columns if c not in categorical_cols]
for c in numeric_cols:
    X[c] = pd.to_numeric(X[c], errors="coerce").fillna(0)

feature_count = X.shape[1]
print(f"features: {feature_count} ({len(categorical_cols)} categorical, "
      f"{len(numeric_cols)} numeric)")
print("columns:", list(X.columns))

# COMMAND ----------

# Random 80/20 split, stratified on label so both halves see churned users.
X_train, X_test, y_train, y_test = train_test_split(
    X, y, test_size=0.2, random_state=42, stratify=y
)
print(f"train: {len(X_train)} rows, test: {len(X_test)} rows")

# COMMAND ----------

# Train + log to MLflow. `mlflow.lightgbm.autolog` would also work; we use the
# explicit API so the run captures exactly the metrics + tags the notebook
# narrates.
with mlflow.start_run(run_name="lightgbm_churn") as run:
    train_ds = lgb.Dataset(X_train, label=y_train, categorical_feature=categorical_cols)
    val_ds = lgb.Dataset(
        X_test, label=y_test, reference=train_ds, categorical_feature=categorical_cols
    )

    params = {
        "objective": "binary",
        "metric": "auc",
        "learning_rate": 0.05,
        "num_leaves": 31,
        "feature_fraction": 0.9,
        "bagging_fraction": 0.8,
        "bagging_freq": 5,
        "verbose": -1,
        "seed": 42,
    }
    mlflow.log_params(params)

    booster = lgb.train(
        params,
        train_ds,
        num_boost_round=200,
        valid_sets=[val_ds],
        callbacks=[lgb.early_stopping(stopping_rounds=20), lgb.log_evaluation(period=0)],
    )

    # Evaluate on the held-out split.
    test_proba = booster.predict(X_test)
    auc = float(roc_auc_score(y_test, test_proba))
    test_pred = (test_proba >= 0.5).astype(int)
    report = classification_report(y_test, test_pred, digits=3)

    print(f"AUC: {auc:.3f}")
    print(report)

    mlflow.log_metric("auc", auc)
    mlflow.log_metric("positive_rate", float(positive_rate))
    mlflow.log_metric("train_rows", float(len(X_train)))
    mlflow.log_metric("test_rows", float(len(X_test)))

    mlflow.set_tag("framework", "lightgbm")
    mlflow.set_tag("feature_count", str(feature_count))
    mlflow.set_tag("auc", f"{auc:.4f}")

    # UC model registry rejects models that lack signature metadata, and
    # `input_example` alone does not infer a signature for the LightGBM
    # flavor in this MLflow version. Build the signature explicitly from
    # the training X / predicted-y pair so registration succeeds.
    from mlflow.models import infer_signature

    input_example = X_train.head(5)
    signature = infer_signature(X_train, booster.predict(X_train))
    mlflow.lightgbm.log_model(
        booster,
        artifact_path="model",
        input_example=input_example,
        signature=signature,
    )

    model_uri = f"runs:/{run.info.run_id}/model"
    print(f"logged model at {model_uri}")

# COMMAND ----------

# Register the run's model into UC and point the `champion` alias at it so
# downstream loaders can pin to a stable reference.
registered = mlflow.register_model(model_uri=model_uri, name=MODEL_NAME)
print(f"registered {MODEL_NAME} version {registered.version}")

client = mlflow.tracking.MlflowClient()
client.set_registered_model_alias(
    name=MODEL_NAME, alias=MODEL_ALIAS, version=registered.version
)
print(f"alias @{MODEL_ALIAS} -> {MODEL_NAME} version {registered.version}")
