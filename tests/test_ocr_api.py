import unittest
from unittest import mock

from routers import ocr


def make_row(
    *,
    index: int,
    filename: str,
    state: str,
    profile: str,
    pair_key: str = "",
    pair_key_source: str = "",
    data: dict | None = None,
    field_sources: dict | None = None,
    qr_data: dict | None = None,
    mrz_data: dict | None = None,
    has_qr: bool = False,
    has_mrz: bool = False,
    face_detected: bool = True,
) -> dict:
    row = ocr._build_empty_row(index, filename)
    row["state"] = state
    row["profile"] = profile
    row["doc_type"] = ocr._PROFILE_TO_DOC_TYPE.get(profile, ocr._state_to_doc_type(state))
    row["pair_key"] = pair_key
    row["pair_key_source"] = pair_key_source
    row["data"] = ocr._empty_person_data()
    row["data"].update(data or {})
    row["field_sources"] = dict(field_sources or {})
    row["qr_data"] = qr_data
    row["mrz_data"] = mrz_data or {}
    row["has_qr"] = has_qr
    row["has_mrz"] = has_mrz
    row["face_detected"] = face_detected
    row["full_b64"] = f"full-{index}"
    row["image"] = mock.Mock()
    row["_side"] = ocr._PROFILE_TO_SIDE_LABEL.get(profile, "unknown")
    return row


class VisionResultNormalizationTests(unittest.TestCase):
    def test_normalize_vision_results_keeps_explicit_source_index(self):
        parsed = [
            {
                "source_image_index": "2",
                "doc_type": "cccd_front",
                "data": None,
            }
        ]

        rows = ocr._normalize_vision_results(parsed, [0, 1, 2], 3)

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["_source_image_index"], 2)
        self.assertEqual(rows[0]["doc_type"], "cccd_front")
        self.assertEqual(rows[0]["data"], {})
        self.assertNotIn("source_image_index", rows[0])

    def test_normalize_vision_results_single_image_keeps_multi_objects_on_same_source(self):
        parsed = [
            {"doc_type": "cccd_front", "data": {}},
            {"doc_type": "cccd_back", "data": {}},
        ]

        rows = ocr._normalize_vision_results(parsed, [4], 5)

        self.assertEqual([row["_source_image_index"] for row in rows], [4, 4])


class DeterministicRuleTests(unittest.TestCase):
    def test_infer_deterministic_state_covers_four_primary_cases(self):
        self.assertEqual(ocr._infer_deterministic_state(has_qr=True, has_mrz=False), ocr.TRIAGE_STATE_FRONT_OLD)
        self.assertEqual(ocr._infer_deterministic_state(has_qr=True, has_mrz=True), ocr.TRIAGE_STATE_BACK_NEW)
        self.assertEqual(ocr._infer_deterministic_state(has_qr=False, has_mrz=True), ocr.TRIAGE_STATE_BACK_OLD)
        self.assertEqual(ocr._infer_deterministic_state(has_qr=False, has_mrz=False), ocr.TRIAGE_STATE_FRONT_UNKNOWN)

    def test_resolve_front_pairs_maps_new_and_old_by_filename_stem(self):
        rows = [
            make_row(
                index=0,
                filename="ngo-van-tan-front.jpg",
                state=ocr.TRIAGE_STATE_FRONT_UNKNOWN,
                profile=ocr.DOC_PROFILE_UNKNOWN,
                face_detected=True,
            ),
            make_row(
                index=1,
                filename="ngo-van-tan-back.jpg",
                state=ocr.TRIAGE_STATE_BACK_NEW,
                profile=ocr.DOC_PROFILE_BACK_NEW,
                pair_key="036065001407",
                pair_key_source="qr",
                has_qr=True,
            ),
            make_row(
                index=2,
                filename="trinh-thi-tuyet-front.jpg",
                state=ocr.TRIAGE_STATE_FRONT_UNKNOWN,
                profile=ocr.DOC_PROFILE_UNKNOWN,
                face_detected=True,
            ),
            make_row(
                index=3,
                filename="trinh-thi-tuyet-back.jpg",
                state=ocr.TRIAGE_STATE_BACK_OLD,
                profile=ocr.DOC_PROFILE_BACK_OLD,
                pair_key="036168006276",
                pair_key_source="mrz",
                has_mrz=True,
            ),
        ]

        ocr._resolve_front_new_pairs(rows)

        self.assertEqual(rows[0]["profile"], ocr.DOC_PROFILE_FRONT_NEW)
        self.assertEqual(rows[0]["pair_key"], "036065001407")
        self.assertEqual(rows[2]["profile"], ocr.DOC_PROFILE_FRONT_OLD)
        self.assertEqual(rows[2]["pair_key"], "036168006276")


