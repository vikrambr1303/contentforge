from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from api.deps import get_db
from models.content import ContentItem
from models.generation_job import GenerationJob
from models.topic import Topic
from schemas.generation import (
    GenerateBatchRequest,
    GenerateBlogRequest,
    GenerateImageRequest,
    GenerateQuoteRequest,
)
from tasks.generate_content import run_blog_generation, run_full_generation, run_image_only, run_quote_only

router = APIRouter(prefix="/generate", tags=["generation"])


@router.post("")
def trigger_generate(body: GenerateBatchRequest, db: Session = Depends(get_db)) -> dict:
    topic = db.get(Topic, body.topic_id)
    if not topic or topic.deleted_at is not None:
        raise HTTPException(404, "Topic not found")
    job_ids: list[int] = []
    for _ in range(body.count):
        item = ContentItem(topic_id=body.topic_id, status="draft")
        db.add(item)
        db.flush()
        job = GenerationJob(
            topic_id=body.topic_id,
            content_item_id=item.id,
            job_type="full",
            status="queued",
        )
        db.add(job)
        db.flush()
        run_full_generation.delay(job.id, body.include_video)
        job_ids.append(job.id)
    db.commit()
    return {"job_ids": job_ids}


@router.post("/quote")
def trigger_quote(body: GenerateQuoteRequest, db: Session = Depends(get_db)) -> dict:
    topic = db.get(Topic, body.topic_id)
    if not topic or topic.deleted_at is not None:
        raise HTTPException(404, "Topic not found")
    item = ContentItem(topic_id=body.topic_id, status="draft")
    db.add(item)
    db.flush()
    job = GenerationJob(
        topic_id=body.topic_id,
        content_item_id=item.id,
        job_type="quote",
        status="queued",
    )
    db.add(job)
    db.flush()
    run_quote_only.delay(job.id)
    db.commit()
    return {"job_id": job.id}


@router.post("/blog")
def trigger_blog(body: GenerateBlogRequest, db: Session = Depends(get_db)) -> dict:
    topic = db.get(Topic, body.topic_id)
    if not topic or topic.deleted_at is not None:
        raise HTTPException(404, "Topic not found")
    item = ContentItem(topic_id=body.topic_id, kind="blog", status="draft")
    db.add(item)
    db.flush()
    job = GenerationJob(
        topic_id=body.topic_id,
        content_item_id=item.id,
        job_type="blog",
        status="queued",
    )
    db.add(job)
    db.flush()
    run_blog_generation.delay(job.id)
    db.commit()
    return {"job_id": job.id}


@router.post("/image")
def trigger_image(body: GenerateImageRequest, db: Session = Depends(get_db)) -> dict:
    item = db.get(ContentItem, body.content_item_id)
    if not item:
        raise HTTPException(404, "Content not found")
    job = GenerationJob(
        topic_id=item.topic_id,
        content_item_id=item.id,
        job_type="image",
        status="queued",
    )
    db.add(job)
    db.flush()
    run_image_only.delay(job.id)
    db.commit()
    return {"job_id": job.id}
