"""POST /api/admin/rescore — kicks off the rescore Job via the SDK."""

from __future__ import annotations

import os

from fastapi import APIRouter, HTTPException

from server.config import get_workspace_client, get_workspace_host
from server.models import RescoreResponse

router = APIRouter()


@router.post("/admin/rescore", response_model=RescoreResponse)
def trigger_rescore() -> RescoreResponse:
    job_id_raw = os.environ.get("RESCORE_JOB_ID")
    if not job_id_raw:
        raise HTTPException(
            status_code=503,
            detail="RESCORE_JOB_ID is not configured for this app.",
        )
    try:
        job_id = int(job_id_raw)
    except ValueError as exc:
        raise HTTPException(
            status_code=500,
            detail=f"RESCORE_JOB_ID must be an integer, got {job_id_raw!r}",
        ) from exc

    client = get_workspace_client()
    try:
        wait = client.jobs.run_now(job_id=job_id)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Failed to trigger job: {exc}") from exc

    # `run_now` returns a Wait[Run] whose .response carries the run_id.
    run_id = getattr(wait, "run_id", None)
    if run_id is None:
        response = getattr(wait, "response", None)
        run_id = getattr(response, "run_id", None)
    if run_id is None:
        raise HTTPException(status_code=502, detail="Job triggered but no run_id was returned.")

    host = get_workspace_host()
    run_page_url = f"{host}/jobs/{job_id}/runs/{run_id}" if host else None

    return RescoreResponse(run_id=int(run_id), run_page_url=run_page_url)
