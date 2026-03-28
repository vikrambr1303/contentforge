import re
from typing import Any

from plugins.base import PostResult, SocialMediaPlugin
from plugins.instagram import client


def _parse_content_id(path: str) -> int | None:
    p = path.replace("\\", "/")
    m = re.search(r"images/(\d+)_composed\.jpg|videos/(\d+)\.mp4", p)
    if not m:
        m = re.search(r"/(\d+)_composed\.jpg|/(\d+)\.mp4", p)
    if not m:
        return None
    g = m.groups()
    return int(next(x for x in g if x))


class Plugin(SocialMediaPlugin):
    name = "instagram"
    display_name = "Instagram"
    supported_content_types = ["image", "video"]

    def credentials_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "required": ["access_token", "instagram_user_id"],
            "properties": {
                "access_token": {"type": "string", "title": "Long-lived Access Token"},
                "instagram_user_id": {"type": "string", "title": "Instagram Business Account ID"},
            },
        }

    def validate_credentials(self, credentials: dict[str, Any]) -> bool:
        token = credentials.get("access_token") or ""
        return bool(token) and client.validate_token(token)

    def post(self, content_path: str, caption: str, content_type: str, credentials: dict[str, Any]) -> PostResult:
        uid = credentials.get("instagram_user_id") or ""
        token = credentials.get("access_token") or ""
        if not uid or not token:
            return PostResult(False, None, "Missing credentials")
        cid = _parse_content_id(content_path)
        if cid is None:
            return PostResult(False, None, "Could not parse content id from path")
        image = content_type == "image"
        url = client.public_url_for_content(cid, image)
        if not url:
            return PostResult(
                False,
                None,
                "Set PUBLIC_BASE_URL in .env to a public HTTPS URL (e.g. ngrok) so Meta can fetch media.",
            )
        img_url = url if image else None
        vid_url = url if not image else None
        try:
            cr = client.create_media(uid, token, img_url, vid_url, caption[:2200])
            c_id = cr.get("id")
            if not c_id:
                return PostResult(False, None, str(cr.get("error", cr)))
            pub = client.publish_media(uid, token, c_id)
            post_id = str(pub.get("id", ""))
            return PostResult(True, post_id or c_id, None)
        except Exception as e:  # noqa: BLE001
            return PostResult(False, None, str(e)[:500])
