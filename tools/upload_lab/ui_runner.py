from __future__ import annotations

import json
import os
import queue
import threading
import traceback
from pathlib import Path

import tkinter as tk
from tkinter import filedialog, messagebox, ttk

try:
    from batch_scan import BASE_DIR, finalize_manifest, run_batch_scan
    from extract_contract import batch_convert_doc_to_docx, extract
    from playwright_uploader import (
        NamDinhUploaderSession,
        finalize_uploaded_records,
        load_upload_queue,
        load_uploader_settings,
        probe_playwright_runtime,
    )
except ImportError:  # pragma: no cover - fallback when imported as package
    from tools.upload_lab.batch_scan import BASE_DIR, finalize_manifest, run_batch_scan
    from tools.upload_lab.extract_contract import batch_convert_doc_to_docx, extract
    from tools.upload_lab.playwright_uploader import (
        NamDinhUploaderSession,
        finalize_uploaded_records,
        load_upload_queue,
        load_uploader_settings,
        probe_playwright_runtime,
    )


APP_TITLE = "Batch Scan Hop Dong Nam Dinh"
DATE_PLACEHOLDER = "dd/mm/yyyy"


class UploadWorker(threading.Thread):
    def __init__(self, app: "App"):
        super().__init__(daemon=True)
        self.app = app
        self.command_queue: queue.Queue[tuple[str, object | None]] = queue.Queue()
        self.stop_event = threading.Event()
        self.runner: NamDinhUploaderSession | None = None

    def enqueue_prepare(self, manifest_path: Path) -> None:
        self.command_queue.put(("prepare", manifest_path))

    def request_stop(self) -> None:
        self.stop_event.set()

    def shutdown(self) -> None:
        self.command_queue.put(("shutdown", None))

    def _ui_log(self, message: str) -> None:
        self.app.after(0, lambda: self.app._append_log(message))

    def run(self) -> None:
        try:
            while True:
                command, payload = self.command_queue.get()
                try:
                    if command == "shutdown":
                        break
                    if command == "prepare":
                        self.stop_event.clear()
                        if self.runner is None:
                            settings = load_uploader_settings(BASE_DIR)
                            self.runner = NamDinhUploaderSession(
                                settings,
                                working_dir=BASE_DIR,
                                log_callback=self._ui_log,
                            )
                        summary = self.runner.prepare_manifest(Path(payload), self.stop_event)
                        self.app.after(0, lambda summary=summary: self.app._on_upload_prepare_done(summary))
                except Exception as exc:  # pragma: no cover - UI worker plumbing
                    tb = traceback.format_exc()
                    self.app.after(0, lambda exc=exc, tb=tb: self.app._on_upload_prepare_error(exc, tb))
                finally:
                    self.command_queue.task_done()
        finally:
            if self.runner is not None:
                self.runner.close()


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(APP_TITLE)
        self.geometry("1120x820")
        self.minsize(920, 680)
        self._busy = False
        self.upload_status_var = tk.StringVar(value="Chua chon manifest.")
        self.upload_manifest_var = tk.StringVar()
        self.batch_folder_var = tk.StringVar()
        self.modified_since_var = tk.StringVar()
        self.full_rescan_var = tk.BooleanVar(value=False)
        self.batch_status_var = tk.StringVar(value="San sang.")
        self.batch_detail_var = tk.StringVar(value="Chua chay batch scan.")
        self.batch_file_var = tk.StringVar(value="")
        self.batch_progress_var = tk.DoubleVar(value=0.0)
        self.extract_file_var = tk.StringVar()
        self.upload_capability_var = tk.StringVar()
        self._last_upload_summary = None
        self.playwright_ready, self.playwright_message = probe_playwright_runtime()
        self.upload_capability_var.set(self.playwright_message)
        self.upload_worker = UploadWorker(self)
        self.upload_worker.start()
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self._build_ui()

    def _build_ui(self) -> None:
        container = ttk.Frame(self, padding=16)
        container.pack(fill="both", expand=True)

        title = ttk.Label(
            container,
            text="Cong cu scan / extract / upload ho so Nam Dinh",
            font=("Segoe UI", 15, "bold"),
        )
        title.pack(anchor="w")

        desc = ttk.Label(
            container,
            text="Batch scan folder, trich xuat 1 file, va chuan bi tab dry-run Playwright tren cung mot giao dien.",
        )
        desc.pack(anchor="w", pady=(4, 12))

        notebook = ttk.Notebook(container)
        notebook.pack(fill="both", expand=True)

        self.batch_tab = ttk.Frame(notebook, padding=12)
        self.extract_tab = ttk.Frame(notebook, padding=12)
        self.upload_tab = ttk.Frame(notebook, padding=12)
        notebook.add(self.batch_tab, text="Batch Scan Folder")
        notebook.add(self.extract_tab, text="Trich Xuat 1 File")
        notebook.add(self.upload_tab, text="Upload Playwright")

        self._build_batch_tab()
        self._build_extract_tab()
        self._build_upload_tab()

        bottom = ttk.Frame(container)
        bottom.pack(fill="both", expand=True, pady=(12, 0))

        log_label = ttk.Label(bottom, text="Ket qua / log", font=("Segoe UI", 10, "bold"))
        log_label.pack(anchor="w")

        self.log_text = tk.Text(bottom, height=14, wrap="word")
        self.log_text.pack(fill="both", expand=True, pady=(6, 0))
        self.log_text.configure(state="disabled")

    def _build_batch_tab(self) -> None:
        ttk.Label(self.batch_tab, text="Folder tong ho so").grid(row=0, column=0, sticky="w")
        ttk.Entry(self.batch_tab, textvariable=self.batch_folder_var, width=80).grid(
            row=1, column=0, sticky="ew", padx=(0, 8)
        )
        ttk.Button(self.batch_tab, text="Browse Folder", command=self._browse_batch_folder).grid(
            row=1, column=1, sticky="ew"
        )

        ttk.Label(self.batch_tab, text="Modified since (YYYY-MM-DD hoac DD/MM/YYYY, co the bo trong)").grid(
            row=2, column=0, sticky="w", pady=(12, 0)
        )
        self.modified_since_entry = tk.Entry(self.batch_tab, textvariable=self.modified_since_var, width=30)
        self.modified_since_entry.grid(row=3, column=0, sticky="w")
        self._set_modified_since_placeholder()
        self.modified_since_entry.bind("<FocusIn>", self._handle_modified_since_focus_in)
        self.modified_since_entry.bind("<FocusOut>", self._handle_modified_since_focus_out)

        ttk.Checkbutton(
            self.batch_tab,
            text="Full rescan (bo qua moc ngay)",
            variable=self.full_rescan_var,
        ).grid(row=4, column=0, sticky="w", pady=(10, 0))

        btn_row = ttk.Frame(self.batch_tab)
        btn_row.grid(row=5, column=0, columnspan=2, sticky="w", pady=(16, 0))
        ttk.Button(
            btn_row,
            text="Chay Batch Scan",
            command=self._run_batch_from_ui,
        ).pack(side="left")
        ttk.Button(
            btn_row,
            text="Chuyen .doc → .docx (1 lan)",
            command=self._run_convert_doc_from_ui,
        ).pack(side="left", padx=(12, 0))

        note = ttk.Label(
            self.batch_tab,
            text="Batch scan se ghi output vao tools/upload_lab/output, manifest vao tools/upload_lab/runs. "
                 "Nut 'Chuyen .doc → .docx' chi can chay 1 lan — file .doc goc giu nguyen.",
        )
        note.grid(row=6, column=0, columnspan=2, sticky="w", pady=(12, 0))

        self.batch_progress = ttk.Progressbar(
            self.batch_tab,
            variable=self.batch_progress_var,
            maximum=100,
            mode="determinate",
        )
        self.batch_progress.grid(row=7, column=0, columnspan=2, sticky="ew", pady=(16, 0))
        ttk.Label(
            self.batch_tab,
            textvariable=self.batch_status_var,
            foreground="#0b5394",
        ).grid(row=8, column=0, columnspan=2, sticky="w", pady=(8, 0))
        ttk.Label(
            self.batch_tab,
            textvariable=self.batch_detail_var,
            wraplength=860,
        ).grid(row=9, column=0, columnspan=2, sticky="w", pady=(4, 0))
        ttk.Label(
            self.batch_tab,
            textvariable=self.batch_file_var,
            wraplength=860,
            foreground="#666666",
        ).grid(row=10, column=0, columnspan=2, sticky="w", pady=(4, 0))

        self.batch_tab.columnconfigure(0, weight=1)

    def _build_extract_tab(self) -> None:
        ttk.Label(self.extract_tab, text="File hop dong .doc hoac .docx").grid(row=0, column=0, sticky="w")
        ttk.Entry(self.extract_tab, textvariable=self.extract_file_var, width=80).grid(
            row=1, column=0, sticky="ew", padx=(0, 8)
        )
        ttk.Button(self.extract_tab, text="Browse File", command=self._browse_extract_file).grid(
            row=1, column=1, sticky="ew"
        )

        ttk.Button(
            self.extract_tab,
            text="Trich Xuat 1 File",
            command=self._run_extract_from_ui,
        ).grid(row=2, column=0, sticky="w", pady=(16, 0))

        note = ttk.Label(
            self.extract_tab,
            text="JSON se duoc luu ngay canh file goc voi hau to *_extracted.json.",
        )
        note.grid(row=3, column=0, columnspan=2, sticky="w", pady=(12, 0))

        self.extract_tab.columnconfigure(0, weight=1)

    def _build_upload_tab(self) -> None:
        ttk.Label(self.upload_tab, text="Manifest batch scan").grid(row=0, column=0, sticky="w")
        ttk.Entry(self.upload_tab, textvariable=self.upload_manifest_var, width=90).grid(
            row=1, column=0, sticky="ew", padx=(0, 8)
        )
        ttk.Button(self.upload_tab, text="Browse Manifest", command=self._browse_manifest).grid(
            row=1, column=1, sticky="ew"
        )

        button_row = ttk.Frame(self.upload_tab)
        button_row.grid(row=2, column=0, columnspan=2, sticky="w", pady=(12, 0))
        self.refresh_upload_button = ttk.Button(button_row, text="Refresh Queue", command=self._refresh_upload_queue)
        self.refresh_upload_button.pack(side="left")
        self.start_upload_button = ttk.Button(button_row, text="Start Dry-run", command=self._start_upload_prepare)
        self.start_upload_button.pack(side="left", padx=(8, 0))
        self.stop_upload_button = ttk.Button(button_row, text="Stop", command=self._stop_upload_prepare)
        self.stop_upload_button.pack(side="left", padx=(8, 0))
        self.finalize_upload_button = ttk.Button(
            button_row,
            text="Finalize Selected",
            command=self._finalize_selected_upload_records,
        )
        self.finalize_upload_button.pack(
            side="left", padx=(8, 0)
        )

        ttk.Label(
            self.upload_tab,
            textvariable=self.upload_status_var,
            foreground="#0b5394",
        ).grid(row=3, column=0, columnspan=2, sticky="w", pady=(12, 0))
        ttk.Label(
            self.upload_tab,
            textvariable=self.upload_capability_var,
            wraplength=860,
            foreground="#a61c00" if not self.playwright_ready else "#38761d",
        ).grid(row=4, column=0, columnspan=2, sticky="w", pady=(6, 0))

        columns = ("record_id", "contract_no", "status", "missing", "source_file")
        self.upload_tree = ttk.Treeview(
            self.upload_tab,
            columns=columns,
            show="headings",
            selectmode="extended",
            height=12,
        )
        headings = {
            "record_id": "Record ID",
            "contract_no": "So cong chung",
            "status": "Trang thai",
            "missing": "Missing/Partial",
            "source_file": "File goc",
        }
        widths = {"record_id": 80, "contract_no": 150, "status": 140, "missing": 180, "source_file": 520}
        for column in columns:
            self.upload_tree.heading(column, text=headings[column])
            self.upload_tree.column(column, width=widths[column], anchor="w")
        self.upload_tree.grid(row=5, column=0, columnspan=2, sticky="nsew", pady=(8, 0))
        self.upload_tree.bind("<Double-1>", self._open_upload_source_file)

        scrollbar = ttk.Scrollbar(self.upload_tab, orient="vertical", command=self.upload_tree.yview)
        scrollbar.grid(row=5, column=2, sticky="ns", pady=(8, 0))
        self.upload_tree.configure(yscrollcommand=scrollbar.set)

        note = ttk.Label(
            self.upload_tab,
            text="Dry-run se mo tab moi cho tung ho so, dung truoc nut Luu, roi chuyen sang ho so tiep theo den khi dat gioi han tab. Tool khong upload file hop dong len web. Double-click vao 1 dong de mo file goc va doi chieu nhanh.",
        )
        note.grid(row=6, column=0, columnspan=2, sticky="w", pady=(12, 0))

        self.upload_tab.columnconfigure(0, weight=1)
        self.upload_tab.rowconfigure(5, weight=1)
        self._apply_upload_capability_state()

    def _browse_batch_folder(self) -> None:
        selected = filedialog.askdirectory(title="Chon folder tong ho so")
        if selected:
            self.batch_folder_var.set(selected)

    def _browse_extract_file(self) -> None:
        selected = filedialog.askopenfilename(
            title="Chon file hop dong .doc hoac .docx",
            filetypes=[("Word files", ("*.doc", "*.docx"))],
        )
        if selected:
            self.extract_file_var.set(selected)

    def _browse_manifest(self) -> None:
        selected = filedialog.askopenfilename(
            title="Chon manifest batch scan",
            initialdir=str(BASE_DIR / "runs"),
            filetypes=[("JSON files", "*.json")],
        )
        if selected:
            self.upload_manifest_var.set(selected)
            self._refresh_upload_queue()

    def _set_busy(self, value: bool) -> None:
        self._busy = value
        self.configure(cursor="")

    def _set_modified_since_placeholder(self) -> None:
        self.modified_since_var.set(DATE_PLACEHOLDER)
        self.modified_since_entry.configure(foreground="#888888")

    def _handle_modified_since_focus_in(self, _event=None) -> None:
        if self.modified_since_var.get().strip().lower() == DATE_PLACEHOLDER:
            self.modified_since_var.set("")
            self.modified_since_entry.configure(foreground="#000000")

    def _handle_modified_since_focus_out(self, _event=None) -> None:
        if not self.modified_since_var.get().strip():
            self._set_modified_since_placeholder()

    def _append_log(self, text: str) -> None:
        self.log_text.configure(state="normal")
        self.log_text.insert("end", text.rstrip() + "\n")
        self.log_text.see("end")
        self.log_text.configure(state="disabled")

    def _apply_upload_capability_state(self) -> None:
        if self.playwright_ready:
            self.start_upload_button.configure(state="normal")
            self.stop_upload_button.configure(state="normal")
            return
        self.start_upload_button.configure(state="disabled")
        self.stop_upload_button.configure(state="disabled")

    def _reset_batch_progress(self) -> None:
        self.batch_progress_var.set(0.0)
        self.batch_status_var.set("San sang.")
        self.batch_detail_var.set("Chua chay batch scan.")
        self.batch_file_var.set("")

    def _format_seconds(self, seconds: float | None) -> str:
        if seconds is None:
            return "--"
        total_seconds = max(0, int(round(seconds)))
        minutes, secs = divmod(total_seconds, 60)
        hours, minutes = divmod(minutes, 60)
        if hours:
            return f"{hours:02d}:{minutes:02d}:{secs:02d}"
        return f"{minutes:02d}:{secs:02d}"

    def _update_batch_progress(self, snapshot: dict) -> None:
        stage = str(snapshot.get("stage") or "")
        step = str(snapshot.get("step") or "")
        processed = int(snapshot.get("processed_files") or 0)
        total = int(snapshot.get("total_files") or 0)
        stats = dict(snapshot.get("stats") or {})
        current_file = str(snapshot.get("current_file") or "")
        last_outcome = str(snapshot.get("last_outcome") or "")
        last_contract_no = str(snapshot.get("last_contract_no") or "")
        rate = float(snapshot.get("files_per_second") or 0.0)
        eta_seconds = snapshot.get("eta_seconds")
        elapsed_seconds = float(snapshot.get("elapsed_seconds") or 0.0)

        progress_value = (processed / total * 100.0) if total else 0.0
        if stage == "done" and total:
            progress_value = 100.0
        self.batch_progress_var.set(progress_value)

        if stage == "indexing":
            self.batch_status_var.set("[BATCH] Dang dem file va khoi tao tien do...")
            self.batch_detail_var.set(
                f"word_files={stats.get('total_docx_files', 0)} | supported={stats.get('total_supported_files', 0)}"
            )
            self.batch_file_var.set("")
            return

        status_parts = [
            f"processed={processed}/{total or 0}",
            f"candidates={stats.get('candidates_found', 0)}",
            f"extract_success={stats.get('extract_success', 0)}",
            f"partial={stats.get('extract_partial', 0)}",
            f"failed={stats.get('extract_failed', 0)}",
            f"speed={rate:.2f} file/s" if rate > 0 else "speed=--",
            f"eta={self._format_seconds(eta_seconds)}",
            f"elapsed={self._format_seconds(elapsed_seconds)}",
        ]

        if stage == "done":
            self.batch_status_var.set("[BATCH] Hoan tat | " + " | ".join(status_parts))
        elif step == "extract":
            self.batch_status_var.set("[BATCH] Dang trich xuat | " + " | ".join(status_parts))
        else:
            self.batch_status_var.set("[BATCH] Dang quet | " + " | ".join(status_parts))

        outcome_text = ""
        if last_outcome:
            outcome_text = last_outcome.replace("_", " ")
            if last_contract_no:
                outcome_text += f" | so={last_contract_no}"
        self.batch_detail_var.set(outcome_text or "Dang xu ly...")
        self.batch_file_var.set(current_file)

    def _run_in_thread(self, target, *, on_error_prefix: str) -> None:
        if self._busy:
            return

        self._set_busy(True)

        def worker():
            try:
                target()
            except Exception as exc:  # pragma: no cover - UI thread handling
                error_text = f"{on_error_prefix}: {exc}\n{traceback.format_exc()}"
                self.after(0, lambda: self._append_log(error_text))
                self.after(0, lambda: messagebox.showerror(APP_TITLE, str(exc)))
            finally:
                self.after(0, lambda: self._set_busy(False))

        threading.Thread(target=worker, daemon=True).start()

    def _run_batch_from_ui(self) -> None:
        folder_value = self.batch_folder_var.get().strip()
        if not folder_value:
            messagebox.showwarning(APP_TITLE, "Vui long chon folder tong ho so.")
            return

        folder_path = Path(folder_value)
        if not folder_path.exists() or not folder_path.is_dir():
            messagebox.showwarning(APP_TITLE, "Folder da chon khong hop le.")
            return

        modified_since = self.modified_since_var.get().strip()
        if modified_since.lower() == DATE_PLACEHOLDER:
            modified_since = ""
        modified_since = modified_since or None
        full_rescan = bool(self.full_rescan_var.get())
        self._reset_batch_progress()
        self.batch_status_var.set("[BATCH] Dang dem file va khoi tao tien do...")
        self.batch_detail_var.set("Dang chuan bi batch scan...")
        self._append_log(f"[BATCH] Bat dau quet: {folder_path}")

        def run_batch():
            manifest = run_batch_scan(
                folder_path,
                modified_since=modified_since,
                full_rescan=full_rescan,
                working_dir=BASE_DIR,
                progress_callback=lambda snapshot: self.after(0, lambda s=snapshot: self._update_batch_progress(s)),
            )
            manifest_path = finalize_manifest(manifest, BASE_DIR / "runs")
            duration_seconds = float(manifest.get("duration_seconds") or 0.0)
            processed_files = int(manifest["stats"].get("processed_files", 0) or 0)
            avg_speed = (processed_files / duration_seconds) if duration_seconds > 0 and processed_files > 0 else 0.0
            summary = (
                f"[BATCH] Xong. processed={processed_files}/{manifest['stats'].get('total_supported_files', 0)}, "
                f"candidates={manifest['stats']['candidates_found']}, "
                f"extract_success={manifest['stats']['extract_success']}, "
                f"partial={manifest['stats'].get('extract_partial', 0)}, "
                f"extract_failed={manifest['stats']['extract_failed']}, "
                f"skipped_duplicate={manifest['stats']['skipped_duplicate']}, "
                f"ready_for_upload={manifest['stats']['ready_for_upload']}, "
                f"avg_speed={avg_speed:.2f} file/s"
            )
            self.after(0, lambda: self._append_log(summary))
            self.after(0, lambda: self._append_log(f"[BATCH] Manifest: {manifest_path}"))
            self.after(
                0,
                lambda: messagebox.showinfo(
                    APP_TITLE,
                    "Batch scan hoan tat.\n\n"
                    f"Manifest: {manifest_path}\n"
                    f"Output: {BASE_DIR / 'output'}",
                ),
            )

        self._run_in_thread(run_batch, on_error_prefix="[BATCH] Loi")

    def _run_convert_doc_from_ui(self) -> None:
        folder_value = self.batch_folder_var.get().strip()
        if not folder_value:
            messagebox.showwarning(APP_TITLE, "Vui long chon folder tong ho so truoc.")
            return

        folder_path = Path(folder_value)
        if not folder_path.exists() or not folder_path.is_dir():
            messagebox.showwarning(APP_TITLE, "Folder da chon khong hop le.")
            return

        self._append_log(f"[CONVERT] Bat dau: {folder_path}")

        def run_convert():
            stats = batch_convert_doc_to_docx(
                folder_path,
                skip_existing=True,
                log_callback=lambda msg: self.after(0, lambda m=msg: self._append_log(m)),
            )
            summary = (
                f"[CONVERT] Ket qua: converted={stats['converted']}, "
                f"skipped={stats['skipped']}, failed={stats['failed']}"
            )
            self.after(0, lambda: self._append_log(summary))
            self.after(
                0,
                lambda: messagebox.showinfo(
                    APP_TITLE,
                    f"Chuyen doi hoan tat.\n\n"
                    f"Da chuyen: {stats['converted']} file\n"
                    f"Bo qua (da co .docx): {stats['skipped']} file\n"
                    f"Loi: {stats['failed']} file",
                ),
            )

        self._run_in_thread(run_convert, on_error_prefix="[CONVERT] Loi")

    def _run_extract_from_ui(self) -> None:
        file_value = self.extract_file_var.get().strip()
        if not file_value:
            messagebox.showwarning(APP_TITLE, "Vui long chon file .doc hoac .docx.")
            return

        file_path = Path(file_value)
        if not file_path.exists() or file_path.suffix.lower() not in {".doc", ".docx"}:
            messagebox.showwarning(APP_TITLE, "File da chon khong hop le hoac khong phai .doc/.docx.")
            return

        self._append_log(f"[EXTRACT] Bat dau: {file_path}")

        def run_extract():
            payload = extract(file_path)
            json_output = json.dumps(payload, ensure_ascii=False, indent=2)
            output_path = file_path.with_name(f"{file_path.stem}_extracted.json")
            output_path.write_text(json_output, encoding="utf-8")
            contract_no = payload.get("web_form", {}).get("so_cong_chung", "")
            self.after(
                0,
                lambda: self._append_log(
                    f"[EXTRACT] Xong. so_cong_chung={contract_no or '(khong co)'} -> {output_path}"
                ),
            )
            self.after(
                0,
                lambda: messagebox.showinfo(
                    APP_TITLE,
                    "Trich xuat thanh cong.\n\n"
                    f"JSON: {output_path}",
                ),
            )

        self._run_in_thread(run_extract, on_error_prefix="[EXTRACT] Loi")

    def _refresh_upload_queue(self) -> None:
        manifest_value = self.upload_manifest_var.get().strip()
        if not manifest_value:
            self.upload_status_var.set("Chua chon manifest.")
            self._replace_upload_tree([])
            return

        manifest_path = Path(manifest_value)
        if not manifest_path.exists():
            messagebox.showwarning(APP_TITLE, "Manifest da chon khong ton tai.")
            return

        try:
            manifest, records, total_pending = load_upload_queue(manifest_path, working_dir=BASE_DIR)
        except Exception as exc:
            self.upload_status_var.set(f"Loi doc queue: {exc}")
            self._replace_upload_tree([])
            self._append_log(f"[UPLOAD] Loi queue: {exc}")
            return

        rows = []
        for record in records:
            missing = ", ".join(record.missing_fields) if record.missing_fields else ""
            rows.append(
                {
                    "record_id": str(record.record_id),
                    "contract_no": record.contract_no,
                    "status": record.status,
                    "missing": missing,
                    "source_file": str(record.source_file),
                }
            )
        self._replace_upload_tree(rows)
        self.upload_status_var.set(
            f"run_id={manifest['run_id']} | pending={total_pending} | manifest={manifest_path.name}"
        )

    def _replace_upload_tree(self, rows: list[dict]) -> None:
        for item in self.upload_tree.get_children():
            self.upload_tree.delete(item)
        for row in rows:
            self.upload_tree.insert(
                "",
                "end",
                iid=row["record_id"],
                values=(
                    row["record_id"],
                    row["contract_no"],
                    row["status"],
                    row["missing"],
                    row["source_file"],
                ),
            )

    def _open_upload_source_file(self, event=None) -> None:
        row_id = self.upload_tree.identify_row(event.y) if event is not None else ""
        if not row_id:
            selection = self.upload_tree.selection()
            row_id = selection[0] if selection else ""
        if not row_id:
            return

        values = self.upload_tree.item(row_id, "values")
        if not values or len(values) < 5:
            return

        source_path = Path(str(values[4]))
        if not source_path.exists():
            self._append_log(f"[UPLOAD] Khong tim thay file goc: {source_path}")
            messagebox.showwarning(APP_TITLE, f"Khong tim thay file goc:\n{source_path}")
            return

        try:
            os.startfile(str(source_path))
            self._append_log(f"[UPLOAD] Mo file goc: {source_path}")
        except Exception as exc:
            self._append_log(f"[UPLOAD] Khong mo duoc file goc {source_path}: {exc}")
            messagebox.showerror(APP_TITLE, str(exc))

    def _start_upload_prepare(self) -> None:
        if self._busy:
            return
        if not self.playwright_ready:
            self.upload_status_var.set(self.playwright_message)
            self._append_log(f"[UPLOAD] {self.playwright_message}")
            messagebox.showwarning(APP_TITLE, self.playwright_message)
            return
        manifest_value = self.upload_manifest_var.get().strip()
        if not manifest_value:
            messagebox.showwarning(APP_TITLE, "Vui long chon manifest.")
            return
        manifest_path = Path(manifest_value)
        if not manifest_path.exists():
            messagebox.showwarning(APP_TITLE, "Manifest khong ton tai.")
            return
        self._set_busy(True)
        self._append_log(f"[UPLOAD] Bat dau dry-run tu manifest: {manifest_path}")
        self.upload_worker.enqueue_prepare(manifest_path)

    def _stop_upload_prepare(self) -> None:
        self.upload_worker.request_stop()
        self._append_log("[UPLOAD] Da gui yeu cau Stop. Bot se dung sau record hien tai.")

    def _on_upload_prepare_done(self, summary: dict) -> None:
        self._set_busy(False)
        self._last_upload_summary = summary
        self._append_log(
            f"[UPLOAD] Xong chunk. prepared={summary['prepared_count']}/{summary['total_pending']} | remaining={summary['remaining']}"
        )
        self._append_log(f"[UPLOAD] Artifact: {summary['artifact_dir']}")
        self._append_log(f"[UPLOAD] {summary['message']}")
        self._refresh_upload_queue()
        self.upload_status_var.set(summary["message"])
        messagebox.showinfo(
            APP_TITLE,
            "Dry-run chunk hoan tat.\n\n"
            f"{summary['message']}\n"
            f"Artifact: {summary['artifact_dir']}",
        )

    def _on_upload_prepare_error(self, exc: Exception, tb: str) -> None:
        self._set_busy(False)
        self._append_log(f"[UPLOAD] Loi: {exc}\n{tb}")
        self._refresh_upload_queue()
        messagebox.showerror(APP_TITLE, str(exc))

    def _finalize_selected_upload_records(self) -> None:
        selected = [int(item_id) for item_id in self.upload_tree.selection()]
        if not selected:
            messagebox.showwarning(APP_TITLE, "Vui long chon it nhat 1 record de finalize.")
            return

        count = finalize_uploaded_records(selected, working_dir=BASE_DIR)
        self._append_log(f"[UPLOAD] Finalize {count} record -> uploaded_success")
        self._refresh_upload_queue()
        messagebox.showinfo(APP_TITLE, f"Da finalize {count} record.")

    def _on_close(self) -> None:
        try:
            self.upload_worker.request_stop()
            self.upload_worker.shutdown()
        except Exception:
            pass
        self.destroy()


def main() -> int:
    app = App()
    app.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
