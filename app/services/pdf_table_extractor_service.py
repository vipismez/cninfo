from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
import threading
from typing import Callable
import unicodedata

import pdfplumber
from openpyxl import Workbook

from app.table_name_dictionary import TABLE_NAME_ALIASES


@dataclass(slots=True)
class ExtractionSummary:
    total: int = 0
    processed: int = 0
    success: int = 0
    failed: int = 0
    skipped: int = 0
    skipped_tables: int = 0
    stopped: bool = False


class PdfTableExtractorService:
    TITLE_KEYWORDS = (
        "关键指标",
        "资产负债表",
        "利润表",
        "现金流量表",
        "所有者权益变动表",
        "主要会计数据",
        "主要财务指标",
        "前十名股东",
        "项目",
        "单位",
        "表",
    )
    SECTION_PREFIX_RE = re.compile(r"^\s*\d+(?:\.\d+){1,3}\s*")
    TABLE_HEADER_LIKE_RE = re.compile(r"(\d{4}年|同比|项目|本年|上年|增减)")
    UNIT_LIKE_RE = re.compile(r"(单位|货币|币种|人民币|万元|亿元)")
    ILLEGAL_XML_RE = re.compile(r"[\x00-\x08\x0B-\x0C\x0E-\x1F\uD800-\uDFFF\uFFFE\uFFFF]")

    def __init__(self) -> None:
        alias_pairs: list[tuple[str, str]] = []
        for canonical, aliases in TABLE_NAME_ALIASES.items():
            alias_pairs.append((self._normalize_text(canonical), canonical))
            for alias in aliases:
                alias_pairs.append((self._normalize_text(alias), canonical))
        # 长别名优先，减少“关键指标”被“指标”类短词误命中。
        self._alias_pairs = sorted(set(alias_pairs), key=lambda item: len(item[0]), reverse=True)

    def process_directory(
        self,
        source_dir: Path,
        target_dir: Path,
        stop_event: threading.Event,
        log: Callable[[str], None],
        progress: Callable[[int, int], None],
    ) -> ExtractionSummary:
        summary = ExtractionSummary()
        pdf_files = sorted(
            [p for p in source_dir.rglob("*") if p.is_file() and p.suffix.lower() == ".pdf"],
            key=lambda p: str(p).lower(),
        )
        summary.total = len(pdf_files)

        for idx, pdf_path in enumerate(pdf_files, start=1):
            if stop_event.is_set():
                summary.stopped = True
                log("收到停止指令，正在结束任务。")
                break

            rel_parent = pdf_path.parent.relative_to(source_dir)
            out_dir = target_dir / rel_parent
            out_path = self._next_available_path(out_dir / f"{pdf_path.stem}.xlsx")
            log(f"[{idx}/{summary.total}] 提取: {pdf_path}")

            try:
                table_count, skipped_tables = self._extract_one_pdf(pdf_path, out_path, stop_event)
                summary.processed += 1
                summary.skipped_tables += skipped_tables
                if table_count <= 0:
                    summary.skipped += 1
                    log("  未命中字典中的表格名称，已跳过。")
                else:
                    summary.success += 1
                    log(f"  成功导出 {table_count} 张表（过滤 {skipped_tables} 张） -> {out_path}")
            except InterruptedError:
                summary.stopped = True
                log("收到停止指令，当前文件中断。")
                break
            except Exception as exc:  # noqa: BLE001
                summary.processed += 1
                summary.failed += 1
                log(f"  失败: {exc}")

            progress(summary.processed, summary.total)

        return summary

    def _extract_one_pdf(self, pdf_path: Path, out_path: Path, stop_event: threading.Event) -> tuple[int, int]:
        wb = Workbook()
        default_sheet = wb.active
        used_name_counts: dict[str, int] = {}
        used_final_names: set[str] = set()
        table_count = 0
        skipped_tables = 0

        with pdfplumber.open(pdf_path) as pdf:
            for page_idx, page in enumerate(pdf.pages, start=1):
                if stop_event.is_set():
                    raise InterruptedError()

                tables = page.find_tables()
                if not tables:
                    continue

                lines = self._extract_text_lines(page)
                for table_idx, table in enumerate(tables, start=1):
                    if stop_event.is_set():
                        raise InterruptedError()

                    rows = self._normalize_rows(table.extract())
                    if not rows:
                        skipped_tables += 1
                        continue

                    title_guess = self._guess_title(lines, table.bbox[1], page_idx, table_idx)
                    canonical_title = self._canonicalize_title(title_guess)
                    if canonical_title is None:
                        fallback = self._title_from_rows(rows)
                        canonical_title = self._canonicalize_title(fallback) if fallback else None
                    if canonical_title is None:
                        skipped_tables += 1
                        continue

                    sheet_name = self._unique_sheet_name(canonical_title, used_name_counts, used_final_names)
                    ws = wb.create_sheet(sheet_name)
                    for row in rows:
                        ws.append(row)
                    table_count += 1

        if table_count <= 0:
            return 0, skipped_tables

        wb.remove(default_sheet)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        wb.save(out_path)
        return table_count, skipped_tables

    def _extract_text_lines(self, page: pdfplumber.page.Page) -> list[tuple[float, str]]:
        if hasattr(page, "extract_text_lines"):
            try:
                rich_lines = page.extract_text_lines()
            except Exception:  # noqa: BLE001
                rich_lines = []
            else:
                out: list[tuple[float, str]] = []
                for item in rich_lines:
                    text = self._normalize_text(str(item.get("text", "")).strip())
                    top = float(item.get("top", 0.0))
                    if text:
                        out.append((top, text))
                if out:
                    return out

        words = page.extract_words(x_tolerance=2, y_tolerance=2)
        if not words:
            return []

        grouped: dict[int, list[dict[str, object]]] = {}
        for w in words:
            top_key = int(round(float(w["top"])))
            grouped.setdefault(top_key, []).append(w)

        lines: list[tuple[float, str]] = []
        for key in sorted(grouped.keys()):
            row_words = sorted(grouped[key], key=lambda item: float(item["x0"]))
            text = "".join(str(item["text"]).strip() for item in row_words if str(item["text"]).strip())
            if text:
                lines.append((float(key), text))
        return lines

    def _guess_title(self, lines: list[tuple[float, str]], table_top: float, page_idx: int, table_idx: int) -> str:
        candidates = [(top, txt) for top, txt in lines if top < table_top and (table_top - top) <= 220]
        if not candidates:
            return f"Table_{page_idx}_{table_idx}"

        # 评分规则：优先章节标题，抑制单位行/表头行/纯数字行。
        best_text = ""
        best_score = -10**9
        for top, txt in candidates:
            score = self._score_title_candidate(txt, top, table_top)
            if score > best_score:
                best_score = score
                best_text = txt

        if best_score < 1:
            best_text = candidates[-1][1]

        title = self._cleanup_title(best_text)
        if not title:
            return f"Table_{page_idx}_{table_idx}"
        return title

    def _score_title_candidate(self, text: str, top: float, table_top: float) -> float:
        score = 0.0
        text = self._normalize_text(text)
        compact = re.sub(r"\s+", "", text)
        dist = table_top - top

        if dist <= 120:
            score += 3.0
        elif dist <= 180:
            score += 1.5

        if self.SECTION_PREFIX_RE.match(text):
            score += 8.0

        for keyword in self.TITLE_KEYWORDS:
            if keyword in compact:
                score += 4.0

        if self.UNIT_LIKE_RE.search(compact) or compact.startswith(("(", "（")):
            score -= 8.0

        if self.TABLE_HEADER_LIKE_RE.search(compact):
            score -= 4.0

        if re.fullmatch(r"[\d,\.()%+-]+", compact):
            score -= 10.0

        length = len(compact)
        if 2 <= length <= 22:
            score += 2.0
        elif length > 48:
            score -= 3.0

        return score

    def _cleanup_title(self, text: str) -> str:
        normalized = self._normalize_text(text)
        no_prefix = self.SECTION_PREFIX_RE.sub("", normalized)
        no_prefix = no_prefix.strip().strip("-—:：.。 ")
        if no_prefix:
            return no_prefix
        return normalized.strip()

    def _canonicalize_title(self, title: str) -> str | None:
        text = self._normalize_text(title)
        for alias, canonical in self._alias_pairs:
            if alias and alias in text:
                return canonical
        return None

    def _title_from_rows(self, rows: list[list[str]]) -> str:
        head = " ".join(" ".join(r) for r in rows[:2])
        return self._normalize_text(head)

    def _normalize_rows(self, rows: list[list[str | None]] | None) -> list[list[str]]:
        if not rows:
            return []

        normalized: list[list[str]] = []
        max_cols = max((len(r) for r in rows), default=0)
        if max_cols == 0:
            return []

        for row in rows:
            padded = list(row) + [""] * (max_cols - len(row))
            cleaned = [self._clean_cell(cell) for cell in padded]
            if any(cell for cell in cleaned):
                normalized.append(cleaned)

        if len(normalized) < 2:
            return []
        return normalized

    @classmethod
    def _clean_cell(cls, value: str | None) -> str:
        if value is None:
            return ""
        text = str(value).strip().replace("\n", " ")
        return cls._normalize_text(text)

    @classmethod
    def _normalize_text(cls, text: str) -> str:
        normalized = unicodedata.normalize("NFKC", text)
        return cls.ILLEGAL_XML_RE.sub("", normalized)

    @staticmethod
    def _unique_sheet_name(raw_title: str, used_counts: dict[str, int], used_final: set[str]) -> str:
        name = re.sub(r"[\\/*?:\[\]]", "_", raw_title)
        name = PdfTableExtractorService._normalize_text(name)
        name = name.strip().strip("'")
        name = name or "Table"
        base = name[:31]

        count = used_counts.get(base, 0)
        while True:
            if count == 0:
                candidate = base
            else:
                suffix = f"_{count + 1}"
                candidate = f"{base[: 31 - len(suffix)]}{suffix}"

            if candidate not in used_final:
                used_counts[base] = count + 1
                used_final.add(candidate)
                return candidate
            count += 1

    @staticmethod
    def _next_available_path(path: Path) -> Path:
        if not path.exists():
            return path
        index = 1
        while True:
            candidate = path.with_name(f"{path.stem}_{index}{path.suffix}")
            if not candidate.exists():
                return candidate
            index += 1