class MrzParserTests(unittest.TestCase):
    def test_parse_cccd_mrz_lines_extracts_id_birth_gender_expiry_and_name(self):
        parsed = ocr._parse_cccd_mrz_lines(
            [
                "IDVNM065001407903606500140`7<<4",
                "6506179M9912315VNM<<<<<<<<<<<8",
                "NGO<<VAN<TAN<<<<<<<<<<<<<<<",
            ]
        )

        self.assertEqual(parsed["so_giay_to"], "036065001407")
        self.assertEqual(parsed["ngay_sinh"], "17/06/1965")
        self.assertEqual(parsed["gioi_tinh"], "Nam")
        self.assertEqual(parsed["ngay_het_han"], "31/12/2099")
        self.assertEqual(parsed["ho_ten_ascii"], "NGO VAN TAN")

    def test_normalize_expiry_value_handles_khong_thoi_han(self):
        self.assertEqual(ocr._normalize_expiry_value("Không thời hạn"), "")


class GroupDocumentsTests(unittest.TestCase):
    def test_group_documents_prefers_pair_key_over_ai_so_giay_to(self):
        results = [
            {
                "doc_type": "cccd_front",
                "profile": ocr.DOC_PROFILE_FRONT_OLD,
                "pair_key": "012345678901",
                "pair_key_source": "qr",
                "filename": "front.jpg",
                "field_sources": {
                    "so_giay_to": "ai",
                    "ho_ten": "qr",
                    "ngay_sinh": "qr",
                    "gioi_tinh": "qr",
                    "dia_chi": "qr",
                    "ngay_cap": "qr",
                },
                "qr_data": {"so_giay_to": "012345678901"},
                "mrz_data": {},
                "data": {
                    "so_giay_to": "999999999999",
                    "ho_ten": "TRỊNH THỊ TUYẾT",
                    "ngay_sinh": "02/06/1968",
                    "gioi_tinh": "Nữ",
                    "dia_chi": "Tổ 8, Thị trấn Lâm, Ý Yên, Nam Định",
                    "ngay_cap": "20/06/2023",
                },
                "_side": "front_old_cccd",
            },
            {
                "doc_type": "cccd_back",
                "profile": ocr.DOC_PROFILE_BACK_OLD,
                "pair_key": "012345678901",
                "pair_key_source": "mrz",
                "filename": "back.jpg",
                "field_sources": {"ngay_cap": "ai"},
                "qr_data": None,
                "mrz_data": {"so_giay_to": "012345678901"},
                "data": {"so_giay_to_mrz": "012345678901", "ngay_cap": "20/06/2023"},
                "_side": "back_old_cccd",
            },
        ]

        grouped = ocr.group_documents(results)

        self.assertEqual(len(grouped["persons"]), 1)
        self.assertEqual(grouped["persons"][0]["so_giay_to"], "012345678901")
        self.assertEqual(grouped["summary"]["matched_pairs"], 1)

    def test_group_documents_only_takes_address_from_front_old_or_back_new(self):
        results = [
            {
                "doc_type": "cccd_front",
                "profile": ocr.DOC_PROFILE_FRONT_NEW,
                "pair_key": "036084011825",
                "pair_key_source": "qr",
                "filename": "front.jpg",
                "field_sources": {
                    "ho_ten": "ai",
                    "so_giay_to": "ai",
                    "ngay_sinh": "ai",
                    "gioi_tinh": "ai",
                    "dia_chi": "ai",
                },
                "qr_data": None,
                "mrz_data": {},
                "data": {
                    "ho_ten": "NGUYỄN HUY HOÀNG",
                    "so_giay_to": "036084011825",
                    "ngay_sinh": "09/12/1984",
                    "gioi_tinh": "Nam",
                    "dia_chi": "KHONG DUOC DUNG",
                },
                "_side": "front_new_cc",
            },
            {
                "doc_type": "cccd_back",
                "profile": ocr.DOC_PROFILE_BACK_NEW,
                "pair_key": "036084011825",
                "pair_key_source": "qr",
                "filename": "back.jpg",
                "field_sources": {"dia_chi": "ai", "ngay_cap": "ai"},
                "qr_data": None,
                "mrz_data": {"so_giay_to": "036084011825"},
                "data": {"so_giay_to_mrz": "036084011825", "dia_chi": "Yên Lương, Ý Yên, Nam Định", "ngay_cap": "06/01/2025"},
                "_side": "back_new_cc",
            },
        ]

        grouped = ocr.group_documents(results)

        self.assertEqual(grouped["persons"][0]["dia_chi"], "Yên Lương, Ý Yên, Nam Định")


