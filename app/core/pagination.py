"""Opaque keyset cursor helpers.

A cursor carries the ``(created_at, id)`` of the last item on a page, encoded as
url-safe base64 of a small JSON object.
"""

import base64
import json
import uuid
from datetime import datetime

from app.core.errors import AppError


def _invalid() -> AppError:
    return AppError(422, "INVALID_CURSOR", "Malformed or invalid cursor", field="cursor")


def encode_cursor(created_at: datetime, id: uuid.UUID) -> str:
    payload = json.dumps({"c": created_at.isoformat(), "i": str(id)}, separators=(",", ":"))
    return base64.urlsafe_b64encode(payload.encode()).decode().rstrip("=")


def decode_cursor(token: str) -> tuple[datetime, uuid.UUID]:
    try:
        padded = token + "=" * (-len(token) % 4)
        data = json.loads(base64.urlsafe_b64decode(padded.encode("ascii")).decode())
        if not isinstance(data, dict):
            raise ValueError("cursor payload is not an object")
        created_at = datetime.fromisoformat(data["c"])
        item_id = uuid.UUID(data["i"])
    except (ValueError, KeyError, TypeError, UnicodeError):
        raise _invalid() from None
    return created_at, item_id
