# Databricks notebook source
# Shared helpers for the Lakebase demo pipelines.
# This file is intentionally not registered as a job task; it is imported by other notebooks.

# COMMAND ----------

import os


def get_param(dbutils, name: str, default: str = "") -> str:
    """Read a job parameter (widget) with a fallback default."""
    try:
        return dbutils.widgets.get(name)
    except Exception:
        return os.environ.get(name.upper(), default)
