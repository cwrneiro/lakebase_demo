# Open points

Tracking what still needs verification, hardening, or polish before this repo is "production-grade fork-and-deploy". Written 2026-04-28.

## Verified working end-to-end

- Bundle two-pass deploy on `<your-workspace-profile>` (catalog `<your-catalog>`)
- Lakebase Autoscaling project + endpoint provisioning
- UC schemas: `lakebase_demo_{raw,curated,scored,synced}`
- Init job: synthetic data → features → heuristic scoring (5k users, 5k scores, 6k recommendations)
- CDF enable + 3 continuous synced tables (`SYNCED_TABLE_ONLINE_CONTINUOUS_UPDATE`)
- App boot with rendered `app/app.yaml`
- All 5 API routes: `/users`, `/users/{id}`, `/users/{id}/actions`, `/users/{id}/explain`, `/admin/rescore`
- Foundation Model rationale (`databricks-claude-sonnet-4-5`)
- Operator writeback round-trip → `public.user_actions` in Lakebase
- `writeback_ingest_job` mirrors writebacks to UC `lakebase_demo_scored.user_actions_cdc`
- Closed-loop decay: `include_writeback_signal=true` rescore drops accepted user's score by 15 per accepted recommendation in the trailing 7 days (verified 100 → 85 with one acceptance)

## Still requiring real verification before claiming fork-and-deploy

