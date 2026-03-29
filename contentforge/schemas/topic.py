from datetime import datetime
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, Field


class ContentStyle(StrEnum):
    """Preset voice / tone for quotes, captions, and blog copy."""

    inspirational = "inspirational"
    educational = "educational"
    humorous = "humorous"
    poetic = "poetic"
    professional = "professional"
    conversational = "conversational"
    provocative = "provocative"
    minimalist = "minimalist"
    storytelling = "storytelling"
    authoritative = "authoritative"
    empathetic = "empathetic"
    journalistic = "journalistic"


CONTENT_STYLE_VALUES: tuple[str, ...] = tuple(s.value for s in ContentStyle)


class TopicCreate(BaseModel):
    name: str = Field(..., max_length=255)
    description: str | None = None
    style: str = Field(default="inspirational", max_length=50)
    image_style: str = Field(default="cinematic, soft light", max_length=500)
    background_source: Literal["diffusers", "unsplash"] = "diffusers"
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
    background_source: Literal["diffusers", "unsplash"] | None = None
    is_active: bool | None = None
    reference_image_strength: float | None = Field(None, ge=0.12, le=0.92)


TopicRefineScope = Literal["description", "image_style", "style", "whole"]


class TopicRefineRequest(BaseModel):
    """Draft topic fields + what to improve. Does not persist; preview only."""

    name: str = Field(default="", max_length=255)
    description: str | None = None
    style: str = Field(default="inspirational", max_length=50)
    image_style: str = Field(default="cinematic, soft light", max_length=500)
    background_source: Literal["diffusers", "unsplash"] = "diffusers"
    scopes: list[TopicRefineScope] = Field(..., min_length=1)
    user_note: str | None = Field(None, max_length=2000)


class TopicRefineFieldSuggestion(BaseModel):
    text: str
    rationale: str = ""


class TopicRefineStyleSuggestion(BaseModel):
    value: ContentStyle
    rationale: str = ""


class TopicRefineResponse(BaseModel):
    description: TopicRefineFieldSuggestion | None = None
    image_style: TopicRefineFieldSuggestion | None = None
    style: TopicRefineStyleSuggestion | None = None


class TopicOut(BaseModel):
    id: int
    name: str
    slug: str
    description: str | None
    style: str
    image_style: str
    background_source: Literal["diffusers", "unsplash"] = "diffusers"
    style_reference_relpath: str | None = None
    reference_image_strength: float | None = None
    is_active: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
