from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from api.deps import get_db
from models.generation_job import GenerationJob
from schemas.generation import JobOut

router = APIRouter(prefix="/jobs", tags=["jobs"])


@router.get("", response_model=list[JobOut])
def list_jobs(
    status: str | None = None,
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
) -> list[GenerationJob]:
    q = select(GenerationJob)
    if status:
        q = q.where(GenerationJob.status == status)
    q = q.order_by(GenerationJob.id.desc()).limit(limit)
    return list(db.scalars(q).all())


@router.get("/{job_id}", response_model=JobOut)
def get_job(job_id: int, db: Session = Depends(get_db)) -> GenerationJob:
    row = db.get(GenerationJob, job_id)
    if not row:
        raise HTTPException(404)
    return row
