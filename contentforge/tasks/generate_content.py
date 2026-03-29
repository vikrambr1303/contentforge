import json
import logging
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from celery.exceptions import SoftTimeLimitExceeded
from sqlalchemy.orm import Session

from config import get_settings
from database import SessionLocal
from models.app_settings import AppSettings
from models.content import ContentItem
from models.generation_job import GenerationJob
from models.topic import Topic
from services import blog_service, caption_service, image_service, llm_service, video_service
from tasks.celery_app import app

logger = logging.getLogger(__name__)


def _coerce_job_payload(raw: object) -> dict[str, Any]:
    """MySQL JSON / drivers may return dict or a JSON string; normalize for revise tasks."""
    if raw is None:
        return {}
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str):
        try:
            data = json.loads(raw)
            return data if isinstance(data, dict) else {}
        except json.JSONDecodeError:
            return {}
    return {}


def _merge_stock_query_with_revision(search_q: str, revision_feedback: str | None) -> str:
    """Ensure Unsplash query changes when the editor gave feedback (LLM may still ignore it)."""
    if not revision_feedback or not revision_feedback.strip():
        return search_q
    fb = revision_feedback.strip().lower()
    words = re.findall(r"[a-z0-9]{3,}", fb)
    extra = " ".join(dict.fromkeys(words))[:60]
    if not extra:
        extra = re.sub(r"[^a-z0-9\s]+", " ", fb).strip()[:40]
    if not extra:
        return search_q
    merged = f"{extra} {search_q}".strip()
    return merged[:130]


def _append_revision_to_sd_prompt(prompt: str, revision_feedback: str | None, max_total: int = 480) -> str:
    if not revision_feedback or not revision_feedback.strip():
        return prompt
    fb = revision_feedback.strip().lower()
    words = re.findall(r"[a-z0-9]{3,}", fb)
    extra = ", ".join(dict.fromkeys(words))[:120]
    if not extra:
        return prompt
    out = f"{prompt}, editor revision: {extra}"
    return out[:max_total]


def _report_job_progress(job_id: int, pct: int, stage: str) -> None:
    """Update job row from a short-lived session (safe to call from SD step callbacks)."""
    db = SessionLocal()
    try:
        job = db.get(GenerationJob, job_id)
        if job and job.status == "running":
            np = min(100, max(0, int(pct)))
            job.progress_percent = max(job.progress_percent, np)
            if stage:
                job.stage = stage[:128]
            db.commit()
    finally:
        db.close()


def _diffusion_step_reporter(job_id: int, lo: int, hi: int):
    def _inner(cur: int, total: int) -> None:
        span = hi - lo
        p = lo + int(span * cur / max(total, 1))
        _report_job_progress(job_id, min(hi, p), "Generating background")

    return _inner


# Global rules for Stable Diffusion backgrounds (prepended style/mood still come from the topic).
_IMAGE_PROMPT_RULES = (
    "no humans, no faces, no people, no hands, no silhouettes of people; "
    "abstract conceptual imagery only, animated illustration and motion-design aesthetic, "
    "stylized shapes, color fields, light and texture, non-photorealistic"
)

_SD_NEGATIVE_PROMPT = (
    "person, people, human, man, woman, child, face, portrait, head, hands, body, "
    "crowd, selfie, figure, silhouette, realistic skin, stock photo model, "
    "photograph of person, walking person, eyes looking at camera"
)

_MOOD_FROM_QUOTE_KEYWORDS: tuple[tuple[tuple[str, ...], str], ...] = (
    (
        ("joy", "love", "hope", "celebrate", "happy", "grateful", "smile", "laugh"),
        "uplifting",
    ),
    (
        ("storm", "dark", "grief", "loss", "rage", "fear", "alone", "broken", "cry"),
        "dramatic",
    ),
    (("calm", "peace", "still", "quiet", "gentle", "rest", "soft"), "serene"),
)


def _mood_hint_from_quote(quote: str) -> str:
    """Cheap mood hint for background prompts when we skip quote revision."""
    t = (quote or "").lower()
    for words, mood in _MOOD_FROM_QUOTE_KEYWORDS:
        if any(w in t for w in words):
            return mood
    return "contemplative"


def _sd_background_prompt(image_style: str, mood: str) -> str:
    # Keep tail short — CLIP max ~77 tokens; long tails get truncated.
    return (
        f"{image_style}, {mood}, {_IMAGE_PROMPT_RULES}, "
        "cinematic light, high quality, no text, vertical composition"
    )


