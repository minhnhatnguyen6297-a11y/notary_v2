from __future__ import annotations

import os
import tempfile
import unicodedata
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

from docx import Document

from tools.upload_lab.batch_scan import connect_registry, parse_modified_since, run_batch_scan, upsert_registry_record
from tools.upload_lab.extract_contract import extract, find_tai_san, scan_docx_for_contract_no


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

    def test_scan_docx_requires_full_ccgd_suffix_not_short_form_only(self):
        docx_path = make_docx(
            self.root / "hop_dong_short_only.docx",
            "HỢP ĐỒNG CHUYỂN NHƯỢNG QUYỀN SỬ DỤNG ĐẤT",
            "Số công chứng 428/2026",
        )

        result = scan_docx_for_contract_no(docx_path)

        self.assertFalse(result["is_contract"])
        self.assertEqual(result["contract_no"], "")

    def test_extract_shortens_web_contract_no_after_full_ccgd_match(self):
        docx_path = make_docx(
            self.root / "hop_dong_full_ccgd.docx",
            "HỢP ĐỒNG CHUYỂN NHƯỢNG QUYỀN SỬ DỤNG ĐẤT",
            "Số công chứng 428/2026/CCGD",
        )

        payload = extract(docx_path)

        self.assertEqual(payload["raw"]["scan_contract_no"], "428/2026/CCGD")
        self.assertEqual(payload["web_form"]["so_cong_chung"], "428/2026")

    def test_extract_does_not_fill_web_contract_no_from_short_form_only(self):
        docx_path = make_docx(
            self.root / "hop_dong_extract_short_only.docx",
            "HỢP ĐỒNG CHUYỂN NHƯỢNG QUYỀN SỬ DỤNG ĐẤT",
            "Số công chứng 428/2026",
        )

        payload = extract(docx_path)

        self.assertEqual(payload["raw"]["scan_contract_no"], "")
        self.assertEqual(payload["web_form"]["so_cong_chung"], "")

    def test_find_tai_san_uses_common_qsdd_anchor_for_transfer(self):
        text = "\n".join(
            [
                "HỢP ĐỒNG CHUYỂN NHƯỢNG QUYỀN SỬ DỤNG ĐẤT",
                "ĐIỀU 1: ĐỐI TƯỢNG CỦA HỢP ĐỒNG",
                "Đối tượng của Hợp đồng này là toàn bộ quyền sử dụng đất của bên A có địa chỉ tại: thôn A, xã B.",
                "- Thửa đất số: 10",
                "- Diện tích: 100 m2",
                "1.2 Bằng Hợp đồng này...",
            ]
        )

        tai_san = find_tai_san(text)

        self.assertTrue(tai_san.startswith("quyền sử dụng đất của bên A có địa chỉ tại"))
        self.assertIn("Thửa đất số: 10", tai_san)
        self.assertNotIn("1.2 Bằng Hợp đồng này", tai_san)

    def test_find_tai_san_supports_folded_doc_text_for_commitment(self):
        text = "\n".join(
            [
                "VĂN BẢN CAM KẾT TÀI SẢN RIÊNG",
                "Hiện nay, ông A đang làm các thủ tục để nhận chuyển nhượng quyền sử dụng đất có địa chỉ tại: thôn A, xã B.",
                "- Thửa đất số: 20",
                "- Diện tích: 200 m2",
                "Hai vợ chồng chúng tôi cam đoan:",
            ]
        )
        folded_like_doc_text = unicodedata.normalize("NFD", text)

        tai_san = find_tai_san(folded_like_doc_text)

        self.assertTrue(tai_san.startswith("quyền sử dụng đất có địa chỉ tại"))
        self.assertIn("Thửa đất số: 20", tai_san)
        self.assertNotIn("Hai vợ chồng chúng tôi cam đoan", tai_san)

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

    def test_batch_scan_accepts_doc_files(self):
        batch_root = self.root / "hoso"
        doc_path = batch_root / "KhachDoc" / "hop_dong.doc"
        doc_path.parent.mkdir(parents=True, exist_ok=True)
        doc_path.write_text("legacy doc placeholder", encoding="utf-8")
        workdir = self.root / "work"

        with patch(
            "tools.upload_lab.batch_scan.scan_docx_for_contract_no",
            return_value={
                "is_contract": True,
                "contract_no": "777/2026/CCGD",
                "reason": "Tim thay so CC: 777/2026/CCGD",
                "text": "dummy preloaded text",
            },
        ) as scan_mock, patch(
            "tools.upload_lab.batch_scan.extract",
            return_value={
                "web_form": {
                    "ten_hop_dong": "Hop dong chuyen nhuong",
                    "so_cong_chung": "777/2026/CCGD",
                    "nhom_hop_dong": "Chuyen nhuong - Mua ban",
                    "loai_tai_san": "Dat dai khong co tai san",
                    "tai_san": "Thua dat ...",
                },
                "raw": {"file_goc": str(doc_path), "missing_web_form_fields": []},
            },
        ) as extract_mock:
            manifest = run_batch_scan(batch_root, working_dir=workdir)

        output_files = sorted((workdir / "output").glob("*.json"))
        self.assertEqual(manifest["stats"]["candidates_found"], 1)
        self.assertEqual(manifest["stats"]["extract_success"], 1)
        self.assertEqual(manifest["stats"]["ready_for_upload"], 1)
        self.assertEqual(len(output_files), 1)
        self.assertIn("777_2026_CCGD", output_files[0].name)
        scan_mock.assert_called_once_with(doc_path, include_text=True)
        self.assertEqual(extract_mock.call_args.args[0], doc_path)
        self.assertEqual(extract_mock.call_args.kwargs["scan_result"]["contract_no"], "777/2026/CCGD")
        self.assertEqual(extract_mock.call_args.kwargs["preloaded_text"], "dummy preloaded text")

    def test_batch_scan_progress_callback_reports_processing(self):
        batch_root = self.root / "hoso"
        docx_path = make_docx(
            batch_root / "KhachTienDo" / "hop_dong.docx",
            "So cong chung 888/2026/CCGD",
        )
        workdir = self.root / "work"
        snapshots: list[dict] = []

        with patch(
            "tools.upload_lab.batch_scan.scan_docx_for_contract_no",
            return_value={
                "is_contract": True,
                "contract_no": "888/2026/CCGD",
                "reason": "Tim thay so CC: 888/2026/CCGD",
                "text": "dummy text",
            },
        ), patch(
            "tools.upload_lab.batch_scan.extract",
            return_value={
                "web_form": {
                    "ten_hop_dong": "Hop dong",
                    "so_cong_chung": "888/2026/CCGD",
                    "nhom_hop_dong": "Khac",
                    "loai_tai_san": "Tai san khac",
                    "tai_san": "Tai san ...",
                },
                "raw": {"file_goc": str(docx_path), "missing_web_form_fields": []},
            },
        ):
            manifest = run_batch_scan(
                batch_root,
                working_dir=workdir,
                progress_callback=lambda snapshot: snapshots.append(snapshot),
            )

        self.assertEqual(manifest["stats"]["processed_files"], 1)
        self.assertGreaterEqual(len(snapshots), 3)
        self.assertEqual(snapshots[0]["stage"], "indexing")
        self.assertEqual(snapshots[-1]["stage"], "done")
        self.assertEqual(snapshots[-1]["processed_files"], 1)
        self.assertEqual(snapshots[-1]["total_files"], 1)

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
