#!/usr/bin/env bash
# Bootstrap: deploy the bundle, grant Postgres perms to the App SP, run the
# init job, create synced tables in Lakebase, apply the user_actions schema,
# and print the app URL.
#
# Usage:
#   ./scripts/bootstrap.sh [-p <profile>] [-t <target>] [--catalog <name>]
#
# Requirements:
#   - databricks CLI v0.285.0+
#   - psql (postgresql client) — `brew install postgresql@16`
#   - jq, envsubst, npm, node
#
# This script is idempotent. It does a two-pass deploy because the Lakebase
# Database resource id (auto-generated when the project is created) must be
# fed back into the App resource binding.

set -euo pipefail

PROFILE="${DATABRICKS_PROFILE:-DEFAULT}"
TARGET="dev"
CATALOG_OVERRIDE=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    -p|--profile) PROFILE="$2"; shift 2;;
    -t|--target)  TARGET="$2";  shift 2;;
    --catalog)    CATALOG_OVERRIDE="$2"; shift 2;;
    -h|--help)
      grep '^#' "$0" | sed 's/^# *//'; exit 0;;
    *) echo "unknown arg: $1" >&2; exit 2;;
  esac
done

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

step() { printf "\n\033[1;36m▸ %s\033[0m\n" "$*"; }
ok()   { printf "\033[1;32m✓ %s\033[0m\n" "$*"; }
err()  { printf "\033[1;31m✗ %s\033[0m\n" "$*" >&2; }

# psql lives at a non-standard path on macOS Homebrew
if [[ -d /opt/homebrew/opt/postgresql@16/bin ]]; then
  export PATH="/opt/homebrew/opt/postgresql@16/bin:$PATH"
fi

# ---------- 0. Tool checks ----------------------------------------------------
step "Checking tools"
for cmd in databricks psql jq envsubst npm node; do
  if ! command -v "$cmd" >/dev/null; then
    err "$cmd is required (see README)"
    exit 1
  fi
done

CLI_VER="$(databricks --version | awk '{print $NF}' | sed 's/^v//')"
required_min="0.285.0"
ver_ok=$(printf "%s\n%s\n" "$required_min" "$CLI_VER" | sort -V | head -n1)
if [[ "$ver_ok" != "$required_min" ]]; then
  err "databricks CLI $required_min+ required (have $CLI_VER)"
  exit 1
fi
ok "tools present (CLI v$CLI_VER)"

# ---------- 1. Resolve bundle vars -------------------------------------------
var_lookup() {
  local k="$1" d="$2"
  databricks bundle summary -p "$PROFILE" -t "$TARGET" -o json 2>/dev/null \
    | jq -r ".variables.\"$k\".value // .variables.\"$k\".default // \"$d\""
}

# CLI flag wins over env var wins over bundle var.
if [[ -n "$CATALOG_OVERRIDE" ]]; then
  export BUNDLE_VAR_catalog_name="$CATALOG_OVERRIDE"
fi

CATALOG="${BUNDLE_VAR_catalog_name:-$(var_lookup catalog_name main)}"
SCHEMA_PREFIX="${BUNDLE_VAR_schema_prefix:-$(var_lookup schema_prefix lakebase_demo)}"
PROJECT_ID="${BUNDLE_VAR_lakebase_project_id:-$(var_lookup lakebase_project_id lakebase-demo)}"
DATABASE="${BUNDLE_VAR_lakebase_database:-$(var_lookup lakebase_database databricks_postgres)}"
SERVING_ENDPOINT="${BUNDLE_VAR_serving_endpoint:-$(var_lookup serving_endpoint databricks-claude-sonnet-4-5)}"
ENABLE_LLM_EXPLAIN="${BUNDLE_VAR_enable_llm_explain:-$(var_lookup enable_llm_explain true)}"

