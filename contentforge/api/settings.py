from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from api.deps import get_db
from models.app_settings import AppSettings
from schemas.settings import SettingsOut, SettingsUpdate
router = APIRouter(prefix="/settings", tags=["settings"])


def _get_or_create(db: Session) -> AppSettings:
    row = db.get(AppSettings, 1)
    if row is None:
        row = AppSettings(
            id=1,
            ollama_model="llama3.2",
            diffusers_model_path="/models/stable-diffusion",
            default_image_style="cinematic lighting, soft gradients",
            caption_cta="",
            generation_retry_limit=2,
            background_source="diffusers",
        )
        db.add(row)
        db.commit()
        db.refresh(row)
    return row


@router.get("", response_model=SettingsOut)
def get_settings_api(db: Session = Depends(get_db)) -> AppSettings:
    return _get_or_create(db)


@router.patch("", response_model=SettingsOut)
def patch_settings(body: SettingsUpdate, db: Session = Depends(get_db)) -> AppSettings:
    row = _get_or_create(db)
    data = body.model_dump(exclude_unset=True)
    for k, v in data.items():
        setattr(row, k, v)
    db.commit()
    db.refresh(row)
    return row