def _prepare_background_prompts(
    topic: Topic,
    mood: str,
    model: str,
    *,
    quote_excerpt: str | None = None,
    revision_feedback: str | None = None,
) -> tuple[str, str, dict[str, str | None]]:
    """LLM-enriched SD prompt when possible; returns (prompt, negative, enrich dict for Unsplash hint)."""
    enriched = llm_service.enrich_sd_prompt_sync(
        topic,
        mood,
        model,
        quote_excerpt=quote_excerpt,
        revision_feedback=revision_feedback,
    )
    visual = enriched.get("visual")
    if visual:
        prompt = (
            f"{visual}, {_IMAGE_PROMPT_RULES}, "
            "cinematic light, high quality, no text, vertical composition"
        )
        neg = _SD_NEGATIVE_PROMPT
        extra = enriched.get("negative_extra")
        if extra:
            neg = f"{_SD_NEGATIVE_PROMPT}, {extra}"
        return prompt, neg, enriched
    return _sd_background_prompt(topic.image_style, mood), _SD_NEGATIVE_PROMPT, enriched


def _produce_background(
    *,
    app_s: AppSettings,
    topic: Topic,
    mood: str,
    model: str,
    enriched: dict[str, str | None],
    prompt: str,
    neg_prompt: str,
    bg_path: Path,
    job_id: int,
    step_lo: int,
    step_hi: int,
    ref_path: Path | None,
    ref_strength: float,
    revision_feedback: str | None = None,
) -> str:
    """Write background JPEG; returns value stored on ContentItem.image_model."""
    source = (getattr(topic, "background_source", None) or "diffusers").strip().lower()
    if source not in ("diffusers", "unsplash"):
        source = "diffusers"

    if source == "unsplash":
        key = get_settings().unsplash_access_key.strip()
        if not key:
            raise ValueError(
                "This topic uses Unsplash for backgrounds but UNSPLASH_ACCESS_KEY is empty. "
                "Set it in the environment (see .env.example) or change the topic to Stable Diffusion."
            )
        mid = (step_lo + step_hi) // 2
        _report_job_progress(job_id, mid, "Finding background photo")
        search_q = llm_service.stock_photo_search_query_sync(
            topic,
            mood,
            model,
            style_hint=enriched.get("visual"),
            revision_feedback=revision_feedback,
        )
        search_q = _merge_stock_query_with_revision(search_q, revision_feedback)
        logger.info("Unsplash final search query: %s", search_q[:140])
        image_service.fetch_unsplash_background(search_q, bg_path, access_key=key)
        return "unsplash"

    step_cb = _diffusion_step_reporter(job_id, step_lo, step_hi)
    diffusers_path = app_s.diffusers_model_path or "/models/stable-diffusion"
    sd_prompt = _append_revision_to_sd_prompt(prompt, revision_feedback)
    image_service.generate_background(
        diffusers_path,
        sd_prompt,
        bg_path,
        negative_prompt=neg_prompt,
        on_diffusion_step=step_cb,
        reference_image_path=ref_path,
        reference_strength=ref_strength,
    )
    return diffusers_path


def _topic_style_reference(topic: Topic) -> tuple[Path | None, float]:
    """Resolve optional img2img reference under data_dir; strength clamped."""
    rel = topic.style_reference_relpath
    if not rel:
        return None, 0.38
    p = Path(get_settings().data_dir) / rel
    if not p.is_file():
        return None, 0.38
    s = topic.reference_image_strength
    if s is None:
        s = 0.38
    return p, max(0.12, min(0.92, float(s)))


def _settings_row(db: Session) -> AppSettings:
    row = db.get(AppSettings, 1)
    if row is None:
        row = AppSettings(
            id=1,
            ollama_model="llama3.2",
            diffusers_model_path="/models/stable-diffusion",
            default_image_style="cinematic lighting",
            caption_cta="",
            generation_retry_limit=2,
        )
        db.add(row)
        db.commit()
        db.refresh(row)
    return row


def _generation_retry_limit(app_s: AppSettings) -> int:
    v = app_s.generation_retry_limit
    if v is None:
        return 2
    return max(0, min(10, int(v)))


def _mark_job_retrying(db: Session, job_id: int, next_attempt: int, total: int) -> None:
    job = db.get(GenerationJob, job_id)
    if not job:
        return
    job.status = "running"
    job.completed_at = None
    job.error_message = None
    job.stage = f"Retry {next_attempt}/{total}"
    db.commit()


def _mark_generating_item_failed(db: Session, job: GenerationJob | None) -> None:
    """If this job was still producing a row, surface failure on the content item."""
    if not job or not job.content_item_id:
        return
    item = db.get(ContentItem, job.content_item_id)
    if item and item.status == "generating":
        item.status = "failed"


def _fail_job_final(db: Session, job_id: int, message: str) -> None:
    job = db.get(GenerationJob, job_id)
    if not job:
        return
    job.status = "failed"
    job.error_message = message[:2000]
    job.stage = "Failed"
    job.completed_at = datetime.now(timezone.utc)
    _mark_generating_item_failed(db, job)
    db.commit()


