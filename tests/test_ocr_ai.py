import io
import unittest
from unittest import mock

from fastapi import HTTPException, UploadFile

from routers import ocr_ai


def make_upload(filename: str, content: bytes = b"fake-image") -> UploadFile:
    return UploadFile(filename=filename, file=io.BytesIO(content))


class AnalyzeImagesTests(unittest.IsolatedAsyncioTestCase):
    def test_mrz_date_to_display_returns_empty_for_malformed_segment(self):
        self.assertEqual(ocr_ai._mrz_date_to_display("82<<20", birth=True), "")

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
        self.assertEqual(person["ngay_cap"], "")
        self.assertEqual(person["_files"], ["front.jpg"])
        self.assertFalse(person["paired"])

    async def test_analyze_images_pairs_ai_front_and_back_after_extract(self):
        uploads = [make_upload("front.jpg"), make_upload("back.jpg")]
        ai_output = [
            [
                {
                    "doc_type": "cccd_front",
                    "data": {
                        "doc_side": "front",
                        "doc_version": "old",
                        "ho_ten": "TRINH THI TUYET",
                        "so_giay_to": "036168006276",
                        "ngay_sinh": "02/06/1968",
                        "gioi_tinh": "Nu",
                        "dia_chi": "Thi tran Lam, Y Yen, Nam Dinh",
                    },
                }
            ],
            [
                {
                    "doc_type": "cccd_back",
                    "data": {
                        "doc_side": "back",
                        "doc_version": "old",
                        "so_giay_to": "1680062760036168006276",
                        "so_giay_to_mrz": "036168006276",
                        "ngay_cap": "12/03/2023",
                    },
                }
            ],
        ]

        with (
            mock.patch.object(ocr_ai, "try_decode_qr", return_value=None),
            mock.patch.object(ocr_ai, "resize_to_base64", return_value="b64"),
            mock.patch.object(ocr_ai, "call_vision_images", return_value=ai_output),
        ):
            result = await ocr_ai.analyze_images(uploads)

        self.assertEqual(len(result["persons"]), 1)
        self.assertEqual(result["summary"]["paired_persons"], 1)
        person = result["persons"][0]
        self.assertTrue(person["paired"])
        self.assertEqual(person["so_giay_to"], "036168006276")
        self.assertEqual(person["ngay_cap"], "12/03/2023")
        self.assertEqual(set(person["_files"]), {"front.jpg", "back.jpg"})

    async def test_analyze_images_pairs_qr_hit_with_matching_ai_front(self):
        uploads = [make_upload("front.jpg"), make_upload("back-qr.jpg")]
        qr_data = {
            "so_giay_to": "012345678901",
            "ho_ten": "NGUYEN VAN AN",
            "ngay_sinh": "01/02/1990",
            "gioi_tinh": "Nam",
            "dia_chi": "123 LE LOI",
            "ngay_cap": "03/04/2021",
            "ngay_het_han": "",
        }
        ai_output = [
            [
                {
                    "doc_type": "cccd_front",
                    "data": {
                        "doc_side": "front",
                        "doc_version": "old",
                        "ho_ten": "NGUYEN VAN AN",
                        "so_giay_to": "012345678900",
                        "ngay_sinh": "01/02/1990",
                        "gioi_tinh": "Nam",
                        "dia_chi": "123 LE LOI",
                    },
                }
            ]
        ]

        with (
            mock.patch.object(ocr_ai, "try_decode_qr", side_effect=[None, "qr-text"]),
            mock.patch.object(ocr_ai, "parse_cccd_qr", return_value=qr_data),
            mock.patch.object(ocr_ai, "resize_to_base64", return_value="b64"),
            mock.patch.object(ocr_ai, "call_vision_images", return_value=ai_output),
        ):
            result = await ocr_ai.analyze_images(uploads)

        self.assertEqual(len(result["persons"]), 1)
        self.assertEqual(result["summary"]["qr_hits"], 1)
        self.assertEqual(result["summary"]["paired_persons"], 1)
        person = result["persons"][0]
        self.assertEqual(person["so_giay_to"], "012345678901")
        self.assertTrue(person["_qr"])
        self.assertEqual(set(person["_files"]), {"front.jpg", "back-qr.jpg"})
        self.assertEqual(person["_source"], "cccd+back")

    async def test_analyze_images_merges_back_group_using_mrz_signature_when_ai_key_is_wrong(self):
        uploads = [make_upload("front.jpg"), make_upload("back.jpg")]
        ai_output = [
            [
                {
                    "doc_type": "cccd_front",
                    "data": {
                        "doc_side": "front",
                        "doc_version": "new",
                        "ho_ten": "NGUYEN VAN NAM",
                        "so_giay_to": "036082000989",
                        "ngay_sinh": "02/02/1982",
                        "gioi_tinh": "Nam",
                    },
                }
            ],
            [
                {
                    "doc_type": "cccd_back",
                    "data": {
                        "doc_side": "back",
                        "doc_version": "new",
                        "so_giay_to_mrz": "0820000989",
                        "mrz_line1": "IDVNM082000098920360820000989<7",
                        "mrz_line2": "8202028M4202020VNM<<<<<<<<<6",
                        "mrz_line3": "NGUYEN<VAN<NAM<<<<<<",
                        "ngay_cap": "02/07/2021",
                    },
                }
            ],
        ]

        with (
            mock.patch.object(ocr_ai, "try_decode_qr", return_value=None),
            mock.patch.object(ocr_ai, "resize_to_base64", return_value="b64"),
            mock.patch.object(ocr_ai, "call_vision_images", return_value=ai_output),
        ):
            result = await ocr_ai.analyze_images(uploads)

        self.assertEqual(len(result["persons"]), 1)
        self.assertEqual(result["summary"]["paired_persons"], 1)
        person = result["persons"][0]
        self.assertEqual(person["so_giay_to"], "036082000989")
        self.assertEqual(person["ngay_cap"], "02/07/2021")
        self.assertEqual(set(person["_files"]), {"front.jpg", "back.jpg"})

    async def test_analyze_images_extracts_cccd_from_secondary_mrz_line_and_pairs(self):
        uploads = [make_upload("front.jpg"), make_upload("back.jpg")]
        ai_output = [
            [
                {
                    "doc_type": "cccd_front",
                    "data": {
                        "doc_side": "front",
                        "doc_version": "old",
                        "ho_ten": "DINH THI THOM",
                        "so_giay_to": "036159002189",
                        "ngay_sinh": "10/06/1959",
                        "gioi_tinh": "Nu",
                        "dia_chi": "YEN TIEN, Y YEN, NAM DINH",
                    },
                }
            ],
            [
                {
                    "doc_type": "cccd_back",
                    "data": {
                        "doc_side": "back",
                        "doc_version": "old",
                        "ho_ten": "TO VAN HUE",
                        "mrz_line1": "IDVNM1590021893",
                        "mrz_line2": "036159002189<<8",
                        "mrz_line3": "5906107F9912315VNM<<<<<<4",
                        "ngay_cap": "22/12/2021",
                    },
                }
            ],
        ]

        with (
            mock.patch.object(ocr_ai, "try_decode_qr", return_value=None),
            mock.patch.object(ocr_ai, "resize_to_base64", return_value="b64"),
            mock.patch.object(ocr_ai, "call_vision_images", return_value=ai_output),
        ):
            result = await ocr_ai.analyze_images(uploads)

        self.assertEqual(len(result["persons"]), 1)
        self.assertEqual(result["summary"]["paired_persons"], 1)
        person = result["persons"][0]
        self.assertEqual(person["so_giay_to"], "036159002189")
        self.assertEqual(person["ho_ten"], "DINH THI THOM")
        self.assertEqual(person["ngay_cap"], "22/12/2021")
        self.assertEqual(set(person["_files"]), {"front.jpg", "back.jpg"})

    async def test_analyze_images_merges_front_and_back_with_same_signature_without_valid_key(self):
        uploads = [make_upload("front.jpg"), make_upload("back.jpg")]
        ai_output = [
            [
                {
                    "doc_type": "cccd_front",
                    "data": {
                        "doc_side": "front",
                        "doc_version": "old",
                        "ho_ten": "PHAM NGOC HUY",
                        "so_giay_to": "03809202299",
                        "ngay_sinh": "12/05/1992",
                        "gioi_tinh": "Nam",
                        "dia_chi": "HA DONG, HA NOI",
                    },
                }
            ],
            [
                {
                    "doc_type": "cccd_back",
                    "data": {
                        "doc_side": "back",
                        "doc_version": "old",
                        "mrz_line1": "IDVNM09202299703809202299",
                        "mrz_line2": "9205129M320512",
                        "mrz_line3": "PHAM<<NGOC<HUY",
                        "so_giay_to_mrz": "092022997038",
                    },
                }
            ],
        ]

        with (
            mock.patch.object(ocr_ai, "try_decode_qr", return_value=None),
            mock.patch.object(ocr_ai, "resize_to_base64", return_value="b64"),
            mock.patch.object(ocr_ai, "call_vision_images", return_value=ai_output),
        ):
            result = await ocr_ai.analyze_images(uploads)

        self.assertEqual(len(result["persons"]), 1)
        self.assertEqual(result["summary"]["paired_persons"], 1)
        person = result["persons"][0]
        self.assertEqual(person["ho_ten"], "PHAM NGOC HUY")
        self.assertEqual(person["ngay_sinh"], "12/05/1992")
        self.assertEqual(person["so_giay_to"], "03809202299")
        self.assertEqual(set(person["_files"]), {"front.jpg", "back.jpg"})

    async def test_analyze_images_merges_back_with_digit_overlap_when_name_is_missing(self):
        uploads = [make_upload("front.jpg"), make_upload("back.jpg")]
        ai_output = [
            [
                {
                    "doc_type": "cccd_front",
                    "data": {
                        "doc_side": "front",
                        "doc_version": "old",
                        "ho_ten": "VU QUOC PHONG",
                        "so_giay_to": "036097016568",
                        "ngay_sinh": "02/02/1997",
                        "gioi_tinh": "Nam",
                    },
                }
            ],
            [
                {
                    "doc_type": "cccd_back",
                    "data": {
                        "doc_side": "back",
                        "doc_version": "new",
                        "mrz_line1": "IDVNM0970165684",
                        "mrz_line2": "97020203702028",
                        "mrz_line3": "9VUCQUOCPHONG",
                        "so_giay_to_mrz": "0970165684",
                        "ngay_cap": "13/07/2023",
                    },
                }
            ],
        ]

        with (
            mock.patch.object(ocr_ai, "try_decode_qr", return_value=None),
            mock.patch.object(ocr_ai, "resize_to_base64", return_value="b64"),
            mock.patch.object(ocr_ai, "call_vision_images", return_value=ai_output),
        ):
            result = await ocr_ai.analyze_images(uploads)

        self.assertEqual(len(result["persons"]), 1)
        self.assertEqual(result["summary"]["paired_persons"], 1)
        person = result["persons"][0]
        self.assertEqual(person["so_giay_to"], "036097016568")
        self.assertEqual(person["ngay_sinh"], "02/02/1997")
        self.assertEqual(person["ngay_cap"], "13/07/2023")
        self.assertEqual(set(person["_files"]), {"front.jpg", "back.jpg"})

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
