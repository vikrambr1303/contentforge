import io
import shutil
import zipfile
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse, StreamingResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from api.deps import get_db
from config import get_settings
from models.content import ContentItem
from models.generation_job import GenerationJob
from models.topic import Topic
from schemas.content import (
    BatchDownloadRequest,
    BlogSectionInfo,
    ContentItemOut,
    ContentItemUpdate,
    ReviseContentRequest,
)
from services import blog_service, caption_service, image_service
from tasks.generate_content import run_revise_blog, run_revise_social

router = APIRouter(prefix="/content", tags=["content"])

# Same URL is reused when files are overwritten (revise/regenerate); avoid stale browser cache.
_DYNAMIC_MEDIA_HEADERS = {"Cache-Control": "private, no-store, must-revalidate"}


def _safe_path(rel: str | None) -> Path | None:
    if not rel:
        return None
    root = Path(get_settings().data_dir).resolve()
    p = (root / rel).resolve()
    if not str(p).startswith(str(root)):
        raise HTTPException(400, "Invalid path")
    return p


@router.get("", response_model=list[ContentItemOut])
def list_content(
    topic_id: int | None = None,
    status: str | None = None,
    kind: str | None = None,
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
) -> list[ContentItem]:
    q = select(ContentItem).order_by(ContentItem.id.desc())
    if topic_id is not None:
        q = q.where(ContentItem.topic_id == topic_id)
    if status:
        q = q.where(ContentItem.status == status)
    else:
        # Hide in-flight and failed generations unless a status filter is chosen explicitly.
        q = q.where(ContentItem.status.notin_(("generating", "failed")))
    if kind:
        q = q.where(ContentItem.kind == kind)
    offset = (page - 1) * limit
    q = q.offset(offset).limit(limit)
    return list(db.scalars(q).all())


def _active_job_on_item(db: Session, content_item_id: int) -> bool:
    q = (
        select(GenerationJob)
        .where(
            GenerationJob.content_item_id == content_item_id,
            GenerationJob.status.in_(("queued", "running")),
        )
        .limit(1)
    )
    return db.scalars(q).first() is not None


@router.get("/{item_id}/blog/sections", response_model=list[BlogSectionInfo])
def blog_section_list(item_id: int, db: Session = Depends(get_db)) -> list[BlogSectionInfo]:
    row = db.get(ContentItem, item_id)
    if not row or row.kind != "blog":
        raise HTTPException(404, "Not a blog content item")
    infos = blog_service.section_infos_for_api(row.blog_markdown or "")
    return [BlogSectionInfo.model_validate(x) for x in infos]


@router.post("/{item_id}/revise")
def revise_content(item_id: int, body: ReviseContentRequest, db: Session = Depends(get_db)) -> dict:
    row = db.get(ContentItem, item_id)
    if not row:
        raise HTTPException(404)
    if _active_job_on_item(db, item_id):
        raise HTTPException(409, "A job is already queued or running for this item")
    if body.mode == "feedback" and not (body.feedback or "").strip():
        raise HTTPException(400, "feedback is required when mode is feedback")
    if body.background_only:
        if row.kind != "social":
            raise HTTPException(400, "background_only applies only to social content")
        if body.mode != "feedback":
            raise HTTPException(400, "background_only requires mode feedback")

    payload: dict[str, str | int | bool] = {
        "mode": body.mode,
        "feedback": (body.feedback or "").strip(),
    }
    if row.kind == "social" and body.background_only:
        payload["background_only"] = True

    if row.kind == "blog":
        md = row.blog_markdown or ""
        sections = blog_service.split_h2_sections(md)
        if body.blog_section_index is None:
            raise HTTPException(400, "blog_section_index is required for blog items")
        idx = body.blog_section_index
        if idx < 0 or idx >= len(sections):
            raise HTTPException(400, "blog_section_index out of range")
        payload["blog_section_index"] = idx
        job_type = "revise_blog"
        delay_fn = run_revise_blog.delay
    elif row.kind == "social":
        if body.blog_section_index is not None:
            raise HTTPException(400, "blog_section_index is only for blog items")
        job_type = "revise_social"
        delay_fn = run_revise_social.delay
    else:
        raise HTTPException(400, "Unsupported content kind")

    job = GenerationJob(
        topic_id=row.topic_id,
        content_item_id=row.id,
        job_type=job_type,
        status="queued",
        payload_json=payload,
    )
    db.add(job)
    db.flush()
    job_id = job.id
    # Commit before Celery so the worker always sees payload_json (avoids race with uncommitted row).
    db.commit()
    delay_fn(job_id)
    return {"job_id": job_id}


