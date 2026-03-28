import json
import logging
import re
import secrets
from typing import Any

import httpx

from config import get_settings
from models.topic import Topic

logger = logging.getLogger(__name__)

# Ollama /api/generate — without temperature the same prompt often yields identical quotes.
_OLLAMA_SAMPLE_OPTIONS: dict[str, Any] = {
    "temperature": 0.88,
    "top_p": 0.92,
    "repeat_penalty": 1.12,
}

# Structured “prompt engineer” output — slightly lower temperature for coherence.
_OLLAMA_ENRICH_OPTIONS: dict[str, Any] = {
    "temperature": 0.72,
    "top_p": 0.9,
    "repeat_penalty": 1.08,
}


def _extract_json(text: str) -> dict[str, Any]:
    text = text.strip()
    m = re.search(r"\{[\s\S]*\}", text)
    if not m:
        raise ValueError("No JSON object in LLM response")
    return json.loads(m.group())


async def generate_quote(topic: Topic, model: str) -> dict[str, str]:
    """Returns quote, author, mood per design doc §9.1."""
    settings = get_settings()
    nonce = secrets.token_hex(4)
    user_prompt = f"""
Generate one memorable quote related to: {topic.name}
Topic description: {topic.description or ""}
Style: {topic.style}

Request id: {nonce} — avoid repeating well-known clichés or the same line you would give for a similar ask; make this instance specific and fresh.

Return JSON with exactly these fields:
  quote: string (the quote, max 120 characters)
  author: string (real or fitting fictional attribution)
  mood: string (one of: serene, dramatic, contemplative, uplifting)
"""
    payload = {
        "model": model,
        "prompt": user_prompt,
        "system": "You are a creative writer. Respond ONLY with valid JSON, no markdown.",
        "stream": False,
        "format": "json",
        "options": _OLLAMA_SAMPLE_OPTIONS,
    }
    async with httpx.AsyncClient(timeout=120.0) as client:
        r = await client.post(f"{settings.ollama_base_url.rstrip('/')}/api/generate", json=payload)
        r.raise_for_status()
        data = r.json()
    raw = data.get("response") or ""
    try:
        parsed = _extract_json(raw)
    except (json.JSONDecodeError, ValueError):
        parsed = json.loads(raw) if raw.strip().startswith("{") else {}
    quote = str(parsed.get("quote", "")).strip()[:500]
    author = str(parsed.get("author", "Unknown")).strip()[:255]
    mood = str(parsed.get("mood", "contemplative")).strip()
    if mood not in ("serene", "dramatic", "contemplative", "uplifting"):
        mood = "contemplative"
    return {"quote": quote, "author": author, "mood": mood}


async def generate_caption(
    topic_name: str,
    quote_text: str,
    cta: str,
    model: str,
) -> str:
    settings = get_settings()
    user_prompt = f"""
Write an Instagram caption under 2200 characters.
Topic: {topic_name}
Quote: {quote_text}
Include relevant hashtags from the topic name and this call-to-action if it fits: {cta or "none"}
Return JSON: {{"caption": "..."}}
"""
    payload = {
        "model": model,
        "prompt": user_prompt,
        "system": "Respond ONLY with valid JSON.",
        "stream": False,
        "format": "json",
        "options": _OLLAMA_SAMPLE_OPTIONS,
    }
    async with httpx.AsyncClient(timeout=120.0) as client:
        r = await client.post(f"{settings.ollama_base_url.rstrip('/')}/api/generate", json=payload)
        r.raise_for_status()
        data = r.json()
    raw = (data.get("response") or "").strip()
    try:
        parsed = _extract_json(raw)
        cap = str(parsed.get("caption", quote_text))[:2200]
    except Exception:
        cap = f"{quote_text}\n\n#{topic_name.replace(' ', '')}"[:2200]
    return cap


