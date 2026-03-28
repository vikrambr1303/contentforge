import re
from typing import Any

from plugins.base import PostResult, SocialMediaPlugin
from plugins.tiktok import client


def _parse_video_content_id(path: str) -> int | None:
    p = path.replace("\\", "/")
    m = re.search(r"videos/(\d+)\.mp4", p) or re.search(r"/(\d+)\.mp4$", p)
    return int(m.group(1)) if m else None


class Plugin(SocialMediaPlugin):
    name = "tiktok"
    display_name = "TikTok"
    supported_content_types = ["video"]

    def credentials_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "required": ["access_token", "privacy_level"],
            "properties": {
                "access_token": {
                    "type": "string",
                    "title": "User access token",
                    "description": "OAuth 2.0 user access token with video.publish (and user.info.basic for validation).",
                },
                "privacy_level": {
                    "type": "string",
                    "title": "Privacy level",
                    "description": "Must be one of the values returned by TikTok creator_info/query for this user.",
                    "enum": [
                        "PUBLIC_TO_EVERYONE",
                        "MUTUAL_FOLLOW_FRIENDS",
                        "FOLLOWER_OF_CREATOR",
                        "SELF_ONLY",
                    ],
                },
                "mark_as_ai_generated": {
                    "type": "boolean",
                    "title": "Label as AI-generated (is_aigc)",
                    "description": "Recommended when content used LLM / generated imagery.",
                    "default": True,
                },
            },
        }

    def validate_credentials(self, credentials: dict[str, Any]) -> bool:
        token = (credentials.get("access_token") or "").strip()
        pl = (credentials.get("privacy_level") or "").strip()
        if not token or not pl:
            return False
        allowed = {
            "PUBLIC_TO_EVERYONE",
            "MUTUAL_FOLLOW_FRIENDS",
            "FOLLOWER_OF_CREATOR",
            "SELF_ONLY",
        }
        if pl not in allowed:
            return False
        if not client.validate_token(token):
            return False
        opts = client.fetch_privacy_level_options(token)
        if opts is not None and pl not in opts:
            return False
        return True

    def post(self, content_path: str, caption: str, content_type: str, credentials: dict[str, Any]) -> PostResult:
        if content_type != "video":
            return PostResult(
                False,
                None,
                "TikTok posting requires video. Re-generate with “Include video” or use content that has an MP4.",
            )
        token = (credentials.get("access_token") or "").strip()
        privacy_level = (credentials.get("privacy_level") or "").strip()
        if not token or not privacy_level:
            return PostResult(False, None, "Missing TikTok credentials")

        cid = _parse_video_content_id(content_path)
        if cid is None:
            return PostResult(False, None, "Could not parse content id from video path")

        url = client.public_video_url_for_content(cid)
        if not url:
            return PostResult(
                False,
                None,
                "Set PUBLIC_BASE_URL or NGROK_LOCAL_API_URL, verify the URL prefix in TikTok Developer Portal "
                "so TikTok can pull the MP4 (PULL_FROM_URL).",
            )

        is_aigc = credentials.get("mark_as_ai_generated")
        if is_aigc is None:
            is_aigc = True

        try:
            data = client.init_direct_video_publish(
                token,
                url,
                caption,
                privacy_level,
                is_aigc=bool(is_aigc),
            )
        except Exception as e:  # noqa: BLE001
            return PostResult(False, None, str(e)[:500])

        err = data.get("error") or {}
        if err.get("code") != "ok":
            msg = err.get("message") or err.get("code") or str(data)[:500]
            return PostResult(False, None, msg[:500])

        publish_id = (data.get("data") or {}).get("publish_id")
        if not publish_id:
            return PostResult(False, None, "TikTok returned no publish_id")

        return PostResult(True, str(publish_id), None)
