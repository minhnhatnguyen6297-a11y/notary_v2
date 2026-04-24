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

    def test_normalize_property_doc_handles_noisy_registry_and_plot_lines(self):
        lines = [
            "II. Thửa đất, nhà ở và tài sản khác gắn liền với đất",
            "1. Thửa đất:",
            "a) Thửa đất: 66",
            "b) Địa chỉ: Tỉnh Lộ 485, xã Yên Bình, huyện Yên Yên, tỉnh Nam Định",
            "Nam Định, ngày 10 tháng 3 năm 2018",
            "VĂN PHÒNG ĐĂNG KÝ ĐẤT ĐAI",
            "Số vạch số cấp GCN: VP00166 10423",
        ]
        doc = ocr_ai._normalize_property_ocr_doc(lines, "property-back.jpg", side="back")
        self.assertEqual(doc["doc_type"], "property")
        self.assertEqual(doc["data"]["so_vao_so"], "VP00166")
        self.assertEqual(doc["data"]["so_thua_dat"], "66")

    def test_extract_property_registry_no_rejects_non_code_followup(self):
        lines = [
            "Vào sổ cấp giấy chứng nhận",
            "Quyền sử dụng đất",
            "Số ...........QSDD/...........",
        ]
        self.assertEqual(ocr_ai._extract_property_registry_no(lines), "")

    def test_extract_property_authority_prefers_real_issuing_agency(self):
        lines = [
            "Ninh Binh, ngay 07 thang 04 nam 2026",
            "VAN PHONG DANG KY DAT DAI NAM DINH",
            "KT. GIAM DOC",
            "PHO GIAM DOC",
        ]
        self.assertEqual(
            ocr_ai._extract_property_authority(lines, "07/04/2026"),
            "VAN PHONG DANG KY DAT DAI NAM DINH",
        )

    def test_extract_property_authority_rejects_warning_sentence(self):
        lines = [
            "Nguoi duoc cap Giay chung nhan khong duoc sua chua, tay xoa hoac bo sung bat ky noi dung nao trong Giay chung nhan; khi bi mat hoac hu hong Giay chung nhan phai khai bao ngay voi co quan cap Giay.",
            "So vao so cap Giay chung nhan: VP56315",
        ]
        self.assertEqual(ocr_ai._extract_property_authority(lines, ""), "")

    def test_should_rescue_property_issue_date_when_footer_year_is_newer(self):
        doc = {
            "doc_type": "property",
            "side": "back",
            "data": {
                "ngay_cap": "10/03/2018",
                "co_quan_cap": "VAN PHONG DANG KY DAT DAI",
            },
            "text_lines": [
                "Nam Dinh, ngay 10 thang 3 nam 2018",
                "VAN PHONG DANG KY DAT DAI",
                "SO DO DUOC BIEN TAP THEO BAN DO DIA CHINH XA YEN BINH LAP NAM 2004 CHINH LY NAM 2023",
            ],
        }
        self.assertTrue(ocr_ai._should_rescue_property_issue_date(doc))

    def test_should_not_rescue_property_issue_date_without_footer_signal(self):
        doc = {
            "doc_type": "property",
            "side": "back",
            "data": {
                "ngay_cap": "15/04/1991",
                "co_quan_cap": "UY BAN NHAN DAN",
            },
            "text_lines": [
                "Ngay 15 thang 4 nam 1991",
                "UY BAN NHAN DAN",
            ],
        }
        self.assertFalse(ocr_ai._should_rescue_property_issue_date(doc))

    def test_extract_property_address_keeps_nam_dinh_continuation(self):
        lines = [
            "Dia chi:",
            "Thon Phuong Nhi",
            "Xa Tan Minh, huyen Kim Son, tinh Nam Dinh",
        ]
        self.assertEqual(
            ocr_ai._extract_property_address(lines),
            "Thon Phuong Nhi, Xa Tan Minh, huyen Kim Son, tinh Nam Dinh",
        )

    def test_extract_property_address_stops_before_footer_date_line(self):
        lines = [
            "Dia chi:",
            "Thon Phuong Nhi",
            "Xa Tan Minh, huyen Kim Son, tinh Nam Dinh",
            "Nam Dinh, ngay 10/07/2023",
            "VAN PHONG DANG KY DAT DAI",
        ]
        self.assertEqual(
            ocr_ai._extract_property_address(lines),
            "Thon Phuong Nhi, Xa Tan Minh, huyen Kim Son, tinh Nam Dinh",
        )

    def test_normalize_property_doc_accepts_standalone_serial_and_owner(self):
        lines = [
            "GIAY CHUNG NHAN",
            "QUYEN SU DUNG DAT, QUYEN SO HUU NHA O VA TAI SAN KHAC GAN LIEN VOI DAT",
            "BM 1451111",
            "Nguoi su dung dat: NGUYEN VAN A",
            "Dia chi: Xa Yen Binh, huyen Y Yen, tinh Nam Dinh",
        ]
        doc = ocr_ai._normalize_property_ocr_doc(lines, "property-owner.jpg")
        self.assertEqual(doc["doc_type"], "property")
        self.assertEqual(doc["data"]["so_serial"], "BM 1451111")
        self.assertEqual(doc["data"]["chu_su_dung"], "NGUYEN VAN A")

    def test_extract_property_serial_rejects_registry_like_standalone_code(self):
        lines = [
            "GIAY CHUNG NHAN",
            "QUYEN SU DUNG DAT",
            "VP123456",
            "So vao so cap GCN: VP123456",
            "Dia chi: Xa Yen Binh, huyen Y Yen, tinh Nam Dinh",
        ]
        self.assertEqual(ocr_ai._extract_property_serial(lines), "")

    def test_normalize_property_doc_extracts_plot_and_map_from_combined_line(self):
        lines = [
            "GIAY CHUNG NHAN",
            "QUYEN SU DUNG DAT",
            "AA 12467547",
            "Thua dat so: 342; To ban do so: 22",
            "Dia chi: Xa Yen Binh, huyen Y Yen, tinh Nam Dinh",
        ]
        doc = ocr_ai._normalize_property_ocr_doc(lines, "property-combined.jpg")
        self.assertEqual(doc["data"]["so_thua_dat"], "342")
        self.assertEqual(doc["data"]["so_to_ban_do"], "22")

    def test_normalize_property_doc_accepts_sparse_back_page(self):
        lines = [
            "a) Thua dat: 66",
            "b) Dia chi: Xa Yen Binh, huyen Y Yen, tinh Nam Dinh",
            "So vao so cap GCN: VP00166",
        ]
        doc = ocr_ai._normalize_property_ocr_doc(lines, "property-sparse.jpg")
        self.assertEqual(doc["doc_type"], "property")
        self.assertEqual(doc["data"]["so_thua_dat"], "66")
        self.assertEqual(doc["data"]["so_vao_so"], "VP00166")

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

    def test_normalize_native_doc_front_drops_issue_date(self):
        lines = [
            "CAN CUOC CONG DAN",
            "So/No: 036080012689",
            "Ho va ten / Full name: NGUYEN VAN CHIEN",
            "Ngay sinh / Date of birth: 20/03/1980",
            "Ngay cap / Date of issue: 01/05/2021",
        ]
        doc = ocr_ai._normalize_native_ocr_doc(lines, "front.jpg")
        self.assertEqual(doc["doc_type"], "person")
        self.assertEqual(doc["side"], "front")
        self.assertEqual(doc["data"]["ngay_cap"], "")

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
        self.assertEqual(result["persons"][0]["side"], "front")
        self.assertIn("missing_back", result["persons"][0]["warnings"])

    async def test_analyze_images_qr_front_pairs_with_back_and_clears_missing_back(self):
        front = make_upload("qr-front.jpg")
        back = make_upload("back.jpg")
        qr_data = {
            "so_giay_to": "036179009696",
            "ho_ten": "DUONG THI XUAN",
            "ngay_sinh": "20/01/1979",
            "gioi_tinh": "Nữ",
            "dia_chi": "Quyet Phong, Yen Ninh, Y Yen, Nam Dinh",
            "ngay_cap": "",
            "ngay_het_han": "",
        }
        outputs = [
            [
                "CAN CUOC CONG DAN",
                "So/No: 036179009696",
                "Ho va ten / Full name: DUONG THI XUAN",
                "Ngay sinh / Date of birth: 20/01/1979",
            ],
            [
                "IDVNM1790096961036179009696<<6",
                "7901209F3901201VNM<<<<<<<<<<<4",
                "DUONG<<THI<XUAN<<<<<<<<<<<<<<<",
                "Ngay, thang, nam / Date, month, year: 25/03/2021",
            ],
        ]

        async def fake_call(*args, **kwargs):
            return outputs.pop(0)

        with (
            mock.patch.object(ocr_ai, "try_decode_qr", side_effect=["qr-text", None]),
            mock.patch.object(ocr_ai, "parse_cccd_qr", return_value=qr_data),
            mock.patch.object(ocr_ai, "_get_api_key", return_value="test-key"),
            mock.patch.object(ocr_ai, "_call_qwen_native_ocr_single", new=mock.AsyncMock(side_effect=fake_call)),
        ):
            result = await ocr_ai.analyze_images([front, back])

        self.assertEqual(result["summary"]["persons"], 1)
        person = result["persons"][0]
        self.assertEqual(person["side"], "front_back")
        self.assertTrue(person["paired"])
        self.assertNotIn("missing_back", person["warnings"])
        self.assertEqual(person["ngay_cap"], "25/03/2021")

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

    async def test_analyze_images_marks_mismatched_front_and_back_as_incomplete(self):
        front = make_upload("chien-front.jpg")
        back = make_upload("tam-back.jpg")
        outputs = [
            [
                "CAN CUOC CONG DAN",
                "So/No: 036080012689",
                "Ho va ten / Full name: NGUYEN VAN CHIEN",
                "Ngay sinh / Date of birth: 20/03/1980",
                "Gioi tinh / Sex: Nam",
                "Noi thuong tru / Place of residence: Khu 7B To 91, Cam Phu, Cam Pha, Quang Ninh",
                "Ngay cap / Date of issue: 01/05/2021",
            ],
            [
                "IDVNM0830120655036083012065<<0",
                "8305273M4305275VNM<<<<<<<<<<<2",
                "NGUYEN<<DUC<TAM<<<<<<<<<<<<<<",
                "Ngay, thang, nam / Date, month, year: 16/12/2021",
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

        self.assertEqual(result["summary"]["persons"], 2)
        by_id = {person["so_giay_to"]: person for person in result["persons"]}
        self.assertIn("036080012689", by_id)
        self.assertIn("036083012065", by_id)
        self.assertIn("missing_back", by_id["036080012689"]["warnings"])
        self.assertIn("missing_front", by_id["036083012065"]["warnings"])
        self.assertEqual(by_id["036080012689"]["ngay_cap"], "")
        self.assertFalse(by_id["036080012689"]["paired"])
        self.assertFalse(by_id["036083012065"]["paired"])

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

    async def test_analyze_property_pair_merges_by_field_and_returns_owner(self):
        front = make_upload("front.jpg")
        back = make_upload("back.jpg")
        outputs = [
            [
                "GIAY CHUNG NHAN",
                "QUYEN SU DUNG DAT",
                "So A 692942",
                "Nguoi su dung dat: NGUYEN VAN A",
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
        self.assertEqual(prop["chu_su_dung"], "NGUYEN VAN A")
        self.assertEqual(result["per_side"]["front"]["doc_type"], "property")
        self.assertEqual(result["per_side"]["back"]["doc_type"], "property")

    async def test_analyze_property_pair_is_order_independent_without_footer_rescue(self):
        pair_a = (make_upload("doc-front.jpg"), make_upload("doc-back.jpg"))
        pair_b = (make_upload("doc-back.jpg"), make_upload("doc-front.jpg"))
        call_filenames: list[str] = []

        async def fake_call(*args, **kwargs):
            filename = kwargs["filename"]
            call_filenames.append(filename)
            if filename.endswith("#footer"):
                return [
                    "Nam Dinh, ngay 10/07/2023",
                    "VAN PHONG DANG KY DAT DAI",
                ]
            if filename == "doc-front.jpg":
                return [
                    "GIAY CHUNG NHAN",
                    "QUYEN SU DUNG DAT",
                    "AA07488103",
                    "Dia chi: Xa Yen Binh, huyen Y Yen, tinh Nam Dinh",
                ]
            if filename == "doc-back.jpg":
                return [
                    "GIAY CHUNG NHAN",
                    "So vao so cap GCN: VP00166",
                    "Nam Dinh, ngay 10 thang 3 nam 2018",
                    "VAN PHONG DANG KY DAT DAI",
                    "SO DO DUOC BIEN TAP THEO BAN DO DIA CHINH XA YEN BINH LAP NAM 2004 CHINH LY NAM 2023",
                ]
            raise AssertionError(f"unexpected filename: {filename}")

        with (
            mock.patch.object(ocr_ai, "_get_api_key", return_value="test-key"),
            mock.patch.object(ocr_ai, "_call_qwen_native_ocr_single", new=mock.AsyncMock(side_effect=fake_call)),
            mock.patch.object(ocr_ai, "_should_retry_property_rotate", return_value=False),
        ):
            result_a = await ocr_ai.analyze_property_pair(*pair_a)
            result_b = await ocr_ai.analyze_property_pair(*pair_b)

        keys = tuple(ocr_ai._PROPERTY_FORM_FIELDS) + ("land_rows",)
        self.assertEqual(
            {key: result_a["property"].get(key) for key in keys},
            {key: result_b["property"].get(key) for key in keys},
        )
        self.assertEqual(result_a["property"]["ngay_cap"], "10/03/2018")
        self.assertEqual(len(call_filenames), 4)
        self.assertFalse(any(name.endswith("#footer") for name in call_filenames))

    def test_merge_property_pair_is_order_independent(self):
        doc_a = {
            "doc_type": "property",
            "data": {
                "so_serial": "AA 12467547",
                "dia_chi": "Xa Yen Binh, huyen Y Yen, tinh Nam Dinh",
                "chu_su_dung": "NGUYEN VAN A",
                "land_rows": [],
            },
        }
        doc_b = {
            "doc_type": "property",
            "data": {
                "so_vao_so": "VP00166",
                "ngay_cap": "10/07/2023",
                "so_thua_dat": "66",
                "so_to_ban_do": "29",
                "land_rows": [],
            },
        }

        left_first = ocr_ai._merge_property_pair(doc_a, doc_b)
        right_first = ocr_ai._merge_property_pair(doc_b, doc_a)

        for key in ("so_serial", "so_vao_so", "ngay_cap", "so_thua_dat", "so_to_ban_do", "dia_chi", "chu_su_dung"):
            self.assertEqual(left_first.get(key), right_first.get(key))

    def test_merge_property_pair_prefers_cleaner_address_and_area(self):
        noisy_doc = {
            "doc_type": "property",
            "data": {
                "dia_chi": "Xa Yen Binh, huyen Y Yen, tinh Nam Dinh, VAN PHONG DANG KY DAT DAI",
                "dien_tich": "447,0",
                "land_rows": [],
            },
        }
        clean_doc = {
            "doc_type": "property",
            "data": {
                "dia_chi": "Xa Yen Binh, huyen Y Yen, tinh Nam Dinh",
                "dien_tich": "447.00",
                "land_rows": [],
            },
        }

        merged = ocr_ai._merge_property_pair(noisy_doc, clean_doc)

        self.assertEqual(merged["dia_chi"], "Xa Yen Binh, huyen Y Yen, tinh Nam Dinh")
        self.assertEqual(merged["dien_tich"], "447.00")

    def test_pick_property_field_value_prefers_recent_issue_date(self):
        chosen, source = ocr_ai._pick_property_field_value("ngay_cap", "31/12/1999", "10/07/2023")
        self.assertEqual(chosen, "10/07/2023")
        self.assertEqual(source, "back")

    def test_pick_property_field_value_prefers_clean_authority(self):
        noisy = "VAN PHONG DANG KY DAT DAI NAM DINH KT GIAM DOC PHO GIAM DOC"
        clean = "VAN PHONG DANG KY DAT DAI NAM DINH"
        chosen, source = ocr_ai._pick_property_field_value("co_quan_cap", noisy, clean)
        self.assertEqual(chosen, clean)
        self.assertEqual(source, "back")

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
