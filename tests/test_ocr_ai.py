import io
import unittest
from unittest import mock

from fastapi import HTTPException, UploadFile

from routers import ocr_ai


def make_upload(filename: str, content: bytes = b"fake-image") -> UploadFile:
    return UploadFile(filename=filename, file=io.BytesIO(content))


class AnalyzeImagesTests(unittest.IsolatedAsyncioTestCase):
    async def test_analyze_images_short_circuits_to_qr(self):
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

        with (
            mock.patch.object(ocr_ai, "try_decode_qr", return_value="qr-text"),
            mock.patch.object(ocr_ai, "parse_cccd_qr", return_value=qr_data),
            mock.patch.object(ocr_ai, "call_vision_images", side_effect=AssertionError("AI should not run")),
        ):
            result = await ocr_ai.analyze_images([upload])

        self.assertEqual(result["summary"]["qr_hits"], 1)
        self.assertEqual(result["summary"]["ai_runs"], 0)
        self.assertEqual(len(result["persons"]), 1)
        self.assertEqual(result["persons"][0]["source_type"], "QR")
        self.assertEqual(result["persons"][0]["so_giay_to"], "012345678901")
        self.assertEqual(result["persons"][0]["_files"], ["qr-card.jpg"])

    async def test_analyze_images_runs_ai_for_non_qr_images(self):
        upload = make_upload("front.jpg")
        ai_output = [
            [
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
        ]

        with (
            mock.patch.object(ocr_ai, "try_decode_qr", return_value=None),
            mock.patch.object(ocr_ai, "resize_to_base64", return_value="b64"),
            mock.patch.object(ocr_ai, "call_vision_images", return_value=ai_output),
        ):
            result = await ocr_ai.analyze_images([upload])

        self.assertEqual(result["summary"]["qr_hits"], 0)
        self.assertEqual(result["summary"]["ai_runs"], 1)
        self.assertEqual(len(result["persons"]), 1)
        person = result["persons"][0]
        self.assertEqual(person["source_type"], "AI")
        self.assertEqual(person["side"], "unknown")
        self.assertEqual(person["ho_ten"], "NGUYEN VAN AN")
        self.assertEqual(person["so_giay_to"], "012345678901")
        self.assertEqual(person["ngay_sinh"], "01/02/1990")
        self.assertEqual(person["ngay_cap"], "03/04/2021")
        self.assertEqual(person["_files"], ["front.jpg"])

    async def test_analyze_images_collects_ai_errors_per_file(self):
        upload = make_upload("broken.jpg")

        with (
            mock.patch.object(ocr_ai, "try_decode_qr", return_value=None),
            mock.patch.object(ocr_ai, "resize_to_base64", return_value="b64"),
            mock.patch.object(
                ocr_ai,
                "call_vision_images",
                return_value=[HTTPException(status_code=502, detail="upstream error")],
            ),
        ):
            result = await ocr_ai.analyze_images([upload])

        self.assertEqual(result["persons"], [])
        self.assertEqual(len(result["errors"]), 1)
        self.assertEqual(result["errors"][0]["filename"], "broken.jpg")
        self.assertEqual(result["errors"][0]["error"], "upstream error")


if __name__ == "__main__":
    unittest.main()