def _run_full_generation_once(
    self,
    db: Session,
    job_id: int,
    include_video: bool,
    attempt_index: int,
    total_attempts: int,
) -> dict:
    job = db.get(GenerationJob, job_id)
    if not job:
        return {"ok": False, "error": "job not found"}

    if attempt_index == 0:
        job.status = "running"
        job.celery_task_id = self.request.id
        job.progress_percent = max(job.progress_percent, 3)
        job.stage = "Starting"
        db.commit()
        logger.info(
            "run_full_generation started job_id=%s celery_task_id=%s",
            job_id,
            self.request.id,
        )
    else:
        job.stage = f"Retry {attempt_index + 1}/{total_attempts}"
        db.commit()
        logger.info(
            "run_full_generation retry job_id=%s attempt %s/%s",
            job_id,
            attempt_index + 1,
            total_attempts,
        )

    topic = db.get(Topic, job.topic_id)
    if not topic or topic.deleted_at is not None:
        job.status = "failed"
        job.error_message = "Topic missing"
        job.stage = "Failed"
        job.completed_at = datetime.now(timezone.utc)
        _mark_generating_item_failed(db, job)
        db.commit()
        return {"ok": False}

    job.progress_percent = max(job.progress_percent, 12)
    job.stage = "Writing quote"
    db.commit()

    app_s = _settings_row(db)
    model = app_s.ollama_model

    item = db.get(ContentItem, job.content_item_id) if job.content_item_id else None
    if not item:
        item = ContentItem(topic_id=topic.id, status="generating")
        db.add(item)
        db.flush()
        job.content_item_id = item.id
        db.commit()
        db.refresh(item)

    q = llm_service.generate_quote_sync(topic, model)
    item.quote_text = q["quote"]
    item.quote_author = q["author"]
    item.generation_model = model
    mood = q["mood"]

    job.progress_percent = max(job.progress_percent, 22)
    job.stage = "Refining image prompt"
    db.commit()

    prompt, neg_prompt, enriched_bg = _prepare_background_prompts(
        topic, mood, model, quote_excerpt=q.get("quote")
    )

    job.progress_percent = max(job.progress_percent, 24)
    job.stage = "Generating background"
    db.commit()

    bg_rel = f"backgrounds/{item.id}_background.jpg"
    img_rel = f"images/{item.id}_composed.jpg"
    data_root = Path(get_settings().data_dir)
    bg_path = data_root / bg_rel
    img_path = data_root / img_rel

    ref_path, ref_strength = _topic_style_reference(topic)
    image_model_label = _produce_background(
        app_s=app_s,
        topic=topic,
        mood=mood,
        model=model,
        enriched=enriched_bg,
        prompt=prompt,
        neg_prompt=neg_prompt,
        bg_path=bg_path,
        job_id=job.id,
        step_lo=26,
        step_hi=86,
        ref_path=ref_path,
        ref_strength=ref_strength,
    )
    item.background_path = bg_rel
    item.image_model = image_model_label
    job.progress_percent = max(job.progress_percent, 88)
    job.stage = "Compositing text"
    db.commit()
    image_service.composite_quote(bg_path, img_path, item.quote_text or "", item.quote_author or "")
    item.image_path = img_rel

    if include_video:
        job.progress_percent = max(job.progress_percent, 92)
        job.stage = "Rendering video"
        db.commit()
        vid_rel = f"videos/{item.id}.mp4"
        vid_path = data_root / vid_rel
        video_service.make_ken_burns_video(img_path, vid_path)
        item.video_path = vid_rel

    job.progress_percent = max(job.progress_percent, 96)
    job.stage = "Writing caption"
    db.commit()
    caption_service.refresh_caption(db, item)

    item.status = "draft"
    job.status = "done"
    job.progress_percent = 100
    job.stage = "Complete"
    job.completed_at = datetime.now(timezone.utc)
    db.commit()
    logger.info("run_full_generation finished job_id=%s item_id=%s", job_id, item.id)
    return {"ok": True, "content_item_id": item.id}


@app.task(
    bind=True,
    name="tasks.generate_content.run_full_generation",
    soft_time_limit=3600,
    time_limit=3720,
)
def run_full_generation(self, job_id: int, include_video: bool = False) -> dict:
    db = SessionLocal()
    try:
        job = db.get(GenerationJob, job_id)
        if not job:
            return {"ok": False, "error": "job not found"}

        app_s = _settings_row(db)
        retry_limit = _generation_retry_limit(app_s)
        total = retry_limit + 1
        last_exc: BaseException | None = None

        for attempt in range(total):
            try:
                if attempt > 0:
                    db.rollback()
                return _run_full_generation_once(self, db, job_id, include_video, attempt, total)
            except SoftTimeLimitExceeded:
                db.rollback()
                job = db.get(GenerationJob, job_id)
                if job:
                    job.status = "failed"
                    job.error_message = (
                        "Generation timed out (soft limit). CPU image generation can exceed an hour; "
                        "retry or give the worker more RAM/CPU."
                    )[:2000]
                    job.stage = "Failed"
                    job.completed_at = datetime.now(timezone.utc)
                    _mark_generating_item_failed(db, job)
                    db.commit()
                logger.warning("run_full_generation soft time limit job_id=%s", job_id)
                raise
            except Exception as e:  # noqa: BLE001
                last_exc = e
                logger.warning(
                    "run_full_generation job_id=%s failed attempt %s/%s: %s",
                    job_id,
                    attempt + 1,
                    total,
                    e,
                )
                if attempt >= retry_limit:
                    db.rollback()
                    _fail_job_final(db, job_id, str(e))
                    raise
                db.rollback()
                _mark_job_retrying(db, job_id, attempt + 2, total)
        if last_exc:
            raise last_exc
        return {"ok": False}
    finally:
        db.close()


