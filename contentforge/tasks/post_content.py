from datetime import datetime, timezone

from sqlalchemy.orm import Session

from database import SessionLocal
from models.content import ContentItem
from models.platform_account import PlatformAccount
from models.post_history import PostHistory
from models.topic import Topic
from plugins.registry import get_plugin, load_plugins
from services import llm_service
from tasks.celery_app import app
from utils.crypto import decrypt_credentials

load_plugins()


@app.task(bind=True, name="tasks.post_content.post_to_platform")
def post_to_platform(self, content_item_id: int, account_id: int) -> dict:
    db = SessionLocal()
    try:
        item = db.get(ContentItem, content_item_id)
        account = db.get(PlatformAccount, account_id)
        if not item or not account:
            return {"ok": False, "error": "Not found"}
        creds = decrypt_credentials(account.credentials_encrypted)
        plugin = get_plugin(account.platform)
        from models.app_settings import AppSettings

        app_s = db.get(AppSettings, 1)
        model = app_s.ollama_model if app_s else "llama3.2"
        topic = db.get(Topic, item.topic_id)
        stored = (item.caption_text or "").strip()
        caption = stored or llm_service.generate_caption_sync(
            topic.name if topic else "Content",
            item.quote_text or "",
            app_s.caption_cta if app_s else "",
            model,
        )
        path = item.video_path or item.image_path
        if not path:
            return {"ok": False, "error": "No media"}
        from config import get_settings

        root = get_settings().data_dir
        content_path = f"{root.rstrip('/')}/{path}"
        ctype = "video" if item.video_path else "image"
        result = plugin.post(content_path, caption, ctype, creds)
        ph = PostHistory(
            content_item_id=item.id,
            platform_account_id=account.id,
            platform_post_id=result.platform_post_id,
            status="success" if result.success else "failed",
            error_message=result.error_message,
            posted_at=datetime.now(timezone.utc),
        )
        db.add(ph)
        if result.success:
            item.status = "posted"
        db.commit()
        return {"ok": result.success, "platform_post_id": result.platform_post_id, "error": result.error_message}
    finally:
        db.close()