step "Resolved variables"
echo "  catalog            = $CATALOG"
echo "  schema_prefix      = $SCHEMA_PREFIX"
echo "  lakebase_project   = $PROJECT_ID"
echo "  lakebase_database  = $DATABASE"
echo "  profile            = $PROFILE"
echo "  target             = $TARGET"

# ---------- 2. Build frontend -------------------------------------------------
step "Building frontend bundle"
(cd app/frontend && [[ -d node_modules ]] || npm ci --silent)
(cd app/frontend && npm run build --silent)
ok "frontend built → app/frontend/dist/"

# ---------- 3. Pass 1 — create the Lakebase project & schemas ----------------
# The App resource needs the Lakebase Database resource id, which is generated
# when the project is created. So we deploy in two passes; the first pass uses
# a placeholder id and the App resource will fail (we expect it). After the
# project exists we look up the real id and re-deploy.

step "Pass 1: deploy bundle (Lakebase project + UC schemas + jobs)"
databricks bundle deploy -p "$PROFILE" -t "$TARGET" 2>&1 | tail -20 || true
# tail output but ignore non-zero exit; the App resource is expected to fail.

# Wait for endpoint
step "Waiting for Lakebase endpoint to become ACTIVE"
for _ in {1..40}; do
  STATE="$(databricks postgres list-endpoints "projects/$PROJECT_ID/branches/production" \
    -p "$PROFILE" -o json 2>/dev/null | jq -r '.[0].status.current_state // "PENDING"')"
  echo "  state: $STATE"
  if [[ "$STATE" == "ACTIVE" ]]; then break; fi
  sleep 6
done
[[ "$STATE" == "ACTIVE" ]] || { err "endpoint did not reach ACTIVE state"; exit 1; }
ok "endpoint ACTIVE"

# Look up the auto-generated Lakebase Database resource id
step "Looking up Lakebase Database resource id"
DB_RESOURCE_ID="$(databricks api get \
  "/api/2.0/postgres/projects/$PROJECT_ID/branches/production/databases" \
  -p "$PROFILE" 2>/dev/null \
  | jq -r --arg pgdb "$DATABASE" \
      '.databases[] | select(.status.postgres_database == $pgdb) | .status.database_id' \
  | head -n1)"
if [[ -z "$DB_RESOURCE_ID" ]]; then
  err "could not find Lakebase Database for postgres db '$DATABASE'"
  exit 1
fi
export BUNDLE_VAR_lakebase_database_resource_id="$DB_RESOURCE_ID"
ok "lakebase_database_resource_id = $DB_RESOURCE_ID"

# ---------- 4. Render app/app.yaml from template -----------------------------
step "Rendering app/app.yaml from template"
RESCORE_JOB_ID="$(databricks bundle summary -p "$PROFILE" -t "$TARGET" -o json 2>/dev/null \
  | jq -r '.resources.jobs.rescore_job.id // "0"')"
LAKEBASE_PROJECT_ID="$PROJECT_ID" \
SERVING_ENDPOINT="$SERVING_ENDPOINT" \
ENABLE_LLM_EXPLAIN="$ENABLE_LLM_EXPLAIN" \
CATALOG_NAME="$CATALOG" \
LAKEBASE_DATABASE="$DATABASE" \
LAKEBASE_SYNC_SCHEMA="${SCHEMA_PREFIX}_synced" \
RESCORE_JOB_ID="$RESCORE_JOB_ID" \
  envsubst '$LAKEBASE_PROJECT_ID $SERVING_ENDPOINT $ENABLE_LLM_EXPLAIN $CATALOG_NAME $LAKEBASE_DATABASE $LAKEBASE_SYNC_SCHEMA $RESCORE_JOB_ID' \
  < app/app.yaml.tmpl > app/app.yaml
ok "app/app.yaml rendered"

# ---------- 5. Pass 2 — full deploy with the real database id ---------------
step "Pass 2: deploy bundle (App resource bound to Lakebase database)"
databricks bundle deploy -p "$PROFILE" -t "$TARGET" --auto-approve
ok "bundle deployed"

