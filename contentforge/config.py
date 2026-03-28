from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    database_url: str = "mysql+pymysql://contentforge:changeme_app@localhost:3306/contentforge?charset=utf8mb4"
    secret_key: str = "development-change-me"
    data_dir: str = "/app/data"
    ollama_base_url: str = "http://localhost:11434"
    celery_broker_url: str = "redis://localhost:6379/0"
    celery_result_backend: str = "redis://localhost:6379/0"
    public_base_url: str = ""

    cors_origins: list[str] = [
        "http://127.0.0.1:5173",
        "http://localhost:5173",
    ]

    # Stable Diffusion (worker): when CUDA is available, use this step count (higher = slower, often sharper).
    sd_inference_steps_gpu: int = 32
    # Set true to keep SD on CPU even if a GPU is visible (debug / shared GPU).
    force_sd_cpu: bool = False

    # Unsplash (https://unsplash.com/oauth/applications) — used when background_source is "unsplash".
    unsplash_access_key: str = ""


@lru_cache
def get_settings() -> Settings:
    return Settings()
