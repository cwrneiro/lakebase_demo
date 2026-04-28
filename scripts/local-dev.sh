#!/usr/bin/env bash
# Local dev loop: starts FastAPI on :8000 and Vite on :5173 with /api proxy.
#
# Reads .env (or .env.local) for DATABRICKS_PROFILE, ENDPOINT_NAME, and PG*.
# You need to have already run `./scripts/bootstrap.sh` once so the Lakebase
# endpoint exists and the user_actions table is created.
#
# Usage: ./scripts/local-dev.sh [-p <profile>]

set -euo pipefail

PROFILE="${DATABRICKS_PROFILE:-DEFAULT}"
while [[ $# -gt 0 ]]; do
  case "$1" in
    -p|--profile) PROFILE="$2"; shift 2;;
    *) echo "unknown arg: $1" >&2; exit 2;;
  esac
done

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

# Source .env if present (does not overwrite existing env)
if [[ -f .env ]]; then
  set -a; . ./.env; set +a
fi

PROJECT_ID="${LAKEBASE_PROJECT_ID:-lakebase-demo}"
DATABASE="${LAKEBASE_DATABASE:-databricks_postgres}"
SCHEMA_PREFIX="${SCHEMA_PREFIX:-lakebase_demo}"

# Resolve PG* env vars from the workspace if not already set
export DATABRICKS_PROFILE="$PROFILE"
if [[ -z "${PGHOST:-}" ]]; then
  export PGHOST="$(databricks postgres list-endpoints \
    "projects/$PROJECT_ID/branches/production" -p "$PROFILE" -o json \
    | jq -r '.[0].status.hosts.host')"
fi
export PGUSER="${PGUSER:-$(databricks current-user me -p "$PROFILE" -o json | jq -r '.userName')}"
export PGPORT="${PGPORT:-5432}"
export PGDATABASE="${PGDATABASE:-$DATABASE}"
export PGSSLMODE="${PGSSLMODE:-require}"
export ENDPOINT_NAME="${ENDPOINT_NAME:-projects/$PROJECT_ID/branches/production/endpoints/primary}"
export SERVING_ENDPOINT="${SERVING_ENDPOINT:-databricks-claude-sonnet-4-5}"
export ENABLE_LLM_EXPLAIN="${ENABLE_LLM_EXPLAIN:-true}"
export LAKEBASE_SYNC_SCHEMA="${LAKEBASE_SYNC_SCHEMA:-${SCHEMA_PREFIX}_synced}"
export RESCORE_JOB_ID="${RESCORE_JOB_ID:-0}"  # 0 disables rescore button locally

# Install Python deps if not present
if ! python -c "import fastapi" >/dev/null 2>&1; then
  echo "▸ installing Python deps via uv"
  uv sync
fi

# Install + run frontend
(cd app/frontend && [[ -d node_modules ]] || npm ci --silent)

trap 'kill 0' SIGINT SIGTERM EXIT

(cd app && uv run uvicorn app:app --reload --port 8000) &
BACKEND_PID=$!

(cd app/frontend && npm run dev) &
FRONTEND_PID=$!

echo
echo "▸ backend:  http://127.0.0.1:8000/api/healthz"
echo "▸ frontend: http://127.0.0.1:5173"
echo

wait $BACKEND_PID $FRONTEND_PID
