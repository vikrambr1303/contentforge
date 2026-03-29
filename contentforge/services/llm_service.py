import json
import logging
import re
import secrets
from dataclasses import dataclass
from typing import Any

import httpx

from config import get_settings
from models.topic import Topic
from schemas.topic import (
    CONTENT_STYLE_VALUES,
    ContentStyle,
    TopicRefineFieldSuggestion,
    TopicRefineResponse,
    TopicRefineStyleSuggestion,
)

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

# Long-form blog: a bit warmer and more varied than enrich JSON, still coherent.
_OLLAMA_BLOG_OPTIONS: dict[str, Any] = {
    "temperature": 0.86,
    "top_p": 0.93,
    "repeat_penalty": 1.14,
}

# Full-article blog generation: Ollama defaults (e.g. num_ctx 2048) truncate long posts—give prompt + output room.
_OLLAMA_BLOG_LONG_OPTIONS: dict[str, Any] = {
    **_OLLAMA_BLOG_OPTIONS,
    "num_ctx": 16384,
    "num_predict": 8192,
}

# Blog topic classification: steadier JSON.
_OLLAMA_BLOG_CLASSIFY_OPTIONS: dict[str, Any] = {
    "temperature": 0.45,
    "top_p": 0.9,
    "repeat_penalty": 1.05,
}

_BLOG_TOPIC_KINDS = frozenset({"technical", "functional", "general"})

# Shown in blog prompts when Mermaid is allowed — reduces Kroki parse failures from sloppy syntax.
_MERMAID_SYNTAX_RULES = """
Mermaid syntax (follow exactly — invalid diagrams break rendering):
- The FIRST non-empty line inside the fence MUST be a diagram type, e.g. `flowchart TD`, `flowchart LR`, or `sequenceDiagram` (not prose above it).
- Never put headings (`#`), **bold** titles, or normal article sentences inside the ```mermaid``` fence—only Mermaid syntax. Explanatory text belongs in the paragraph after the closing ```.
- Use simple node IDs: letters/digits only (A, B, C1). Put readable text in square brackets: `A[Read data]` or `B["Label with (parentheses)"]` — quotes required if the label contains `()`, `"`, or `]`.
- Link with `-->` on its own or chained: `A --> B --> C`. Avoid HTML, markdown, or nested ``` inside the mermaid block.
- Valid minimal example:
```mermaid
flowchart LR
    A[Input] --> B[Process]
    B --> C[Output]
```
"""




@dataclass(frozen=True)
class BlogGenerationPlan:
    """LLM-inferred shape for one blog generation run."""

    topic_kind: str  # technical | functional | general
    mermaid_max: int  # 0 = no diagrams; 1 or 2 = optional Mermaid cap
    content_focus: str


DEFAULT_BLOG_PLAN = BlogGenerationPlan(
    topic_kind="general",
    mermaid_max=1,
    content_focus="Balanced coverage: clear explanations and practical takeaways.",
)