class AiPlanningTests(unittest.TestCase):
    def setUp(self):
        self.settings = {
            "batch_size": 2,
            "max_concurrency": 1,
            "timeout_seconds": 30.0,
            "retry_count": 0,
            "retry_base_delay_ms": 100,
            "openai_max_tokens_per_image": 500,
            "timing_log": False,
            "timing_slow_ms": 999999.0,
            "enable_targeted_fields": True,
            "enable_mrz_local": True,
        }

    def test_build_ai_plan_skips_ai_for_five_pairs_when_qr_or_mrz_are_enough(self):
        rows = []
        old_keys = ["036168006276", "036082000989", "036185021354"]
        for offset, key in enumerate(old_keys):
            rows.append(
                make_row(
                    index=offset * 2,
                    filename=f"old-{offset}-front.jpg",
                    state=ocr.TRIAGE_STATE_FRONT_OLD,
                    profile=ocr.DOC_PROFILE_FRONT_OLD,
                    pair_key=key,
                    pair_key_source="qr",
                    has_qr=True,
                    data={
                        "so_giay_to": key,
                        "ho_ten": f"OLD FRONT {offset}",
                        "ngay_sinh": "01/01/1980",
                        "gioi_tinh": "Nam",
                        "dia_chi": "Nam Định",
                        "ngay_cap": "01/01/2020",
                    },
                    field_sources={
                        "so_giay_to": "qr",
                        "ho_ten": "qr",
                        "ngay_sinh": "qr",
                        "gioi_tinh": "qr",
                        "dia_chi": "qr",
                        "ngay_cap": "qr",
                    },
                )
            )
            rows.append(
                make_row(
                    index=offset * 2 + 1,
                    filename=f"old-{offset}-back.jpg",
                    state=ocr.TRIAGE_STATE_BACK_OLD,
                    profile=ocr.DOC_PROFILE_BACK_OLD,
                    pair_key=key,
                    pair_key_source="mrz",
                    has_mrz=True,
                    mrz_data={"so_giay_to": key},
                    data={"so_giay_to": key, "ngay_cap": "01/01/2020"},
                    field_sources={"so_giay_to": "mrz", "ngay_cap": "ai"},
                )
            )

        new_keys = ["036065001407", "036084011825"]
        for offset, key in enumerate(new_keys, start=len(rows)):
            rows.append(
                make_row(
                    index=offset * 2,
                    filename=f"new-{offset}-front.jpg",
                    state=ocr.TRIAGE_STATE_FRONT_NEW,
                    profile=ocr.DOC_PROFILE_FRONT_NEW,
                    pair_key=key,
                    pair_key_source="qr",
                    data={
                        "so_giay_to": key,
                        "ho_ten": f"NEW FRONT {offset}",
                        "ngay_sinh": "01/01/1980",
                        "gioi_tinh": "Nam",
                    },
                    field_sources={
                        "so_giay_to": "ai",
                        "ho_ten": "ai",
                        "ngay_sinh": "ai",
                        "gioi_tinh": "ai",
                    },
                )
            )
            rows.append(
                make_row(
                    index=offset * 2 + 1,
                    filename=f"new-{offset}-back.jpg",
                    state=ocr.TRIAGE_STATE_BACK_NEW,
                    profile=ocr.DOC_PROFILE_BACK_NEW,
                    pair_key=key,
                    pair_key_source="qr",
                    has_qr=True,
                    has_mrz=True,
                    data={
                        "so_giay_to": key,
                        "ho_ten": f"NEW BACK {offset}",
                        "ngay_sinh": "01/01/1980",
                        "gioi_tinh": "Nam",
                        "dia_chi": "Nam Định",
                        "ngay_cap": "01/01/2025",
                    },
                    field_sources={
                        "so_giay_to": "qr",
                        "ho_ten": "qr",
                        "ngay_sinh": "qr",
                        "gioi_tinh": "qr",
                        "dia_chi": "qr",
                        "ngay_cap": "qr",
                    },
                )
            )

        plans = ocr._build_ai_plan(rows, self.settings)

        self.assertEqual(plans, [])

    def test_build_ai_plan_asks_back_fields_when_mrz_exists_but_front_qr_not_confirmed(self):
        row = make_row(
            index=0,
            filename="new-back-qr-fail.jpg",
            state=ocr.TRIAGE_STATE_BACK_OLD,
            profile=ocr.DOC_PROFILE_BACK_OLD,
            pair_key="036084011825",
            pair_key_source="mrz",
            has_mrz=True,
            mrz_data={"so_giay_to": "036084011825"},
            data={"so_giay_to": "036084011825"},
            field_sources={"so_giay_to": "mrz"},
        )

        with mock.patch.object(ocr, "_crop_image_to_base64", return_value="crop"):
            plans = ocr._build_ai_plan([row], self.settings)

        self.assertEqual(len(plans), 1)
        self.assertEqual(plans[0]["targets"], ("dia_chi", "ngay_cap"))

    def test_build_ai_plan_targets_front_old_when_old_front_is_paired_from_back(self):
        rows = [
            make_row(
                index=0,
                filename="old-front.jpg",
                state=ocr.TRIAGE_STATE_FRONT_OLD,
                profile=ocr.DOC_PROFILE_FRONT_OLD,
                pair_key="036168006276",
                pair_key_source="mrz",
                face_detected=True,
                data={"so_giay_to": "036168006276"},
                field_sources={"so_giay_to": "ai"},
            ),
            make_row(
                index=1,
                filename="old-back.jpg",
                state=ocr.TRIAGE_STATE_BACK_OLD,
                profile=ocr.DOC_PROFILE_BACK_OLD,
                pair_key="036168006276",
                pair_key_source="mrz",
                has_mrz=True,
                mrz_data={"so_giay_to": "036168006276"},
                data={"so_giay_to": "036168006276"},
                field_sources={"so_giay_to": "mrz"},
            ),
        ]

        with mock.patch.object(ocr, "_crop_image_to_base64", return_value="crop"):
            plans = ocr._build_ai_plan(rows, self.settings)

        self.assertEqual(len(plans), 2)
        self.assertEqual(plans[0]["targets"], ("ho_ten", "so_giay_to", "ngay_sinh", "gioi_tinh", "dia_chi"))


