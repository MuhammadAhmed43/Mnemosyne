"""Daily update check against GitHub releases (Doc 16 §6). No user data sent;
failures are non-fatal. The engine never auto-updates — it only notifies."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional

import httpx

logger = logging.getLogger("mnemosyne.update")

RELEASES_URL = "https://api.github.com/repos/mnemosyne/engine/releases/latest"


@dataclass
class UpdateInfo:
    current: str
    latest: str
    download_url: str


def _newer(latest: str, current: str) -> bool:
    def parts(v: str) -> list[int]:
        return [int(x) for x in v.split(".") if x.isdigit()]

    return parts(latest) > parts(current)


async def check_for_updates(current_version: str) -> Optional[UpdateInfo]:
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            r = await client.get(RELEASES_URL)
            data = r.json()
            latest = str(data["tag_name"]).lstrip("v")
            if _newer(latest, current_version):
                return UpdateInfo(current_version, latest, data.get("html_url", ""))
    except Exception:  # noqa: BLE001 - update check failure is non-critical
        return None
    return None
