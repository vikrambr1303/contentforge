from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path

import httpx
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from PIL import Image
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from api.deps import get_db
from config import get_settings
from models.app_settings import AppSettings
from models.content import ContentItem
from models.topic import Topic
from schemas.topic import TopicCreate, TopicOut, TopicRefineRequest, TopicRefineResponse, TopicUpdate
from services import llm_service
from utils.slug import slugify

router = APIRouter(prefix="/topics", tags=["topics"])


@router.get("", response_model=list[TopicOut])
def list_topics(db: Session = Depends(get_db)) -> list[Topic]:
    q = select(Topic).where(Topic.deleted_at.is_(None)).order_by(Topic.id.desc())
    return list(db.scalars(q).all())


@router.post("/refine-preview", response_model=TopicRefineResponse)
def refine_topic_preview(body: TopicRefineRequest, db: Session = Depends(get_db)) -> TopicRefineResponse:
    """LLM-assisted topic brief improvements; does not persist."""
    row = db.get(AppSettings, 1)
    if row is None:
        raise HTTPException(503, "App settings not initialized")
    model = (row.ollama_model or "llama3.2").strip()
    try:
        return llm_service.refine_topic_draft_sync(
            name=body.name,
            description=body.description,
            style=body.style,
            image_style=body.image_style,
            background_source=body.background_source,
            scopes=list(body.scopes),
            user_note=body.user_note,
            model=model,
        )
    except ValueError as e:
        raise HTTPException(422, str(e)) from e
    except httpx.HTTPError as e:
        raise HTTPException(502, f"Ollama request failed: {e}") from e


@router.post("", response_model=TopicOut)
def create_topic(body: TopicCreate, db: Session = Depends(get_db)) -> Topic:
    base = slugify(body.name)
    slug = base
    n = 1
    while db.scalar(select(func.count()).select_from(Topic).where(Topic.slug == slug)):
        slug = f"{base}-{n}"
        n += 1
    row = Topic(
        name=body.name,
        slug=slug,
        description=body.description,
        style=body.style,
        image_style=body.image_style,
        background_source=body.background_source,
        is_active=body.is_active,
        reference_image_strength=body.reference_image_strength,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def _reference_file_path(topic: Topic) -> Path | None:
    rel = topic.style_reference_relpath
    if not rel:
        return None
    root = Path(get_settings().data_dir).resolve()
    path = (Path(get_settings().data_dir) / rel).resolve()
    if not str(path).startswith(str(root)):
        return None
    return path if path.is_file() else None


@router.get("/{topic_id}/reference-image")
def get_topic_reference_image(topic_id: int, db: Session = Depends(get_db)) -> FileResponse:
    row = db.get(Topic, topic_id)
    if not row or row.deleted_at is not None:
        raise HTTPException(404, "Topic not found")
    path = _reference_file_path(row)
    if path is None:
        raise HTTPException(404, "No reference image")
    return FileResponse(path, media_type="image/jpeg")


@router.post("/{topic_id}/reference-image", response_model=TopicOut)
async def upload_topic_reference_image(
    topic_id: int,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
) -> Topic:
    row = db.get(Topic, topic_id)
    if not row or row.deleted_at is not None:
        raise HTTPException(404, "Topic not found")
    ct = (file.content_type or "").lower()
    if ct not in ("image/jpeg", "image/jpg", "image/png", "image/webp"):
        raise HTTPException(400, "File must be JPEG, PNG, or WebP")
    raw = await file.read()
    if len(raw) > 8 * 1024 * 1024:
        raise HTTPException(400, "Image must be 8MB or smaller")
    try:
        img = Image.open(BytesIO(raw)).convert("RGB")
    except Exception:
        raise HTTPException(400, "Could not read image") from None
    img.thumbnail((1024, 1024), Image.Resampling.LANCZOS)
    rel = f"topic_refs/{topic_id}/reference.jpg"
    dest = Path(get_settings().data_dir) / rel
    dest.parent.mkdir(parents=True, exist_ok=True)
    img.save(dest, format="JPEG", quality=88)
    row.style_reference_relpath = rel
    db.commit()
    db.refresh(row)
    return row


@router.delete("/{topic_id}/reference-image", response_model=TopicOut)
def delete_topic_reference_image(topic_id: int, db: Session = Depends(get_db)) -> Topic:
    row = db.get(Topic, topic_id)
    if not row or row.deleted_at is not None:
        raise HTTPException(404, "Topic not found")
    path = _reference_file_path(row)
    if path is not None:
        try:
            path.unlink()
        except OSError:
            pass
    row.style_reference_relpath = None
    db.commit()
    db.refresh(row)
    return row


@router.get("/{topic_id}", response_model=TopicOut)
def get_topic(topic_id: int, db: Session = Depends(get_db)) -> Topic:
    row = db.get(Topic, topic_id)
    if not row or row.deleted_at is not None:
        raise HTTPException(404, "Topic not found")
    return row


@router.patch("/{topic_id}", response_model=TopicOut)
def update_topic(topic_id: int, body: TopicUpdate, db: Session = Depends(get_db)) -> Topic:
    row = db.get(Topic, topic_id)
    if not row or row.deleted_at is not None:
        raise HTTPException(404, "Topic not found")
    data = body.model_dump(exclude_unset=True)
    for k, v in data.items():
        setattr(row, k, v)
    db.commit()
    db.refresh(row)
    return row


@router.delete("/{topic_id}", status_code=204)
def delete_topic(topic_id: int, db: Session = Depends(get_db)) -> None:
    row = db.get(Topic, topic_id)
    if not row or row.deleted_at is not None:
        raise HTTPException(404, "Topic not found")
    row.deleted_at = datetime.now(timezone.utc)
    row.is_active = False
    db.execute(update(ContentItem).where(ContentItem.topic_id == topic_id).values(status="archived"))
    db.commit()
