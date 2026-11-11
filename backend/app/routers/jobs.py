"""Read and steer background jobs. Starting one belongs to the resource it works on
(see POST /api/items/generate): this router only knows the generic part."""
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.services import jobs
from app.services.jobs import Job

router = APIRouter(prefix="/api/jobs", tags=["jobs"])


class JobSummary(BaseModel):
    """What the job list returns: everything except the log and the result."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    kind: str
    subject: str | None
    status: str
    progress: str
    total: int
    done: int
    error: str
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None


class JobOut(JobSummary):
    log_text: str
    result: dict | None


async def _job_or_404(db: AsyncSession, job_id: str) -> Job:
    row = await db.get(Job, job_id)
    if row is None:
        raise HTTPException(404, "Job not found")
    return row


@router.get("", response_model=list[JobSummary])
async def list_jobs(subject: str | None = None, limit: int = 20, db: AsyncSession = Depends(get_db)):
    stmt = select(Job).order_by(Job.created_at.desc()).limit(max(1, min(limit, 100)))
    if subject is not None:
        stmt = stmt.where(Job.subject == subject)
    return list((await db.scalars(stmt)).all())


@router.get("/{job_id}", response_model=JobOut)
async def get_job(job_id: str, db: AsyncSession = Depends(get_db)):
    return await _job_or_404(db, job_id)


@router.post("/{job_id}/cancel", response_model=JobOut)
async def cancel_job(job_id: str, db: AsyncSession = Depends(get_db)):
    """The job notices at its next gate or check_cancelled(), and stops there."""
    row = await _job_or_404(db, job_id)
    if row.status in jobs.ACTIVE:
        if row.status == "queued":   # never started, so nothing else will close it off
            row.finished_at = datetime.now(UTC)
            row.log_text = (row.log_text or "") + "Cancelled.\n"
        row.status, row.progress = "cancelled", ""
        await db.commit()
    return row


@router.post("/{job_id}/retry", response_model=JobOut, status_code=202)
async def retry_job(job_id: str, db: AsyncSession = Depends(get_db)):
    """A new job with the same kind, parameters and subject. The old one is kept as history."""
    old = await _job_or_404(db, job_id)
    if old.status in jobs.ACTIVE:
        raise HTTPException(409, f"Job is still {old.status}")
    return await jobs.enqueue(db, old.kind, dict(old.params or {}), subject=old.subject)
