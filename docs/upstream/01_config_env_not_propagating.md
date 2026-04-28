# DABs `config.env` on App resources does not propagate to runtime env_vars

**Status:** Draft, not yet filed.
**Repo:** Lakebase reverse-ETL demo (Field Engineering reference).

## Observed behavior

When a Databricks Asset Bundle declares an `apps` resource with environment
variables under `config.env` (or under the App resource's nested `env`/`config`
mapping), those values are **not** present in the App's runtime environment
after `databricks bundle deploy`. Inside the App, `os.environ` simply does not
contain the keys the bundle declared.

The original `resources/app.yml` block we removed declared roughly:

```yaml
# (removed; intent reconstructed from the comment at resources/app.yml:24-26)
resources:
  apps:
    demo_app:
      name: ${var.app_name}
      source_code_path: ${workspace.file_path}/app
      config:
        env:
          - name: ENDPOINT_NAME
            value: "projects/${var.lakebase_project_id}/branches/production/endpoints/primary"
          - name: SERVING_ENDPOINT
            value: ${var.serving_endpoint}
          - name: CATALOG_NAME
            value: ${var.catalog_name}
          # ...etc.
```

After deploy, those variables were missing from the running App. The App's
FastAPI server then failed to construct its Lakebase connection string because
`ENDPOINT_NAME` was unset. We verified this empirically against a real
workspace (`<your-workspace-profile>`) before falling back to the workaround below.

## Workaround in this repo

We removed `config.env` from the bundle and instead render an `app/app.yaml`
file from a template using `envsubst` inside `bootstrap.sh`:

- `app/app.yaml.tmpl` (committed) holds the env-var schema with `${VAR}`
  placeholders.
- `scripts/bootstrap.sh:135-148` substitutes bundle-resolved values into the
  template and writes `app/app.yaml` (gitignored).
- `databricks.yml:51-56` adds `app/app.yaml` to the bundle sync include list so
  the rendered file is uploaded with the rest of the App source.

Reference: `scripts/bootstrap.sh:135-148`:

```sh
LAKEBASE_PROJECT_ID="$PROJECT_ID" \
SERVING_ENDPOINT="$SERVING_ENDPOINT" \
ENABLE_LLM_EXPLAIN="$ENABLE_LLM_EXPLAIN" \
CATALOG_NAME="$CATALOG" \
LAKEBASE_DATABASE="$DATABASE" \
LAKEBASE_SYNC_SCHEMA="${SCHEMA_PREFIX}_synced" \
RESCORE_JOB_ID="$RESCORE_JOB_ID" \
  envsubst '$LAKEBASE_PROJECT_ID $SERVING_ENDPOINT ...' \
  < app/app.yaml.tmpl > app/app.yaml
```

This works but it means a forker cannot run `databricks bundle deploy` alone;
they must use our shell wrapper. That defeats one of the bundle's main value
propositions.

## What we'd want

`config.env` (or whatever the canonical bundle field is) on an `apps` resource
should land in the App's runtime environment without manual templating. If
this is intentional (e.g., security review prevents arbitrary value injection
from a bundle), please document it explicitly and provide a bundle-native
mechanism that does work. A `secrets` reference would be acceptable.

## Repro steps

1. Create a minimal bundle with one `apps` resource and `source_code_path`
   pointing at a Python "hello world" FastAPI app that prints `os.environ`.
2. Add a `config.env` block (or whatever the schema specifies) declaring
   `FOO=bar`.
3. Run `databricks bundle deploy`.
4. Hit the App and observe that `FOO` is missing from `os.environ`.

## Versions

- Bundle schema: implicit (no `bundle.schema_version` set in `databricks.yml`).
- `databricks-sdk`: `>=0.81.0` per `pyproject.toml:11`.
- `databricks` CLI: TBD — verify with `databricks --version`. `bootstrap.sh`
  asserts `>= v0.285.0` (`scripts/bootstrap.sh:56-62`).
- Workspace where reproduced: `<your-workspace-profile>` (AWS).
