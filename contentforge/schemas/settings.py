from typing import Literal

from pydantic import BaseModel, Field


class SettingsOut(BaseModel):
    ollama_model: str
    diffusers_model_path: str
    default_image_style: str
    caption_cta: str
    generation_retry_limit: int = 2
    background_source: Literal["diffusers", "unsplash"] = "diffusers"

    model_config = {"from_attributes": True}


class SettingsUpdate(BaseModel):
    ollama_model: str | None = Field(None, max_length=100)
    diffusers_model_path: str | None = Field(None, max_length=1024)
    default_image_style: str | None = Field(None, max_length=500)
    caption_cta: str | None = Field(None, max_length=500)
    generation_retry_limit: int | None = Field(None, ge=0, le=10)
    background_source: Literal["diffusers", "unsplash"] | None = None