1. ~~**Full teardown + clean re-bootstrap cycle**~~ — **verified end-to-end 2026-04-28**. Teardown ~30s wall; fresh bootstrap got the app live at `https://lakebase-demo-<your-workspace-id>.aws.databricksapps.com` after the sync (#25), snapshot (#26), grant (#27), and app-start ordering fixes landed. All five routes return 200/422 to a real OBO token. Browser smoke (#3) confirms the UI loads users and runs the LLM rationale.
2. **`scripts/local-dev.sh`** — never started. Default `LAKEBASE_DATABASE` was wrong (now fixed); also adds `LAKEBASE_SYNC_SCHEMA` export. Untested because IP allowlisting blocks the local Postgres connection from a typical dev box.
3. ~~**Browser smoke test of the UI**~~ — **verified 2026-04-28** via `web-devloop-tester`. UserList renders 50 rows/page, sort toggles asc/desc, pagination + Previous-disable on page 1 work, UserDetail shows metadata + ScoreBadge (red=high, green=low) + recommendations + ExplainPanel; LLM "Generate" returns a 3–4 sentence rationale instantly; Accept writes to action history with operator email. Zero console errors, zero 5xx, all 7 XHRs returned 200. One residual: tier-filter combobox shows the options in the a11y tree but a programmatic click didn't open the visual menu — keyboard works, may be an MCP-driver quirk vs. a real a11y bug. Worth keyboard-testing in person.
4. **Multi-deployer scenario** — would the SP grants leak across deployers sharing one workspace? Untested.

## Polish gaps with low blast radius

5. ~~**No CI**~~ — fixed in Wave 1: `.github/workflows/ci.yml` runs ruff, pytest, vitest, tsc, npm build, and bundle YAML-syntax check on PR + push.
6. ~~**`lucide-react@1.8.0`**~~ — **icons render correctly** in the deployed app (verified 2026-04-28). Sort arrows, filter, sparkles, check, X, refresh all paint as proper SVGs with no visual artifacts. The version string is still suspicious vs. the canonical 0.4xx series and worth investigating if a lucide upgrade ever surfaces a regression — but functionally not blocking.
7. ~~**Pyright noise in pipeline notebooks**~~ — fixed in Wave 1: `pipelines/.pyrightconfig.json` suppresses `reportUndefinedVariable`.
8. ~~**No `screenshot.png` in README**~~ — added: `docs/screenshots/list-view-high-risk.png` is the README hero shot; `docs/screenshots/detail-with-recommendations.png` covers the detail view; `screenshot.png` at repo root for backwards reference.
9. ~~**No tests**~~ — fixed in Wave 1: 11 backend pytest + 12 frontend vitest tests, all green in CI.
10. **psql install path on Linux** — bootstrap auto-adds `/opt/homebrew/opt/postgresql@16/bin` (macOS) but expects `psql` on PATH for Linux users. Documented; not auto-resolved.

## Architectural items worth filing upstream / following up

11. **Bundle `config.env` does not propagate to App runtime env_vars** — empirically confirmed during testing; we work around with `app/app.yaml.tmpl` + `envsubst`. Could be a Databricks bundle bug or schema misuse on our part. File a Slack thread / Issue before publishing the repo so we don't ship a workaround for something fixable upstream.
12. **DABs has no `postgres_databases` resource type** — that's why the two-pass deploy is necessary. If Databricks adds it, the manual `database_resource_id` lookup in `bootstrap.sh` collapses to a single deploy.
13. **`config.env` removed from `resources/app.yml`** — replaced with a comment. If the upstream behaviour gets fixed, the comment should be deleted and `config.env` re-added.
14. **DABs sometimes reports `Deployment complete!` without actually creating the synced UC schema** — observed once during testing. `bootstrap.sh` now defensively does `CREATE SCHEMA IF NOT EXISTS` between passes. Worth flagging upstream if reproducible.
15. **Synced tables created via `databricks postgres create-synced-table` are imperative** — not in the bundle. If a future DABs version supports `synced_database_tables` resources targeting Autoscaling cleanly, we can move them in.

## Bootstrap robustness (discovered during the verification cycle on 2026-04-28)

23. **Bootstrap fails immediately after a fresh teardown** with Terraform error `project with such id already exists in the workspace`, even though `databricks api get .../projects/lakebase-demo` returns `not found` and the project is absent from `list-projects`. Reproduced twice, ~30s apart, on `<your-workspace-profile>` / `<your-catalog>`. Almost certainly a Lakebase server-side soft-delete reservation window. Workaround candidates: (a) sleep N minutes between teardown and bootstrap, (b) randomize `lakebase_project_id` per run, (c) retry-with-backoff on Pass 1. Needs to be fixed before the demo is forkable — first-time forkers won't hit it (no prior project), but anyone who does `teardown && bootstrap` to recover from a bad state will.
24. **`bootstrap.sh` endpoint-wait loop fragility** — `set -e -o pipefail` is on; if `databricks postgres list-endpoints ...` errors (e.g., project not yet visible after Pass 1, or transient API hiccup), the loop exits silently on the first iteration without retrying. Fix: `|| true` on the assignment, or branch on `state == ""` before grepping. Saw this manifest as a silent hang then exit during the #23 failure mode.
25. **`sync.include` acts as an exclusive allowlist on Databricks CLI v0.298.0** — discovered 2026-04-28 during fresh-bootstrap verification. The original `databricks.yml` had `sync.include: [app/app.yaml, app/frontend/dist/**]` intending only to add gitignored paths *on top of* the default git-tracked sync. On v0.298.0 this dropped everything outside `app/**` from the upload (verified: only `files/app/` and `files/open_points.md` landed in workspace; `pipelines/`, `lakebase/`, `scripts/`, `resources/` all missing). Init job's notebook task then fails with `Unable to access the notebook ... does not exist`. **Fixed in commit `378c894`** by enumerating every top-level path in `sync.include` and adding more aggressive `sync.exclude` patterns. Worth filing upstream — either the docs need to be explicit that `include` is a hard allowlist, or the CLI should restore additive behavior.
26. **Stale sync-snapshot survives a partial deploy** — discovered 2026-04-28. When Pass 1 fails after the file-upload phase (the documented placeholder-DB Terraform error, or any other Pass-1 fault), the CLI still persists its sync-snapshot under `.databricks/bundle/<target>/sync-snapshots/*.json`. On retry the CLI consults the snapshot and concludes "files already synced", skipping the upload — even when the workspace doesn't actually have them (e.g., because the schema changed via #25's fix). Symptom: bundle deploy reports success but `pipelines/` etc. are still missing from the workspace. **Fixed defensively** in `bootstrap.sh` by `rm -f .databricks/bundle/$TARGET/sync-snapshots/*.json` immediately before Pass 1.
27. **Synced-table GRANTs are silent no-ops without `SET ROLE databricks_superuser`** — discovered 2026-04-28. Lakebase synced tables are owned by databricks-managed roles (e.g. `databricks_writer_<id>`), not by the deployer. PostgreSQL permits the deployer to issue `GRANT SELECT ON ALL TABLES IN SCHEMA <synced>` but it grants nothing because the deployer doesn't own those tables. Symptom: app comes up RUNNING; every read 500s with `permission denied for table users` until a manual re-grant. **Fixed in `bootstrap.sh` step 10** by wrapping the synced-schema grants in `SET ROLE databricks_superuser` (the deployer is automatically a member). Same step also added a wait loop polling `information_schema.tables` so the GRANT runs after the synced tables actually exist in PG (the prior code raced against `--no-wait` create). Step 11 was reordered so `apps start` runs before `apps deploy` — `databricks apps deploy` requires the app's compute to be RUNNING, and on a fresh deploy the bundle creates the App in STOPPED state.

