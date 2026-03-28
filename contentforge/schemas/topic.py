from datetime import datetime

from pydantic import BaseModel, Field


class TopicCreate(BaseModel):
    name: str = Field(..., max_length=255)
    description: str | None = None
    style: str = Field(default="inspirational", max_length=50)
    image_style: str = Field(default="cinematic, soft light", max_length=500)
    target_count: int = Field(default=10, ge=0)
    is_active: bool = True
    reference_image_strength: float | None = Field(
        None,
        ge=0.12,
        le=0.92,
        description="img2img strength when a style reference is set; lower ≈ closer to reference",
    )


class TopicUpdate(BaseModel):
    name: str | None = Field(None, max_length=255)
    description: str | None = None
    style: str | None = Field(None, max_length=50)
    image_style: str | None = Field(None, max_length=500)
    target_count: int | None = Field(None, ge=0)
    is_active: bool | None = None
    reference_image_strength: float | None = Field(None, ge=0.12, le=0.92)


class TopicOut(BaseModel):
    id: int
    name: str
    slug: str
    description: str | None
    style: str
    image_style: str
    style_reference_relpath: str | None = None
    reference_image_strength: float | None = None
    target_count: int
    is_active: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
