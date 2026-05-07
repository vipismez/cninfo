from __future__ import annotations

from datetime import date

from app.config import CATEGORY_MAP, PLATE_MAP, PLATE_ORDER
from app.models import AnnouncementItem, SearchFilter
from app.services.cninfo_client import CninfoClient
from app.services.master_data_service import MasterDataService


class SearchService:
    def __init__(self, client: CninfoClient, master_data: MasterDataService) -> None:
        self.client = client
        self.master_data = master_data

    def search(self, flt: SearchFilter) -> list[AnnouncementItem]:
        items: list[AnnouncementItem] = []
        seen_ids: set[str] = set()
        query_symbols = self._resolve_symbols(flt.queries)

        for query_symbol in query_symbols:
            page_num = 1
            while len(items) < flt.max_records:
                payload = self._build_payload(flt, page_num, query_symbol)
                data = self.client.query_announcements(payload)
                rows = data.get("announcements") or []
                if not rows:
                    break

                for row in rows:
                    ann = AnnouncementItem(
                        announcement_id=str(row.get("announcementId", "")),
                        sec_code=str(row.get("secCode", "")),
                        sec_name=str(row.get("secName", "")),
                        title=str(row.get("announcementTitle", "")),
                        announcement_time=str(row.get("announcementTime", "")),
                        adjunct_url=str(row.get("adjunctUrl", "")),
                    )
                    if ann.announcement_id and ann.announcement_id in seen_ids:
                        continue
                    if flt.keyword and flt.keyword not in ann.title:
                        continue

                    if ann.announcement_id:
                        seen_ids.add(ann.announcement_id)
                    items.append(ann)
                    if len(items) >= flt.max_records:
                        break

                if len(rows) < flt.page_size:
                    break
                page_num += 1

        return items

    def _build_payload(
        self,
        flt: SearchFilter,
        page_num: int,
        query_symbol: str,
    ) -> dict[str, str | int]:

        category_values = [CATEGORY_MAP[key] for key in flt.categories if key in CATEGORY_MAP]
        plate_values = [PLATE_MAP[key] for key in flt.plates if key in PLATE_MAP]
        if not plate_values:
            plate_values = [PLATE_MAP[key] for key in PLATE_ORDER if key in PLATE_MAP]
        payload: dict[str, str | int] = {
            "pageNum": page_num,
            "pageSize": flt.page_size,
            "column": "szse",
            "tabName": "fulltext",
            "plate": ";".join(plate_values),
            "stock": query_symbol,
            "searchkey": flt.keyword,
            "secid": "",
            "category": ";".join(category_values),
            "trade": ";".join(flt.industries),
            "seDate": self._date_range(flt.start_date, flt.end_date),
            "sortName": "",
            "sortType": "",
            "isHLtitle": "true",
        }
        return payload

    def _resolve_symbols(self, queries: tuple[str, ...]) -> list[str]:
        if not queries:
            return [""]

        symbols: list[str] = []
        for raw in queries:
            text = raw.strip()
            if not text:
                continue
            security = None
            if text.isdigit():
                security = self.master_data.get(text.zfill(6) if len(text) <= 6 else text)
            else:
                matches = self.master_data.search(text, limit=1)
                if matches:
                    security = matches[0]

            if security is None:
                continue

            symbol = security.symbol
            if security.org_id:
                symbol = f"{security.symbol},{security.org_id}"
            if symbol not in symbols:
                symbols.append(symbol)

        return symbols or [""]

    @staticmethod
    def _date_range(start: date, end: date) -> str:
        return f"{start.isoformat()}~{end.isoformat()}"