## Functional follow-ups (the demo works without these but they're tempting)

16. ~~**Replace heuristic scorer with a real model**~~ — **done 2026-04-28**. New notebook `pipelines/03a_train_churn_model.py` trains a LightGBM binary classifier on `${catalog}.${schema_prefix}_curated.user_features`, logs to MLflow, and registers under `${catalog}.${schema_prefix}_curated.churn_model` in UC with the `champion` alias. `pipelines/03_score_users.py` was refactored to `mlflow.pyfunc.load_model("models:/<catalog>.<schema_prefix>_curated.churn_model@champion")`, predict, scale to 0-100, and clip — preserving the closed-loop decay and the recommendations table downstream. `resources/jobs.yml` got a `train_churn_model` task wired between `compute_features` and `score_users`. The honest caveat: the synthetic-data label (`subscriptions.status == 'churned'`) is sampled randomly with fixed weights, not derived from feature behavior, so the model's predictive accuracy isn't meaningful. The demo value is the architecture (training notebook → MLflow → UC registry → alias load), not the model's quality. A production fork should retrain on actual historical churn outcomes.
17. **Continuous-sync latency measurement** — never instrumented. The "live demo" claim depends on it, so timing it once would be useful.
18. **Per-deployment Lakebase database** instead of the shared `databricks_postgres`. Would need a fresh Lakebase Database resource (with role) created via SDK in `bootstrap.sh`. Cleaner separation; not needed for the demo to work.
19. **Frontend states for empty-data / loading errors** — currently shows generic toasts. Could be friendlier.

## Hygiene

20. **Apache-2.0 LICENSE present** (added in `8c06f51`). README references it.
21. **`uv.lock` and `package-lock.json` committed** — locked for reproducibility. Note: future Python or Node version bumps may surprise contributors.
22. **No `CONTRIBUTING.md` / no issue templates** — fine if this stays a Field Engineering reference repo; needed if it goes to a wider audience.

## Suggested next moves, in priority order

1. Run `./scripts/teardown.sh -p <your-workspace-profile> --yes` then `./scripts/bootstrap.sh -p <your-workspace-profile> --catalog <your-catalog>` to verify items #1 (and incidentally #14).
2. Open the deployed app in a browser; resolve item #3 and grab a screenshot for the README (#8) and #6 (lucide check).
3. Add CI (#5) before publishing.
4. Decide what to do about #11 (file upstream vs ship workaround).
