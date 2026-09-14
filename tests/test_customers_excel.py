import asyncio
from datetime import date
from io import BytesIO
import unittest

import openpyxl

from routers.customers import (
    EXCEL_COLUMNS,
    as_input_value,
    download_template,
    normalize_excel_header,
    consonant_skeleton,
    header_matches_keyword,
    parse_date,
    validate_customer_form,
    quick_update,
    inline_create,
)


class DummyQuery:
    def filter(self, *args, **kwargs):
        return self

    def first(self):
        return None


class DummyDb:
    def query(self, *args, **kwargs):
        return DummyQuery()


class CustomerExcelImportTests(unittest.TestCase):
    def test_quick_update_empty_fields_clear_and_omitted_fields_remain(self):
        customer = type("Customer", (), {"id": 1, "ho_ten": "A", "gioi_tinh": "Nam", "ngay_sinh": date(1990, 1, 1), "ngay_chet": None, "so_giay_to": "123", "ngay_cap": None, "dia_chi": "Old"})()
        class Db:
            def get(self, *_args): return customer
            def commit(self): pass
            def refresh(self, *_args): pass
        quick_update(1, ho_ten="", gioi_tinh=None, ngay_sinh=None, ngay_chet=None, so_giay_to=None, ngay_cap=None, dia_chi="", db=Db())
        self.assertEqual(customer.ho_ten, "")
        self.assertIsNone(customer.dia_chi)
        self.assertEqual(customer.gioi_tinh, "Nam")
        self.assertEqual(customer.so_giay_to, "123")

    def test_inline_create_existing_preserves_omitted_and_clears_submitted_empty(self):
        customer = type("Customer", (), {"id": 1, "ho_ten": "Old", "gioi_tinh": "Nam", "ngay_sinh": date(1990, 1, 1), "ngay_chet": None, "so_giay_to": "123", "ngay_cap": date(2020, 1, 1), "dia_chi": "Old"})()
        class Query:
            def filter(self, *_args): return self
            def first(self): return customer
        class Db:
            def query(self, *_args): return Query()
            def commit(self): pass
            def refresh(self, *_args): pass
        inline_create(ho_ten="New", so_giay_to="123", gioi_tinh=None, ngay_sinh=None, ngay_chet=None, ngay_cap=None, dia_chi=None, db=Db())
        self.assertEqual(customer.gioi_tinh, "Nam")
        self.assertEqual(customer.dia_chi, "Old")
        inline_create(ho_ten="New", so_giay_to="123", gioi_tinh="", ngay_sinh="", ngay_chet="", ngay_cap="", dia_chi="", db=Db())
        self.assertIsNone(customer.gioi_tinh)
        self.assertIsNone(customer.ngay_sinh)
        self.assertIsNone(customer.ngay_cap)
        self.assertIsNone(customer.dia_chi)

    def test_numeric_year_is_not_treated_as_excel_serial(self):
        self.assertEqual(parse_date(1995), date(1995, 1, 1))
        self.assertEqual(as_input_value(1995, is_date=True), "1995")

    def test_excel_serial_date_still_imports_as_real_date(self):
        self.assertEqual(parse_date(44927), date(2023, 1, 1))

    def test_normalize_excel_header_matches_vietnamese_titles(self):
        self.assertIn("ho va ten", normalize_excel_header("Họ và tên"))
        self.assertIn("ngay sinh", normalize_excel_header("Ngày sinh"))
        self.assertIn("so giay to", normalize_excel_header("Số giấy tờ"))

    def test_garbled_headers_match_by_consonant_skeleton(self):
        self.assertEqual(consonant_skeleton("H? v? t?n"), "hvtn")
        self.assertTrue(header_matches_keyword("H? v? t?n", "ho va ten"))
        self.assertTrue(header_matches_keyword("Gi?i t?nh", "gioi_tinh"))

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