@router.post("/{item_id}/caption/refresh", response_model=ContentItemOut)
def refresh_content_caption(item_id: int, db: Session = Depends(get_db)) -> ContentItem:
    row = db.get(ContentItem, item_id)
    if not row:
        raise HTTPException(404)
    if row.kind != "social":
        raise HTTPException(400, "Captions apply only to social content items")
    caption_service.refresh_caption(db, row)
    db.commit()
    db.refresh(row)
    return row


@router.get("/{item_id}", response_model=ContentItemOut)
def get_content(item_id: int, db: Session = Depends(get_db)) -> ContentItem:
    row = db.get(ContentItem, item_id)
    if not row:
        raise HTTPException(404)
    return row


@router.patch("/{item_id}", response_model=ContentItemOut)
def patch_content(item_id: int, body: ContentItemUpdate, db: Session = Depends(get_db)) -> ContentItem:
    row = db.get(ContentItem, item_id)
    if not row:
        raise HTTPException(404)
    data = body.model_dump(exclude_unset=True)
    if row.kind == "blog":
        for k, v in data.items():
            setattr(row, k, v)
    elif "quote_text" in data or "quote_author" in data:
        for k, v in data.items():
            if k != "status":
                setattr(row, k, v)
        bg = _safe_path(row.background_path)
        out = _safe_path(row.image_path)
        if bg and out and bg.exists() and row.quote_text:
            image_service.composite_quote(bg, out, row.quote_text, row.quote_author or "")
        if row.kind == "social":
            caption_service.refresh_caption(db, row)
    else:
        for k, v in data.items():
            setattr(row, k, v)
    db.commit()
    db.refresh(row)
    return row


@router.delete("/{item_id}", status_code=204)
def delete_content(item_id: int, db: Session = Depends(get_db)) -> None:
    row = db.get(ContentItem, item_id)
    if not row:
        raise HTTPException(404)
    for rel in (row.image_path, row.video_path, row.background_path):
        p = _safe_path(rel)
        if p and p.is_file():
            p.unlink()
    blog_dir = Path(get_settings().data_dir).resolve() / "blog" / str(item_id)
    if blog_dir.is_dir():
        shutil.rmtree(blog_dir, ignore_errors=True)
    db.delete(row)
    db.commit()


@router.get("/{item_id}/image")
def serve_image(item_id: int, db: Session = Depends(get_db)) -> FileResponse:
    row = db.get(ContentItem, item_id)
    if not row or not row.image_path:
        raise HTTPException(404)
    p = _safe_path(row.image_path)
    if not p or not p.is_file():
        raise HTTPException(404)
    return FileResponse(p, media_type="image/jpeg", headers=_DYNAMIC_MEDIA_HEADERS)


@router.get("/{item_id}/video")
def serve_video(item_id: int, db: Session = Depends(get_db)) -> FileResponse:
    row = db.get(ContentItem, item_id)
    if not row or not row.video_path:
        raise HTTPException(404)
    p = _safe_path(row.video_path)
    if not p or not p.is_file():
        raise HTTPException(404)
    return FileResponse(p, media_type="video/mp4", headers=_DYNAMIC_MEDIA_HEADERS)


