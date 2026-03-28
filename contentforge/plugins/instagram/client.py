from typing import Any

import httpx

from utils.public_url import get_public_base_url


def validate_token(access_token: str) -> bool:
    try:
        with httpx.Client(timeout=30.0) as client:
            r = client.get(
                "https://graph.facebook.com/v19.0/me",
                params={"fields": "id", "access_token": access_token},
            )
            if r.status_code != 200:
                return False
            data = r.json()
            return "id" in data
    except Exception:
        return False


def create_media(
    instagram_user_id: str,
    access_token: str,
    image_url: str | None,
    video_url: str | None,
    caption: str,
) -> dict[str, Any]:
    params: dict[str, Any] = {"caption": caption, "access_token": access_token}
    if image_url:
        params["image_url"] = image_url
    if video_url:
        params["media_type"] = "REELS"
        params["video_url"] = video_url
    with httpx.Client(timeout=120.0) as client:
        r = client.post(
            f"https://graph.facebook.com/v19.0/{instagram_user_id}/media",
            data=params,
        )
        r.raise_for_status()
        return r.json()


def publish_media(instagram_user_id: str, access_token: str, creation_id: str) -> dict[str, Any]:
    with httpx.Client(timeout=120.0) as client:
        r = client.post(
            f"https://graph.facebook.com/v19.0/{instagram_user_id}/media_publish",
            data={"creation_id": creation_id, "access_token": access_token},
        )
        r.raise_for_status()
        return r.json()


def public_url_for_content(content_item_id: int, image: bool) -> str:
    base = get_public_base_url()
    if not base:
        return ""
    kind = "image" if image else "video"
    return f"{base}/api/content/{content_item_id}/{kind}"
