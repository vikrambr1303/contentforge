from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class ContentItemUpdate(BaseModel):
    quote_text: str | None = None
    quote_author: str | None = None
    blog_markdown: str | None = None
    status: str | None = Field(None, max_length=20)


class ContentItemOut(BaseModel):
    id: int
    topic_id: int
    kind: str = "social"
    quote_text: str | None
    quote_author: str | None
    caption_text: str | None = None
    blog_markdown: str | None = None
    blog_assets_json: list | None = None
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


class BlogSectionInfo(BaseModel):
    index: int
    label: str
    preview: str


class ReviseContentRequest(BaseModel):
    mode: Literal["feedback", "random"]
    feedback: str = ""
    blog_section_index: int | None = None
    # Social only: with mode=feedback, skip quote rewrite and only regenerate background + composite.
    background_only: bool = False