class CallVisionBatchV2Tests(unittest.IsolatedAsyncioTestCase):
    async def test_call_vision_batch_v2_splits_images_into_configured_chunks(self):
        recorded_chunks: list[list[int]] = []

        async def fake_call_chunk(
            client,
            *,
            chunk,
            total_images,
            model,
            api_key,
            is_gemini,
            settings,
            prompt=ocr.SYSTEM_PROMPT,
            image_detail="high",
            openai_max_tokens_per_image=None,
            allow_split_fallback=True,
        ):
            recorded_chunks.append([image_index for image_index, _ in chunk])
            return [
                {
                    "doc_type": "unknown",
                    "data": {},
                    "_source_image_index": image_index,
                }
                for image_index, _ in chunk
            ]

        settings = {
            "batch_size": 2,
            "max_concurrency": 1,
            "timeout_seconds": 30.0,
            "retry_count": 0,
            "retry_base_delay_ms": 100,
            "openai_max_tokens_per_image": 500,
            "timing_log": False,
            "timing_slow_ms": 999999.0,
            "enable_targeted_fields": True,
            "enable_mrz_local": True,
        }

        with mock.patch.object(ocr, "_get_primary_model", return_value="gpt-4o-mini"), \
             mock.patch.object(ocr, "_get_api_key", return_value="test-key"), \
             mock.patch.object(ocr, "_get_ai_ocr_settings", return_value=settings), \
             mock.patch.object(ocr, "_call_vision_provider_chunk", side_effect=fake_call_chunk):
            rows = await ocr.call_vision_batch_v2(["img-0", "img-1", "img-2", "img-3", "img-4"])

        self.assertEqual(recorded_chunks, [[0, 1], [2, 3], [4]])
        self.assertEqual([row["_source_image_index"] for row in rows], [0, 1, 2, 3, 4])

    async def test_call_vision_provider_chunk_splits_when_source_index_is_missing(self):
        class DummyResponse:
            headers = {}
            text = "{}"
            status_code = 200
            is_success = True

            def json(self):
                return {}

        settings = {
            "batch_size": 2,
            "max_concurrency": 1,
            "timeout_seconds": 30.0,
            "retry_count": 0,
            "retry_base_delay_ms": 100,
            "openai_max_tokens_per_image": 500,
            "timing_log": False,
            "timing_slow_ms": 999999.0,
            "enable_targeted_fields": True,
            "enable_mrz_local": True,
        }

        with mock.patch.object(
            ocr,
            "_post_vision_request_with_retry",
            new=mock.AsyncMock(return_value=DummyResponse()),
        ) as request_mock, \
             mock.patch.object(ocr, "_extract_vision_text", return_value="[]"), \
             mock.patch.object(
                 ocr,
                 "parse_json_safe",
                 return_value=[{"doc_type": "cccd_front", "data": {}}],
             ):
            rows = await ocr._call_vision_provider_chunk(
                client=mock.Mock(),
                chunk=[(0, "img-0"), (1, "img-1")],
                total_images=2,
                model="gpt-4o-mini",
                api_key="test-key",
                is_gemini=False,
                settings=settings,
            )

        self.assertEqual(request_mock.await_count, 3)
        self.assertEqual([row["_source_image_index"] for row in rows], [0, 1])


if __name__ == "__main__":
    unittest.main()