def _run_quote_only_once(
    self,
    db: Session,
    job_id: int,
    attempt_index: int,
    total_attempts: int,
) -> dict:
    job = db.get(GenerationJob, job_id)
    if not job:
        return {"ok": False}

    if attempt_index == 0:
        job.status = "running"
        job.celery_task_id = self.request.id
        job.progress_percent = max(job.progress_percent, 5)
        job.stage = "Writing quote"
        db.commit()
    else:
        job.stage = f"Retry {attempt_index + 1}/{total_attempts}"
        db.commit()

    topic = db.get(Topic, job.topic_id)
    app_s = _settings_row(db)
    item = db.get(ContentItem, job.content_item_id) if job.content_item_id else None
    if not topic or not item:
        job.status = "failed"
        job.error_message = "Missing topic or content"
        job.stage = "Failed"
        job.completed_at = datetime.now(timezone.utc)
        _mark_generating_item_failed(db, job)
        db.commit()
        return {"ok": False}

    q = llm_service.generate_quote_sync(topic, app_s.ollama_model)
    item.quote_text = q["quote"]
    item.quote_author = q["author"]
    item.generation_model = app_s.ollama_model
    job.progress_percent = max(job.progress_percent, 92)
    job.stage = "Writing caption"
    db.commit()
    caption_service.refresh_caption(db, item)
    item.status = "draft"
    job.status = "done"
    job.progress_percent = 100
    job.stage = "Complete"
    job.completed_at = datetime.now(timezone.utc)
    db.commit()
    return {"ok": True}


@app.task(
    bind=True,
    name="tasks.generate_content.run_quote_only",
    soft_time_limit=600,
    time_limit=660,
)
def run_quote_only(self, job_id: int) -> dict:
    db = SessionLocal()
    try:
        job = db.get(GenerationJob, job_id)
        if not job:
            return {"ok": False}

        app_s = _settings_row(db)
        retry_limit = _generation_retry_limit(app_s)
        total = retry_limit + 1
        last_exc: BaseException | None = None

        for attempt in range(total):
            try:
                if attempt > 0:
                    db.rollback()
                return _run_quote_only_once(self, db, job_id, attempt, total)
            except SoftTimeLimitExceeded:
                db.rollback()
                job = db.get(GenerationJob, job_id)
                if job:
                    job.status = "failed"
                    job.error_message = "Quote generation timed out. Check Ollama is reachable."[:2000]
                    job.stage = "Failed"
                    job.completed_at = datetime.now(timezone.utc)
                    _mark_generating_item_failed(db, job)
                    db.commit()
                raise
            except Exception as e:  # noqa: BLE001
                last_exc = e
                logger.warning(
                    "run_quote_only job_id=%s failed attempt %s/%s: %s",
                    job_id,
                    attempt + 1,
                    total,
                    e,
                )
                if attempt >= retry_limit:
                    db.rollback()
                    _fail_job_final(db, job_id, str(e))
                    raise
                db.rollback()
                _mark_job_retrying(db, job_id, attempt + 2, total)
        if last_exc:
            raise last_exc
        return {"ok": False}
    finally:
        db.close()