@router.get("/{item_id}/download/image")
def download_image(item_id: int, db: Session = Depends(get_db)) -> FileResponse:
    row = db.get(ContentItem, item_id)
    if not row or not row.image_path:
        raise HTTPException(404)
    p = _safe_path(row.image_path)
    if not p or not p.is_file():
        raise HTTPException(404)
    topic = db.get(Topic, row.topic_id)
    slug = topic.slug if topic else "content"
    name = f"{slug}_{row.created_at.date()}_{item_id}.jpg"
    return FileResponse(p, media_type="image/jpeg", filename=name, content_disposition_type="attachment")


@router.get("/{item_id}/download/video")
def download_video(item_id: int, db: Session = Depends(get_db)) -> FileResponse:
    row = db.get(ContentItem, item_id)
    if not row or not row.video_path:
        raise HTTPException(404)
    p = _safe_path(row.video_path)
    if not p or not p.is_file():
        raise HTTPException(404)
    topic = db.get(Topic, row.topic_id)
    slug = topic.slug if topic else "content"
    name = f"{slug}_{row.created_at.date()}_{item_id}.mp4"
    return FileResponse(p, media_type="video/mp4", filename=name, content_disposition_type="attachment")


@router.get("/{item_id}/blog/diagram/{diagram_index}")
def serve_blog_diagram(item_id: int, diagram_index: int, db: Session = Depends(get_db)) -> FileResponse:
    row = db.get(ContentItem, item_id)
    if not row or row.kind != "blog" or diagram_index < 0:
        raise HTTPException(404)
    rel = f"blog/{item_id}/diagram_{diagram_index}.png"
    p = _safe_path(rel)
    if not p or not p.is_file():
        raise HTTPException(404)
    return FileResponse(p, media_type="image/png", headers=_DYNAMIC_MEDIA_HEADERS)


@router.get("/{item_id}/download/blog")
def download_blog_bundle(item_id: int, db: Session = Depends(get_db)) -> StreamingResponse:
    row = db.get(ContentItem, item_id)
    if not row or row.kind != "blog" or not row.blog_markdown:
        raise HTTPException(404)
    topic = db.get(Topic, row.topic_id)
    slug = topic.slug if topic else "content"
    prefix = f"{slug}_{row.created_at.date()}_{item_id}"
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(f"{prefix}/post.md", row.blog_markdown.encode("utf-8"))
        for rel in row.blog_assets_json or []:
            p = _safe_path(rel)
            if p and p.is_file():
                zf.write(p, f"{prefix}/{p.name}")
    buf.seek(0)
    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{prefix}_blog.zip"'},
    )


@router.post("/download/batch")
def download_batch(body: BatchDownloadRequest, db: Session = Depends(get_db)) -> StreamingResponse:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for cid in body.ids:
            item = db.get(ContentItem, cid)
            if not item:
                continue
            topic = db.get(Topic, item.topic_id)
            slug = topic.slug if topic else "content"
            date = str(item.created_at.date())
            if getattr(item, "kind", "social") == "blog" and item.blog_markdown:
                bp = f"{slug}_{date}_{item.id}_blog"
                zf.writestr(f"{bp}/post.md", item.blog_markdown.encode("utf-8"))
                for rel in item.blog_assets_json or []:
                    p = _safe_path(rel)
                    if p and p.is_file():
                        zf.write(p, f"{bp}/{p.name}")
                continue
            if item.image_path:
                p = _safe_path(item.image_path)
                if p and p.is_file():
                    zf.write(p, f"{slug}_{date}_{item.id}.jpg")
            if body.include_video and item.video_path:
                p = _safe_path(item.video_path)
                if p and p.is_file():
                    zf.write(p, f"{slug}_{date}_{item.id}.mp4")
    buf.seek(0)
    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="application/zip",
        headers={"Content-Disposition": 'attachment; filename="contentforge_export.zip"'},
    )