def generate_quote_sync(topic: Topic, model: str) -> dict[str, str]:
    """Sync variant for Celery workers."""
    settings = get_settings()
    nonce = secrets.token_hex(4)
    user_prompt = f"""
Generate one memorable quote related to: {topic.name}
Topic description: {topic.description or ""}
Style: {topic.style}

Request id: {nonce} — avoid repeating well-known clichés or the same line you would give for a similar ask; make this instance specific and fresh.

Return JSON with exactly these fields:
  quote: string (the quote, max 120 characters)
  author: string (real or fitting fictional attribution)
  mood: string (one of: serene, dramatic, contemplative, uplifting)
"""
    payload = {
        "model": model,
        "prompt": user_prompt,
        "system": "You are a creative writer. Respond ONLY with valid JSON, no markdown.",
        "stream": False,
        "format": "json",
        "options": _OLLAMA_SAMPLE_OPTIONS,
    }
    with httpx.Client(timeout=120.0) as client:
        r = client.post(f"{settings.ollama_base_url.rstrip('/')}/api/generate", json=payload)
        r.raise_for_status()
        data = r.json()
    raw = data.get("response") or ""
    try:
        parsed = _extract_json(raw)
    except (json.JSONDecodeError, ValueError):
        parsed = json.loads(raw) if raw.strip().startswith("{") else {}
    quote = str(parsed.get("quote", "")).strip()[:500]
    author = str(parsed.get("author", "Unknown")).strip()[:255]
    mood = str(parsed.get("mood", "contemplative")).strip()
    if mood not in ("serene", "dramatic", "contemplative", "uplifting"):
        mood = "contemplative"
    return {"quote": quote, "author": author, "mood": mood}


def generate_caption_sync(topic_name: str, quote_text: str, cta: str, model: str) -> str:
    settings = get_settings()
    user_prompt = f"""
Write an Instagram caption under 2200 characters.
Topic: {topic_name}
Quote: {quote_text}
Include relevant hashtags from the topic name and this call-to-action if it fits: {cta or "none"}
Return JSON: {{"caption": "..."}}
"""
    payload = {
        "model": model,
        "prompt": user_prompt,
        "system": "Respond ONLY with valid JSON.",
        "stream": False,
        "format": "json",
        "options": _OLLAMA_SAMPLE_OPTIONS,
    }
    with httpx.Client(timeout=120.0) as client:
        r = client.post(f"{settings.ollama_base_url.rstrip('/')}/api/generate", json=payload)
        r.raise_for_status()
        data = r.json()
    raw = (data.get("response") or "").strip()
    try:
        parsed = _extract_json(raw)
        cap = str(parsed.get("caption", quote_text))[:2200]
    except Exception:
        cap = f"{quote_text}\n\n#{topic_name.replace(' ', '')}"[:2200]
    return cap


def enrich_sd_prompt_sync(
    topic: Topic,
    mood: str,
    model: str,
    *,
    quote_excerpt: str | None = None,
) -> dict[str, str | None]:
    """
    Expand topic + mood (+ optional quote) into a richer Stable Diffusion prompt stem via Ollama.

    Returns {"visual": str | None, "negative_extra": str | None}. If "visual" is None, callers
    should fall back to a simple template (e.g. image_style + mood only).
    """
    settings = get_settings()
    qx = (quote_excerpt or "").strip()
    if len(qx) > 160:
        qx = qx[:157] + "…"
    quote_block = (
        f'Line from the generated quote (thematic color/metaphor only; do not depict text): "{qx}"\n'
        if qx
        else ""
    )
    ref_note = ""
    if getattr(topic, "style_reference_relpath", None):
        ref_note = (
            "\nA user-uploaded reference image will steer color, lighting, and layout (img2img). "
            "Propose an abstract background in the same visual family (palette, energy) — do not assume "
            "or describe specific objects from that image.\n"
        )

    user_prompt = f"""You write fragments for Stable Diffusion 1.5 image prompts (backgrounds only).

Topic name: {topic.name}
Topic description: {topic.description or "(none)"}
Editor visual style hint: {topic.image_style}
Mood: {mood}
{ref_note}{quote_block}
Write one dense comma-separated ENGLISH fragment: abstract or highly stylized scenery — color, light, atmosphere, shapes, texture, motion-energy. Premium motion-design / illustrative / gradient-art bias. Not a stock photo.

Hard rules:
- NO people, faces, hands, bodies, silhouettes, crowds.
- NO readable text, letters, logos, watermarks, UI, screenshots.
- Non-photorealistic; avoid hyperreal skin or documentary look.

Return JSON only, exactly:
{{"visual": "<=280 chars, comma-separated keywords/phrases only>", "negative_extra": "<=120 chars extra negatives or empty string>"}}

Do not put aspect ratio words in "visual". No markdown."""

    payload = {
        "model": model,
        "prompt": user_prompt,
        "system": "Respond ONLY with valid JSON, no markdown.",
        "stream": False,
        "format": "json",
        "options": _OLLAMA_ENRICH_OPTIONS,
    }
    url = f"{settings.ollama_base_url.rstrip('/')}/api/generate"
    # httpx requires a default timeout or all of connect/read/write/pool.
    timeout = httpx.Timeout(connect=10.0, read=90.0, write=60.0, pool=10.0)
    try:
        logger.info("SD prompt enrichment: POST %s model=%s", url, model)
        with httpx.Client(timeout=timeout) as client:
            r = client.post(url, json=payload)
            r.raise_for_status()
            data = r.json()
        raw = data.get("response") or ""
        parsed = _extract_json(raw)
        logger.info("SD prompt enrichment: done for topic=%s", topic.name[:80])
    except (httpx.HTTPError, json.JSONDecodeError, ValueError, TypeError) as e:
        logger.warning("SD prompt enrichment failed, using template fallback: %s", e)
        return {"visual": None, "negative_extra": None}

    visual = str(parsed.get("visual", "")).strip()
    neg_x = str(parsed.get("negative_extra", "")).strip()
    if len(visual) > 320:
        visual = visual[:317] + "…"
    if len(neg_x) > 160:
        neg_x = neg_x[:157] + "…"
    if not visual:
        return {"visual": None, "negative_extra": None}
    return {"visual": visual, "negative_extra": neg_x or None}


