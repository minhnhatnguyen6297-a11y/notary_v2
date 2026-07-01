import asyncio
from datetime import date
from io import BytesIO
import unittest

import openpyxl
from fastapi import UploadFile
from starlette.requests import Request

from routers.customers import (
    EXCEL_COLUMNS,
    as_input_value,
    consonant_skeleton,
    download_template,
    header_matches_keyword,
    normalize_excel_header,
    parse_date,
    upload_excel,
    validate_customer_form,
)


class DummyQuery:
    def filter(self, *args, **kwargs):
        return self

    def first(self):
        return None


class DummyDb:
    def __init__(self):
        self.added = []

    def query(self, *args, **kwargs):
        return DummyQuery()

    def add(self, obj):
        self.added.append(obj)

    def commit(self):
        return None

    def refresh(self, obj):
        if getattr(obj, "id", None) is None:
            obj.id = len(self.added)

    def rollback(self):
        return None


class CustomerExcelImportTests(unittest.TestCase):
    def test_numeric_year_is_not_treated_as_excel_serial(self):
        self.assertEqual(parse_date(1995), date(1995, 1, 1))
        self.assertEqual(as_input_value(1995, is_date=True), "1995")

    def test_excel_serial_date_still_imports_as_real_date(self):
        self.assertEqual(parse_date(44927), date(2023, 1, 1))

    def test_normalize_excel_header_matches_vietnamese_titles(self):
        self.assertIn("ho va ten", normalize_excel_header("Họ và tên"))
        self.assertIn("ngay sinh", normalize_excel_header("Ngày sinh"))
        self.assertIn("so giay to", normalize_excel_header("Số giấy tờ"))

    def test_header_matches_keyword_for_garbled_question_mark_headers(self):
        self.assertEqual(consonant_skeleton("H? v? t?n"), "hvtn")
        self.assertTrue(header_matches_keyword("H? v? t?n", "ho va ten"))
        self.assertTrue(header_matches_keyword("Gi?i t?nh", "gioi_tinh"))
        self.assertTrue(header_matches_keyword("Ng?y c?p", "ngay_cap"))
        self.assertFalse(header_matches_keyword("??a ch?", "dia_chi"))

    def test_upload_excel_accepts_garbled_vietnamese_headers(self):
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.append(["H? v? t?n", "Gi?i t?nh", "Ng?y sinh", "S? gi?y t?", "Ng?y c?p", "??a ch?"])
        ws.append(["Tran Van A", "Nam", "1988", "", "2021-05-20", "Nam Dinh"])
        buf = BytesIO()
        wb.save(buf)
        buf.seek(0)

        async def run_upload():
            req = Request({"type": "http", "method": "POST", "path": "/customers/upload-excel", "headers": []})
            db = DummyDb()
            response = await upload_excel(req, UploadFile(filename="test.xlsx", file=buf), db)
            return response.context

        context = asyncio.run(run_upload())
        self.assertIsNone(context["error_global"])
        self.assertEqual(context["added"], 1)
        self.assertEqual(len(context["added_customers"]), 1)
        self.assertEqual(context["added_customers"][0]["ho_ten"], "Tran Van A")

    def test_missing_document_number_is_cleaned_to_none(self):
        cleaned, errors = validate_customer_form(
            {
                "ho_ten": "Nguyen Van A",
                "gioi_tinh": "Nam",
                "ngay_sinh": "1995",
                "ngay_chet": "",
                "so_giay_to": "",
                "ngay_cap": "",
                "dia_chi": "",
            },
            DummyDb(),
        )

        self.assertEqual(errors, {})
        self.assertIsNone(cleaned["so_giay_to"])

    def test_template_formats_date_columns_as_text(self):
        async def collect_response_body():
            chunks = []
            response = download_template()
            async for chunk in response.body_iterator:
                chunks.append(chunk)
            return b"".join(chunks)

        body = asyncio.run(collect_response_body())
        wb = openpyxl.load_workbook(BytesIO(body))
        ws = wb.active

        for idx, field in enumerate(EXCEL_COLUMNS, start=1):
            if field in {"ngay_sinh", "ngay_chet", "ngay_cap"}:
                self.assertEqual(ws.cell(row=2, column=idx).number_format, "@")


if __name__ == "__main__":
    unittest.main()
