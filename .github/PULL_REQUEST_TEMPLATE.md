## Summary

-
-

## Test plan

- [ ] `uv run ruff check .` passes
- [ ] Frontend type-check + build passes (`cd app/frontend && npx tsc --noEmit && npm run build`)
- [ ] Bundle YAML parses (`uv run python -c "import yaml; yaml.safe_load(open('databricks.yml'))"`)
- [ ] Manually verified change against a deployed workspace (describe how)

## Linked issue

<!-- e.g. Closes #123, or "n/a" -->