def stock_photo_search_query_sync(
    topic: Topic,
    mood: str,
    model: str,
    *,
    style_hint: str | None = None,
) -> str:
    """
    Short keyword line for Unsplash search (real photos). Falls back to topic-based words if Ollama fails.
    """
    settings = get_settings()
    sh = (style_hint or "").strip()
    if len(sh) > 240:
        sh = sh[:237] + "…"
    user_prompt = f"""Topic: {topic.name}
Topic description: {topic.description or "(none)"}
Mood: {mood}
Prior art direction (optional, may be abstract prompt language): {sh or "(none)"}

Produce 2-6 lowercase English words suitable for searching royalty-free photos (e.g. Unsplash).
Prefer landscapes, skies, water, fog, textures, plants, mountains, ocean — atmospheric and on-theme.
No proper names, no instructions, no commas inside the string.

Return JSON only: {{"q": "word1 word2 word3"}}"""

    payload = {
        "model": model,
        "prompt": user_prompt,
        "system": "Respond ONLY with valid JSON, no markdown.",
        "stream": False,
        "format": "json",
        "options": _OLLAMA_ENRICH_OPTIONS,
    }
    url = f"{settings.ollama_base_url.rstrip('/')}/api/generate"
    timeout = httpx.Timeout(connect=10.0, read=90.0, write=60.0, pool=10.0)
    try:
        with httpx.Client(timeout=timeout) as client:
            r = client.post(url, json=payload)
            r.raise_for_status()
            data = r.json()
        raw = data.get("response") or ""
        parsed = _extract_json(raw)
        q = str(parsed.get("q", "")).strip().lower()
        q = re.sub(r"[^a-z0-9\s-]+", " ", q)
        q = " ".join(q.split())[:120]
        if q:
            logger.info("Stock photo search query: %s", q[:100])
            return q
    except (httpx.HTTPError, json.JSONDecodeError, ValueError, TypeError) as e:
        logger.warning("Stock photo query LLM failed, using topic fallback: %s", e)

    base = topic.name.lower()
    base = re.sub(r"[^a-z0-9\s]+", " ", base)
    base = " ".join(base.split())[:40]
    tail = f"{mood} moody landscape abstract".lower()
    tail = re.sub(r"[^a-z0-9\s]+", " ", tail)
    tail = " ".join(tail.split())[:50]
    out = f"{base} {tail}".strip()
    return out[:120] if out else "moody nature abstract sky"


async def list_ollama_models() -> list[dict[str, Any]]:
    settings = get_settings()
    async with httpx.AsyncClient(timeout=30.0) as client:
        r = await client.get(f"{settings.ollama_base_url.rstrip('/')}/api/tags")
        r.raise_for_status()
        data = r.json()
    return list(data.get("models") or [])