def _run_image_only_once(
    self,
    db: Session,
    job_id: int,
    attempt_index: int,
    total_attempts: int,
) -> dict:
    job = db.get(GenerationJob, job_id)
    if not job:
        return {"ok": False}

    if attempt_index == 0:
        job.status = "running"
        job.celery_task_id = self.request.id
        job.progress_percent = max(job.progress_percent, 5)
        job.stage = "Preparing image"
        db.commit()
    else:
        job.stage = f"Retry {attempt_index + 1}/{total_attempts}"
        db.commit()

    topic = db.get(Topic, job.topic_id)
    app_s = _settings_row(db)
    item = db.get(ContentItem, job.content_item_id) if job.content_item_id else None
    if not topic or not item or not item.quote_text:
        job.status = "failed"
        job.error_message = "Missing data"
        job.stage = "Failed"
        job.completed_at = datetime.now(timezone.utc)
        _mark_generating_item_failed(db, job)
        db.commit()
        return {"ok": False}

    q = {"mood": "contemplative"}
    bg_rel = f"backgrounds/{item.id}_background.jpg"
    img_rel = f"images/{item.id}_composed.jpg"
    data_root = Path(get_settings().data_dir)
    bg_path = data_root / bg_rel
    img_path = data_root / img_rel
    job.progress_percent = max(job.progress_percent, 16)
    job.stage = "Refining image prompt"
    db.commit()
    prompt, neg_prompt, enriched_bg = _prepare_background_prompts(
        topic, q["mood"], app_s.ollama_model, quote_excerpt=item.quote_text
    )
    job.progress_percent = max(job.progress_percent, 18)
    job.stage = "Generating background"
    db.commit()
    ref_path, ref_strength = _topic_style_reference(topic)
    image_model_label = _produce_background(
        app_s=app_s,
        topic=topic,
        mood=q["mood"],
        model=app_s.ollama_model,
        enriched=enriched_bg,
        prompt=prompt,
        neg_prompt=neg_prompt,
        bg_path=bg_path,
        job_id=job.id,
        step_lo=20,
        step_hi=88,
        ref_path=ref_path,
        ref_strength=ref_strength,
    )
    item.background_path = bg_rel
    item.image_model = image_model_label
    job.progress_percent = max(job.progress_percent, 90)
    job.stage = "Compositing text"
    db.commit()
    image_service.composite_quote(bg_path, img_path, item.quote_text, item.quote_author or "")
    item.image_path = img_rel
    job.progress_percent = max(job.progress_percent, 96)
    job.stage = "Writing caption"
    db.commit()
    caption_service.refresh_caption(db, item)
    job.status = "done"
    job.progress_percent = 100
    job.stage = "Complete"
    job.completed_at = datetime.now(timezone.utc)
    db.commit()
    return {"ok": True}


@app.task(
    bind=True,
    name="tasks.generate_content.run_image_only",
    soft_time_limit=3600,
    time_limit=3720,
)
def run_image_only(self, job_id: int) -> dict:
    db = SessionLocal()
    try:
        job = db.get(GenerationJob, job_id)
        if not job:
            return {"ok": False}

        app_s = _settings_row(db)
        retry_limit = _generation_retry_limit(app_s)
        total = retry_limit + 1
        last_exc: BaseException | None = None

        for attempt in range(total):
            try:
                if attempt > 0:
                    db.rollback()
                return _run_image_only_once(self, db, job_id, attempt, total)
            except SoftTimeLimitExceeded:
                db.rollback()
                job = db.get(GenerationJob, job_id)
                if job:
                    job.status = "failed"
                    job.error_message = (
                        "Image generation timed out (soft limit). Retry or allocate more resources."
                    )[:2000]
                    job.stage = "Failed"
                    job.completed_at = datetime.now(timezone.utc)
                    _mark_generating_item_failed(db, job)
                    db.commit()
                raise
            except Exception as e:  # noqa: BLE001
                last_exc = e
                logger.warning(
                    "run_image_only job_id=%s failed attempt %s/%s: %s",
                    job_id,
                    attempt + 1,
                    total,
                    e,
                )
                if attempt >= retry_limit:
                    db.rollback()
                    _fail_job_final(db, job_id, str(e))
                    raise
                db.rollback()
                _mark_job_retrying(db, job_id, attempt + 2, total)
        if last_exc:
            raise last_exc
        return {"ok": False}
    finally:
        db.close()


def _run_blog_generation_once(
    self,
    db: Session,
    job_id: int,
    attempt_index: int,
    total_attempts: int,
) -> dict:
    job = db.get(GenerationJob, job_id)
    if not job:
        return {"ok": False}

    if attempt_index == 0:
        job.status = "running"
        job.celery_task_id = self.request.id
        job.progress_percent = max(job.progress_percent, 5)
        job.stage = "Starting blog job"
        db.commit()
    else:
        job.stage = f"Retry {attempt_index + 1}/{total_attempts}"
        db.commit()

    topic = db.get(Topic, job.topic_id)
    item = db.get(ContentItem, job.content_item_id) if job.content_item_id else None
    if not topic or topic.deleted_at is not None or not item or item.kind != "blog":
        job.status = "failed"
        job.error_message = "Missing topic or blog content item"
        job.stage = "Failed"
        job.completed_at = datetime.now(timezone.utc)
        _mark_generating_item_failed(db, job)
        db.commit()
        return {"ok": False}

    app_s = _settings_row(db)
    model = app_s.ollama_model

    job.progress_percent = max(job.progress_percent, 8)
    job.stage = "Planning blog (topic type & diagrams)"
    db.commit()

    plan = llm_service.classify_blog_topic_sync(topic, model)

    job.progress_percent = max(job.progress_percent, 14)
    job.stage = "Writing article (LLM)"
    db.commit()

    md_raw = llm_service.generate_blog_post_sync(topic, model, plan=plan)
    if not md_raw or len(md_raw) < 80:
        job.status = "failed"
        job.error_message = "Model returned empty or very short markdown"
        job.stage = "Failed"
        job.completed_at = datetime.now(timezone.utc)
        _mark_generating_item_failed(db, job)
        db.commit()
        return {"ok": False}

    job.progress_percent = max(job.progress_percent, 55)
    job.stage = "Rendering diagrams (if any)"
    db.commit()

    data_root = Path(get_settings().data_dir)
    final_md, rels = blog_service.process_blog_markdown(
        item_id=item.id,
        raw_markdown=md_raw,
        data_root=data_root,
    )

    item.blog_markdown = final_md
    item.blog_assets_json = rels or None
    item.generation_model = model
    item.status = "draft"

    job.status = "done"
    job.progress_percent = 100
    job.stage = "Complete"
    job.completed_at = datetime.now(timezone.utc)
    db.commit()
    return {"ok": True}


