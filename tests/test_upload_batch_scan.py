from __future__ import annotations

import os
import tempfile
import unittest
from datetime import datetime
from pathlib import Path

from docx import Document

from UPLOAD.batch_scan import connect_registry, parse_modified_since, run_batch_scan, upsert_registry_record
from UPLOAD.extract_contract import scan_docx_for_contract_no


def make_docx(path: Path, *paragraphs: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    doc = Document()
    for paragraph in paragraphs:
        doc.add_paragraph(paragraph)
    doc.save(str(path))
    return path


def set_mtime(path: Path, iso_date: str) -> None:
    dt = datetime.fromisoformat(iso_date)
    ts = dt.timestamp()
    os.utime(path, (ts, ts))


class UploadBatchScanTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tempdir.cleanup)
        self.root = Path(self.tempdir.name)

    def test_parse_modified_since_accepts_vietnamese_date_format(self):
        self.assertEqual(str(parse_modified_since("01/01/2026")), "2026-01-01")
        self.assertEqual(str(parse_modified_since("2026-01-01")), "2026-01-01")

    def test_scan_docx_for_contract_no_detects_last_match(self):
        docx_path = make_docx(
            self.root / "hop_dong.docx",
            "Trang đầu có số cũ 111/2026/CCGD",
            "LỜI CHỨNG",
            "Số công chứng 428/2026/CCGD",
        )

        result = scan_docx_for_contract_no(docx_path)

        self.assertTrue(result["is_contract"])
        self.assertEqual(result["contract_no"], "428/2026/CCGD")

    def test_scan_docx_requires_contract_no_not_just_keyword(self):
        docx_path = make_docx(
            self.root / "hop_dong_khong_so.docx",
            "HỢP ĐỒNG CHUYỂN NHƯỢNG QUYỀN SỬ DỤNG ĐẤT",
            "Nội dung hợp đồng nhưng chưa có số công chứng",
        )

        result = scan_docx_for_contract_no(docx_path)

        self.assertFalse(result["is_contract"])
        self.assertEqual(result["contract_no"], "")
        self.assertIn("keyword", result["reason"].lower())

    def test_batch_scan_finds_depth_three_and_skips_depth_four(self):
        batch_root = self.root / "hoso"
        make_docx(
            batch_root / "A" / "B" / "C" / "allowed.docx",
            "Số công chứng 428/2026/CCGD",
        )
        make_docx(
            batch_root / "A" / "B" / "C" / "D" / "blocked.docx",
            "Số công chứng 429/2026/CCGD",
        )
        workdir = self.root / "work"

        manifest = run_batch_scan(batch_root, working_dir=workdir)

        output_files = sorted((workdir / "output").glob("*.json"))
        self.assertEqual(manifest["stats"]["candidates_found"], 1)
        self.assertEqual(len(output_files), 1)
        self.assertIn("428_2026_CCGD", output_files[0].name)

    def test_batch_scan_skips_when_contract_already_uploaded_success(self):
        batch_root = self.root / "hoso"
        docx_path = make_docx(
            batch_root / "KhachA" / "hop_dong.docx",
            "Số công chứng 428/2026/CCGD",
        )
        workdir = self.root / "work"
        conn = connect_registry(workdir / "registry.sqlite3")
        self.addCleanup(conn.close)
        stat_result = docx_path.stat()
        upsert_registry_record(
            conn,
            file_key="seed-uploaded-success",
            file_path=docx_path,
            stat_result=stat_result,
            customer_folder="KhachA",
            contract_no="428/2026/CCGD",
            status="uploaded_success",
            run_id="seedrun",
            uploaded_success_at="2026-04-06T10:00:00",
            reason="Seed uploaded success",
        )
        conn.close()

        manifest = run_batch_scan(batch_root, working_dir=workdir)

        self.assertEqual(manifest["stats"]["skipped_duplicate"], 1)
        self.assertFalse((workdir / "output").exists())

    def test_batch_scan_retries_failed_file_even_if_older_than_modified_since(self):
        batch_root = self.root / "hoso"
        docx_path = make_docx(
            batch_root / "KhachB" / "hop_dong.docx",
            "Số công chứng 555/2026/CCGD",
        )
        set_mtime(docx_path, "2026-04-01T09:00:00")
        workdir = self.root / "work"

        conn = connect_registry(workdir / "registry.sqlite3")
        self.addCleanup(conn.close)
        stat_result = docx_path.stat()
        upsert_registry_record(
            conn,
            file_key="seed-upload-failed",
            file_path=docx_path,
            stat_result=stat_result,
            customer_folder="KhachB",
            contract_no="555/2026/CCGD",
            status="upload_failed",
            run_id="seedrun",
            last_error="Network error",
            reason="Seed upload failed",
        )
        conn.close()

        manifest = run_batch_scan(
            batch_root,
            modified_since="2026-04-05",
            working_dir=workdir,
        )

        output_files = list((workdir / "output").glob("*.json"))
        self.assertEqual(manifest["stats"]["total_skipped_old"], 0)
        self.assertEqual(manifest["stats"]["extract_success"], 1)
        self.assertEqual(len(output_files), 1)


if __name__ == "__main__":
    unittest.main()