# ---------- 6. Apply user_actions schema -------------------------------------
step "Applying lakebase/00_schema.sql to $DATABASE"
HOST="$(databricks postgres list-endpoints "projects/$PROJECT_ID/branches/production" \
  -p "$PROFILE" -o json | jq -r '.[0].status.hosts.host')"
TOKEN="$(databricks postgres generate-database-credential \
  "projects/$PROJECT_ID/branches/production/endpoints/primary" \
  -p "$PROFILE" -o json | jq -r '.token')"
EMAIL="$(databricks current-user me -p "$PROFILE" -o json | jq -r '.userName')"

PSQL_ENV=(env "PGPASSWORD=$TOKEN")
CONN_APP="host=$HOST port=5432 dbname=$DATABASE user=$EMAIL sslmode=require"

"${PSQL_ENV[@]}" psql -v ON_ERROR_STOP=1 "$CONN_APP" -f lakebase/00_schema.sql
ok "user_actions table ready"

# ---------- 7. Run init job ---------------------------------------------------
step "Running init job (synthetic data + features + scoring)"
databricks bundle run init_job -p "$PROFILE" -t "$TARGET"
ok "init job complete"

# ---------- 8. Enable Change Data Feed on source UC tables -------------------
step "Enabling CDF on source tables (required for continuous synced tables)"
WID="$(databricks warehouses list -p "$PROFILE" -o json | jq -r '.[0].id')"
for tbl in \
  "$CATALOG.${SCHEMA_PREFIX}_raw.users" \
  "$CATALOG.${SCHEMA_PREFIX}_scored.user_scores" \
  "$CATALOG.${SCHEMA_PREFIX}_scored.recommendations"; do
  databricks api post /api/2.0/sql/statements -p "$PROFILE" \
    --json "$(jq -n --arg t "$tbl" --arg w "$WID" \
      '{statement: "ALTER TABLE \($t) SET TBLPROPERTIES (delta.enableChangeDataFeed = true)", warehouse_id: $w, wait_timeout: "30s"}')" \
    >/dev/null
  echo "  CDF on $tbl"
done
ok "CDF enabled on all source tables"

# ---------- 9. Create synced tables -------------------------------------------
step "Creating synced tables (UC → Lakebase, continuous)"

create_synced () {
  local id="$1" pk="$2" src="$3"
  if databricks postgres get-synced-table "synced_tables/$id" \
       -p "$PROFILE" -o json >/dev/null 2>&1; then
    echo "  $id already exists; skipping"; return
  fi
  databricks postgres create-synced-table "$id" \
    --json "$(jq -n --arg src "$src" --arg pk "$pk" --arg br "projects/$PROJECT_ID/branches/production" --arg db "$DATABASE" \
      '{spec: {
        branch: $br,
        postgres_database: $db,
        source_table_full_name: $src,
        primary_key_columns: [$pk],
        scheduling_policy: "CONTINUOUS",
        create_database_objects_if_missing: true
      }}')" \
    -p "$PROFILE" --no-wait >/dev/null
  echo "  ▸ $id queued"
}
create_synced "$CATALOG.${SCHEMA_PREFIX}_synced.users"           "user_id"           "$CATALOG.${SCHEMA_PREFIX}_raw.users"
create_synced "$CATALOG.${SCHEMA_PREFIX}_synced.user_scores"     "user_id"           "$CATALOG.${SCHEMA_PREFIX}_scored.user_scores"
create_synced "$CATALOG.${SCHEMA_PREFIX}_synced.recommendations" "recommendation_id" "$CATALOG.${SCHEMA_PREFIX}_scored.recommendations"
ok "synced tables created"

