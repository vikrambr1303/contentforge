from typing import Any

import httpx

from utils.public_url import get_public_base_url

TIKTOK_API = "https://open.tiktokapis.com"


def fetch_privacy_level_options(access_token: str) -> list[str] | None:
    """Returns allowed privacy_level values for this user, or None if the query failed."""
    try:
        timeout = httpx.Timeout(connect=10.0, read=30.0, write=10.0, pool=10.0)
        with httpx.Client(timeout=timeout) as client:
            r = client.post(
                f"{TIKTOK_API}/v2/post/publish/creator_info/query/",
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Content-Type": "application/json; charset=UTF-8",
                },
                json={},
            )
            if r.status_code != 200:
                return None
            data = r.json()
            if (data.get("error") or {}).get("code") != "ok":
                return None
            opts = (data.get("data") or {}).get("privacy_level_options")
            if isinstance(opts, list):
                return [str(x) for x in opts]
    except Exception:
        return None
    return None


def validate_token(access_token: str) -> bool:
    """Light check: token works for user.info.basic (typical alongside video.publish)."""
    if not access_token.strip():
        return False
    try:
        timeout = httpx.Timeout(connect=10.0, read=30.0, write=10.0, pool=10.0)
        with httpx.Client(timeout=timeout) as client:
            r = client.get(
                f"{TIKTOK_API}/v2/user/info/",
                params={"fields": "open_id"},
                headers={"Authorization": f"Bearer {access_token}"},
            )
            if r.status_code != 200:
                return False
            data = r.json()
            return (data.get("error") or {}).get("code") == "ok" and bool(
                (data.get("data") or {}).get("user", {}).get("open_id")
            )
    except Exception:
        return False


def public_video_url_for_content(content_item_id: int) -> str:
    base = get_public_base_url()
    if not base:
        return ""
    return f"{base}/api/content/{content_item_id}/video"


def init_direct_video_publish(
    access_token: str,
    video_url: str,
    title: str,
    privacy_level: str,
    *,
    is_aigc: bool = True,
) -> dict[str, Any]:
    """
    Direct post init with PULL_FROM_URL. Requires video.publish scope and verified media URL domain.
    See https://developers.tiktok.com/doc/content-posting-api-reference-direct-post
    """
    body: dict[str, Any] = {
        "post_info": {
            "title": (title or "")[:2200],
            "privacy_level": privacy_level,
            "disable_duet": False,
            "disable_comment": False,
            "disable_stitch": False,
            "brand_content_toggle": False,
            "brand_organic_toggle": False,
            "is_aigc": bool(is_aigc),
        },
        "source_info": {
            "source": "PULL_FROM_URL",
            "video_url": video_url,
        },
    }
    timeout = httpx.Timeout(connect=15.0, read=120.0, write=60.0, pool=10.0)
    with httpx.Client(timeout=timeout) as client:
        r = client.post(
            f"{TIKTOK_API}/v2/post/publish/video/init/",
            headers={
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json; charset=UTF-8",
            },
            json=body,
        )
        try:
            return r.json()
        except Exception:
            return {"error": {"code": "parse_error", "message": r.text[:500]}}
