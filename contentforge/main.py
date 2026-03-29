import asyncio
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api import content, generation, jobs, llm, platforms, settings as settings_api, topics, ws
from config import get_settings
from plugins.registry import load_plugins
from services.realtime import ConnectionManager, redis_subscriber_task


@asynccontextmanager
async def lifespan(app: FastAPI):
    load_plugins()
    settings = get_settings()
    root = Path(settings.data_dir)
    for sub in ("images", "videos", "backgrounds", "topic_refs", "blog"):
        (root / sub).mkdir(parents=True, exist_ok=True)

    manager = ConnectionManager()
    app.state.ws_manager = manager
    redis_task = asyncio.create_task(redis_subscriber_task(settings.celery_broker_url, manager))
    try:
        yield
    finally:
        redis_task.cancel()
        try:
            await redis_task
        except asyncio.CancelledError:
            pass


app = FastAPI(title="ContentForge API", version="0.1.0", lifespan=lifespan)

settings = get_settings()
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(topics.router, prefix="/api")
app.include_router(content.router, prefix="/api")
app.include_router(generation.router, prefix="/api")
app.include_router(jobs.router, prefix="/api")
app.include_router(platforms.router, prefix="/api")
app.include_router(settings_api.router, prefix="/api")
app.include_router(llm.router, prefix="/api")
app.include_router(ws.router, prefix="/api")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
