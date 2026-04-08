import io
import unittest
from unittest.mock import AsyncMock, patch

from fastapi import UploadFile

from routers import ocr


def make_upload(filename: str, content: bytes = b"fake-image") -> UploadFile:
    return UploadFile(filename=filename, file=io.BytesIO(content))


def make_settings() -> dict:
    return {
        "timing_log": False,
        "preprocess_workers": 0,
        "preprocess_warmup": False,
    }


class AnalyzeImagesTests(unittest.IsolatedAsyncioTestCase):
    async def test_analyze_images_groups_preprocessed_qr_row(self):
        upload = make_upload("qr-card.jpg")
        qr_data = {
            "so_giay_to": "012345678901",
            "ho_ten": "NGUYEN VAN AN",
            "ngay_sinh": "01/02/1990",
            "gioi_tinh": "Nam",
            "dia_chi": "123 LE LOI",
            "ngay_cap": "03/04/2021",
            "ngay_het_han": "03/04/2031",
        }
        row = ocr._build_empty_row(0, "qr-card.jpg")
        row["doc_type"] = "cccd_front"
        row["profile"] = ocr.DOC_PROFILE_FRONT_OLD
        row["state"] = ocr.TRIAGE_STATE_FRONT_OLD
        row["qr_text"] = "qr-text"
        row["qr_data"] = qr_data
        row["has_qr"] = True
        ocr._apply_source_merge(row["data"], row["field_sources"], qr_data, source="qr", profile=row["profile"])
        ocr._sync_row_identity(row)

        with (
            patch.object(ocr, "_get_ai_ocr_settings", return_value=make_settings()),
            patch.object(ocr, "_preprocess_ai_file_items", new=AsyncMock(return_value=([row], []))),
            patch.object(ocr, "_build_ai_plan", return_value=[]),
            patch.object(ocr, "_build_escalation_plans", return_value=[]),
            patch.object(ocr, "_execute_ai_plans", new=AsyncMock(side_effect=AssertionError("AI should not run"))),
        ):
            result = await ocr.analyze_images([upload])

        self.assertEqual(result["summary"]["total_images"], 1)
        self.assertEqual(result["summary"]["cccd_fronts"], 1)
        self.assertEqual(len(result["persons"]), 1)
        self.assertEqual(result["persons"][0]["so_giay_to"], "012345678901")
        self.assertTrue(result["persons"][0]["_qr"])
        self.assertEqual(result["persons"][0]["_files"], ["qr-card.jpg"])

    async def test_analyze_images_applies_ai_results_for_non_qr_images(self):
        upload = make_upload("front.jpg")
        row = ocr._build_empty_row(0, "front.jpg")
        row["state"] = ocr.TRIAGE_STATE_FRONT_UNKNOWN
        row["profile"] = ocr.DOC_PROFILE_UNKNOWN
        plans = [{"record_index": 0, "mode": "full"}]
        ai_results = {
            0: [
                {
                    "doc_type": "cccd_front",
                    "data": {
                        "ho_ten": " NGUYEN VAN AN ",
                        "so_giay_to": "0123 456 789 01",
                        "ngay_sinh": "1-2-1990",
                        "gioi_tinh": "male",
                        "dia_chi": " 123 LE LOI ",
                        "ngay_cap": "3.4.2021",
                        "ngay_het_han": "",
                    },
                }
            ]
        }

        with (
            patch.object(ocr, "_get_ai_ocr_settings", return_value=make_settings()),
            patch.object(ocr, "_preprocess_ai_file_items", new=AsyncMock(return_value=([row], []))),
            patch.object(ocr, "_build_ai_plan", return_value=plans),
            patch.object(ocr, "_build_escalation_plans", return_value=[]),
            patch.object(ocr, "_execute_ai_plans", new=AsyncMock(return_value=ai_results)),
        ):
            result = await ocr.analyze_images([upload])

        self.assertEqual(result["summary"]["total_images"], 1)
        self.assertEqual(result["summary"]["cccd_fronts"], 1)
        self.assertEqual(len(result["persons"]), 1)
        person = result["persons"][0]
        self.assertEqual(person["ho_ten"], "NGUYEN VAN AN")
        self.assertEqual(person["so_giay_to"], "012345678901")
        self.assertEqual(person["ngay_sinh"], "01/02/1990")
        self.assertEqual(person["ngay_cap"], "")
        self.assertEqual(person["_files"], ["front.jpg"])

    async def test_analyze_images_collects_preprocess_errors(self):
        upload = make_upload("broken.jpg")

        with (
            patch.object(ocr, "_get_ai_ocr_settings", return_value=make_settings()),
            patch.object(
                ocr,
                "_preprocess_ai_file_items",
                new=AsyncMock(return_value=([], [{"filename": "broken.jpg", "error": "upstream error"}])),
            ),
        ):
            result = await ocr.analyze_images([upload])

        self.assertEqual(result["persons"], [])
        self.assertEqual(len(result["errors"]), 1)
        self.assertEqual(result["errors"][0]["filename"], "broken.jpg")
        self.assertEqual(result["errors"][0]["error"], "upstream error")


if __name__ == "__main__":
    unittest.main()
