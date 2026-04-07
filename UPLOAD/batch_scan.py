from __future__ import annotations

import argparse
import hashlib
import json
import os
import sqlite3
import time
from datetime import datetime
from pathlib import Path
from typing import Optional
from uuid import uuid4

try:
    from extract_contract import extract, get_missing_web_form_fields, scan_docx_for_contract_no
except ImportError:  # pragma: no cover - fallback when imported as package
    from UPLOAD.extract_contract import extract, get_missing_web_form_fields, scan_docx_for_contract_no


BASE_DIR = Path(__file__).resolve().parent
OUTPUT_DIR = BASE_DIR / "output"
RUNS_DIR = BASE_DIR / "runs"
REGISTRY_DB_PATH = BASE_DIR / "registry.sqlite3"
MAX_SCAN_DEPTH = 3
RETRYABLE_STATUSES = {"extract_failed", "upload_failed"}
UNSUPPORTED_SUFFIXES = {".xls", ".xlsx"}
SKIP_TEMP_PREFIX = "~$"
REGISTRY_EXTRA_COLUMNS = {
    "prepared_at": "TEXT",
    "artifact_dir": "TEXT",
    "verify_json": "TEXT",
}


def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def parse_args():
    parser = argparse.ArgumentParser(description="Batch scan folder hop dong Word (.doc/.docx)")
    parser.add_argument("--folder", help="Folder tong can quet")
    parser.add_argument("--modified-since", help="Chi quet file sua tu ngay YYYY-MM-DD hoac DD/MM/YYYY tro di")
    parser.add_argument("--full-rescan", action="store_true", help="Bo qua bo loc ngay va quet lai toan bo")
    return parser.parse_args()


def parse_modified_since(value: Optional[str]) -> Optional[datetime.date]:
    if not value:
        return None
    raw = str(value).strip()
    if not raw:
        return None

    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y"):
        try:
            return datetime.strptime(raw, fmt).date()
        except ValueError:
            continue

    raise ValueError("modified_since phai theo YYYY-MM-DD hoac DD/MM/YYYY")


def choose_folder_via_dialog() -> Optional[Path]:
    try:
        import tkinter as tk
        from tkinter import filedialog
    except Exception as exc:  # pragma: no cover - depends on local GUI environment
        raise RuntimeError(f"Khong mo duoc hop thoai chon folder: {exc}") from exc

    root = tk.Tk()
    root.withdraw()
    root.attributes("-topmost", True)
    try:
        selected = filedialog.askdirectory(title="Chon folder tong ho so")
    finally:
        root.destroy()
    if not selected:
        return None
    return Path(selected)


def sanitize_contract_no(contract_no: str) -> str:
    return str(contract_no or "").strip().replace("/", "_")


def file_identity_key(file_path: Path, stat_result: os.stat_result) -> str:
    raw = f"{file_path.resolve()}|{stat_result.st_mtime_ns}|{stat_result.st_size}"
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()


def output_json_name(contract_no: str, file_key: str) -> str:
    return f"{sanitize_contract_no(contract_no)}_{file_key[:8]}.json"


def resolve_customer_folder(root_folder: Path, file_path: Path) -> str:
    relative = file_path.relative_to(root_folder)
    if len(relative.parts) > 1:
        return relative.parts[0]
    return root_folder.name


