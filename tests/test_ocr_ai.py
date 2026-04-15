import io
import unittest
from unittest import mock

from fastapi import HTTPException, UploadFile

from routers import ocr_ai


def make_upload(filename: str, content: bytes = b"fake-image") -> UploadFile:
    return UploadFile(filename=filename, file=io.BytesIO(content))


class AnalyzeImagesTests(unittest.IsolatedAsyncioTestCase):
    def test_normalize_property_doc_extracts_core_fields(self):
        lines = [
            "GIAY CHUNG NHAN",
            "QUYEN SU DUNG DAT, QUYEN SO HUU TAI SAN GAN LIEN VOI DAT",
            "So vao so cap GCN: VP00166",
            "AA07488103",
            "Thua dat: 66",
            "To ban do so: 29",
            "Dia chi: Thon Phuong Nhi, xa Tan Minh, tinh Ninh Binh",
            "Nam Dinh, ngay 10/07/2023",
            "VAN PHONG DANG KY DAT DAI",
        ]
        doc = ocr_ai._normalize_property_ocr_doc(lines, "property.jpg")
        self.assertEqual(doc["doc_type"], "property")
        self.assertEqual(doc["data"]["so_serial"], "AA07488103")
        self.assertEqual(doc["data"]["so_vao_so"], "VP00166")
        self.assertEqual(doc["data"]["so_thua_dat"], "66")
        self.assertEqual(doc["data"]["so_to_ban_do"], "29")
        self.assertEqual(doc["data"]["ngay_cap"], "10/07/2023")

    def test_normalize_property_doc_unknown_for_non_property(self):
        doc = ocr_ai._normalize_property_ocr_doc(["Hoa don dien tu", "Tong tien: 123000"], "bill.jpg")
        self.assertEqual(doc["doc_type"], "unknown")

    def test_parse_person_mrz_extracts_expected_fields(self):
        mrz = ocr_ai._parse_person_mrz(
            [
                "IDVNM0970165684036097016568<<9",
                "9702020M3702028VNM<<<<<<<<<<<0",
                "VU<<QUOC<PHONG<<<<<<<<<<<<<<",
            ]
        )
        self.assertEqual(mrz["so_giay_to"], "036097016568")
        self.assertEqual(mrz["ho_ten"], "VU QUOC PHONG")
        self.assertEqual(mrz["ngay_sinh"], "02/02/1997")
        self.assertEqual(mrz["gioi_tinh"], "Nam")

    def test_extract_address_strips_expiry_label_noise(self):
        lines = [
            "Nơi thường trú / Place of residence:",
            "Thôn Tam Yên Bằng, Ý Yên, Nam Định, Cơ quan cấp / Date of expiry:",
        ]
        self.assertEqual(ocr_ai._extract_address(lines), "Thôn Tam Yên Bằng, Ý Yên, Nam Định")

    def test_extract_address_strips_expiry_noise_same_line(self):
        lines = [
            "Nơi thường trú / Place of residence: Yên Tiến, Ý Yên, Nam Định, Cơ quan cấp / Date of expiry:",
        ]
        self.assertEqual(ocr_ai._extract_address(lines), "Yên Tiến, Ý Yên, Nam Định")

    def test_extract_native_ocr_lines_from_text_payload(self):
        payload = {
            "output": {
                "choices": [
                    {
                        "message": {
                            "content": [
                                {"text": "LINE 1\\nLINE 2"},
                            ]
                        }
                    }
                ]
            }
        }
        self.assertEqual(ocr_ai._extract_native_ocr_lines(payload), ["LINE 1", "LINE 2"])

    def test_normalize_native_doc_prefers_mrz_on_back(self):
        lines = [
            "Pham Cong Nguyen",
            "IDVNM1790096961036179009696<<6",
            "7901209F3901201VNM<<<<<<<<<<<4",
            "DUONG<<THI<XUAN<<<<<<<<<<<<<<<",
        ]
        doc = ocr_ai._normalize_native_ocr_doc(lines, "back.jpg")
        self.assertEqual(doc["doc_type"], "person")
        self.assertEqual(doc["side"], "back")
        self.assertEqual(doc["data"]["ho_ten"], "DUONG THI XUAN")
        self.assertEqual(doc["data"]["so_giay_to"], "036179009696")

    async def test_analyze_images_prefers_qr_over_ai_result(self):
        upload = make_upload("qr-card.jpg")
        qr_data = {
            "so_giay_to": "012345678901",
            "ho_ten": "NGUYEN VAN AN",
            "ngay_sinh": "01/02/1990",
            "gioi_tinh": "Nam",
            "dia_chi": "123 LE LOI",
            "ngay_cap": "03/04/2021",
            "ngay_het_han": "",
        }
        with (
            mock.patch.object(ocr_ai, "try_decode_qr", return_value="qr-text"),
            mock.patch.object(ocr_ai, "parse_cccd_qr", return_value=qr_data),
            mock.patch.object(ocr_ai, "_get_api_key", return_value="test-key"),
            mock.patch.object(ocr_ai, "_call_qwen_native_ocr_single", new=mock.AsyncMock(return_value=["WRONG OCR"])),
        ):
            result = await ocr_ai.analyze_images([upload])

        self.assertEqual(result["summary"]["qr_hits"], 1)
        self.assertEqual(result["summary"]["ai_runs"], 0)
        self.assertEqual(len(result["persons"]), 1)
        self.assertEqual(result["persons"][0]["source_type"], "QR")

    async def test_analyze_images_runs_native_ocr_for_non_qr_images(self):
        upload = make_upload("front.jpg")
        lines = [
            "So/No: 012345678901",
            "Ho va ten / Full name: NGUYEN VAN AN",
            "Ngay sinh / Date of birth: 01/02/1990",
            "Gioi tinh / Sex: Nam",
            "Noi thuong tru / Place of residence: 123 LE LOI",
            "Ngay cap / Date of issue: 03/04/2021",
        ]
        with (
            mock.patch.object(ocr_ai, "try_decode_qr", return_value=None),
            mock.patch.object(ocr_ai, "_get_api_key", return_value="test-key"),
            mock.patch.object(ocr_ai, "_call_qwen_native_ocr_single", new=mock.AsyncMock(return_value=lines)),
        ):
            result = await ocr_ai.analyze_images([upload])

        self.assertEqual(result["summary"]["qr_hits"], 0)
        self.assertEqual(result["summary"]["ai_runs"], 1)
        self.assertEqual(len(result["persons"]), 1)
        person = result["persons"][0]
        self.assertEqual(person["source_type"], "AI")
        self.assertEqual(person["so_giay_to"], "012345678901")
        self.assertEqual(person["ho_ten"], "NGUYEN VAN AN")

    async def test_analyze_images_collects_native_errors_per_file(self):
        upload = make_upload("broken.jpg")
        with (
            mock.patch.object(ocr_ai, "try_decode_qr", return_value=None),
            mock.patch.object(ocr_ai, "_get_api_key", return_value="test-key"),
            mock.patch.object(
                ocr_ai,
                "_call_qwen_native_ocr_single",
                new=mock.AsyncMock(side_effect=HTTPException(status_code=502, detail="upstream error")),
            ),
        ):
            result = await ocr_ai.analyze_images([upload])

        self.assertEqual(result["persons"], [])
        self.assertEqual(len(result["errors"]), 1)
        self.assertEqual(result["errors"][0]["filename"], "broken.jpg")
        self.assertEqual(result["errors"][0]["error"], "upstream error")

    async def test_analyze_images_pairs_front_back_by_id(self):
        front = make_upload("front.jpg")
        back = make_upload("back.jpg")
        outputs = [
            [
                "So/No: 036179009696",
                "Ho va ten / Full name: DUONG THI XUAN",
                "Ngay sinh / Date of birth: 20/01/1979",
            ],
            [
                "IDVNM1790096961036179009696<<6",
                "7901209F3901201VNM<<<<<<<<<<<4",
                "DUONG<<THI<XUAN<<<<<<<<<<<<<<<",
                "Noi cu tru / Place of residence: Quyet Phong, Yen Ninh, Y Yen, Nam Dinh",
            ],
        ]

        async def fake_call(*args, **kwargs):
            return outputs.pop(0)

        with (
            mock.patch.object(ocr_ai, "try_decode_qr", return_value=None),
            mock.patch.object(ocr_ai, "_get_api_key", return_value="test-key"),
            mock.patch.object(ocr_ai, "_call_qwen_native_ocr_single", new=mock.AsyncMock(side_effect=fake_call)),
        ):
            result = await ocr_ai.analyze_images([front, back])

        self.assertEqual(result["summary"]["persons"], 1)
        person = result["persons"][0]
        self.assertEqual(person["so_giay_to"], "036179009696")
        self.assertTrue(person["paired"])
        self.assertEqual(len(person.get("_files", [])), 2)

    async def test_analyze_property_images_returns_properties_only(self):
        uploads = [make_upload("property-1.jpg"), make_upload("unknown-1.jpg")]
        outputs = [
            [
                "GIAY CHUNG NHAN",
                "QUYEN SU DUNG DAT",
                "So A 692942",
                "So vao so cap Giay chung nhan: VP56315",
                "Dia chi: Xa Yen Binh, huyen Y Yen, tinh Nam Dinh",
            ],
            ["Anh chup khong phai so do"],
        ]

        async def fake_call(*args, **kwargs):
            return outputs.pop(0)

        with (
            mock.patch.object(ocr_ai, "_get_api_key", return_value="test-key"),
            mock.patch.object(ocr_ai, "_call_qwen_native_ocr_single", new=mock.AsyncMock(side_effect=fake_call)),
        ):
            result = await ocr_ai.analyze_property_images(uploads)

        self.assertEqual(result["persons"], [])
        self.assertEqual(len(result["properties"]), 1)
        self.assertEqual(result["properties"][0]["so_serial"], "A 692942")
        self.assertEqual(result["summary"]["properties"], 1)
        self.assertEqual(result["summary"]["unknowns"], 1)

    async def test_analyze_property_pair_merges_front_back_with_precedence(self):
        front = make_upload("front.jpg")
        back = make_upload("back.jpg")
        outputs = [
            [
                "GIAY CHUNG NHAN",
                "QUYEN SU DUNG DAT",
                "So A 692942",
                "Thua dat: 66",
                "To ban do so: 29",
                "Dia chi: Xa Yen Binh, huyen Y Yen, tinh Nam Dinh",
            ],
            [
                "GIAY CHUNG NHAN",
                "So vao so cap GCN: VP00166",
                "Nam Dinh, ngay 10/07/2023",
                "VAN PHONG DANG KY DAT DAI",
            ],
        ]

        async def fake_call(*args, **kwargs):
            return outputs.pop(0)

        with (
            mock.patch.object(ocr_ai, "_get_api_key", return_value="test-key"),
            mock.patch.object(ocr_ai, "_call_qwen_native_ocr_single", new=mock.AsyncMock(side_effect=fake_call)),
            mock.patch.object(ocr_ai, "_should_retry_property_rotate", return_value=False),
        ):
            result = await ocr_ai.analyze_property_pair(front, back)

        prop = result["property"]
        self.assertEqual(prop["so_serial"], "A 692942")
        self.assertEqual(prop["so_vao_so"], "VP00166")
        self.assertEqual(prop["ngay_cap"], "10/07/2023")
        self.assertEqual(prop["so_thua_dat"], "66")
        self.assertEqual(prop["so_to_ban_do"], "29")
        self.assertEqual(result["per_side"]["front"]["doc_type"], "property")
        self.assertEqual(result["per_side"]["back"]["doc_type"], "property")

    def test_pair_persons_allows_fuzzy_id_when_name_matches(self):
        front = {
            "ho_ten": "DƯƠNG THỊ XUÂN",
            "so_giay_to": "036179009696",
            "ngay_sinh": "20/01/1979",
            "gioi_tinh": "Nữ",
            "dia_chi": "Quyet Phong",
            "ngay_cap": "",
            "ngay_het_han": "",
            "_source": "AI",
            "source_type": "AI",
            "side": "front",
            "_files": ["front.jpg"],
            "_qr": False,
            "field_sources": {},
            "warnings": [],
        }
        back = {
            "ho_ten": "DUONG THI XUAN",
            "so_giay_to": "036179009697",
            "ngay_sinh": "20/01/1979",
            "gioi_tinh": "Nu",
            "dia_chi": "",
            "ngay_cap": "25/03/2021",
            "ngay_het_han": "",
            "_source": "AI",
            "source_type": "AI",
            "side": "back",
            "_files": ["back.jpg"],
            "_qr": False,
            "field_sources": {},
            "warnings": [],
        }
        merged = ocr_ai._pair_persons([front, back])
        self.assertEqual(len(merged), 1)
        self.assertTrue(merged[0]["paired"])
        self.assertEqual(merged[0]["side"], "front_back")
        self.assertEqual(len(merged[0].get("_files", [])), 2)

    def test_pair_persons_rejects_fuzzy_id_when_mismatch_too_high(self):
        front = {
            "ho_ten": "DƯƠNG THỊ XUÂN",
            "so_giay_to": "036179009696",
            "ngay_sinh": "20/01/1979",
            "gioi_tinh": "Nữ",
            "dia_chi": "Quyet Phong",
            "ngay_cap": "",
            "ngay_het_han": "",
            "_source": "AI",
            "source_type": "AI",
            "side": "front",
            "_files": ["front.jpg"],
            "_qr": False,
            "field_sources": {},
            "warnings": [],
        }
        back = {
            "ho_ten": "DUONG THI XUAN",
            "so_giay_to": "036179009786",
            "ngay_sinh": "20/01/1979",
            "gioi_tinh": "Nu",
            "dia_chi": "",
            "ngay_cap": "25/03/2021",
            "ngay_het_han": "",
            "_source": "AI",
            "source_type": "AI",
            "side": "back",
            "_files": ["back.jpg"],
            "_qr": False,
            "field_sources": {},
            "warnings": [],
        }
        merged = ocr_ai._pair_persons([front, back])
        self.assertEqual(len(merged), 2)
        self.assertFalse(merged[0]["paired"])
        self.assertFalse(merged[1]["paired"])


if __name__ == "__main__":
    unittest.main()
