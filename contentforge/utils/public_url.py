"""
Resolve the public HTTPS base URL for media webhooks (Instagram, TikTok, etc.).

1. If PUBLIC_BASE_URL is set, it wins (stable production).
2. Else if NGROK_LOCAL_API_URL is set, query ngrok's local API (GET /api/tunnels) each time.
   With a reserved ngrok domain, the returned public_url stays the same across restarts.

Ngrok local API: https://ngrok.com/docs/agent/api/
"""

import logging

import httpx

from config import get_settings

logger = logging.getLogger(__name__)


def get_public_base_url() -> str:
    """
    Return base URL with no trailing slash, or "" if unavailable.
    Not cached: each call reflects the current ngrok tunnel (new URL after restart).
    """
    s = get_settings()
    manual = (s.public_base_url or "").strip()
    if manual:
        return manual.rstrip("/")

    api_root = (s.ngrok_local_api_url or "").strip().rstrip("/")
    if not api_root:
        return ""

    try:
        timeout = httpx.Timeout(connect=2.0, read=5.0, write=2.0, pool=2.0)
        with httpx.Client(timeout=timeout) as client:
            r = client.get(f"{api_root}/api/tunnels")
            r.raise_for_status()
            data = r.json()
    except Exception as e:
        logger.warning("Could not read ngrok tunnels from %s: %s", api_root, e)
        return ""

    tunnels = data.get("tunnels") or []
    # Prefer HTTPS (required by Instagram / TikTok for media URLs).
    for t in tunnels:
        url = (t.get("public_url") or "").strip().rstrip("/")
        if url.startswith("https://"):
            return url
    for t in tunnels:
        url = (t.get("public_url") or "").strip().rstrip("/")
        if url.startswith("http://"):
            return url
    return ""
