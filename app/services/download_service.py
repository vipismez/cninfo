from __future__ import annotations

import re
from pathlib import Path

from app.config import DOWNLOAD_DIR, ILLEGAL_FILE_CHARS
from app.models import AnnouncementItem
from app.services.cninfo_client import CninfoClient


class DownloadService:
    def __init__(self, client: CninfoClient, base_dir: Path | None = None) -> None:
        self.client = client
        self.base_dir = base_dir or DOWNLOAD_DIR

    def split_batch(self, announcements: list[AnnouncementItem], max_count: int = 50) -> tuple[list[AnnouncementItem], int]:
        batch = announcements[:max_count]
        remain = max(0, len(announcements) - max_count)
        return batch, remain

    def download(self, announcements: list[AnnouncementItem]) -> tuple[int, list[str]]:
        done = 0
        errors: list[str] = []
        for item in announcements:
            try:
                target = self._target_path(item)
                self.client.download_adjunct(item.adjunct_url, target)
                done += 1
            except Exception as exc:  # noqa: BLE001
                errors.append(f"{item.sec_code} {item.title}: {exc}")
        return done, errors

    def _target_path(self, ann: AnnouncementItem) -> Path:
        sec_code = self._sanitize(ann.sec_code)
        sec_name = self._sanitize(ann.sec_name)
        title = self._sanitize(ann.title)

        folder_name = f"{sec_code}{sec_name}".strip()
        file_name = f"{sec_code}{sec_name}{title}.pdf"

        folder = self.base_dir / folder_name
        target = folder / file_name
        if target.exists():
            target = folder / f"{sec_code}{sec_name}{title}_{ann.announcement_id}.pdf"
        return target

    @staticmethod
    def _sanitize(text: str) -> str:
        text = text.strip()
        if not text:
            return "未知"
        pattern = "[" + re.escape(ILLEGAL_FILE_CHARS) + "]"
        text = re.sub(pattern, "_", text)
        return re.sub(r"\s+", "", text)
