from __future__ import annotations

from typing import Any
import base64
import binascii
import json


def encode_hit_id(payload: dict[str, object]) -> str:
    """Encode a retrieval hit payload as URL-safe, padding-free JSON base64."""
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def decode_hit_id(hit_id: str) -> dict[str, Any]:
    """Decode and validate a retrieval hit id payload."""
    try:
        padding = "=" * (-len(hit_id) % 4)
        raw = base64.urlsafe_b64decode((hit_id + padding).encode("ascii"))
        payload = json.loads(raw.decode("utf-8"))
    except (binascii.Error, json.JSONDecodeError, UnicodeDecodeError, ValueError) as exc:
        raise ValueError("Invalid retrieval hit id") from exc
    if not isinstance(payload, dict):
        raise ValueError("Invalid retrieval hit id")
    return payload
