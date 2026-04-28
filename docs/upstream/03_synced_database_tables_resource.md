# Feature request: `synced_database_tables` resource type in DABs targeting Lakebase Autoscaling

**Status:** Draft, not yet filed.
**Repo:** Lakebase reverse-ETL demo (Field Engineering reference).

## Problem

`databricks postgres create-synced-table` is an imperative CLI command. There
is no DABs resource type that lets a bundle declare "this UC table should be
synced to this Lakebase database, continuously, with this primary key". As a
result, the demo cannot fully express its data plane in the bundle and has to
fall back to shell-driven imperative provisioning.

For a reverse-ETL demo the synced tables ARE the integration surface — the
piece a customer most wants to read declaratively. Forcing forkers to run
shell to create them undermines the bundle's promise.

## Reference: how the demo creates them today

`scripts/bootstrap.sh:204-229` defines a helper and three calls. One full call
verbatim:

```sh
create_synced () {
  local id="$1" pk="$2" src="$3"
  if databricks postgres get-synced-table "synced_tables/$id" \
       -p "$PROFILE" -o json >/dev/null 2>&1; then
    echo "  $id already exists; skipping"; return
  fi
  databricks postgres create-synced-table "$id" \
    --json "$(jq -n --arg src "$src" --arg pk "$pk" \
                    --arg br "projects/$PROJECT_ID/branches/production" \
                    --arg db "$DATABASE" \
      '{spec: {
        branch: $br,
        postgres_database: $db,
        source_table_full_name: $src,
        primary_key_columns: [$pk],
        scheduling_policy: "CONTINUOUS",
        create_database_objects_if_missing: true
      }}')" \
    -p "$PROFILE" --no-wait >/dev/null
}
create_synced "$CATALOG.${SCHEMA_PREFIX}_synced.users"           "user_id"           "$CATALOG.${SCHEMA_PREFIX}_raw.users"
create_synced "$CATALOG.${SCHEMA_PREFIX}_synced.user_scores"     "user_id"           "$CATALOG.${SCHEMA_PREFIX}_scored.user_scores"
create_synced "$CATALOG.${SCHEMA_PREFIX}_synced.recommendations" "recommendation_id" "$CATALOG.${SCHEMA_PREFIX}_scored.recommendations"
```

It also requires CDF to be enabled on the source tables before creation
(`scripts/bootstrap.sh:189-202`), which is itself imperative.

## Proposed resource shape

By analogy to existing bundle resources:

```yaml
resources:
  synced_database_tables:
    users:
      target_table_full_name: ${var.catalog_name}.${var.schema_prefix}_synced.users
      source_table_full_name: ${var.catalog_name}.${var.schema_prefix}_raw.users
      branch: ${resources.postgres_databases.main_db.branch_path}
      postgres_database: databricks_postgres
      primary_key_columns: [user_id]
      scheduling_policy: CONTINUOUS   # or TRIGGERED, with `schedule:` block
      create_database_objects_if_missing: true
      # Optional: ensureChangeDataFeed: true on the source delta table.
```

Should support both `CONTINUOUS` (this demo's mode) and `TRIGGERED`
(scheduled refresh) policies. CDF enablement on the source UC table is a
common prerequisite — having the resource handle that automatically when
`scheduling_policy: CONTINUOUS` is set would remove another imperative step
(currently `scripts/bootstrap.sh:189-202`).

Cross-resource references should let users wire a synced table onto the
proposed `postgres_databases` resource (see
`docs/upstream/02_postgres_databases_resource.md`) so the whole reverse-ETL
graph is one bundle.

## Special note: related issue worth investigating

`open_points.md` item #14: DABs has been observed reporting
`Deployment complete!` without actually creating the synced UC schema (the
schema declared in `resources/catalog.yml`, e.g. `lakebase_demo_synced`).
We saw it once during testing. As a defensive measure the bootstrap script
re-creates schemas via SQL between passes (`scripts/bootstrap.sh:155-167`):

```sh
# Belt-and-suspenders: DABs has been observed to report "Deployment complete!"
# without actually creating the synced schema. ...
for s in raw curated scored synced; do
  databricks api post /api/2.0/sql/statements ...
    "{statement: \"CREATE SCHEMA IF NOT EXISTS $c.$s\", ...}"
done
```

If this is reproducible, it's a separate bug worth investigating alongside
the synced-tables resource work — synced-table creation explodes confusingly
when the target schema is silently missing.
