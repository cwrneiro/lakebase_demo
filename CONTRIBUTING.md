# Contributing

## Development

See the [README quickstart](README.md) for end-to-end setup (fork, configure
`databricks.yml`, run `scripts/bootstrap.sh`).

For iterating on the app locally against a deployed Lakebase Postgres
instance, use [`scripts/local-dev.sh`](scripts/local-dev.sh). Note: this
requires your IP to be on the Lakebase instance allowlist — see the script
header for instructions.

## Branch / commit conventions

- Branch off `main`; open PRs against `main`.
- Commit messages follow Conventional Commits: `type: short subject`,
  optionally with a scope. Examples from history:
  - `fix: harden bootstrap/teardown/local-dev for fork-and-deploy`
  - `fix(writeback): use SDK API + bump databricks-sdk in writeback notebook`
- Keep commits logical and self-contained. Squash fixups before review.

## Running checks locally

Run before pushing:

```bash
# Python
uv sync --dev
uv run ruff check .
uv run python -c "from app.server.routes import admin, actions, explain, user_detail, users"

# Bundle YAML
uv run python -c "import yaml; yaml.safe_load(open('databricks.yml'))"
for f in resources/*.yml; do
  uv run python -c "import yaml; yaml.safe_load(open('$f'))"
done

# Frontend
cd app/frontend
npm ci
npx tsc --noEmit
npm run build
```

Optionally, run a real bundle validation against your workspace:

```bash
databricks bundle validate -t dev
```

## Filing issues

Use the templates in
[`.github/ISSUE_TEMPLATE/`](.github/ISSUE_TEMPLATE/):

- `bug_report.md` for reproducible bugs.
- `feature_request.md` for proposed enhancements.

Include workspace region, Databricks CLI version, and OS for any
deploy/runtime issue.
