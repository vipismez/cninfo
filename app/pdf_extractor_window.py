from __future__ import annotations

from datetime import datetime
import os
from pathlib import Path
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from tkinter.scrolledtext import ScrolledText

from app.config import DOWNLOAD_DIR
from app.services.pdf_table_extractor_service import ExtractionSummary, PdfTableExtractorService


class PdfExtractorWindow:
    """PDF 表格提取独立窗口。"""

    def __init__(self, parent: tk.Tk) -> None:
        self.parent = parent
        self.window = tk.Toplevel(parent)
        self.window.title("PDF表格提取工具")
        self.window.geometry("980x620")
        self.window.minsize(860, 520)

        self.source_var = tk.StringVar(value=str(DOWNLOAD_DIR))
        self.target_var = tk.StringVar(value=str(DOWNLOAD_DIR))
        self.progress_var = tk.StringVar(value="等待开始")

        self._worker: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._service = PdfTableExtractorService()

        self._build_ui()
        self.window.protocol("WM_DELETE_WINDOW", self.on_close)

    def _build_ui(self) -> None:
        """构建目录配置、控制按钮与滚动日志区域。"""

        root = ttk.Frame(self.window, padding=12)
        root.pack(fill=tk.BOTH, expand=True)
        root.columnconfigure(0, weight=1)
        root.rowconfigure(1, weight=1)

        path_frame = ttk.LabelFrame(root, text="提取配置", padding=10)
        path_frame.grid(row=0, column=0, sticky=tk.EW)
        path_frame.columnconfigure(1, weight=1)

        ttk.Label(path_frame, text="源文件目录").grid(row=0, column=0, sticky=tk.W)
        ttk.Entry(path_frame, textvariable=self.source_var).grid(row=0, column=1, sticky=tk.EW, padx=(8, 8))
        ttk.Button(path_frame, text="浏览", command=self.pick_source_dir).grid(row=0, column=2)

        ttk.Label(path_frame, text="目标目录").grid(row=1, column=0, sticky=tk.W, pady=(8, 0))
        ttk.Entry(path_frame, textvariable=self.target_var).grid(row=1, column=1, sticky=tk.EW, padx=(8, 8), pady=(8, 0))
        ttk.Button(path_frame, text="浏览", command=self.pick_target_dir).grid(row=1, column=2, pady=(8, 0))

        op = ttk.Frame(path_frame)
        op.grid(row=2, column=0, columnspan=3, sticky=tk.W, pady=(10, 0))
        self.start_btn = ttk.Button(op, text="开始提取", command=self.start_extract)
        self.start_btn.pack(side=tk.LEFT)
        self.stop_btn = ttk.Button(op, text="停止", command=self.stop_extract, state=tk.DISABLED)
        self.stop_btn.pack(side=tk.LEFT, padx=8)
        ttk.Button(op, text="清空日志", command=self.clear_logs).pack(side=tk.LEFT, padx=8)
        ttk.Button(op, text="目标=源目录", command=self.use_same_target).pack(side=tk.LEFT, padx=8)
        ttk.Button(op, text="打开目标目录", command=self.open_target_dir).pack(side=tk.LEFT, padx=8)

        ttk.Label(path_frame, textvariable=self.progress_var).grid(row=3, column=0, columnspan=3, sticky=tk.W, pady=(8, 0))

        log_frame = ttk.LabelFrame(root, text="进度日志", padding=10)
        log_frame.grid(row=1, column=0, sticky=tk.NSEW, pady=(10, 0))
        log_frame.columnconfigure(0, weight=1)
        log_frame.rowconfigure(0, weight=1)

        self.log_text = ScrolledText(log_frame, wrap=tk.WORD, state=tk.DISABLED)
        self.log_text.grid(row=0, column=0, sticky=tk.NSEW)

    def pick_source_dir(self) -> None:
        selected = filedialog.askdirectory(title="选择源文件目录", initialdir=self.source_var.get())
        if selected:
            self.source_var.set(selected)

    def pick_target_dir(self) -> None:
        selected = filedialog.askdirectory(title="选择目标目录", initialdir=self.target_var.get())
        if selected:
            self.target_var.set(selected)

    def use_same_target(self) -> None:
        self.target_var.set(self.source_var.get())

    def open_target_dir(self) -> None:
        target = Path(self.target_var.get().strip())
        if not target.exists():
            messagebox.showwarning("目录不存在", "目标目录不存在")
            return
        os.startfile(target)  # type: ignore[attr-defined]

    def clear_logs(self) -> None:
        self.log_text.configure(state=tk.NORMAL)
        self.log_text.delete("1.0", tk.END)
        self.log_text.configure(state=tk.DISABLED)

    def start_extract(self) -> None:
        """启动后台提取任务，避免阻塞 UI 线程。"""

        if self._worker and self._worker.is_alive():
            messagebox.showinfo("提示", "任务正在执行中")
            return

        source = Path(self.source_var.get().strip())
        target = Path(self.target_var.get().strip())

        if not source.exists() or not source.is_dir():
            messagebox.showerror("目录错误", "源文件目录不存在")
            return

        target.mkdir(parents=True, exist_ok=True)
        self._stop_event.clear()
        self._set_running(True)
        self._log("开始提取任务")

        def _run() -> None:
            summary = self._service.process_directory(
                source_dir=source,
                target_dir=target,
                stop_event=self._stop_event,
                log=self._thread_log,
                progress=self._thread_progress,
            )
            self.window.after(0, lambda: self._on_done(summary))

        self._worker = threading.Thread(target=_run, daemon=True)
        self._worker.start()

    def stop_extract(self) -> None:
        """请求软停止：当前文件结束后退出。"""

        self._stop_event.set()
        self._log("已请求停止，正在等待当前文件处理结束...")

    def _set_running(self, running: bool) -> None:
        self.start_btn.configure(state=tk.DISABLED if running else tk.NORMAL)
        self.stop_btn.configure(state=tk.NORMAL if running else tk.DISABLED)

    def _thread_log(self, msg: str) -> None:
        """将后台日志安全回投到 UI 线程。"""

        self.window.after(0, lambda: self._log(msg))

    def _thread_progress(self, done: int, total: int) -> None:
        self.window.after(0, lambda: self.progress_var.set(f"处理中: {done}/{total}"))

    def _log(self, message: str) -> None:
        stamp = datetime.now().strftime("%H:%M:%S")
        self.log_text.configure(state=tk.NORMAL)
        self.log_text.insert(tk.END, f"[{stamp}] {message}\n")
        self.log_text.see(tk.END)
        self.log_text.configure(state=tk.DISABLED)

    def _on_done(self, summary: ExtractionSummary) -> None:
        self._set_running(False)
        if summary.total == 0:
            self.progress_var.set("未找到PDF文件")
            self._log("源目录中未找到PDF文件")
            return

        self.progress_var.set(
            f"完成: 总数{summary.total}，成功{summary.success}，失败{summary.failed}，跳过文件{summary.skipped}，跳过表格{summary.skipped_tables}"
        )
        if summary.stopped:
            self._log("任务已停止")
        self._log(
            f"任务结束，总数={summary.total}，成功={summary.success}，失败={summary.failed}，跳过文件={summary.skipped}，跳过表格={summary.skipped_tables}"
        )

    def on_close(self) -> None:
        if self._worker and self._worker.is_alive():
            if not messagebox.askyesno("确认", "任务仍在执行，确认关闭窗口吗？"):
                return
            self._stop_event.set()
        self.window.destroy()
