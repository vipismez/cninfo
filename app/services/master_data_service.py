from __future__ import annotations

import json
from pathlib import Path
import re

import requests

from app.models import Security


CNINFO_MASTER_URLS = {
    "stock": [
        ("https://www.cninfo.com.cn/new/data/szse_stock.json", "CN"),
        ("https://www.cninfo.com.cn/new/data/hke_stock.json", "HK"),
        ("https://www.cninfo.com.cn/new/data/gfzr_stock.json", "BJ"),
    ],
    "fund": [("https://www.cninfo.com.cn/new/data/fund_stock.json", "CN")],
    "bond": [("https://www.cninfo.com.cn/new/data/bond_stock.json", "CN")],
}


class MasterDataService:
    def __init__(self, data_file: Path) -> None:
        self.data_file = data_file
        self._items: list[Security] = []
        self._by_symbol: dict[str, Security] = {}

    def load(self) -> None:
        if self._needs_refresh():
            self.refresh_from_cninfo()

        if not self.data_file.exists():
            self._items = []
            self._by_symbol = {}
            return

        payload = json.loads(self.data_file.read_text(encoding="utf-8"))
        self._items = [
            Security(
                symbol=row["symbol"],
                exchange=row.get("exchange", ""),
                name=row.get("name", ""),
                pinyin=row.get("pinyin", ""),
                sec_type=row.get("type", ""),
                org_id=row.get("org_id", ""),
                category=row.get("category", ""),
                industry=row.get("industry", ""),
                is_active=row.get("is_active", True),
            )
            for row in payload
        ]
        self._by_symbol = {item.symbol: item for item in self._items}

    def refresh_from_cninfo(self) -> None:
        session = requests.Session()
        session.headers.update(
            {
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
                ),
                "Referer": "https://www.cninfo.com.cn/",
            }
        )

        rows: list[dict[str, object]] = []
        for sec_type, configs in CNINFO_MASTER_URLS.items():
            for url, exchange_hint in configs:
                payload = self._fetch_json(session, url)
                rows.extend(self._normalize_cninfo_rows(payload.get("stockList", []), sec_type, exchange_hint))

        if not rows:
            return

        dedup: dict[str, dict[str, object]] = {}
        for row in rows:
            dedup[f"{row['symbol']}.{row['sec_type']}"] = row

        self.data_file.parent.mkdir(parents=True, exist_ok=True)
        self.data_file.write_text(
            json.dumps(list(dedup.values()), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def count(self) -> int:
        return len(self._items)

    def list_industries(self) -> list[str]:
        return sorted({item.industry for item in self._items if item.industry})

    def search(self, text: str, limit: int = 20) -> list[Security]:
        text = text.strip().lower()
        if not text:
            return []

        out: list[Security] = []
        for item in self._items:
            if (
                text in item.symbol.lower()
                or text in item.name.lower()
                or text in item.pinyin.lower()
            ):
                out.append(item)
            if len(out) >= limit:
                break
        return out

    def get(self, symbol: str) -> Security | None:
        return self._by_symbol.get(symbol)

    def industry_of(self, symbol: str) -> str:
        rec = self._by_symbol.get(symbol)
        return rec.industry if rec else ""

    def _needs_refresh(self) -> bool:
        if not self.data_file.exists():
            return True

        try:
            payload = json.loads(self.data_file.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return True

        return len(payload) < 1000 or self._payload_looks_garbled(payload)

    def _normalize_cninfo_rows(
        self,
        rows: list[dict[str, object]],
        sec_type: str,
        exchange_hint: str,
    ) -> list[dict[str, object]]:
        out: list[dict[str, object]] = []
        for row in rows:
            symbol = str(row.get("code", "")).strip()
            name = str(row.get("zwjc", "")).strip()
            pinyin = str(row.get("pinyin", "")).strip().upper()
            if not symbol or not name:
                continue

            exchange = self._infer_exchange(symbol, exchange_hint)
            out.append(
                {
                    "symbol": symbol,
                    "exchange": exchange,
                    "name": name,
                    "pinyin": pinyin,
                    "type": sec_type,
                    "sec_type": sec_type,
                    "org_id": str(row.get("orgId", "")).strip(),
                    "category": str(row.get("category", "")).strip(),
                    "industry": "",
                    "is_active": True,
                }
            )
        return out

    def _fetch_json(self, session: requests.Session, url: str) -> dict[str, object]:
        resp = session.get(url, timeout=25)
        resp.raise_for_status()

        encodings = [resp.encoding, resp.apparent_encoding, "utf-8", "utf-8-sig", "gb18030", "gbk"]
        candidates: list[tuple[int, dict[str, object]]] = []
        raw = resp.content

        for encoding in [enc for enc in encodings if enc]:
            try:
                payload = json.loads(raw.decode(encoding))
            except (UnicodeDecodeError, json.JSONDecodeError):
                continue
            candidates.append((self._payload_score(payload), payload))

        if not candidates:
            raise ValueError(f"无法解析主数据 JSON: {url}")

        candidates.sort(key=lambda item: item[0], reverse=True)
        return candidates[0][1]

    def _payload_score(self, payload: dict[str, object]) -> int:
        rows = payload.get("stockList", []) if isinstance(payload, dict) else []
        score = 0
        for row in rows[:50]:
            name = str(getattr(row, "get", lambda *_: "")("zwjc", ""))
            score += len(re.findall(r"[\u4e00-\u9fff]", name)) * 3
            score -= len(re.findall(r"[ƽ���]", name)) * 2
        return score

    def _payload_looks_garbled(self, payload: list[dict[str, object]]) -> bool:
        sample_names = [str(row.get("name", "")) for row in payload[:50]]
        chinese_chars = sum(len(re.findall(r"[\u4e00-\u9fff]", name)) for name in sample_names)
        return chinese_chars == 0

    @staticmethod
    def _infer_exchange(symbol: str, exchange_hint: str) -> str:
        if exchange_hint == "HK":
            return "HK"
        if exchange_hint == "BJ":
            return "BJ"
        if len(symbol) == 5:
            return "HK"
        if symbol.startswith(("4", "8")):
            return "BJ"
        if symbol.startswith(("5", "6", "9")):
            return "SH"
        return "SZ"
