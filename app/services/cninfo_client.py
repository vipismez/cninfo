from __future__ import annotations

from pathlib import Path
from typing import Any

import requests

from app.config import CNINFO_HOME, CNINFO_QUERY_URL, DEFAULT_HEADERS, STATIC_BASE
from app.services.rate_limiter import RateLimiter


class CninfoClient:
    def __init__(self, limiter: RateLimiter) -> None:
        self.limiter = limiter
        self.session = requests.Session()
        self.session.headers.update(DEFAULT_HEADERS)
        self._warmed = False

    def warmup(self) -> None:
        if self._warmed:
            return
        self.limiter.wait()
        self.session.get(CNINFO_HOME, timeout=12)
        self._warmed = True

    def query_announcements(self, params: dict[str, Any]) -> dict[str, Any]:
        self.warmup()
        self.limiter.wait()
        resp = self.session.post(CNINFO_QUERY_URL, data=params, timeout=20)
        resp.raise_for_status()
        return resp.json()

    def download_adjunct(self, adjunct_url: str, target: Path) -> None:
        if not adjunct_url:
            raise ValueError("adjunct_url 为空")

        full_url = adjunct_url
        if not adjunct_url.startswith("http"):
            full_url = STATIC_BASE + adjunct_url.lstrip("/")

        self.limiter.wait()
        with self.session.get(full_url, timeout=40, stream=True) as resp:
            resp.raise_for_status()
            target.parent.mkdir(parents=True, exist_ok=True)
            with target.open("wb") as fp:
                for chunk in resp.iter_content(chunk_size=1024 * 64):
                    if chunk:
                        fp.write(chunk)
