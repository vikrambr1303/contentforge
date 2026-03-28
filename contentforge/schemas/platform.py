from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class AccountCreate(BaseModel):
    platform: str
    display_name: str = Field(..., max_length=255)
    credentials: dict[str, Any]


class PlatformAccountOut(BaseModel):
    id: int
    platform: str
    display_name: str
    is_active: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class PostRequest(BaseModel):
    content_item_id: int
    account_id: int


class PostHistoryOut(BaseModel):
    id: int
    content_item_id: int
    platform_account_id: int
    platform_post_id: str | None
    status: str
    error_message: str | None
    posted_at: datetime

    model_config = {"from_attributes": True}
