#!/usr/bin/env bash
# Teardown: removes everything bootstrap.sh created.
#
# Usage: ./scripts/teardown.sh [-p <profile>] [-t <target>] [--yes]
#
# This is destructive. Synced tables, the Lakebase project (and its data),
# the bundle's UC catalog, and the deployed App will all be deleted.

set -euo pipefail

PROFILE="${DATABRICKS_PROFILE:-DEFAULT}"
TARGET="dev"
ASSUME_YES=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    -p|--profile) PROFILE="$2"; shift 2;;
    -t|--target)  TARGET="$2";  shift 2;;
    --yes)        ASSUME_YES=1; shift;;
    *) echo "unknown arg: $1" >&2; exit 2;;
  esac
done

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

step() { printf "\n\033[1;36m▸ %s\033[0m\n" "$*"; }
ok()   { printf "\033[1;32m✓ %s\033[0m\n" "$*"; }

PROJECT_ID="$(databricks bundle summary -p "$PROFILE" -t "$TARGET" -o json \
  2>/dev/null | jq -r '.variables.lakebase_project_id.value // .variables.lakebase_project_id.default // "lakebase-demo"')"
CATALOG="$(databricks bundle summary -p "$PROFILE" -t "$TARGET" -o json \
  2>/dev/null | jq -r '.variables.catalog_name.value // .variables.catalog_name.default // "main"')"

if [[ "$ASSUME_YES" != "1" ]]; then
  echo
  echo "This will DELETE:"
  echo "  - the deployed bundle resources (jobs, app)"
  echo "  - Lakebase project: projects/$PROJECT_ID (and ALL data inside it)"
  echo "  - UC catalog:       $CATALOG"
  echo "  - Synced tables registered against $CATALOG.public.*"
  echo
  read -r -p "Type 'destroy' to continue: " confirm
  [[ "$confirm" == "destroy" ]] || { echo "aborted"; exit 1; }
fi

step "Deleting synced tables (best-effort)"
for tbl in users user_scores recommendations; do
  databricks postgres delete-synced-table "$CATALOG.public.$tbl" \
    -p "$PROFILE" 2>/dev/null || true
done
ok "synced tables deleted"

step "Destroying bundle"
databricks bundle destroy -p "$PROFILE" -t "$TARGET" --auto-approve
ok "bundle destroyed"

# `bundle destroy` should remove the Postgres project too because it was a
# bundle-managed resource. Belt-and-suspenders cleanup if it didn't:
step "Ensuring Lakebase project is gone"
databricks postgres delete-project "projects/$PROJECT_ID" \
  -p "$PROFILE" 2>/dev/null || true
ok "teardown complete"