@app.task(
    bind=True,
    name="tasks.generate_content.run_blog_generation",
    soft_time_limit=1200,
    time_limit=1260,
)
def run_blog_generation(self, job_id: int) -> dict:
    db = SessionLocal()
    try:
        job = db.get(GenerationJob, job_id)
        if not job:
            return {"ok": False}

        app_s = _settings_row(db)
        retry_limit = _generation_retry_limit(app_s)
        total = retry_limit + 1
        last_exc: BaseException | None = None

        for attempt in range(total):
            try:
                if attempt > 0:
                    db.rollback()
                return _run_blog_generation_once(self, db, job_id, attempt, total)
            except SoftTimeLimitExceeded:
                db.rollback()
                job = db.get(GenerationJob, job_id)
                if job:
                    job.status = "failed"
                    job.error_message = (
                        "Blog generation timed out. Try a smaller topic or a faster model."
                    )[:2000]
                    job.stage = "Failed"
                    job.completed_at = datetime.now(timezone.utc)
                    _mark_generating_item_failed(db, job)
                    db.commit()
                raise
            except Exception as e:  # noqa: BLE001
                last_exc = e
                logger.warning(
                    "run_blog_generation job_id=%s failed attempt %s/%s: %s",
                    job_id,
                    attempt + 1,
                    total,
                    e,
                )
                if attempt >= retry_limit:
                    db.rollback()
                    _fail_job_final(db, job_id, str(e))
                    raise
                db.rollback()
                _mark_job_retrying(db, job_id, attempt + 2, total)
        if last_exc:
            raise last_exc
        return {"ok": False}
    finally:
        db.close()


