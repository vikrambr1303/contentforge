import logging

from sqlalchemy.orm import Session

from models.app_settings import AppSettings
from models.content import ContentItem
from models.topic import Topic
from services import llm_service

logger = logging.getLogger(__name__)


def refresh_caption(db: Session, item: ContentItem) -> None:
    """Fill ``caption_text`` from the quote + topic + CTA (social items only)."""
    if item.kind != "social":
        return
    text = (item.quote_text or "").strip()
    if not text:
        item.caption_text = None
        return
    topic = db.get(Topic, item.topic_id)
    app = db.get(AppSettings, 1)
    if not topic or not app:
        return
    try:
        item.caption_text = llm_service.generate_caption_sync(
            topic.name or "Content",
            text,
            app.caption_cta or "",
            app.ollama_model,
        )
    except Exception as e:  # noqa: BLE001
        logger.warning("refresh_caption failed for item %s: %s", item.id, e)
