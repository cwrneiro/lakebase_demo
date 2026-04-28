"""FastAPI entrypoint for the Lakebase reverse-ETL operator queue."""

from __future__ import annotations

import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from server.db import pool
from server.routes import actions, admin, explain, user_detail, users


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Open the Lakebase pool once at startup. `wait=True` blocks the boot
    # until at least one connection is checked out, so a misconfigured DB
    # surfaces as a clean startup failure instead of failing every request.
    pool.open(wait=True, timeout=30.0)
    try:
        yield
    finally:
        pool.close()


app = FastAPI(
    title="Lakebase Reverse-ETL Operator Queue",
    description=(
        "Operator-facing API for triaging churn-risk users. Reads synced "
        "score/recommendation tables and writes operator decisions back to "
        "Lakebase for closed-loop learning."
    ),
    lifespan=lifespan,
)

# Routers are mounted under /api so they don't collide with the SPA fallback.
app.include_router(users.router, prefix="/api", tags=["users"])
app.include_router(user_detail.router, prefix="/api", tags=["users"])
app.include_router(actions.router, prefix="/api", tags=["actions"])
app.include_router(explain.router, prefix="/api", tags=["llm"])
app.include_router(admin.router, prefix="/api", tags=["admin"])


@app.get("/api/healthz", tags=["meta"])
def healthz() -> dict:
    """Liveness probe used by local devloop scripts."""
    return {"status": "ok"}


# --- SPA static mount -------------------------------------------------------
# The frontend is built into `app/frontend/dist/` by `npm run build`. We mount
# its `assets/` directory at `/assets` and fall back to `index.html` for any
# unmatched, non-/api path so client-side routing works on direct loads.
_FRONTEND_DIST = Path(__file__).parent / "frontend" / "dist"
_FRONTEND_ASSETS = _FRONTEND_DIST / "assets"
_INDEX_HTML = _FRONTEND_DIST / "index.html"

if _FRONTEND_ASSETS.is_dir():
    app.mount("/assets", StaticFiles(directory=str(_FRONTEND_ASSETS)), name="assets")


@app.get("/{full_path:path}", include_in_schema=False)
def spa_fallback(full_path: str):
    """Serve the SPA shell for any non-/api route."""
    # `/api/...` is handled by the routers above; if we got here for an /api
    # path it's genuinely unknown, so return a JSON 404 instead of HTML.
    if full_path.startswith("api/") or full_path == "api":
        return JSONResponse(status_code=404, content={"detail": "Not Found"})
    if _INDEX_HTML.is_file():
        return FileResponse(str(_INDEX_HTML))
    return JSONResponse(
        status_code=503,
        content={
            "detail": (
                "Frontend bundle missing: build with `cd app/frontend && npm "
                "run build` (expected output at app/frontend/dist/index.html)."
            )
        },
    )


# Allow `python app.py` for ad-hoc local runs (CI/CLI usually uses uvicorn).
if __name__ == "__main__":  # pragma: no cover
    import uvicorn

    uvicorn.run(
        "app:app",
        host="0.0.0.0",
        port=int(os.environ.get("PORT", "8000")),
        reload=False,
    )