def classify_blog_topic_sync(topic: Topic, model: str) -> BlogGenerationPlan:
    """
    Decide whether the brief is mainly technical, functional, or mixed, and whether Mermaid helps.
    One fast JSON call before the long blog generation.
    """
    settings = get_settings()
    nonce = secrets.token_hex(4)
    name = (topic.name or "").strip()[:500]
    desc = (topic.description or "").strip()[:8000]
    style = (topic.style or "").strip()[:80]
    user_prompt = f"""You route blog briefs for a content tool. Read the topic and return JSON ONLY (no markdown fences).

Topic name: {name or "(empty)"}
Topic description: {desc or "(empty)"}
Declared voice/style hint: {style or "(none)"}

Return exactly this JSON shape:
{{
  "topic_kind": "technical" | "functional" | "general",
  "include_mermaid": boolean,
  "mermaid_max": 0 | 1 | 2,
  "content_focus": "one concise sentence: what the article should emphasize"
}}

Definitions:
- technical: systems, engineering, APIs, architecture, security, infrastructure, data pipelines, algorithms, developer or SRE audience.
- functional: business process, product workflows, user journeys, stakeholder value, adoption, operations without deep internals, softer skill or strategy topics.
- general: mixed, unclear, or broad audience — balanced coverage.

include_mermaid: true only if diagrams (flow, sequence, component relationships) would genuinely help. false for pure narrative, opinion, culture, or topics where diagrams add little.
mermaid_max: if include_mermaid is false, use 0. If true, use 1 or 2 based on how many distinct visual structures are justified (prefer 1 unless the brief clearly needs two).

Request id: {nonce}
"""
    payload = {
        "model": model,
        "prompt": user_prompt,
        "system": "You respond ONLY with valid JSON, no markdown.",
        "stream": False,
        "format": "json",
        "options": _OLLAMA_BLOG_CLASSIFY_OPTIONS,
    }
    try:
        with httpx.Client(timeout=httpx.Timeout(connect=15.0, read=120.0, write=60.0, pool=10.0)) as client:
            r = client.post(f"{settings.ollama_base_url.rstrip('/')}/api/generate", json=payload)
            r.raise_for_status()
            data = r.json()
        raw = (data.get("response") or "").strip()
        parsed = _extract_json(raw)
    except Exception as e:
        logger.warning("classify_blog_topic_sync failed, using default plan: %s", e)
        return DEFAULT_BLOG_PLAN

    kind = str(parsed.get("topic_kind", "general")).strip().lower()
    if kind not in _BLOG_TOPIC_KINDS:
        kind = "general"
    include = bool(parsed.get("include_mermaid", True))
    try:
        mm = int(parsed.get("mermaid_max", 1))
    except (TypeError, ValueError):
        mm = 1
    mm = max(0, min(2, mm))
    if not include:
        mm = 0
    elif mm < 1:
        mm = 1 if include else 0
    focus = str(parsed.get("content_focus", "") or "").strip()[:500]
    if not focus:
        focus = DEFAULT_BLOG_PLAN.content_focus

    plan = BlogGenerationPlan(topic_kind=kind, mermaid_max=mm, content_focus=focus)
    logger.info("blog topic classified: kind=%s mermaid_max=%s", plan.topic_kind, plan.mermaid_max)
    return plan


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


def _caption_user_prompt(topic_name: str, quote_text: str, cta: str) -> str:
    cta_line = (cta or "").strip() or "none"
    return f"""Write an Instagram / TikTok caption (max 2200 characters).

Topic: {topic_name}
Quote on the image: {quote_text}
Editor CTA hint (use when it fits naturally; if the hint is literally "none", you may skip it): {cta_line}

Requirements:
1) Write 1–3 short paragraphs that hook the reader and connect to the *idea* of the quote—do not paste the full quote as the entire caption; you may quote a short phrase in quotation marks if it helps.
2) After one blank line, add a **keyword hashtag block**: **8–14** hashtags for discovery. Each tag must be one token starting with #, using only letters, numbers, and underscores (no spaces inside a tag). Mix:
   - 1–2 broad tags derived from the topic name (e.g. #Mindfulness, #SlowLiving)
   - several specific tags for themes in the quote (e.g. #Solitude, #InnerPeace)
   - optional niche tags only if they fit
3) When the CTA hint is not "none", weave it into a closing line or sentence when it fits.

Return JSON: {{"caption": "..."}}"""