def _run_revise_social_once(
    self,
    db: Session,
    job_id: int,
    attempt_index: int,
    total_attempts: int,
) -> dict:
    job = db.get(GenerationJob, job_id)
    if not job:
        return {"ok": False}

    if attempt_index == 0:
        job.status = "running"
        job.celery_task_id = self.request.id
        job.progress_percent = max(job.progress_percent, 5)
        job.stage = "Starting revision"
        db.commit()
    else:
        job.stage = f"Retry {attempt_index + 1}/{total_attempts}"
        db.commit()

    payload = _coerce_job_payload(job.payload_json)
    mode = str(payload.get("mode") or "random").strip().lower()
    use_feedback = mode == "feedback"
    feedback = str(payload.get("feedback") or "").strip()
    if use_feedback and not feedback:
        job.status = "failed"
        job.error_message = "Feedback mode requires non-empty feedback"
        job.stage = "Failed"
        job.completed_at = datetime.now(timezone.utc)
        db.commit()
        return {"ok": False}

    logger.info(
        "revise_social job_id=%s mode=%s use_feedback=%s feedback_len=%s background_only=%s",
        job_id,
        mode,
        use_feedback,
        len(feedback),
        bool(payload.get("background_only")) and use_feedback,
    )

    topic = db.get(Topic, job.topic_id)
    item = db.get(ContentItem, job.content_item_id) if job.content_item_id else None
    if not topic or topic.deleted_at is not None or not item or item.kind != "social":
        job.status = "failed"
        job.error_message = "Missing topic or social content item"
        job.stage = "Failed"
        job.completed_at = datetime.now(timezone.utc)
        db.commit()
        return {"ok": False}

    app_s = _settings_row(db)
    model = app_s.ollama_model
    regen_video = bool(item.video_path)
    revision_fb = feedback if use_feedback else None
    background_only = bool(payload.get("background_only")) and use_feedback

    if background_only:
        job.progress_percent = max(job.progress_percent, 15)
        job.stage = "Keeping quote; refining background"
        db.commit()
        mood = _mood_hint_from_quote(item.quote_text or "")
        logger.info(
            "revise_social job_id=%s background_only=True mood_hint=%s",
            job_id,
            mood,
        )
    else:
        job.progress_percent = max(job.progress_percent, 15)
        job.stage = "Revising quote"
        db.commit()

        q = llm_service.revise_quote_for_social_sync(
            topic,
            model,
            previous_quote=item.quote_text or "",
            previous_author=item.quote_author or "",
            feedback=feedback,
            use_feedback=use_feedback,
        )
        item.quote_text = q["quote"]
        item.quote_author = q["author"]
        mood = q["mood"]

    item.generation_model = model

    job.progress_percent = max(job.progress_percent, 30)
    job.stage = "Refining image prompt"
    db.commit()

    prompt, neg_prompt, enriched_bg = _prepare_background_prompts(
        topic,
        mood,
        model,
        quote_excerpt=item.quote_text,
        revision_feedback=revision_fb,
    )

    job.progress_percent = max(job.progress_percent, 35)
    job.stage = "Generating background"
    db.commit()

    bg_rel = f"backgrounds/{item.id}_background.jpg"
    img_rel = f"images/{item.id}_composed.jpg"
    data_root = Path(get_settings().data_dir)
    bg_path = data_root / bg_rel
    img_path = data_root / img_rel

    ref_path, ref_strength = _topic_style_reference(topic)
    image_model_label = _produce_background(
        app_s=app_s,
        topic=topic,
        mood=mood,
        model=model,
        enriched=enriched_bg,
        prompt=prompt,
        neg_prompt=neg_prompt,
        bg_path=bg_path,
        job_id=job.id,
        step_lo=40,
        step_hi=85,
        ref_path=ref_path,
        ref_strength=ref_strength,
        revision_feedback=revision_fb,
    )
    item.background_path = bg_rel
    item.image_model = image_model_label

    job.progress_percent = max(job.progress_percent, 90)
    job.stage = "Compositing"
    db.commit()
    image_service.composite_quote(bg_path, img_path, item.quote_text or "", item.quote_author or "")
    item.image_path = img_rel

    if regen_video:
        job.progress_percent = max(job.progress_percent, 93)
        job.stage = "Rendering video"
        db.commit()
        vid_rel = f"videos/{item.id}.mp4"
        vid_path = data_root / vid_rel
        if vid_path.is_file():
            vid_path.unlink()
        video_service.make_ken_burns_video(img_path, vid_path)
        item.video_path = vid_rel

    need_caption = (not background_only) or not (item.caption_text or "").strip()
    if need_caption:
        job.progress_percent = max(job.progress_percent, 96)
        job.stage = "Writing caption"
        db.commit()
        caption_service.refresh_caption(db, item)

    job.status = "done"
    job.progress_percent = 100
    job.stage = "Complete"
    job.completed_at = datetime.now(timezone.utc)
    db.commit()
    return {"ok": True}


@app.task(
    bind=True,
    name="tasks.generate_content.run_revise_social",
    soft_time_limit=3600,
    time_limit=3720,
)
def run_revise_social(self, job_id: int) -> dict:
    db = SessionLocal()
    try:
        job = db.get(GenerationJob, job_id)
        if not job:
            return {"ok": False}

        app_s = _settings_row(db)
        retry_limit = _generation_retry_limit(app_s)
        total = retry_limit + 1
        last_exc: BaseException | None = None

        for attempt in range(total):
            try:
                if attempt > 0:
                    db.rollback()
                return _run_revise_social_once(self, db, job_id, attempt, total)
            except SoftTimeLimitExceeded:
                db.rollback()
                job = db.get(GenerationJob, job_id)
                if job:
                    job.status = "failed"
                    job.error_message = (
                        "Social revision timed out. Retry or allocate more worker resources."
                    )[:2000]
                    job.stage = "Failed"
                    job.completed_at = datetime.now(timezone.utc)
                    db.commit()
                raise
            except Exception as e:  # noqa: BLE001
                last_exc = e
                logger.warning(
                    "run_revise_social job_id=%s failed attempt %s/%s: %s",
                    job_id,
                    attempt + 1,
                    total,
                    e,
                )
                if attempt >= retry_limit:
                    db.rollback()
                    _fail_job_final(db, job_id, str(e))
                    raise
                db.rollback()
                _mark_job_retrying(db, job_id, attempt + 2, total)
        if last_exc:
            raise last_exc
        return {"ok": False}
    finally:
        db.close()


