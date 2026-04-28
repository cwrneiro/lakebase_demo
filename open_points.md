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

1. ~~**Full teardown + clean re-bootstrap cycle**~~ — **teardown verified clean 2026-04-28** (synced tables, bundle destroy, project delete all worked, ~30s wall). Bootstrap immediately afterward hit a new race (see #23) so the *re-bootstrap* half is still unverified.
2. **`scripts/local-dev.sh`** — never started. Default `LAKEBASE_DATABASE` was wrong (now fixed); also adds `LAKEBASE_SYNC_SCHEMA` export. Untested because IP allowlisting blocks the local Postgres connection from a typical dev box.
3. **Browser smoke test of the UI** — `curl` confirms the API works, but UserList / UserDetail / ScoreBadge / ExplainPanel rendering is unverified visually. Sort/filter/pagination behaviour and toast notifications never observed.
4. **Multi-deployer scenario** — would the SP grants leak across deployers sharing one workspace? Untested.

## Polish gaps with low blast radius

5. **No CI** — `databricks bundle validate`, `npm run build`, and `python -c "import app"` all run in seconds. A single GitHub Actions job would catch >80% of regressions before fork-time.
6. **`lucide-react@1.8.0`** — npm resolved this version; current canonical is in the 0.4xx range. Unverified visually. Build succeeds (necessary but not sufficient).
7. **Pyright noise in pipeline notebooks** — `dbutils`/`spark` flagged as undefined because they are notebook globals. Cosmetic, but a future contributor opens the file and sees squiggles. Fix: a `pipelines/.pyrightconfig.json` excluding those modules.
8. **No `screenshot.png` in README** — plan called for one. Can't take it without browser verification (#3).
9. **No tests** — backend has no pytest, frontend has no vitest. Routes' SQL is verified only by the manual API session.
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
25. **`sync.include` acts as an exclusive allowlist on Databricks CLI v0.298.0** — discovered 2026-04-28 during fresh-bootstrap verification. The original `databricks.yml` had `sync.include: [app/app.yaml, app/frontend/dist/**]` intending only to add gitignored paths *on top of* the default git-tracked sync. On v0.298.0 this dropped everything outside `app/**` from the upload (verified: only `files/app/` and `files/open_points.md` landed in workspace; `pipelines/`, `lakebase/`, `scripts/`, `resources/` all missing). Init job's notebook task then fails with `Unable to access the notebook ... does not exist`. **Fixed in this commit** by enumerating every top-level path in `sync.include` and adding more aggressive `sync.exclude` patterns. Worth filing upstream — either the docs need to be explicit that `include` is a hard allowlist, or the CLI should restore additive behavior.

## Functional follow-ups (the demo works without these but they're tempting)

16. **Replace heuristic scorer with a real model** — plan said "swap for `lightgbm` later". Not done. Acceptable for a demo, but if anyone forks this for a real conversation it's the obvious next move.
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