async def generate_caption(
    topic_name: str,
    quote_text: str,
    cta: str,
    model: str,
) -> str:
    settings = get_settings()
    user_prompt = _caption_user_prompt(topic_name, quote_text, cta)
    payload = {
        "model": model,
        "prompt": user_prompt,
        "system": "Respond ONLY with valid JSON. The caption must include the hashtag block as specified.",
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
    user_prompt = _caption_user_prompt(topic_name, quote_text, cta)
    payload = {
        "model": model,
        "prompt": user_prompt,
        "system": "Respond ONLY with valid JSON. The caption must include the hashtag block as specified.",
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
    revision_feedback: str | None = None,
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

    rv = (revision_feedback or "").strip()
    if len(rv) > 400:
        rv = rv[:397] + "…"
    revision_block = ""
    if rv:
        revision_block = f"""
IMPORTANT — Editor revision feedback (this run replaces a previous background; obey this strongly in "visual" and "negative_extra" when relevant):
{rv}

"""

    user_prompt = f"""You write fragments for Stable Diffusion 1.5 image prompts (backgrounds only).

Topic name: {topic.name}
Topic description: {topic.description or "(none)"}
Editor visual style hint: {topic.image_style}
Mood: {mood}
{ref_note}{quote_block}{revision_block}
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
    revision_feedback: str | None = None,
) -> str:
    """
    Short keyword line for Unsplash search (real photos). Falls back to topic-based words if Ollama fails.
    """
    settings = get_settings()
    sh = (style_hint or "").strip()
    if len(sh) > 240:
        sh = sh[:237] + "…"
    rv = (revision_feedback or "").strip()
    if len(rv) > 320:
        rv = rv[:317] + "…"
    rev_line = (
        f"\nEditor revision feedback — keywords MUST reflect this (e.g. different setting, palette, or subject): {rv}\n"
        if rv
        else ""
    )
    user_prompt = f"""Topic: {topic.name}
Topic description: {topic.description or "(none)"}
Mood: {mood}
Prior art direction (optional, may be abstract prompt language): {sh or "(none)"}
{rev_line}
Produce 2-8 lowercase English words suitable for searching royalty-free photos (e.g. Unsplash).
Prefer landscapes, skies, water, fog, textures, plants, mountains, ocean — atmospheric and on-theme unless the revision feedback clearly asks for something else (e.g. urban, studio, minimal).
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
    if rv:
        fb_words = " ".join(re.findall(r"[a-z0-9]{3,}", rv.lower()))[:60]
        if fb_words:
            out = f"{fb_words} {out}".strip()
    return out[:120] if out else "moody nature abstract sky"


def revise_quote_for_social_sync(
    topic: Topic,
    model: str,
    *,
    previous_quote: str,
    previous_author: str,
    feedback: str,
    use_feedback: bool,
) -> dict[str, str]:
    """Regenerate quote + attribution for social revision; respects user feedback or random variation."""
    settings = get_settings()
    nonce = secrets.token_hex(4)
    prev_q = (previous_quote or "").strip()[:300]
    prev_a = (previous_author or "").strip()[:200]
    if use_feedback:
        fb = (feedback or "").strip()[:2000]
        user_prompt = f"""
Topic: {topic.name}
Description: {topic.description or ""}
Style: {topic.style}

Current quote: "{prev_q}"
Current attribution: {prev_a}

Editor feedback (apply as much as possible while keeping a single short quote line):
{fb}

Request id: {nonce}

Return JSON with exactly:
  quote: string (max 120 characters)
  author: string (attribution, max 255 chars)
  mood: string (one of: serene, dramatic, contemplative, uplifting)
"""
    else:
        user_prompt = f"""
Topic: {topic.name}
Description: {topic.description or ""}
Style: {topic.style}

Previous attempt (do not copy verbatim; produce a clearly different line):
Quote: "{prev_q}"
Author: {prev_a}

Request id: {nonce} — fresh variation only, same theme. No user feedback to apply.

Return JSON with exactly:
  quote: string (max 120 characters)
  author: string
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
    if not quote:
        quote = prev_q[:120] or "—"
    return {"quote": quote, "author": author, "mood": mood}


def revise_blog_section_sync(
    topic: Topic,
    model: str,
    *,
    section_block: str,
    section_index: int,
    feedback: str,
    use_feedback: bool,
) -> str:
    """Rewrite one blog section (full block text in/out). Markdown only."""
    settings = get_settings()
    nonce = secrets.token_hex(4)
    block = section_block.strip()
    if len(block) > 12000:
        block = block[:11997] + "…"
    if use_feedback:
        fb = (feedback or "").strip()[:4000]
        user_prompt = f"""
Blog topic: {topic.name}
Context: {topic.description or "(none)"}
Voice: {topic.style}

You are replacing section index {section_index} of a Markdown article. Output ONLY that section’s markdown,
from the first line of the block through the end (include the ## heading line if the current block starts with ##;
if this is the opening block, keep the # title and any intro as appropriate).

Current block:
---
{block}
---

Editor feedback:
{fb}

Request id: {nonce}

Rules: Preserve any ```mermaid``` fences if you keep diagrams; syntax must be valid. No HTML. No preamble outside the block.
"""
    else:
        user_prompt = f"""
Blog topic: {topic.name}
Context: {topic.description or "(none)"}
Voice: {topic.style}

Rewrite section index {section_index} with a fresh variation. Do not copy the current text verbatim.

Current block:
---
{block}
---

Request id: {nonce} — stochastic alternative; no specific user feedback.

Output ONLY the replacement markdown for this section (same structural role: preamble vs ## section).
Rules: ```mermaid``` allowed; valid syntax. No HTML. No preamble.
"""
    payload = {
        "model": model,
        "prompt": user_prompt,
        "system": "You write Markdown only. Output nothing before or after the section body.",
        "stream": False,
        "options": _OLLAMA_BLOG_LONG_OPTIONS,
    }
    with httpx.Client(timeout=httpx.Timeout(connect=15.0, read=420.0, write=60.0, pool=10.0)) as client:
        r = client.post(f"{settings.ollama_base_url.rstrip('/')}/api/generate", json=payload)
        r.raise_for_status()
        data = r.json()
    raw = (data.get("response") or "").strip()
    if raw.startswith("```"):
        raw = re.sub(r"^```(?:markdown|md)?\s*\n", "", raw)
        raw = re.sub(r"\n```\s*$", "", raw)
    return raw.strip()


def generate_blog_post_sync(topic: Topic, model: str, *, plan: BlogGenerationPlan | None = None) -> str:
    """
    Produce a Medium-friendly Markdown article. Mermaid depth follows ``plan`` (from classify_blog_topic_sync).
    Output is plain markdown only (no JSON wrapper).
    """
    plan = plan or DEFAULT_BLOG_PLAN
    settings = get_settings()
    nonce = secrets.token_hex(4)

    if plan.topic_kind == "technical":
        angle = """Article angle (technical audience):
- Prefer precise terms for components, interfaces, data flow, failure modes, and tradeoffs. Short code or pseudo-code only when it clarifies a point.
- It is fine to go deeper on “how it works” and edge cases; assume readers can handle technical vocabulary."""
    elif plan.topic_kind == "functional":
        angle = """Article angle (functional / product / operations):
- Center on who does what, outcomes, workflows, adoption, and value for teams or customers. Use concrete scenarios (“When a team …”).
- Define jargon briefly when needed; avoid unnecessary internals unless the brief clearly demands them."""
    else:
        angle = """Article angle (balanced):
- Blend clear explanation with practical takeaway. Neither a pure architecture deep-dive nor generic marketing—credible and useful."""

    if plan.mermaid_max <= 0:
        diagram_rules = """Diagrams:
- Do NOT use ```mermaid``` code blocks. Explain structure with prose, short lists, or a markdown table if helpful."""
    elif plan.mermaid_max == 1:
        diagram_rules = """Diagrams (optional, at most one):
- You MAY include at most ONE ```mermaid``` block only if a single diagram clearly clarifies structure. Keep it under ~25 nodes/lines.
- If plain writing is enough, skip the diagram entirely.
- After a diagram (if any), one short conversational paragraph—not a robotic caption.
""" + _MERMAID_SYNTAX_RULES
    else:
        diagram_rules = """Diagrams (optional, up to two):
- You MAY include up to TWO separate ```mermaid``` blocks only where each adds real clarity. Do not add charts for padding—many strong posts have zero diagrams.
- Each diagram under ~25 nodes/lines.
- After each diagram, a short paragraph in plain language.
""" + _MERMAID_SYNTAX_RULES

    focus_line = f"\nEditor focus for this run: {plan.content_focus}\n"

    user_prompt = f"""
Write a blog post in Markdown for people who care about: {topic.name}

Context from the editor: {topic.description or "(none)"}
Adopt this voice as much as it fits: {topic.style}

{angle}
{focus_line}
Request id: {nonce} — avoid generic “SEO sludge”; sound like one careful human wrote it for readers, not a brochure.

Voice and rhythm (critical):
- Mix short punchy sentences with longer explanatory ones. Vary paragraph length; a few tight sections are fine, but most ## sections should include **several developed paragraphs** (not only one-liners).
- Prefer concrete scenarios, numbers, or “for example …” over abstract slogans. It’s fine to acknowledge tradeoffs or “when this breaks down.”
- Use **bold** sparingly for real emphasis, not every other phrase. Bullets only where they actually help (steps, options), not for every paragraph.
- You may address the reader as “you” occasionally, or pose a real question—don’t stay in passive corporate voice.
- Light opinion is OK (“I tend to …”, “In practice …”) without claiming a fake personal biography.

Phrases and patterns to AVOID (they read as machine-default):
“In today’s fast-paced world”, “In conclusion”, “It’s important to note”, “Let’s dive in”, “game-changer”, “unlock”, “leverage”, “synergy”, “holistic”, “at the end of the day”, “robust ecosystem”, numbered “Firstly / Secondly / Lastly” chains, and starting every section with “In this section we will …”.

Structure:
- Output ONLY the article as Markdown. No preamble. No markdown wrapper fence around the whole post.
- First line: a single H1 title that sounds like a human headline, not a keyword stack.
- Use ## and ###; aim for **at least five ## sections** (more if the topic warrants). Section titles must be specific (not “Introduction” / “Overview” unless unavoidable).
- **Length:** target **about 1,800–3,500 words** for a normal topic—substantial, article-length copy. Only go shorter if the brief is explicitly narrow; never compress into a skimpy outline or bullet-only post unless the topic truly fits that shape.

{diagram_rules}

Technical: no HTML. Links as markdown [text](url) or (#). No meta-commentary about how the post was written.

Start with the # title line only.
"""
    sys_mermaid = (
        " Follow diagram rules in the prompt exactly (including when to omit Mermaid)."
        if plan.mermaid_max > 0
        else " Do not use Mermaid diagram blocks."
    )
    payload = {
        "model": model,
        "prompt": user_prompt,
        "system": (
            "You are an experienced technical writer and blogger. You write in Markdown only. "
            "Your prose is natural, specific, and slightly informal when the topic allows—never stiff, "
            "never filler, never obviously templated. "
            "You write long-form articles: meet the word-count and section-depth targets in the prompt—do not end early with a thin summary."
            + sys_mermaid
        ),
        "stream": False,
        "options": _OLLAMA_BLOG_LONG_OPTIONS,
    }
    with httpx.Client(timeout=httpx.Timeout(connect=15.0, read=420.0, write=60.0, pool=10.0)) as client:
        r = client.post(f"{settings.ollama_base_url.rstrip('/')}/api/generate", json=payload)
        r.raise_for_status()
        data = r.json()
    raw = (data.get("response") or "").strip()
    if raw.startswith("```"):
        raw = re.sub(r"^```(?:markdown|md)?\s*\n", "", raw)
        raw = re.sub(r"\n```\s*$", "", raw)
    return raw.strip()


_STYLE_ENUM = CONTENT_STYLE_VALUES


def refine_topic_draft_sync(
    *,
    name: str,
    description: str | None,
    style: str,
    image_style: str,
    background_source: str,
    scopes: list[str],
    user_note: str | None,
    model: str,
) -> TopicRefineResponse:
    """
    Improve topic brief fields for ContentForge generation. Preview-only; caller does not persist.
    """
    settings = get_settings()
    note = (user_note or "").strip()[:2000]
    raw_scopes = set(scopes)
    if "whole" in raw_scopes:
        targets = {"description", "image_style", "style"}
    else:
        targets = {s for s in raw_scopes if s in ("description", "image_style", "style")}

    if not targets:
        return TopicRefineResponse()

    desc_in = (description or "").strip()[:12000]
    style_in = (style or "inspirational").strip().lower()
    if style_in not in _STYLE_ENUM:
        style_in = ContentStyle.inspirational.value
    img_in = (image_style or "").strip()[:500]
    name_in = (name or "").strip()[:255]
    bg = (background_source or "diffusers").strip().lower()

    targets_list = ", ".join(sorted(targets))
    note_block = f"\nEditor extra instructions (follow if sensible):\n{note}\n" if note else ""

    user_prompt = f"""You are an editorial assistant for a content generation app. The user is drafting a TOPIC brief
used to generate social quote cards and blog posts. Improve clarity and usefulness for LLM-driven generation.

Current draft:
- Name (for context only; do not rename in JSON): {name_in or "(empty)"}
- Description: {desc_in or "(empty)"}
- Content style (one of: {", ".join(_STYLE_ENUM)}): {style_in}
- Image mood / visual style hint (short phrase for image prompts): {img_in or "(empty)"}
- Background images: {"Unsplash stock photos" if bg == "unsplash" else "Stable Diffusion (local)"}

Improve ONLY these parts: {targets_list}
{note_block}
Rules:
- Description: concrete audience, themes, tone, boundaries; avoid generic filler. Max ~4000 characters in "text".
- Image mood: comma-separated or short phrase; vivid but not contradictory; max 500 chars in "text". Good for {"stock photo keywords" if bg == "unsplash" else "SD prompts"}.
- Content style: pick exactly one slug from the list above — only if "style" is in scope.

Return JSON ONLY, no markdown fences, shape:
{{
  "description": null or {{"text": "...", "rationale": "one short sentence"}},
  "image_style": null or {{"text": "...", "rationale": "..."}},
  "style": null or {{"value": "{'|'.join(_STYLE_ENUM)}", "rationale": "..."}}
}}
Include a key only if that part is in the improvement list. Use null for omitted parts.
"""
    payload = {
        "model": model,
        "prompt": user_prompt,
        "system": "You respond ONLY with valid JSON, no markdown.",
        "stream": False,
        "format": "json",
        "options": _OLLAMA_ENRICH_OPTIONS,
    }
    url = f"{settings.ollama_base_url.rstrip('/')}/api/generate"
    timeout = httpx.Timeout(connect=15.0, read=120.0, write=60.0, pool=10.0)
    with httpx.Client(timeout=timeout) as client:
        r = client.post(url, json=payload)
        r.raise_for_status()
        data = r.json()
    raw = (data.get("response") or "").strip()
    try:
        parsed = _extract_json(raw)
    except (json.JSONDecodeError, ValueError) as e:
        logger.warning("refine_topic_draft: bad JSON from model: %s", e)
        raise ValueError("Model did not return valid JSON. Try again or shorten your note.") from e

    out_desc: TopicRefineFieldSuggestion | None = None
    out_img: TopicRefineFieldSuggestion | None = None
    out_style: TopicRefineStyleSuggestion | None = None

    if "description" in targets:
        d = parsed.get("description")
        if isinstance(d, dict):
            text = str(d.get("text", "")).strip()[:8000]
            rat = str(d.get("rationale", "")).strip()[:500]
            if text:
                out_desc = TopicRefineFieldSuggestion(text=text, rationale=rat)

    if "image_style" in targets:
        d = parsed.get("image_style")
        if isinstance(d, dict):
            text = str(d.get("text", "")).strip()[:500]
            rat = str(d.get("rationale", "")).strip()[:500]
            if text:
                out_img = TopicRefineFieldSuggestion(text=text, rationale=rat)

    if "style" in targets:
        d = parsed.get("style")
        if isinstance(d, dict):
            val = str(d.get("value", "")).strip().lower()
            if val not in _STYLE_ENUM:
                val = style_in
            rat = str(d.get("rationale", "")).strip()[:500]
            out_style = TopicRefineStyleSuggestion(value=ContentStyle(val), rationale=rat)

    return TopicRefineResponse(description=out_desc, image_style=out_img, style=out_style)


async def list_ollama_models() -> list[dict[str, Any]]:
    settings = get_settings()
    async with httpx.AsyncClient(timeout=30.0) as client:
        r = await client.get(f"{settings.ollama_base_url.rstrip('/')}/api/tags")
        r.raise_for_status()
        data = r.json()
    return list(data.get("models") or [])
