from datetime import datetime

from pydantic import BaseModel, Field


class GenerateBatchRequest(BaseModel):
    topic_id: int
    count: int = Field(default=1, ge=1, le=50)
    include_video: bool = False


class GenerateQuoteRequest(BaseModel):
    topic_id: int


class GenerateImageRequest(BaseModel):
    content_item_id: int


class GenerateBlogRequest(BaseModel):
    topic_id: int


class JobOut(BaseModel):
    id: int
    topic_id: int
    content_item_id: int | None
    job_type: str
    status: str
    progress_percent: int = 0
    stage: str | None = None
    celery_task_id: str | None
    error_message: str | None
    created_at: datetime
    completed_at: datetime | None

    model_config = {"from_attributes": True}
