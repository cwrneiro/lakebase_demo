# Feature request: `postgres_databases` (or equivalent) resource type in DABs

**Status:** Draft, not yet filed.
**Repo:** Lakebase reverse-ETL demo (Field Engineering reference).

## Problem

DABs today supports `resources.postgres_projects` (which creates a Lakebase
Autoscaling project + branch + endpoint) but has **no resource type for the
Postgres databases inside that project**. The auto-created `databricks_postgres`
database is given an opaque, server-generated `database_id` (e.g.
`db-xxxx-yyyy`), and that id is exactly what an `apps` resource needs to bind
to Lakebase via `resources.apps.<name>.resources[].postgres.database`.

See `resources/app.yml:12`:

```yaml
database: projects/${var.lakebase_project_id}/branches/production/databases/${var.lakebase_database_resource_id}
```

There is no way to express "give me the database id of the database named
`databricks_postgres` in this project" inside a bundle today. The id is
generated server-side, post-deploy.

So this demo deploys in **two passes**:

1. **Pass 1** (`scripts/bootstrap.sh:104-105`): `databricks bundle deploy` with
   `lakebase_database_resource_id=PLACEHOLDER_DATABASE_RESOURCE_ID`
   (`databricks.yml:25-30`). The Lakebase project, branch, endpoint, and UC
   schemas are created. The App resource fails to validate because the
   placeholder isn't a real id; we expect and tolerate this.
2. We poll the endpoint until it is ACTIVE
   (`scripts/bootstrap.sh:108-118`), then look up the real id via the REST
   API (`scripts/bootstrap.sh:121-133`):

   ```sh
   DB_RESOURCE_ID="$(databricks api get \
     "/api/2.0/postgres/projects/$PROJECT_ID/branches/production/databases" \
     -p "$PROFILE" 2>/dev/null \
     | jq -r --arg pgdb "$DATABASE" \
         '.databases[] | select(.status.postgres_database == $pgdb) | .status.database_id' \
     | head -n1)"
   export BUNDLE_VAR_lakebase_database_resource_id="$DB_RESOURCE_ID"
   ```

3. **Pass 2** (`scripts/bootstrap.sh:151-153`): re-run
   `databricks bundle deploy` with the real id exported as a bundle var. The
   App resource now binds correctly.

## Why two-pass is hard for forkers

The whole point of DABs is "clone the repo, set a profile, run
`databricks bundle deploy`". Two-pass deploys break that:

- CI cannot just call `databricks bundle deploy` and consider the work done.
- A fresh user who runs `databricks bundle deploy` directly will see the App
  resource fail with a confusing "database not found" error, with no
  indication that they are supposed to run a wrapper script.
- The lookup script is bash-specific, depends on `jq`, and assumes the user
  has the same CLI auth profile as the one used by the bundle.

For this repo we shipped `scripts/bootstrap.sh` to paper over it, but every
fork-and-deploy demo or real customer adoption hits this wall.

## Proposed resource shape

By analogy to `resources.postgres_projects`, add a `postgres_databases`
resource that creates (or adopts) a database inside an existing project and
exposes its server-generated id for downstream resources:

```yaml
resources:
  postgres_databases:
    main_db:
      project: ${resources.postgres_projects.demo_lakebase.project_id}
      branch: production
      postgres_database: databricks_postgres   # name as it exists in PG
      # adopt_existing: true  # tolerate the auto-created databricks_postgres
  apps:
    demo_app:
      resources:
        - name: lakebase
          postgres:
            branch: ${resources.postgres_databases.main_db.branch_path}
            database: ${resources.postgres_databases.main_db.id}
            permission: CAN_CONNECT_AND_CREATE
```

Exposed attributes that downstream needs: at minimum `id` (the
`db-xxxx-yyyy` resource id) and `branch_path`
(`projects/<id>/branches/<branch>`). One example covers the demo's needs.

## Workaround

See `scripts/bootstrap.sh:121-133` (the REST lookup) and
`scripts/bootstrap.sh:151-153` (the second deploy). The placeholder default
for `lakebase_database_resource_id` lives in `databricks.yml:25-30`.
