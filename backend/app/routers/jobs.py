"""Poll / cancel long-running jobs (video encoding, SD-zip build)."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from ..services import jobs as jobs_service

router = APIRouter(prefix="/api", tags=["jobs"])


@router.get("/jobs/{job_id}")
async def get_job(job_id: str) -> dict:
    job = jobs_service.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Unknown job")
    return job.as_dict()


@router.post("/jobs/{job_id}/cancel")
async def cancel_job(job_id: str) -> dict:
    """Ask a running job to stop. The worker polls this and bails out cleanly
    (e.g. the SD-zip build discards its half-written temp file)."""
    if not jobs_service.request_cancel(job_id):
        raise HTTPException(status_code=404, detail="Unknown job")
    return {"ok": True}