def _run_revise_blog_once(
    self,
    db: Session,
    job_id: int,
    attempt_index: int,
    total_attempts: int,
) -> dict:
    job = db.get(GenerationJob, job_id)
    if not job:
        return {"ok": False}

    if attempt_index == 0:
        job.status = "running"
        job.celery_task_id = self.request.id
        job.progress_percent = max(job.progress_percent, 5)
        job.stage = "Starting blog revision"
        db.commit()
    else:
        job.stage = f"Retry {attempt_index + 1}/{total_attempts}"
        db.commit()

    payload = _coerce_job_payload(job.payload_json)
    mode = str(payload.get("mode") or "random").strip().lower()
    use_feedback = mode == "feedback"
    feedback = str(payload.get("feedback") or "").strip()
    if use_feedback and not feedback:
        job.status = "failed"
        job.error_message = "Feedback mode requires non-empty feedback"
        job.stage = "Failed"
        job.completed_at = datetime.now(timezone.utc)
        db.commit()
        return {"ok": False}

    logger.info(
        "revise_blog job_id=%s mode=%s use_feedback=%s feedback_len=%s section=%s",
        job_id,
        mode,
        use_feedback,
        len(feedback),
        payload.get("blog_section_index"),
    )

    try:
        sec_idx = int(payload.get("blog_section_index"))
    except (TypeError, ValueError):
        sec_idx = -1

    topic = db.get(Topic, job.topic_id)
    item = db.get(ContentItem, job.content_item_id) if job.content_item_id else None
    if not topic or topic.deleted_at is not None or not item or item.kind != "blog":
        job.status = "failed"
        job.error_message = "Missing topic or blog content item"
        job.stage = "Failed"
        job.completed_at = datetime.now(timezone.utc)
        db.commit()
        return {"ok": False}

    md = item.blog_markdown or ""
    sections = blog_service.split_h2_sections(md)
    if sec_idx < 0 or sec_idx >= len(sections):
        job.status = "failed"
        job.error_message = "Invalid blog_section_index"
        job.stage = "Failed"
        job.completed_at = datetime.now(timezone.utc)
        db.commit()
        return {"ok": False}

    app_s = _settings_row(db)
    model = app_s.ollama_model

    job.progress_percent = max(job.progress_percent, 20)
    job.stage = "Rewriting section (LLM)"
    db.commit()

    new_block = llm_service.revise_blog_section_sync(
        topic,
        model,
        section_block=sections[sec_idx],
        section_index=sec_idx,
        feedback=feedback,
        use_feedback=use_feedback,
    )
    if not (new_block or "").strip():
        job.status = "failed"
        job.error_message = "Model returned an empty section"
        job.stage = "Failed"
        job.completed_at = datetime.now(timezone.utc)
        db.commit()
        return {"ok": False}

    try:
        full_md = blog_service.replace_h2_section(md, sec_idx, new_block)
    except ValueError:
        job.status = "failed"
        job.error_message = "Could not splice section into document"
        job.stage = "Failed"
        job.completed_at = datetime.now(timezone.utc)
        db.commit()
        return {"ok": False}

    job.progress_percent = max(job.progress_percent, 55)
    job.stage = "Rendering diagrams"
    db.commit()

    data_root = Path(get_settings().data_dir)
    blog_service.clear_blog_diagram_pngs(item.id, data_root)
    final_md, rels = blog_service.process_blog_markdown(
        item_id=item.id,
        raw_markdown=full_md,
        data_root=data_root,
    )
    item.blog_markdown = final_md
    item.blog_assets_json = rels or None
    item.generation_model = model

    job.status = "done"
    job.progress_percent = 100
    job.stage = "Complete"
    job.completed_at = datetime.now(timezone.utc)
    db.commit()
    return {"ok": True}


@app.task(
    bind=True,
    name="tasks.generate_content.run_revise_blog",
    soft_time_limit=1200,
    time_limit=1260,
)
def run_revise_blog(self, job_id: int) -> dict:
    db = SessionLocal()
    try:
        job = db.get(GenerationJob, job_id)
        if not job:
            return {"ok": False}

        app_s = _settings_row(db)
        retry_limit = _generation_retry_limit(app_s)
        total = retry_limit + 1
        last_exc: BaseException | None = None

        for attempt in range(total):
            try:
                if attempt > 0:
                    db.rollback()
                return _run_revise_blog_once(self, db, job_id, attempt, total)
            except SoftTimeLimitExceeded:
                db.rollback()
                job = db.get(GenerationJob, job_id)
                if job:
                    job.status = "failed"
                    job.error_message = (
                        "Blog revision timed out. Try a smaller section or a faster model."
                    )[:2000]
                    job.stage = "Failed"
                    job.completed_at = datetime.now(timezone.utc)
                    db.commit()
                raise
            except Exception as e:  # noqa: BLE001
                last_exc = e
                logger.warning(
                    "run_revise_blog job_id=%s failed attempt %s/%s: %s",
                    job_id,
                    attempt + 1,
                    total,
                    e,
                )
                if attempt >= retry_limit:
                    db.rollback()
                    _fail_job_final(db, job_id, str(e))
                    raise
                db.rollback()
                _mark_job_retrying(db, job_id, attempt + 2, total)
        if last_exc:
            raise last_exc
        return {"ok": False}
    finally:
        db.close()
