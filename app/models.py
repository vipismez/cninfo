from __future__ import annotations

from dataclasses import dataclass
from datetime import date


@dataclass(slots=True)
class Security:
    symbol: str
    exchange: str
    name: str
    pinyin: str
    sec_type: str
    industry: str
    org_id: str = ""
    category: str = ""
    is_active: bool = True


@dataclass(slots=True)
class SearchFilter:
    start_date: date
    end_date: date
    queries: tuple[str, ...] = ()
    keyword: str = ""
    plates: tuple[str, ...] = ()
    industries: tuple[str, ...] = ()
    categories: tuple[str, ...] = ()
    page_size: int = 30
    max_records: int = 300


@dataclass(slots=True)
class AnnouncementItem:
    announcement_id: str
    sec_code: str
    sec_name: str
    title: str
    announcement_time: str
    adjunct_url: str
