"""Shared value serialization for repository SQL params."""

from __future__ import annotations

import json
from datetime import datetime


def ser(value: object) -> object:
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, (dict, list)):
        return json.dumps(value)
    if hasattr(value, "value"):  # Enum
        return value.value
    return value
