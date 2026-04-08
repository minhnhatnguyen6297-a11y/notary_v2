from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock
from unittest.mock import patch

from openpyxl import Workbook

from tools.upload_lab.batch_scan import connect_registry, get_row_by_id, upsert_registry_record
from tools.upload_lab.playwright_uploader import (
    build_upload_form_data,
    field_value_matches,
    finalize_uploaded_records,
    get_field_value_candidates,
    get_uploader_setup_status,
    identify_missing_fields,
    load_upload_queue,
    load_uploader_settings,
    probe_playwright_runtime,
    read_exported_contract_numbers,
    save_uploader_env,
    split_records_by_existing_contract_nos,
)


def make_output_json(path: Path, *, contract_no: str, file_goc: str, ten_hop_dong: str = "Hợp đồng chuyển nhượng") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "web_form": {
            "ten_hop_dong": ten_hop_dong,
            "ngay_cong_chung": "06/04/2026",
            "so_cong_chung": contract_no,
            "nhom_hop_dong": "Chuyển nhượng - Mua bán",
            "loai_tai_san": "Đất đai không có tài sản",
            "cong_chung_vien": "Phạm Minh Chi",
            "thu_ky": "Nguyễn Nhật Minh",
            "nguoi_yeu_cau": "Ông A",
            "duong_su": "BÊN A ...",
            "tai_san": "Thửa đất ...",
        },
        "raw": {
            "file_goc": file_goc,
        },
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


class PlaywrightUploaderQueueTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tempdir.cleanup)
        self.root = Path(self.tempdir.name)
        self.workdir = self.root / "upload_lab"
        self.workdir.mkdir(parents=True, exist_ok=True)
        self.conn = connect_registry(self.workdir / "registry.sqlite3")
        self.addCleanup(self.conn.close)
        self.env_patch = patch.dict(
            os.environ,
            {key: value for key, value in os.environ.items() if not key.startswith("ND_")},
            clear=True,
        )
        self.env_patch.start()
        self.addCleanup(self.env_patch.stop)

    def _seed_record(self, *, file_key: str, run_id: str, contract_no: str, status: str, output_json_path: Path) -> int:
        source_file = self.root / f"{file_key}.docx"
        source_file.write_text("dummy", encoding="utf-8")
        stat_result = source_file.stat()
        upsert_registry_record(
            self.conn,
            file_key=file_key,
            file_path=source_file,
            stat_result=stat_result,
            customer_folder="KhachA",
            contract_no=contract_no,
            status=status,
            run_id=run_id,
            output_json_path=str(output_json_path),
            reason="seed",
        )
        row = self.conn.execute("SELECT id FROM file_registry WHERE file_key = ?", (file_key,)).fetchone()
        return int(row[0])

    def test_load_upload_queue_uses_manifest_run_id_and_excludes_uploaded_success(self):
        run_id = "run123"
        other_run = "run999"
        file_goc = str(self.root / "goc1.docx")
        Path(file_goc).write_text("dummy", encoding="utf-8")
        output1 = make_output_json(self.workdir / "output" / "1.json", contract_no="111/2026/CCGD", file_goc=file_goc)
        output2 = make_output_json(self.workdir / "output" / "2.json", contract_no="222/2026/CCGD", file_goc=file_goc)
        output3 = make_output_json(self.workdir / "output" / "3.json", contract_no="333/2026/CCGD", file_goc=file_goc)

        self._seed_record(file_key="k1", run_id=run_id, contract_no="111/2026/CCGD", status="extracted", output_json_path=output1)
        self._seed_record(file_key="k2", run_id=run_id, contract_no="222/2026/CCGD", status="prepared_dry_run", output_json_path=output2)
        self._seed_record(file_key="k3", run_id=run_id, contract_no="333/2026/CCGD", status="uploaded_success", output_json_path=output3)
        self._seed_record(file_key="k4", run_id=other_run, contract_no="444/2026/CCGD", status="extracted", output_json_path=output1)

        manifest_path = self.workdir / "runs" / "manifest.json"
        manifest_path.parent.mkdir(parents=True, exist_ok=True)
        manifest_path.write_text(json.dumps({"run_id": run_id}), encoding="utf-8")

        manifest, records, total_pending = load_upload_queue(manifest_path, working_dir=self.workdir)

        self.assertEqual(manifest["run_id"], run_id)
        self.assertEqual(total_pending, 2)
        self.assertEqual([record.contract_no for record in records], ["111/2026/CCGD", "222/2026/CCGD"])

    def test_finalize_uploaded_records_marks_selected_rows(self):
        run_id = "run123"
        file_goc = str(self.root / "goc2.docx")
        Path(file_goc).write_text("dummy", encoding="utf-8")
        output_path = make_output_json(self.workdir / "output" / "x.json", contract_no="555/2026/CCGD", file_goc=file_goc)
        record_id = self._seed_record(
            file_key="finalize-key",
            run_id=run_id,
            contract_no="555/2026/CCGD",
            status="prepared_partial",
            output_json_path=output_path,
        )

        count = finalize_uploaded_records([record_id], working_dir=self.workdir)
        row = get_row_by_id(self.conn, record_id)

        self.assertEqual(count, 1)
        self.assertEqual(row["status"], "uploaded_success")
        self.assertTrue(row["uploaded_success_at"])

    def test_upload_form_normalizes_contract_no_and_does_not_require_source_file(self):
        payload = {
            "web_form": {
                "ten_hop_dong": "Hop dong",
                "ngay_cong_chung": "06/04/2026",
                "so_cong_chung": "555/2026/CCGD",
                "nhom_hop_dong": "Khac",
                "loai_tai_san": "Tai san khac",
                "tai_san": "Tai san ...",
            },
            "raw": {
                "file_goc": "",
            },
        }

        upload_form = build_upload_form_data(payload)

        self.assertEqual(upload_form["so_cong_chung"], "555/2026")
        self.assertEqual(identify_missing_fields(upload_form), [])

    def test_contract_group_aliases_match_for_dropdown_values(self):
        candidates = get_field_value_candidates("nhom_hop_dong", "Cam kết - Thỏa thuận")

        self.assertIn("Thoả thuận - Cam kết", candidates)
        self.assertIn("Cam kết - Thỏa thuận", candidates)
        self.assertIn("Thỏa thuận - Cam kết", candidates)
        self.assertTrue(
            field_value_matches("nhom_hop_dong", "Cam kết - Thỏa thuận", "Thoả thuận - Cam kết")
        )

    def test_read_exported_contract_numbers_reads_column_a(self):
        export_path = self.root / "So_cong_chung.xlsx"
        workbook = Workbook()
        sheet = workbook.active
        sheet["A1"] = "SỐ CÔNG CHỨNG"
        sheet["A2"] = "405/2026"
        sheet["A3"] = " 413/2026/CCGD "
        sheet["A4"] = None
        sheet["A5"] = "414/2026"
        sheet["B2"] = "bo qua cot khac"
        workbook.save(export_path)
        workbook.close()

        contract_nos = read_exported_contract_numbers(export_path)

        self.assertEqual(contract_nos, {"405/2026", "413/2026", "414/2026"})

    def test_split_records_by_existing_contract_nos_filters_duplicates(self):
        run_id = "run-dup"
        file_goc = str(self.root / "goc3.docx")
        Path(file_goc).write_text("dummy", encoding="utf-8")
        output1 = make_output_json(self.workdir / "output" / "dup1.json", contract_no="405/2026/CCGD", file_goc=file_goc)
        output2 = make_output_json(self.workdir / "output" / "dup2.json", contract_no="999/2026/CCGD", file_goc=file_goc)

        self._seed_record(file_key="dup-k1", run_id=run_id, contract_no="405/2026/CCGD", status="extracted", output_json_path=output1)
        self._seed_record(file_key="dup-k2", run_id=run_id, contract_no="999/2026/CCGD", status="prepared_partial", output_json_path=output2)

        manifest_path = self.workdir / "runs" / "dup_manifest.json"
        manifest_path.parent.mkdir(parents=True, exist_ok=True)
        manifest_path.write_text(json.dumps({"run_id": run_id}), encoding="utf-8")

        _, records, _ = load_upload_queue(manifest_path, working_dir=self.workdir)
        filtered, duplicates = split_records_by_existing_contract_nos(records, {"405/2026"})

        self.assertEqual([record.contract_no for record in duplicates], ["405/2026/CCGD"])
        self.assertEqual([record.contract_no for record in filtered], ["999/2026/CCGD"])

    def test_save_and_load_uploader_env_roundtrip(self):
        save_uploader_env(
            {
                "ND_BASE_URL": "https://example.test",
                "ND_LOGIN_URL": "https://example.test/login",
                "ND_CREATE_URL": "https://example.test/create",
                "ND_USERNAME": "operator",
                "ND_PASSWORD": "secret",
                "ND_STORAGE_STATE_PATH": "nd_storage_state.json",
                "ND_MAX_PREPARED_TABS": "7",
                "ND_POST_PREPARE_DELAY_MS": "2500",
            },
            base_dir=self.workdir,
        )

        settings = load_uploader_settings(self.workdir)

        self.assertEqual(settings.base_url, "https://example.test")
        self.assertEqual(settings.login_url, "https://example.test/login")
        self.assertEqual(settings.create_url, "https://example.test/create")
        self.assertEqual(settings.username, "operator")
        self.assertEqual(settings.password, "secret")
        self.assertEqual(settings.max_prepared_tabs, 7)
        self.assertEqual(settings.post_prepare_delay_ms, 2500)
        self.assertEqual(settings.storage_state_path, (self.workdir / "nd_storage_state.json").resolve())

    def test_get_uploader_setup_status_tracks_storage_state(self):
        save_uploader_env(
            {
                "ND_BASE_URL": "https://example.test",
                "ND_LOGIN_URL": "https://example.test/login",
                "ND_CREATE_URL": "https://example.test/create",
                "ND_USERNAME": "operator",
                "ND_PASSWORD": "secret",
                "ND_STORAGE_STATE_PATH": "nd_storage_state.json",
            },
            base_dir=self.workdir,
        )

        status = get_uploader_setup_status(self.workdir)
        self.assertFalse(status["ready"])
        self.assertFalse(status["storage_state_exists"])

        storage_state = self.workdir / "nd_storage_state.json"
        storage_state.write_text("{}", encoding="utf-8")

        status = get_uploader_setup_status(self.workdir)
        self.assertTrue(status["ready"])
        self.assertTrue(status["storage_state_exists"])
        self.assertEqual(status["storage_state_path"], storage_state.resolve())


class PlaywrightRuntimeProbeTests(unittest.TestCase):
    def test_probe_reports_missing_package(self):
        with mock.patch("tools.upload_lab.playwright_uploader.importlib_util.find_spec", return_value=None):
            ready, message = probe_playwright_runtime()

        self.assertFalse(ready)
        self.assertIn("Chua cai Playwright", message)

    def test_probe_reports_ready_when_sync_api_imports(self):
        with mock.patch("tools.upload_lab.playwright_uploader.importlib_util.find_spec", return_value=object()):
            with mock.patch("tools.upload_lab.playwright_uploader.importlib.import_module", return_value=object()):
                ready, message = probe_playwright_runtime()

        self.assertTrue(ready)
        self.assertIn("san sang", message.lower())


if __name__ == "__main__":
    unittest.main()
