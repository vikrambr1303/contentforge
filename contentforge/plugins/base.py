from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any


@dataclass
class PostResult:
    success: bool
    platform_post_id: str | None
    error_message: str | None


class SocialMediaPlugin(ABC):
    name: str
    display_name: str
    supported_content_types: list[str]

    @abstractmethod
    def credentials_schema(self) -> dict[str, Any]:
        ...

    @abstractmethod
    def validate_credentials(self, credentials: dict[str, Any]) -> bool:
        ...

    @abstractmethod
    def post(self, content_path: str, caption: str, content_type: str, credentials: dict[str, Any]) -> PostResult:
        ...
