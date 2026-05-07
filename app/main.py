from __future__ import annotations

import threading
import calendar
from datetime import date, datetime, timedelta
from pathlib import Path
import tkinter as tk
from tkinter import messagebox, ttk
from tkcalendar import DateEntry

from app.config import CATEGORY_ORDER, DATA_DIR, DOWNLOAD_DIR, PLATE_ORDER
from app.models import AnnouncementItem, SearchFilter
from app.pdf_extractor_window import PdfExtractorWindow
from app.services.cninfo_client import CninfoClient
from app.services.download_service import DownloadService
from app.services.industry_options_service import IndustryOptionsService
from app.services.master_data_service import MasterDataService
from app.services.rate_limiter import RateLimiter
from app.services.search_service import SearchService


class MainApp:
    KEYWORD_PLACEHOLDER = "非必须"
    QUERY_PLACEHOLDER = "请输入股票代码/简称/拼音"

    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("巨潮公告批量下载器")
        self.root.geometry("1280x820")

        self.start_var = tk.StringVar(value=(date.today() - timedelta(days=30)).isoformat())
        self.end_var = tk.StringVar(value=date.today().isoformat())
        self.query_var = tk.StringVar()
        self.keyword_var = tk.StringVar()
        self.status_var = tk.StringVar(value="就绪")
        self.period_var = tk.StringVar(value="1个月")

        self.category_vars: dict[str, tk.BooleanVar] = {
            name: tk.BooleanVar(value=False) for name in CATEGORY_ORDER
        }

        self.master = MasterDataService(DATA_DIR / "master_data.json")
        self.master.load()
        self.industry_service = IndustryOptionsService()
        self.industry_options = self.industry_service.load_industries()

        self.selected_queries: list[str] = []
        self.query_candidate_symbols: list[str] = []
        self.query_candidate_displays: list[str] = []
        self.query_display_to_symbol: dict[str, str] = {}
        self.industry_vars: dict[str, tk.BooleanVar] = {
            name: tk.BooleanVar(value=False) for name in self.industry_options
        }
        self.plate_vars: dict[str, tk.BooleanVar] = {
            name: tk.BooleanVar(value=False) for name in PLATE_ORDER
        }

        limiter = RateLimiter(min_interval=0.8, jitter=(0.2, 1.2))
        client = CninfoClient(limiter)
        self.search_service = SearchService(client, self.master)
        self.download_service = DownloadService(client)

        self.results: list[AnnouncementItem] = []
        self.checked_result_ids: set[str] = set()
        self.extractor_window: PdfExtractorWindow | None = None

        self._build_ui()

    def _build_ui(self) -> None:
        container = ttk.Frame(self.root, padding=12)
        container.pack(fill=tk.BOTH, expand=True)
        container.columnconfigure(0, weight=1)
        container.rowconfigure(1, weight=1)

        self._build_filters(container)
        self._build_results(container)

        status_bar = ttk.Label(container, textvariable=self.status_var, anchor=tk.W)
        status_bar.grid(row=2, column=0, sticky=tk.EW, pady=(8, 0))

    def _build_filters(self, parent: ttk.Frame) -> None:
        frm = ttk.LabelFrame(parent, text="筛选条件", padding=12)
        frm.grid(row=0, column=0, sticky=tk.EW)

        top_frame = ttk.Frame(frm)
        top_frame.grid(row=0, column=0, sticky=tk.EW)
        top_frame.columnconfigure(0, weight=0)
        top_frame.columnconfigure(1, weight=1)

        top_left = ttk.Frame(top_frame)
        top_left.grid(row=0, column=0, sticky=tk.W, padx=(0, 10))
        top_left.columnconfigure(5, weight=1)

        ttk.Label(top_left, text="开始日期").grid(row=0, column=0, sticky=tk.W)
        self.start_picker = DateEntry(
            top_left,
            textvariable=self.start_var,
            width=13,
            date_pattern="yyyy-mm-dd",
            locale="zh_CN",
        )
        self.start_picker.grid(row=0, column=1, sticky=tk.W, padx=(6, 14))
        self.start_picker.bind("<<DateEntrySelected>>", self.on_start_date_selected)
        ttk.Label(top_left, text="结束日期").grid(row=0, column=2, sticky=tk.W)
        self.end_picker = DateEntry(
            top_left,
            textvariable=self.end_var,
            width=13,
            date_pattern="yyyy-mm-dd",
            locale="zh_CN",
        )
        self.end_picker.grid(row=0, column=3, sticky=tk.W, padx=(6, 0))
        self.end_picker.bind("<<DateEntrySelected>>", self.on_end_date_selected)

        quick_date_row = ttk.Frame(top_left)
        quick_date_row.grid(row=0, column=4, sticky=tk.W, padx=(10, 0))
        ttk.Label(quick_date_row, text="快捷区间").pack(side=tk.LEFT)
        self.period_combo = ttk.Combobox(
            quick_date_row,
            textvariable=self.period_var,
            width=8,
            state="readonly",
            values=("1个月", "半年", "1年", "2年"),
        )
        self.period_combo.pack(side=tk.LEFT, padx=(6, 0))
        self.period_combo.bind("<<ComboboxSelected>>", self.on_period_selected)

        self._sync_date_picker_limits()

        ttk.Label(top_left, text="标题关键词").grid(row=1, column=0, sticky=tk.W, pady=(8, 0))
        self.keyword_entry = ttk.Entry(top_left, textvariable=self.keyword_var, foreground="#888888", width=44)
        self.keyword_entry.grid(row=1, column=1, columnspan=4, sticky=tk.W, pady=(8, 0), padx=(6, 0))
        self.keyword_entry.bind("<FocusIn>", self.on_keyword_focus_in)
        self.keyword_entry.bind("<FocusOut>", self.on_keyword_focus_out)
        self._apply_keyword_placeholder()

        ttk.Label(top_left, text="代码/简称/拼音").grid(row=2, column=0, sticky=tk.W, pady=(8, 0))
        self.query_entry = ttk.Entry(top_left, textvariable=self.query_var, foreground="#888888", width=44)
        self.query_entry.grid(row=2, column=1, columnspan=4, sticky=tk.W, pady=(8, 0), padx=(6, 0))
        self.query_entry.bind("<FocusIn>", self.on_query_focus_in)
        self.query_entry.bind("<FocusOut>", self.on_query_focus_out)
        self.query_entry.bind("<KeyRelease>", self.on_query_input)
        self.query_entry.bind("<Return>", self.on_query_enter)
        self.query_entry.bind("<Escape>", self.on_query_escape)
        self.query_entry.bind("<Down>", self.on_query_down)
        self.query_entry.bind("<Up>", self.on_query_up)
        self._apply_query_placeholder()

        top_right = ttk.LabelFrame(top_frame, text="已选股票", padding=6)
        top_right.grid(row=0, column=1, sticky=tk.NSEW)
        top_right.columnconfigure(0, weight=1)
        top_right.rowconfigure(0, weight=1)

        self.query_selected_list = tk.Listbox(top_right, height=4, selectmode=tk.EXTENDED)
        self.query_selected_list.grid(row=0, column=0, sticky=tk.NSEW)

        selected_scroll = ttk.Scrollbar(top_right, orient=tk.VERTICAL, command=self.query_selected_list.yview)
        self.query_selected_list.configure(yscrollcommand=selected_scroll.set)
        selected_scroll.grid(row=0, column=1, sticky=tk.NS, padx=(6, 0))

        selected_btns = ttk.Frame(top_right)
        selected_btns.grid(row=0, column=2, sticky=tk.NS, padx=(8, 0))
        ttk.Button(selected_btns, text="移除选中", command=self.remove_selected_queries).pack(fill=tk.X)
        ttk.Button(selected_btns, text="清空代码", command=self.clear_selected_queries).pack(fill=tk.X, pady=(8, 0))

        self._build_query_popup()

        sections_frame = ttk.Frame(frm)
        sections_frame.grid(row=1, column=0, sticky=tk.EW, pady=(10, 0))
        sections_frame.columnconfigure(0, weight=1)
        sections_frame.columnconfigure(1, weight=2)
        sections_frame.columnconfigure(2, weight=2)

        plate_frame = ttk.LabelFrame(sections_frame, text="板块", padding=6)
        plate_frame.grid(row=0, column=0, sticky=tk.NSEW, padx=(0, 8))
        for idx, name in enumerate(PLATE_ORDER):
            row = idx // 2
            col = idx % 2
            ttk.Checkbutton(plate_frame, text=name, variable=self.plate_vars[name]).grid(
                row=row,
                column=col,
                sticky=tk.W,
                padx=6,
                pady=3,
            )

        self.industry_frame = ttk.LabelFrame(sections_frame, text="行业", padding=6)
        self.industry_frame.grid(row=0, column=1, sticky=tk.NSEW, padx=(0, 8))
        self.industry_canvas = tk.Canvas(self.industry_frame, height=110, highlightthickness=0)
        industry_scroll = ttk.Scrollbar(self.industry_frame, orient=tk.VERTICAL, command=self.industry_canvas.yview)
        self.industry_canvas.configure(yscrollcommand=industry_scroll.set)
        self.industry_inner = ttk.Frame(self.industry_canvas)
        self.industry_inner.bind(
            "<Configure>",
            lambda _e: self.industry_canvas.configure(scrollregion=self.industry_canvas.bbox("all")),
        )
        self.industry_canvas.create_window((0, 0), window=self.industry_inner, anchor="nw")
        self.industry_canvas.grid(row=0, column=0, sticky=tk.NSEW)
        industry_scroll.grid(row=0, column=1, sticky=tk.NS)
        self.industry_frame.columnconfigure(0, weight=1)

        self.refresh_query_suggestions("")
        self.refresh_industry_checkboxes()
        self._refresh_selected_queries_list()

        cat_frame = ttk.LabelFrame(sections_frame, text="公告分类", padding=6)
        cat_frame.grid(row=0, column=2, sticky=tk.NSEW)
        self.category_canvas = tk.Canvas(cat_frame, height=110, highlightthickness=0)
        category_scroll = ttk.Scrollbar(cat_frame, orient=tk.VERTICAL, command=self.category_canvas.yview)
        self.category_canvas.configure(yscrollcommand=category_scroll.set)
        self.category_inner = ttk.Frame(self.category_canvas)
        self.category_inner.bind(
            "<Configure>",
            lambda _e: self.category_canvas.configure(scrollregion=self.category_canvas.bbox("all")),
        )
        self.category_canvas.create_window((0, 0), window=self.category_inner, anchor="nw")
        self.category_canvas.grid(row=0, column=0, sticky=tk.NSEW)
        category_scroll.grid(row=0, column=1, sticky=tk.NS)
        cat_frame.columnconfigure(0, weight=1)

        for idx, name in enumerate(CATEGORY_ORDER):
            row = idx // 5
            col = idx % 5
            ttk.Checkbutton(self.category_inner, text=name, variable=self.category_vars[name]).grid(
                row=row,
                column=col,
                sticky=tk.W,
                padx=6,
                pady=4,
            )

        btn_row = ttk.Frame(frm)
        btn_row.grid(row=2, column=0, sticky=tk.W, pady=8)
        ttk.Button(btn_row, text="检索", command=self.search_clicked).pack(side=tk.LEFT)
        ttk.Button(btn_row, text="清空板块", command=self.clear_selected_plates).pack(side=tk.LEFT, padx=8)
        ttk.Button(btn_row, text="清空分类", command=self.clear_categories).pack(side=tk.LEFT, padx=8)
        ttk.Button(btn_row, text="全选分类", command=self.select_all_categories).pack(side=tk.LEFT)
        ttk.Button(btn_row, text="PDF表格提取", command=self.open_pdf_extractor).pack(side=tk.LEFT, padx=8)

        frm.columnconfigure(0, weight=1)

    def _build_query_popup(self) -> None:
        self.query_popup = tk.Toplevel(self.root)
        self.query_popup.withdraw()
        self.query_popup.overrideredirect(True)
        self.query_popup.transient(self.root)

        popup_frame = ttk.Frame(self.query_popup, borderwidth=1, relief=tk.SOLID)
        popup_frame.pack(fill=tk.BOTH, expand=True)

        self.query_popup_list = tk.Listbox(popup_frame, height=8)
        self.query_popup_list.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.query_popup_list.bind("<ButtonRelease-1>", self.on_query_popup_pick)
        self.query_popup_list.bind("<Double-Button-1>", self.on_query_popup_pick)

        popup_scroll = ttk.Scrollbar(popup_frame, orient=tk.VERTICAL, command=self.query_popup_list.yview)
        popup_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self.query_popup_list.configure(yscrollcommand=popup_scroll.set)

    def _build_results(self, parent: ttk.Frame) -> None:
        frm = ttk.LabelFrame(parent, text="检索结果", padding=12)
        frm.grid(row=1, column=0, sticky=tk.NSEW, pady=(10, 0))

        columns = ("sel", "date", "code", "name", "title")
        self.tree = ttk.Treeview(frm, columns=columns, show="headings", height=18)
        self.tree.heading("sel", text="选择")
        self.tree.heading("date", text="公告日期")
        self.tree.heading("code", text="代码")
        self.tree.heading("name", text="简称")
        self.tree.heading("title", text="标题")

        self.tree.column("sel", width=58, anchor=tk.CENTER, stretch=False)
        self.tree.column("date", width=150, anchor=tk.W)
        self.tree.column("code", width=90, anchor=tk.W)
        self.tree.column("name", width=120, anchor=tk.W)
        self.tree.column("title", width=700, anchor=tk.W)

        self.tree.bind("<Button-1>", self.on_tree_click)

        y_scroll = ttk.Scrollbar(frm, orient=tk.VERTICAL, command=self.tree.yview)
        self.tree.configure(yscrollcommand=y_scroll.set)

        self.tree.grid(row=0, column=0, sticky=tk.NSEW)
        y_scroll.grid(row=0, column=1, sticky=tk.NS)

        op = ttk.Frame(frm)
        op.grid(row=1, column=0, columnspan=2, sticky=tk.W, pady=(10, 0))
        ttk.Button(op, text="全选", command=self.select_all_results).pack(side=tk.LEFT)
        ttk.Button(op, text="反选", command=self.invert_result_selection).pack(side=tk.LEFT, padx=8)
        ttk.Button(op, text="清空勾选", command=self.clear_result_selection).pack(side=tk.LEFT, padx=8)
        ttk.Button(op, text="下载已选（最多50）", command=self.download_selected).pack(side=tk.LEFT)
        ttk.Button(op, text="下载前50条", command=self.download_top_50).pack(side=tk.LEFT, padx=8)

        frm.columnconfigure(0, weight=1)
        frm.rowconfigure(0, weight=1)

    def clear_categories(self) -> None:
        for var in self.category_vars.values():
            var.set(False)

    def select_all_categories(self) -> None:
        for var in self.category_vars.values():
            var.set(True)

    def _selected_categories(self) -> tuple[str, ...]:
        return tuple(k for k, v in self.category_vars.items() if v.get())

    def _selected_plates(self) -> tuple[str, ...]:
        return tuple(k for k, v in self.plate_vars.items() if v.get())

    def clear_selected_plates(self) -> None:
        for var in self.plate_vars.values():
            var.set(False)

    def _apply_keyword_placeholder(self) -> None:
        if not self.keyword_var.get().strip():
            self.keyword_var.set(self.KEYWORD_PLACEHOLDER)
            self.keyword_entry.configure(foreground="#888888")

    def _clear_keyword_placeholder(self) -> None:
        if self.keyword_var.get().strip() == self.KEYWORD_PLACEHOLDER:
            self.keyword_var.set("")
        self.keyword_entry.configure(foreground="#000000")

    def on_keyword_focus_in(self, _event: tk.Event) -> None:
        if self.keyword_var.get().strip() == self.KEYWORD_PLACEHOLDER:
            self._clear_keyword_placeholder()

    def on_keyword_focus_out(self, _event: tk.Event) -> None:
        if not self.keyword_var.get().strip():
            self._apply_keyword_placeholder()

    def _apply_query_placeholder(self) -> None:
        if not self.query_var.get().strip():
            self.query_var.set(self.QUERY_PLACEHOLDER)
            self.query_entry.configure(foreground="#888888")

    def _clear_query_placeholder(self) -> None:
        if self.query_var.get().strip() == self.QUERY_PLACEHOLDER:
            self.query_var.set("")
        self.query_entry.configure(foreground="#000000")

    def _query_input_text(self) -> str:
        text = self.query_var.get().strip()
        return "" if text == self.QUERY_PLACEHOLDER else text

    def on_query_focus_in(self, _event: tk.Event) -> None:
        if self.query_var.get().strip() == self.QUERY_PLACEHOLDER:
            self._clear_query_placeholder()

    def on_query_focus_out(self, _event: tk.Event) -> None:
        if not self.query_var.get().strip():
            self._apply_query_placeholder()

    def _parse_date_var(self, value: str, fallback: date) -> date:
        try:
            return datetime.strptime(value.strip(), "%Y-%m-%d").date()
        except ValueError:
            return fallback

    def _sync_date_picker_limits(self) -> None:
        start_dt = self._parse_date_var(self.start_var.get(), date.today() - timedelta(days=30))
        end_dt = self._parse_date_var(self.end_var.get(), date.today())
        if end_dt < start_dt:
            end_dt = start_dt
            self.end_var.set(end_dt.isoformat())
            self.end_picker.set_date(end_dt)

        self.start_picker.configure(maxdate=end_dt)
        self.end_picker.configure(mindate=start_dt)

    def on_start_date_selected(self, _event: tk.Event) -> None:
        start_dt = self._parse_date_var(self.start_var.get(), date.today() - timedelta(days=30))
        end_dt = self._parse_date_var(self.end_var.get(), date.today())
        if start_dt > end_dt:
            end_dt = start_dt
            self.end_var.set(end_dt.isoformat())
            self.end_picker.set_date(end_dt)
        self._sync_date_picker_limits()

    def on_end_date_selected(self, _event: tk.Event) -> None:
        start_dt = self._parse_date_var(self.start_var.get(), date.today() - timedelta(days=30))
        end_dt = self._parse_date_var(self.end_var.get(), date.today())
        if end_dt < start_dt:
            start_dt = end_dt
            self.start_var.set(start_dt.isoformat())
            self.start_picker.set_date(start_dt)
        self._sync_date_picker_limits()

    def on_period_selected(self, _event: tk.Event) -> None:
        label = self.period_var.get().strip()
        month_map = {
            "1个月": 1,
            "半年": 6,
            "1年": 12,
            "2年": 24,
        }
        months = month_map.get(label)
        if months is None:
            return
        self.apply_quick_date_range(months)

    def _add_months(self, base: date, months: int) -> date:
        month_index = (base.month - 1) + months
        year = base.year + (month_index // 12)
        month = (month_index % 12) + 1
        max_day = calendar.monthrange(year, month)[1]
        day = min(base.day, max_day)
        return date(year, month, day)

    def apply_quick_date_range(self, months: int) -> None:
        end_dt = date.today()
        start_dt = self._add_months(end_dt, -months)
        self.start_var.set(start_dt.isoformat())
        self.end_var.set(end_dt.isoformat())
        self.start_picker.set_date(start_dt)
        self.end_picker.set_date(end_dt)
        self._sync_date_picker_limits()

    def refresh_query_suggestions(self, text: str) -> None:
        text = text.strip()
        if not text:
            recs = []
        elif text.isdigit():
            recs = self.master.search(text, limit=20)
            if not recs:
                recs = []
        else:
            recs = self.master.search(text, limit=20)

        self.query_candidate_symbols = [rec.symbol for rec in recs]
        self.query_candidate_displays = []
        self.query_display_to_symbol.clear()
        for rec in recs:
            display = f"{rec.symbol} {rec.name} {rec.pinyin}"
            self.query_candidate_displays.append(display)
            self.query_display_to_symbol[display] = rec.symbol
        self.query_popup_list.delete(0, tk.END)
        for display in self.query_candidate_displays:
            self.query_popup_list.insert(tk.END, display)

    def on_query_input(self, _event: tk.Event) -> None:
        text = self._query_input_text()
        self.refresh_query_suggestions(text)
        if len(text.strip()) >= 2 and self.query_candidate_displays:
            self.root.after(10, self._show_query_popup)
        else:
            self._hide_query_popup()

    def on_query_enter(self, _event: tk.Event) -> str:
        if self.query_popup.winfo_viewable() and self.query_popup_list.size() > 0:
            self._pick_current_query_candidate()
            return "break"
        self.add_query_from_input()
        return "break"

    def on_query_escape(self, _event: tk.Event) -> str:
        self._hide_query_popup()
        return "break"

    def on_query_down(self, _event: tk.Event) -> str:
        self._move_query_popup_selection(1)
        return "break"

    def on_query_up(self, _event: tk.Event) -> str:
        self._move_query_popup_selection(-1)
        return "break"

    def _show_query_popup(self) -> None:
        if not self.query_candidate_displays:
            self._hide_query_popup()
            return

        self.query_popup.update_idletasks()
        x = self.query_entry.winfo_rootx()
        y = self.query_entry.winfo_rooty() + self.query_entry.winfo_height() + 2
        width = self.query_entry.winfo_width()
        height = min(max(len(self.query_candidate_displays), 1), 8) * 22 + 4
        self.query_popup.geometry(f"{width}x{height}+{x}+{y}")
        self.query_popup.deiconify()
        self.query_popup.lift()
        self._set_query_popup_selection(0)
        self.query_entry.focus_set()

    def _hide_query_popup(self) -> None:
        if hasattr(self, "query_popup"):
            self.query_popup.withdraw()

    def on_query_popup_pick(self, _event: tk.Event) -> None:
        self._pick_current_query_candidate()

    def _pick_current_query_candidate(self) -> None:
        idx = self.query_popup_list.curselection()
        if not idx:
            if self.query_popup_list.size() == 0:
                return
            self._set_query_popup_selection(0)
            idx = self.query_popup_list.curselection()
            if not idx:
                return
        self.query_var.set(self.query_popup_list.get(idx[0]))
        self.add_query_from_input()

    def _move_query_popup_selection(self, delta: int) -> None:
        if not self.query_candidate_displays:
            return
        if not self.query_popup.winfo_viewable():
            self._show_query_popup()
            return

        current = self.query_popup_list.curselection()
        if current:
            index = current[0] + delta
        else:
            index = 0 if delta > 0 else self.query_popup_list.size() - 1

        index = max(0, min(index, self.query_popup_list.size() - 1))
        self._set_query_popup_selection(index)

    def _set_query_popup_selection(self, index: int) -> None:
        if self.query_popup_list.size() == 0:
            return
        self.query_popup_list.selection_clear(0, tk.END)
        self.query_popup_list.selection_set(index)
        self.query_popup_list.activate(index)
        self.query_popup_list.see(index)

    def add_query_from_input(self) -> None:
        text = self._query_input_text()
        candidate_symbol = ""
        if text in self.query_display_to_symbol:
            candidate_symbol = self.query_display_to_symbol[text]
        elif self.query_candidate_symbols:
            candidate_symbol = self.query_candidate_symbols[0]
        elif text.isdigit():
            candidate_symbol = text.zfill(6) if len(text) <= 6 else text

        if not candidate_symbol:
            self.status_var.set("未匹配到可加入的代码")
            return

        if candidate_symbol not in self.selected_queries:
            self.selected_queries.append(candidate_symbol)
            self._refresh_selected_queries_list()
        self.query_var.set("")
        self.refresh_query_suggestions("")
        self._hide_query_popup()
        self._apply_query_placeholder()
        self.query_entry.focus_set()

    def remove_selected_queries(self) -> None:
        selected = list(self.query_selected_list.curselection())
        if not selected:
            return
        for i in reversed(selected):
            value = self.query_selected_list.get(i)
            if " " in value:
                symbol = value.split(" ", 1)[0]
            else:
                symbol = value
            self.query_selected_list.delete(i)
            if symbol in self.selected_queries:
                self.selected_queries.remove(symbol)
        self._refresh_selected_queries_list()

    def clear_selected_queries(self) -> None:
        self.selected_queries.clear()
        self._refresh_selected_queries_list()

    def _refresh_selected_queries_list(self) -> None:
        self.query_selected_list.delete(0, tk.END)
        for symbol in self.selected_queries:
            rec = self.master.get(symbol)
            if rec is None:
                self.query_selected_list.insert(tk.END, symbol)
            else:
                self.query_selected_list.insert(tk.END, f"{rec.symbol} {rec.name}")

    def refresh_industry_checkboxes(self) -> None:
        for child in self.industry_inner.winfo_children():
            child.destroy()

        for idx, item in enumerate(self.industry_options):
            row = idx // 2
            col = idx % 2
            ttk.Checkbutton(
                self.industry_inner,
                text=item,
                variable=self.industry_vars[item],
            ).grid(row=row, column=col, sticky=tk.W, padx=6, pady=4)

    def clear_selected_industries(self) -> None:
        for var in self.industry_vars.values():
            var.set(False)
        self.refresh_industry_checkboxes()

    def _selected_industries(self) -> tuple[str, ...]:
        return tuple(name for name, var in self.industry_vars.items() if var.get())

    def search_clicked(self) -> None:
        if self._query_input_text():
            self.add_query_from_input()

        if not self.selected_queries:
            messagebox.showwarning("缺少股票代码", "检索前请至少添加 1 条已选股票")
            self.status_var.set("请先添加至少 1 条已选股票")
            return

        try:
            start = datetime.strptime(self.start_var.get().strip(), "%Y-%m-%d").date()
            end = datetime.strptime(self.end_var.get().strip(), "%Y-%m-%d").date()
        except ValueError:
            messagebox.showerror("日期格式错误", "请输入 YYYY-MM-DD 格式日期")
            return

        if end < start:
            messagebox.showerror("日期范围错误", "结束日期不能早于开始日期")
            return

        flt = SearchFilter(
            start_date=start,
            end_date=end,
            queries=tuple(self.selected_queries),
            keyword="" if self.keyword_var.get().strip() == self.KEYWORD_PLACEHOLDER else self.keyword_var.get().strip(),
            plates=self._selected_plates(),
            industries=self._selected_industries(),
            categories=self._selected_categories(),
            page_size=30,
            max_records=500,
        )

        self.status_var.set("正在检索，请稍候...")
        threading.Thread(target=self._run_search, args=(flt,), daemon=True).start()

    def _run_search(self, flt: SearchFilter) -> None:
        try:
            rows = self.search_service.search(flt)
            self.root.after(0, lambda: self._render_results(rows))
        except Exception as exc:  # noqa: BLE001
            self.root.after(0, lambda: messagebox.showerror("检索失败", str(exc)))
            self.root.after(0, lambda: self.status_var.set("检索失败"))

    def _render_results(self, rows: list[AnnouncementItem]) -> None:
        self.results = rows
        self.checked_result_ids.clear()
        for item in self.tree.get_children():
            self.tree.delete(item)
        for idx, row in enumerate(rows):
            self.tree.insert(
                "",
                tk.END,
                iid=str(idx),
                values=("☐", row.announcement_time, row.sec_code, row.sec_name, row.title),
            )
        self.status_var.set(f"检索完成，共 {len(rows)} 条")

    def on_tree_click(self, event: tk.Event) -> str | None:
        region = self.tree.identify("region", event.x, event.y)
        column = self.tree.identify_column(event.x)
        if region != "cell" or column != "#1":
            return None

        row_id = self.tree.identify_row(event.y)
        if not row_id:
            return "break"

        if row_id in self.checked_result_ids:
            self.checked_result_ids.remove(row_id)
            self.tree.set(row_id, "sel", "☐")
        else:
            self.checked_result_ids.add(row_id)
            self.tree.set(row_id, "sel", "☑")
        return "break"

    def select_all_results(self) -> None:
        for iid in self.tree.get_children():
            self.checked_result_ids.add(str(iid))
            self.tree.set(iid, "sel", "☑")

    def invert_result_selection(self) -> None:
        for iid in self.tree.get_children():
            if str(iid) in self.checked_result_ids:
                self.checked_result_ids.remove(str(iid))
                self.tree.set(iid, "sel", "☐")
            else:
                self.checked_result_ids.add(str(iid))
                self.tree.set(iid, "sel", "☑")

    def clear_result_selection(self) -> None:
        self.checked_result_ids.clear()
        for iid in self.tree.get_children():
            self.tree.set(iid, "sel", "☐")

    def download_selected(self) -> None:
        selected_ids = list(self.checked_result_ids)
        if not selected_ids:
            messagebox.showinfo("提示", "请先在结果表中选择需要下载的公告")
            return

        picked: list[AnnouncementItem] = [self.results[int(iid)] for iid in sorted(selected_ids, key=int)]
        if len(picked) > 50:
            messagebox.showwarning("超出限制", "单次下载最多50份，将自动截断为前50份")
            picked = picked[:50]

        self._start_download(picked)

    def download_top_50(self) -> None:
        if not self.results:
            messagebox.showinfo("提示", "请先检索")
            return
        batch, remain = self.download_service.split_batch(self.results, max_count=50)
        if remain > 0:
            self.status_var.set(f"当前结果 {len(self.results)} 条，本次下载前50条，剩余 {remain} 条")
        self._start_download(batch)

    def _start_download(self, rows: list[AnnouncementItem]) -> None:
        if not rows:
            messagebox.showinfo("提示", "没有可下载记录")
            return
        self.status_var.set(f"开始下载，共 {len(rows)} 份...")
        threading.Thread(target=self._run_download, args=(rows,), daemon=True).start()

    def _run_download(self, rows: list[AnnouncementItem]) -> None:
        done, errors = self.download_service.download(rows)

        def _done() -> None:
            if errors:
                self.status_var.set(f"下载完成，成功 {done}，失败 {len(errors)}")
                messagebox.showwarning("部分下载失败", "\n".join(errors[:8]))
            else:
                self.status_var.set(f"下载完成，成功 {done}")
                messagebox.showinfo("下载完成", f"成功下载 {done} 份公告")

        self.root.after(0, _done)

    def open_pdf_extractor(self) -> None:
        if self.extractor_window and self.extractor_window.window.winfo_exists():
            self.extractor_window.window.deiconify()
            self.extractor_window.window.lift()
            self.extractor_window.window.focus_force()
            return

        self.extractor_window = PdfExtractorWindow(self.root)


def main() -> None:
    DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)
    root = tk.Tk()
    MainApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
