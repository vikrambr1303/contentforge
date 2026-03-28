import base64
import hashlib
import json
from typing import Any

from cryptography.fernet import Fernet

from config import get_settings


def _fernet() -> Fernet:
    key = hashlib.sha256(get_settings().secret_key.encode()).digest()
    return Fernet(base64.urlsafe_b64encode(key))


def encrypt_credentials(data: dict[str, Any]) -> str:
    return _fernet().encrypt(json.dumps(data).encode()).decode()


def decrypt_credentials(blob: str) -> dict[str, Any]:
    raw = _fernet().decrypt(blob.encode())
    return json.loads(raw.decode())