def ensure_registry_schema(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS file_registry (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            file_key TEXT NOT NULL UNIQUE,
            file_path TEXT NOT NULL,
            file_mtime_ns INTEGER NOT NULL,
            file_size INTEGER NOT NULL,
            customer_folder TEXT,
            contract_no TEXT,
            status TEXT NOT NULL,
            matched_at TEXT,
            extracted_at TEXT,
            uploaded_success_at TEXT,
            last_error TEXT,
            run_id TEXT,
            output_json_path TEXT,
            reason TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """
    )
    existing_columns = {
        row[1]
        for row in conn.execute("PRAGMA table_info(file_registry)").fetchall()
    }
    for column_name, column_sql in REGISTRY_EXTRA_COLUMNS.items():
        if column_name not in existing_columns:
            conn.execute(f"ALTER TABLE file_registry ADD COLUMN {column_name} {column_sql}")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_file_registry_contract_no ON file_registry(contract_no)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_file_registry_status ON file_registry(status)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_file_registry_run_id ON file_registry(run_id)")
    conn.commit()


def connect_registry(db_path: Path = REGISTRY_DB_PATH) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    ensure_registry_schema(conn)
    return conn


def get_row_by_file_key(conn: sqlite3.Connection, file_key: str):
    return conn.execute(
        "SELECT * FROM file_registry WHERE file_key = ? LIMIT 1",
        (file_key,),
    ).fetchone()


def get_row_by_id(conn: sqlite3.Connection, record_id: int):
    return conn.execute(
        "SELECT * FROM file_registry WHERE id = ? LIMIT 1",
        (record_id,),
    ).fetchone()


def get_latest_status_for_path(conn: sqlite3.Connection, file_path: Path) -> Optional[str]:
    row = conn.execute(
        """
        SELECT status
        FROM file_registry
        WHERE file_path = ?
        ORDER BY id DESC
        LIMIT 1
        """,
        (str(file_path.resolve()),),
    ).fetchone()
    return row["status"] if row else None


def has_uploaded_success(conn: sqlite3.Connection, contract_no: str) -> bool:
    row = conn.execute(
        """
        SELECT 1
        FROM file_registry
        WHERE contract_no = ? AND status = 'uploaded_success'
        LIMIT 1
        """,
        (contract_no,),
    ).fetchone()
    return row is not None


def upsert_registry_record(
    conn: sqlite3.Connection,
    *,
    file_key: str,
    file_path: Path,
    stat_result: os.stat_result,
    customer_folder: str,
    status: str,
    run_id: str,
    contract_no: str = "",
    matched_at: Optional[str] = None,
    extracted_at: Optional[str] = None,
    uploaded_success_at: Optional[str] = None,
    last_error: Optional[str] = None,
    output_json_path: Optional[str] = None,
    reason: Optional[str] = None,
    prepared_at: Optional[str] = None,
    artifact_dir: Optional[str] = None,
    verify_json: Optional[str] = None,
) -> None:
    existing = get_row_by_file_key(conn, file_key)
    created_at = existing["created_at"] if existing else now_iso()
    updated_at = now_iso()
    conn.execute(
        """
        INSERT INTO file_registry (
            file_key,
            file_path,
            file_mtime_ns,
            file_size,
            customer_folder,
            contract_no,
            status,
            matched_at,
            extracted_at,
            uploaded_success_at,
            last_error,
            run_id,
            output_json_path,
            reason,
            prepared_at,
            artifact_dir,
            verify_json,
            created_at,
            updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(file_key) DO UPDATE SET
            file_path = excluded.file_path,
            file_mtime_ns = excluded.file_mtime_ns,
            file_size = excluded.file_size,
            customer_folder = excluded.customer_folder,
            contract_no = excluded.contract_no,
            status = excluded.status,
            matched_at = COALESCE(excluded.matched_at, file_registry.matched_at),
            extracted_at = COALESCE(excluded.extracted_at, file_registry.extracted_at),
            uploaded_success_at = COALESCE(excluded.uploaded_success_at, file_registry.uploaded_success_at),
            last_error = excluded.last_error,
            run_id = excluded.run_id,
            output_json_path = COALESCE(excluded.output_json_path, file_registry.output_json_path),
            reason = excluded.reason,
            prepared_at = COALESCE(excluded.prepared_at, file_registry.prepared_at),
            artifact_dir = COALESCE(excluded.artifact_dir, file_registry.artifact_dir),
            verify_json = COALESCE(excluded.verify_json, file_registry.verify_json),
            updated_at = excluded.updated_at
        """,
        (
            file_key,
            str(file_path.resolve()),
            stat_result.st_mtime_ns,
            stat_result.st_size,
            customer_folder,
            contract_no,
            status,
            matched_at,
            extracted_at,
            uploaded_success_at,
            last_error,
            run_id,
            output_json_path,
            reason,
            prepared_at,
            artifact_dir,
            verify_json,
            created_at,
            updated_at,
        ),
    )
    conn.commit()


def load_manifest(manifest_path: Path | str) -> dict:
    path = Path(manifest_path)
    return json.loads(path.read_text(encoding="utf-8"))


def fetch_registry_records_for_run(
    conn: sqlite3.Connection,
    run_id: str,
    *,
    statuses: Optional[tuple[str, ...] | list[str]] = None,
    limit: Optional[int] = None,
) -> list[sqlite3.Row]:
    sql = ["SELECT * FROM file_registry WHERE run_id = ?"]
    params: list[object] = [run_id]
    if statuses:
        placeholders = ",".join("?" for _ in statuses)
        sql.append(f"AND status IN ({placeholders})")
        params.extend(list(statuses))
    sql.append("ORDER BY id ASC")
    if limit is not None:
        sql.append("LIMIT ?")
        params.append(int(limit))
    return conn.execute(" ".join(sql), tuple(params)).fetchall()


def update_registry_record_by_id(
    conn: sqlite3.Connection,
    record_id: int,
    *,
    status: Optional[str] = None,
    last_error: Optional[str] = None,
    reason: Optional[str] = None,
    uploaded_success_at: Optional[str] = None,
    prepared_at: Optional[str] = None,
    artifact_dir: Optional[str] = None,
    verify_json: Optional[str] = None,
    output_json_path: Optional[str] = None,
) -> None:
    fields = []
    params: list[object] = []

    def add_field(column: str, value) -> None:
        fields.append(f"{column} = ?")
        params.append(value)

    if status is not None:
        add_field("status", status)
    if last_error is not None:
        add_field("last_error", last_error)
    if reason is not None:
        add_field("reason", reason)
    if uploaded_success_at is not None:
        add_field("uploaded_success_at", uploaded_success_at)
    if prepared_at is not None:
        add_field("prepared_at", prepared_at)
    if artifact_dir is not None:
        add_field("artifact_dir", artifact_dir)
    if verify_json is not None:
        add_field("verify_json", verify_json)
    if output_json_path is not None:
        add_field("output_json_path", output_json_path)

    add_field("updated_at", now_iso())
    params.append(int(record_id))
    conn.execute(
        f"UPDATE file_registry SET {', '.join(fields)} WHERE id = ?",
        tuple(params),
    )
    conn.commit()


def mark_records_uploaded_success(
    conn: sqlite3.Connection,
    record_ids: list[int],
    *,
    reason: str = "Finalized via UI",
) -> None:
    timestamp = now_iso()
    for record_id in record_ids:
        update_registry_record_by_id(
            conn,
            int(record_id),
            status="uploaded_success",
            uploaded_success_at=timestamp,
            reason=reason,
            last_error="",
        )


def should_skip_by_modified_since(
    conn: sqlite3.Connection,
    file_path: Path,
    stat_result: os.stat_result,
    modified_since,
    *,
    full_rescan: bool,
) -> bool:
    if full_rescan or modified_since is None:
        return False

    file_date = datetime.fromtimestamp(stat_result.st_mtime).date()
    if file_date >= modified_since:
        return False

    latest_status = get_latest_status_for_path(conn, file_path)
    if latest_status in RETRYABLE_STATUSES:
        return False
    return True


def save_output_json(output_dir: Path, contract_no: str, file_key: str, payload: dict) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / output_json_name(contract_no, file_key)
    output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return output_path


def initial_manifest(folder_root: Path, modified_since: Optional[str], full_rescan: bool, run_id: str) -> dict:
    started_at = now_iso()
    return {
        "run_id": run_id,
        "started_at": started_at,
        "finished_at": None,
        "duration_seconds": None,
        "folder_root": str(folder_root),
        "modified_since": modified_since,
        "full_rescan": full_rescan,
        "stats": {
            "total_subfolders": 0,
            "total_docx_files": 0,
            "total_supported_files": 0,
            "processed_files": 0,
            "total_skipped_temp": 0,
            "total_skipped_unsupported": 0,
            "total_skipped_old": 0,
            "candidates_found": 0,
            "extract_success": 0,
            "extract_failed": 0,
            "extract_partial": 0,
            "skipped_duplicate": 0,
            "ready_for_upload": 0,
        },
        "errors": [],
    }


def append_error(manifest: dict, file_path: Path, error: str) -> None:
    manifest["errors"].append({"file": str(file_path), "error": error})


def collect_batch_files(folder_root: Path, manifest: dict) -> tuple[list[Path], list[Path]]:
    supported_files: list[Path] = []
    unsupported_files: list[Path] = []

    for current_root, dirs, files in os.walk(str(folder_root)):
        current_path = Path(current_root)
        relative_dir = current_path.relative_to(folder_root)
        depth = len(relative_dir.parts)
        if depth > 0:
            manifest["stats"]["total_subfolders"] += 1
        if depth >= MAX_SCAN_DEPTH:
            dirs[:] = []

        for name in files:
            file_path = current_path / name
            suffix = file_path.suffix.lower()

            if suffix in (".docx", ".doc"):
                manifest["stats"]["total_docx_files"] += 1

            if name.startswith(SKIP_TEMP_PREFIX) and suffix in (".docx", ".doc"):
                manifest["stats"]["total_skipped_temp"] += 1
                continue

            if suffix in UNSUPPORTED_SUFFIXES:
                unsupported_files.append(file_path)
                manifest["stats"]["total_skipped_unsupported"] += 1
                continue

            if suffix in (".docx", ".doc"):
                supported_files.append(file_path)

    manifest["stats"]["total_supported_files"] = len(supported_files)
    return supported_files, unsupported_files


def emit_progress(
    progress_callback,
    manifest: dict,
    *,
    stage: str,
    step: str = "",
    current_file: Optional[Path] = None,
    process_started_at: Optional[float] = None,
    last_outcome: str = "",
    last_reason: str = "",
    last_contract_no: str = "",
) -> None:
    if not progress_callback:
        return

    processed_files = int(manifest["stats"].get("processed_files", 0) or 0)
    total_files = int(manifest["stats"].get("total_supported_files", 0) or 0)
    elapsed_seconds = max(0.0, time.perf_counter() - process_started_at) if process_started_at else 0.0
    files_per_second = (processed_files / elapsed_seconds) if elapsed_seconds > 0 and processed_files > 0 else 0.0
    eta_seconds = None
    if total_files > processed_files and files_per_second > 0:
        eta_seconds = (total_files - processed_files) / files_per_second

    snapshot = {
        "stage": stage,
        "step": step,
        "current_file": str(current_file) if current_file else "",
        "processed_files": processed_files,
        "total_files": total_files,
        "elapsed_seconds": round(elapsed_seconds, 3),
        "files_per_second": round(files_per_second, 3),
        "eta_seconds": round(eta_seconds, 3) if eta_seconds is not None else None,
        "last_outcome": last_outcome,
        "last_reason": last_reason,
        "last_contract_no": last_contract_no,
        "stats": dict(manifest["stats"]),
    }
    try:
        progress_callback(snapshot)
    except Exception:
        pass


def finalize_manifest(manifest: dict, runs_dir: Path) -> Path:
    finished_at = now_iso()
    started_at = datetime.fromisoformat(manifest["started_at"])
    finished_dt = datetime.fromisoformat(finished_at)
    manifest["finished_at"] = finished_at
    manifest["duration_seconds"] = round((finished_dt - started_at).total_seconds(), 3)
    runs_dir.mkdir(parents=True, exist_ok=True)
    output_path = runs_dir / f"{finished_dt.strftime('%Y-%m-%d_%H%M%S')}.json"
    output_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return output_path


def run_batch_scan(
    folder_root: Path,
    *,
    modified_since: Optional[str] = None,
    full_rescan: bool = False,
    working_dir: Optional[Path] = None,
    progress_callback=None,
) -> dict:
    folder_root = Path(folder_root)
    if not folder_root.exists() or not folder_root.is_dir():
        raise FileNotFoundError(f"Folder khong hop le: {folder_root}")

    working_dir = Path(working_dir or BASE_DIR)
    output_dir = working_dir / "output"
    registry_db = working_dir / "registry.sqlite3"
    modified_since_date = parse_modified_since(modified_since)
    run_id = uuid4().hex[:8]
    manifest = initial_manifest(folder_root.resolve(), modified_since, full_rescan, run_id)
    conn = connect_registry(registry_db)
    process_started_at: Optional[float] = None

    try:
        emit_progress(progress_callback, manifest, stage="indexing", step="collect_files")
        supported_files, unsupported_files = collect_batch_files(folder_root, manifest)
        emit_progress(progress_callback, manifest, stage="indexing", step="collected")

        for file_path in unsupported_files:
            try:
                stat_result = file_path.stat()
            except OSError as exc:
                append_error(manifest, file_path, f"Khong doc duoc stat file: {exc}")
                continue

            file_key = file_identity_key(file_path, stat_result)
            customer_folder = resolve_customer_folder(folder_root, file_path)
            upsert_registry_record(
                conn,
                file_key=file_key,
                file_path=file_path,
                stat_result=stat_result,
                customer_folder=customer_folder,
                status="skipped_unsupported",
                run_id=run_id,
                last_error="unsupported",
                reason="File khong duoc ho tro",
            )

        process_started_at = time.perf_counter()
        emit_progress(progress_callback, manifest, stage="processing", step="start", process_started_at=process_started_at)

        for file_path in supported_files:
            emit_progress(
                progress_callback,
                manifest,
                stage="processing",
                step="scan",
                current_file=file_path,
                process_started_at=process_started_at,
            )

            try:
                stat_result = file_path.stat()
            except OSError as exc:
                append_error(manifest, file_path, f"Khong doc duoc stat file: {exc}")
                manifest["stats"]["processed_files"] += 1
                emit_progress(
                    progress_callback,
                    manifest,
                    stage="processing",
                    step="file_done",
                    current_file=file_path,
                    process_started_at=process_started_at,
                    last_outcome="stat_error",
                    last_reason=str(exc),
                )
                continue

            file_key = file_identity_key(file_path, stat_result)
            customer_folder = resolve_customer_folder(folder_root, file_path)

            if should_skip_by_modified_since(
                conn,
                file_path,
                stat_result,
                modified_since_date,
                full_rescan=full_rescan,
            ):
                upsert_registry_record(
                    conn,
                    file_key=file_key,
                    file_path=file_path,
                    stat_result=stat_result,
                    customer_folder=customer_folder,
                    status="skipped_old_file",
                    run_id=run_id,
                    last_error=None,
                    reason="File cu hon modified_since",
                )
                manifest["stats"]["total_skipped_old"] += 1
                manifest["stats"]["processed_files"] += 1
                emit_progress(
                    progress_callback,
                    manifest,
                    stage="processing",
                    step="file_done",
                    current_file=file_path,
                    process_started_at=process_started_at,
                    last_outcome="skipped_old",
                )
                continue

            scan_result = scan_docx_for_contract_no(file_path, include_text=True)
            if not scan_result.get("is_contract"):
                reason = scan_result.get("reason", "Khong thay so cong chung")
                if reason.lower().startswith("khong doc duoc file"):
                    append_error(manifest, file_path, reason)
                manifest["stats"]["processed_files"] += 1
                emit_progress(
                    progress_callback,
                    manifest,
                    stage="processing",
                    step="file_done",
                    current_file=file_path,
                    process_started_at=process_started_at,
                    last_outcome="not_contract",
                    last_reason=reason,
                )
                continue

            contract_no = str(scan_result.get("contract_no", "")).strip()
            if not contract_no:
                manifest["stats"]["processed_files"] += 1
                emit_progress(
                    progress_callback,
                    manifest,
                    stage="processing",
                    step="file_done",
                    current_file=file_path,
                    process_started_at=process_started_at,
                    last_outcome="empty_contract_no",
                )
                continue

            manifest["stats"]["candidates_found"] += 1

            if has_uploaded_success(conn, contract_no):
                upsert_registry_record(
                    conn,
                    file_key=file_key,
                    file_path=file_path,
                    stat_result=stat_result,
                    customer_folder=customer_folder,
                    contract_no=contract_no,
                    status="skipped_duplicate",
                    run_id=run_id,
                    reason="Contract_no da co uploaded_success",
                )
                manifest["stats"]["skipped_duplicate"] += 1
                manifest["stats"]["processed_files"] += 1
                emit_progress(
                    progress_callback,
                    manifest,
                    stage="processing",
                    step="file_done",
                    current_file=file_path,
                    process_started_at=process_started_at,
                    last_outcome="skipped_duplicate",
                    last_contract_no=contract_no,
                )
                continue

            matched_at = now_iso()
            upsert_registry_record(
                conn,
                file_key=file_key,
                file_path=file_path,
                stat_result=stat_result,
                customer_folder=customer_folder,
                contract_no=contract_no,
                status="matched",
                run_id=run_id,
                matched_at=matched_at,
                reason=scan_result.get("reason", ""),
            )

            emit_progress(
                progress_callback,
                manifest,
                stage="processing",
                step="extract",
                current_file=file_path,
                process_started_at=process_started_at,
                last_contract_no=contract_no,
            )

            try:
                payload = extract(
                    file_path,
                    scan_result=scan_result,
                    preloaded_text=scan_result.get("text"),
                )
                output_path = save_output_json(output_dir, contract_no, file_key, payload)
            except Exception as exc:
                upsert_registry_record(
                    conn,
                    file_key=file_key,
                    file_path=file_path,
                    stat_result=stat_result,
                    customer_folder=customer_folder,
                    contract_no=contract_no,
                    status="extract_failed",
                    run_id=run_id,
                    matched_at=matched_at,
                    last_error=str(exc),
                    reason="Extract that bai",
                )
                manifest["stats"]["extract_failed"] += 1
                manifest["stats"]["processed_files"] += 1
                append_error(manifest, file_path, f"Extract loi: {exc}")
                emit_progress(
                    progress_callback,
                    manifest,
                    stage="processing",
                    step="file_done",
                    current_file=file_path,
                    process_started_at=process_started_at,
                    last_outcome="extract_failed",
                    last_reason=str(exc),
                    last_contract_no=contract_no,
                )
                continue

            missing_fields = payload.get("raw", {}).get("missing_web_form_fields") or []
            if not missing_fields:
                missing_fields = get_missing_web_form_fields(
                    payload.get("web_form") or {},
                    file_hop_dong=payload.get("raw", {}).get("file_goc", ""),
                )
            if missing_fields:
                manifest["stats"]["extract_partial"] += 1

            extracted_at = now_iso()
            reason = "Extract thanh cong"
            if missing_fields:
                reason = f"Extract thanh cong (partial: {', '.join(missing_fields)})"
            upsert_registry_record(
                conn,
                file_key=file_key,
                file_path=file_path,
                stat_result=stat_result,
                customer_folder=customer_folder,
                contract_no=contract_no,
                status="extracted",
                run_id=run_id,
                matched_at=matched_at,
                extracted_at=extracted_at,
                output_json_path=str(output_path),
                reason=reason,
            )
            manifest["stats"]["extract_success"] += 1
            manifest["stats"]["ready_for_upload"] += 1
            manifest["stats"]["processed_files"] += 1
            emit_progress(
                progress_callback,
                manifest,
                stage="processing",
                step="file_done",
                current_file=file_path,
                process_started_at=process_started_at,
                last_outcome="extract_partial" if missing_fields else "extracted",
                last_reason=reason,
                last_contract_no=contract_no,
            )
    finally:
        conn.close()

    emit_progress(progress_callback, manifest, stage="done", step="done", process_started_at=process_started_at)
    return manifest


def main() -> int:
    args = parse_args()

    try:
        folder_root = Path(args.folder) if args.folder else choose_folder_via_dialog()
    except RuntimeError as exc:
        print(exc)
        return 1

    if folder_root is None:
        print("Da huy chon folder. Ket thuc sach.")
        return 0

    try:
        manifest = run_batch_scan(
            folder_root,
            modified_since=args.modified_since,
            full_rescan=bool(args.full_rescan),
        )
        manifest_path = finalize_manifest(manifest, RUNS_DIR)
    except Exception as exc:
        print(f"Loi batch scan: {exc}")
        return 1

    print(json.dumps(manifest, ensure_ascii=False, indent=2))
    print(f"\nManifest: {manifest_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
