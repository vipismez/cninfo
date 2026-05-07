from __future__ import annotations

import re
from typing import Final

import requests

SCRIPT_URL: Final[str] = "https://www.cninfo.com.cn/new/js/app/disclosure/notice/history-notice.js"

# 来自巨潮页面“行业”下拉的默认回退值（当在线抓取失败时使用）。
FALLBACK_INDUSTRIES: Final[list[str]] = [
    "农、林、牧、渔业",
    "采矿业",
    "制造业",
    "电力、热力、燃气及水生产和供应业",
    "建筑业",
    "批发和零售业",
    "交通运输、仓储和邮政业",
    "住宿和餐饮业",
    "信息传输、软件和信息技术服务业",
    "金融业",
    "房地产业",
    "租赁和商务服务业",
    "科学研究和技术服务业",
    "水利、环境和公共设施管理业",
    "居民服务、修理和其他服务业",
    "教育",
    "卫生和社会工作",
    "文化、体育和娱乐业",
    "综合",
]


class IndustryOptionsService:
    def __init__(self) -> None:
        self.session = requests.Session()
        self.session.headers.update(
            {
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
                ),
                "Referer": "https://www.cninfo.com.cn/",
            }
        )

    def load_industries(self) -> list[str]:
        try:
            js = self._fetch_script_text()
            industries = self._extract_industries(js)
            if industries:
                return industries
        except Exception:  # noqa: BLE001
            pass
        return list(FALLBACK_INDUSTRIES)

    def _fetch_script_text(self) -> str:
        resp = self.session.get(SCRIPT_URL, timeout=15)
        resp.raise_for_status()

        # 该脚本历史上可能使用 gbk 编码，优先尝试 gbk，再回退 utf-8。
        raw = resp.content
        try:
            return raw.decode("gbk")
        except UnicodeDecodeError:
            return raw.decode("utf-8", errors="ignore")

    def _extract_industries(self, script_text: str) -> list[str]:
        blocks = re.findall(r'"industry"\s*:\s*\[(.*?)\]', script_text, flags=re.S)
        if not blocks:
            return []

        values: list[str] = []
        for block in blocks:
            keys = re.findall(r'"key"\s*:\s*"([^"]+)"', block)
            for key in keys:
                cleaned = key.strip()
                if not cleaned:
                    continue
                if cleaned not in values:
                    values.append(cleaned)

        # 过滤掉明显乱码块（兼容脚本编码异常场景）
        normalized = [v for v in values if "\ufffd" not in v and len(v) <= 40]
        return normalized
