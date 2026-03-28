from fastapi import APIRouter

from services.llm_service import list_ollama_models

router = APIRouter(prefix="/llm", tags=["llm"])


@router.get("/models")
async def list_models() -> list[dict]:
    return await list_ollama_models()
