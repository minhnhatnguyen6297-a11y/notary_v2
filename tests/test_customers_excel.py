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
    parse_date,
    validate_customer_form,
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
    def test_numeric_year_is_not_treated_as_excel_serial(self):
        self.assertEqual(parse_date(1995), date(1995, 1, 1))
        self.assertEqual(as_input_value(1995, is_date=True), "1995")

    def test_excel_serial_date_still_imports_as_real_date(self):
        self.assertEqual(parse_date(44927), date(2023, 1, 1))

    def test_normalize_excel_header_matches_vietnamese_titles(self):
        self.assertIn("ho va ten", normalize_excel_header("Họ và tên"))
        self.assertIn("ngay sinh", normalize_excel_header("Ngày sinh"))
        self.assertIn("so giay to", normalize_excel_header("Số giấy tờ"))

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
