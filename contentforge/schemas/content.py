from datetime import datetime

from pydantic import BaseModel, Field


class ContentItemUpdate(BaseModel):
    quote_text: str | None = None
    quote_author: str | None = None
    status: str | None = Field(None, max_length=20)


class ContentItemOut(BaseModel):
    id: int
    topic_id: int
    quote_text: str | None
    quote_author: str | None
    image_path: str | None
    video_path: str | None
    background_path: str | None
    status: str
    generation_model: str | None
    image_model: str | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class BatchDownloadRequest(BaseModel):
    ids: list[int]
    include_video: bool = False