# ---------- 10. Grant Postgres perms to the App SP ---------------------------
step "Granting Postgres perms to the App service principal"
SP="$(databricks apps get "$(jq -r '.resources.apps.demo_app.name // "lakebase-demo"' \
       <<<"$(databricks bundle summary -p "$PROFILE" -t "$TARGET" -o json)")" \
       -p "$PROFILE" -o json | jq -r '.service_principal_client_id')"
echo "  app SP client_id = $SP"

# Wait briefly for the SP role to appear in Postgres
for _ in {1..15}; do
  exists="$("${PSQL_ENV[@]}" psql -tAc "SELECT 1 FROM pg_roles WHERE rolname = '$SP'" "$CONN_APP" || true)"
  [[ "$exists" == "1" ]] && break
  echo "  waiting for SP role..."
  sleep 4
done

"${PSQL_ENV[@]}" psql -v ON_ERROR_STOP=1 "$CONN_APP" -c \
  "GRANT USAGE ON SCHEMA \"${SCHEMA_PREFIX}_synced\" TO \"$SP\""
"${PSQL_ENV[@]}" psql -v ON_ERROR_STOP=1 "$CONN_APP" -c \
  "GRANT SELECT ON ALL TABLES IN SCHEMA \"${SCHEMA_PREFIX}_synced\" TO \"$SP\""
"${PSQL_ENV[@]}" psql -v ON_ERROR_STOP=1 "$CONN_APP" -c \
  "ALTER DEFAULT PRIVILEGES IN SCHEMA \"${SCHEMA_PREFIX}_synced\" GRANT SELECT ON TABLES TO \"$SP\""
"${PSQL_ENV[@]}" psql -v ON_ERROR_STOP=1 "$CONN_APP" -c \
  "GRANT USAGE ON SCHEMA public TO \"$SP\""
"${PSQL_ENV[@]}" psql -v ON_ERROR_STOP=1 "$CONN_APP" -c \
  "GRANT SELECT, INSERT, UPDATE, DELETE ON public.user_actions TO \"$SP\""
"${PSQL_ENV[@]}" psql -v ON_ERROR_STOP=1 "$CONN_APP" -c \
  "ALTER ROLE \"$SP\" SET search_path TO \"${SCHEMA_PREFIX}_synced\", public"
ok "SP $SP granted; default search_path set"

# ---------- 11. Deploy the App code ------------------------------------------
step "Deploying app code"
APP_NAME="$(databricks bundle summary -p "$PROFILE" -t "$TARGET" -o json \
  | jq -r '.resources.apps.demo_app.name // "lakebase-demo"')"
APP_SOURCE="/Workspace/Users/$EMAIL/.bundle/lakebase-reverse-etl-demo/$TARGET/files/app"
databricks apps deploy "$APP_NAME" --source-code-path "$APP_SOURCE" -p "$PROFILE" >/dev/null
ok "app code deployed"

# Restart in case the pool cached old connections
databricks apps stop "$APP_NAME" -p "$PROFILE" >/dev/null 2>&1 || true
sleep 5
databricks apps start "$APP_NAME" -p "$PROFILE" >/dev/null

# ---------- 12. Print summary ------------------------------------------------
APP_URL="$(databricks apps get "$APP_NAME" -p "$PROFILE" -o json | jq -r '.url')"
cat <<EOF

  Catalog:    $CATALOG
  Lakebase:   projects/$PROJECT_ID/branches/production/endpoints/primary
  Database:   $DATABASE
  Schemas:    ${SCHEMA_PREFIX}_{raw,curated,scored,synced}
  App:        $APP_URL
  Logs:       $APP_URL/logz

  Verify the demo:
    1. Open the app URL above (it may take ~30s to be reachable after start).
    2. Click any high-risk user → "Generate" the LLM rationale.
    3. Accept a recommendation → check 'public.user_actions' in Lakebase.
    4. The writeback_ingest_job (every minute) mirrors that to UC at
       $CATALOG.${SCHEMA_PREFIX}_scored.user_actions_cdc.

EOF
ok "bootstrap complete"
