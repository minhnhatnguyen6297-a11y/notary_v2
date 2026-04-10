import os
import tempfile
import unittest
from unittest import mock
from types import SimpleNamespace

import numpy as np
from fastapi import FastAPI
from fastapi.testclient import TestClient

from routers import ocr_local


def make_box(x1: int, y1: int, x2: int, y2: int) -> dict:
    return {
        "box": np.array(
            [[x1, y1], [x2, y1], [x2, y2], [x1, y2]],
            dtype=np.float32,
        )
    }


def make_image_bytes(img: np.ndarray) -> bytes:
    ok, encoded = ocr_local.cv2.imencode(".jpg", img)
    if not ok:
        raise RuntimeError("failed to encode image fixture")
    return encoded.tobytes()


class FilterTargetBoxesTests(unittest.TestCase):
    def test_filter_target_boxes_keeps_only_valid_front_id_boxes(self):
        img_shape = (1000, 700)
        boxes = [
            make_box(200, 220, 560, 280),
            make_box(180, 760, 560, 820),
            make_box(260, 240, 268, 248),
            make_box(2, 210, 120, 280),
        ]

        filtered = ocr_local.filter_target_boxes(
            boxes,
            img_shape,
            ocr_local.TRIAGE_STATE_FRONT_NEW,
            "id",
        )

        self.assertEqual(len(filtered), 1)
        x1, y1, x2, y2 = ocr_local._box_bounds(filtered[0]["box"])
        self.assertEqual((int(x1), int(y1), int(x2), int(y2)), (200, 220, 560, 280))

    def test_filter_target_boxes_uses_unknown_detail_wide_roi(self):
        img_shape = (1000, 700)
        boxes = [
            make_box(120, 180, 600, 250),
            make_box(40, 40, 660, 120),
        ]

        filtered = ocr_local.filter_target_boxes(
            boxes,
            img_shape,
            ocr_local.TRIAGE_STATE_UNKNOWN,
            "detail",
        )

        self.assertEqual(len(filtered), 1)
        center_x, center_y = ocr_local._box_center_ratio(filtered[0]["box"], img_shape)
        self.assertGreater(center_x, 0.08)
        self.assertGreater(center_y, 0.14)


class ParseFullTextTests(unittest.TestCase):
    def test_extract_id_12_from_mrz_text_uses_canonical_22_digit_rule(self):
        cases = {
            "IDVNM065001407903606500140`7<<4": "036065001407",
            "IDVNM0820009892036082000989<<7": "036082000989",
            "IDVNM1680062760036168006276<<5": "036168006276",
            "IDVNM0840118259036084011825<<4": "036084011825",
        }

        for text, expected in cases.items():
            with self.subTest(text=text):
                extracted = ocr_local._extract_id_12_from_mrz_text(text)
                self.assertEqual(extracted, expected)
                self.assertNotIn(extracted, {"065001407903", "082000989203"})

    def test_parse_cccd_fulltext_front_old_extracts_key_fields(self):
        full_text = """
        CAN CUOC CONG DAN
        So 012345678901
        Ho va ten: NGUYEN VAN AN
        Ngay sinh: 01/02/1990
        Gioi tinh: Nam
        Quoc tich: Viet Nam
        Noi thuong tru: 123 DUONG LE LOI
        PHUONG BEN NGHE, QUAN 1, TP HCM
        Ngay cap: 03/04/2021
        """

        data = ocr_local._parse_cccd_fulltext(full_text, ocr_local.DOC_PROFILE_FRONT_OLD)

        self.assertEqual(data["so_giay_to"], "012345678901")
        self.assertEqual(data["ho_ten"], "NGUYEN VAN AN")
        self.assertEqual(data["ngay_sinh"], "01/02/1990")
        self.assertEqual(data["gioi_tinh"], "Nam")
        self.assertEqual(data["ngay_cap"], "03/04/2021")
        self.assertIn("123 DUONG LE LOI", data["dia_chi"])
        self.assertIn("QUAN 1", data["dia_chi"])

    def test_parse_cccd_fulltext_back_new_reads_mrz_id_and_dates(self):
        full_text = """
        NOI CU TRU: 25 NGUYEN TRAI
        PHUONG 7, QUAN 5, TP HCM
        Ngay cap: 03-04-2021
        Co gia tri den: 03-04-2031
        IDVNM<<<<012345678901<<<<<<<<<<<<
        """

        data = ocr_local._parse_cccd_fulltext(full_text, ocr_local.DOC_PROFILE_BACK_NEW)

        self.assertEqual(data["so_giay_to"], "012345678901")
        self.assertEqual(data["ngay_cap"], "03/04/2021")
        self.assertEqual(data["ngay_het_han"], "03/04/2031")
        self.assertIn("25 NGUYEN TRAI", data["dia_chi"])


class DetectorAndCropTests(unittest.TestCase):
    def test_rapidocr_detect_boxes_handles_numpy_array_output(self):
        detector_output = np.array(
            [
                [[10, 20], [30, 20], [30, 40], [10, 40]],
                [[50, 60], [70, 60], [70, 90], [50, 90]],
            ],
            dtype=np.float32,
        )

        with mock.patch.object(ocr_local, "_get_rapidocr_engine", return_value=lambda img: (detector_output, 12.34)):
            boxes, elapsed = ocr_local._rapidocr_detect_boxes(np.zeros((100, 100, 3), dtype=np.uint8))

        self.assertEqual(len(boxes), 2)
        self.assertEqual(elapsed, 12340.0)

    def test_crop_box_image_upscales_small_text_line(self):
        img = np.full((80, 160, 3), 255, dtype=np.uint8)
        box = np.array([[20, 20], [120, 20], [120, 34], [20, 34]], dtype=np.float32)

        crop = ocr_local._crop_box_image(img, box)

        self.assertIsNotNone(crop)
        self.assertGreaterEqual(crop.shape[0], ocr_local.LOCAL_OCR_REC_MIN_HEIGHT)


class MergeFlowTests(unittest.TestCase):
    def test_rekey_and_delta_merge_keep_single_person_record(self):
        persons_map = {}
        person_order = []

        record = ocr_local._ensure_person_record(persons_map, person_order, "img:0", "front.jpg", 0)
        front_data = {
            "so_giay_to": "012345678901",
            "ho_ten": "NGUYEN VAN AN",
            "ngay_sinh": "01/02/1990",
            "gioi_tinh": "Nam",
            "dia_chi": "",
            "ngay_cap": "",
            "ngay_het_han": "",
        }
        ocr_local._merge_person_data(record["data"], front_data, record["field_sources"], "OCR")
        record["side"] = "front"
        record["profile"] = ocr_local.DOC_PROFILE_FRONT_NEW

        new_key = ocr_local._rekey_person_record(persons_map, person_order, "img:0", "012345678901")
        self.assertEqual(new_key, "012345678901")
        self.assertEqual(person_order, ["012345678901"])

        same_person = ocr_local._ensure_person_record(persons_map, person_order, "012345678901", "back.jpg", 1)
        self.assertIs(same_person, persons_map["012345678901"])
        self.assertEqual(len(person_order), 1)

        back_data = {
            "so_giay_to": "012345678901",
            "ho_ten": "",
            "ngay_sinh": "",
            "gioi_tinh": "",
            "dia_chi": "25 NGUYEN TRAI, QUAN 5, TP HCM",
            "ngay_cap": "03/04/2021",
            "ngay_het_han": "03/04/2031",
        }
        ocr_local._merge_person_data(same_person["data"], back_data, same_person["field_sources"], "OCR")

        merged = ocr_local._empty_person_data()
        merged_sources = {}
        ocr_local._merge_person_data(merged, front_data, merged_sources, "OCR")
        ocr_local._merge_person_data(merged, back_data, merged_sources, "OCR")
        ocr_local._apply_delta_merge(
            merged,
            [
                {
                    "data": front_data,
                    "source_type": "OCR",
                    "side": "front",
                    "profile": ocr_local.DOC_PROFILE_FRONT_NEW,
                },
                {
                    "data": back_data,
                    "source_type": "OCR",
                    "side": "back",
                    "profile": ocr_local.DOC_PROFILE_BACK_NEW,
                },
            ],
        )

        self.assertEqual(merged["so_giay_to"], "012345678901")
        self.assertEqual(merged["ho_ten"], "NGUYEN VAN AN")
        self.assertEqual(merged["dia_chi"], "25 NGUYEN TRAI, QUAN 5, TP HCM")
        self.assertEqual(merged["ngay_cap"], "03/04/2021")


class TriageContractTests(unittest.TestCase):
    def test_runtime_taxonomy_mapping_matches_expected_contract(self):
        self.assertEqual(
            ocr_local._triage_state_from_signals(face_detected=True, qr_detected=True, mrz_score=0.0),
            ocr_local.TRIAGE_STATE_FRONT_OLD,
        )
        self.assertEqual(
            ocr_local._triage_state_from_signals(face_detected=True, qr_detected=False, mrz_score=0.0),
            ocr_local.TRIAGE_STATE_FRONT_NEW,
        )
        self.assertEqual(
            ocr_local._triage_state_from_signals(face_detected=False, qr_detected=True, mrz_score=0.0),
            ocr_local.TRIAGE_STATE_BACK_NEW,
        )
        self.assertEqual(
            ocr_local._triage_state_from_signals(
                face_detected=False,
                qr_detected=False,
                mrz_score=ocr_local.LOCAL_OCR_TRIAGE_MRZ_MIN_SCORE + 0.1,
            ),
            ocr_local.TRIAGE_STATE_BACK_OLD,
        )

    def test_infer_doc_profile_does_not_treat_personal_identification_number_as_back(self):
        normalized_lines = [
            "can cuoc",
            "so dinh danh ca nhan personal identification number",
            "nguyen huy hoang",
        ]
        self.assertEqual(
            ocr_local._infer_doc_profile(normalized_lines, "cccd_front"),
            ocr_local.DOC_PROFILE_FRONT_NEW,
        )


@unittest.skipIf(ocr_local.cv2 is None or ocr_local.np is None, "opencv not available")
class BlobTriageTests(unittest.TestCase):
    @staticmethod
    def _make_blob_front(angle: int = 0) -> np.ndarray:
        img = np.full((420, 720, 3), 255, dtype=np.uint8)
        ocr_local.cv2.circle(img, (120, 82), 34, (0, 0, 255), -1)
        ocr_local.cv2.rectangle(img, (520, 110), (618, 200), (0, 180, 230), -1)
        return ocr_local._rotate_by_angle(img, angle)

    def test_blob_triage_recovers_front_orientation_across_rotations(self):
        for angle in (0, 90, 180, 270):
            with self.subTest(angle=angle):
                triage = ocr_local._triage_crop_orientation(self._make_blob_front(angle))
                self.assertEqual(triage["triage_path"], "blob_front")
                self.assertEqual(triage["triage_state"], ocr_local.TRIAGE_STATE_FRONT_NEW)
                self.assertEqual(triage["orientation_angle"], (360 - angle) % 360)
                self.assertGreaterEqual(float(triage["blob_confidence"]), 0.4)

    def test_legacy_fallback_still_runs_when_blob_misses(self):
        crop = np.full((260, 420, 3), 255, dtype=np.uint8)

        def fake_orientation_row(_crop, _proxy, angle):
            row = {
                "angle": angle,
                "face_detected": angle == 90,
                "qr_detected": False,
                "qr_validated": False,
                "mrz_score": 0.0,
                "triage_state": ocr_local.TRIAGE_STATE_FRONT_NEW if angle == 90 else ocr_local.TRIAGE_STATE_UNKNOWN,
                "confidence": 0.78 if angle == 90 else 0.05,
            }
            return row, 0.0

        with mock.patch.object(
            ocr_local,
            "_scan_front_blob_orientation",
            return_value={"side": "unknown", "confidence": 0.0, "angle": 0, "markers": [], "angle_candidates": []},
        ), mock.patch.object(ocr_local, "_analyze_orientation_row", side_effect=fake_orientation_row):
            triage = ocr_local._triage_crop_orientation(crop)

        self.assertEqual(triage["triage_path"], "legacy")
        self.assertEqual(triage["orientation_angle"], 90)
        self.assertEqual(triage["triage_state"], ocr_local.TRIAGE_STATE_FRONT_NEW)

    def test_blob_front_qr_without_face_falls_back_to_legacy_classifier(self):
        crop = np.full((260, 420, 3), 255, dtype=np.uint8)

        def fake_orientation_row(_crop, _proxy, angle):
            row = {
                "angle": angle,
                "face_detected": False,
                "qr_detected": angle == 90,
                "qr_validated": False,
                "mrz_score": 0.2 if angle == 90 else 0.0,
                "triage_state": ocr_local.TRIAGE_STATE_BACK_NEW if angle == 90 else ocr_local.TRIAGE_STATE_UNKNOWN,
                "confidence": 0.64 if angle == 90 else 0.04,
            }
            return row, 0.0

        with mock.patch.object(
            ocr_local,
            "_scan_front_blob_orientation",
            return_value={"side": "front", "confidence": 0.9, "angle": 90, "markers": ["chip"], "angle_candidates": []},
        ), mock.patch.object(ocr_local, "_analyze_orientation_row", side_effect=fake_orientation_row):
            triage = ocr_local._triage_crop_orientation(crop)

        self.assertEqual(triage["triage_path"], "legacy")
        self.assertEqual(triage["triage_state"], ocr_local.TRIAGE_STATE_BACK_NEW)
        self.assertEqual(triage["orientation_angle"], 90)

    def test_unknown_prepare_skips_rapidocr_detection(self):
        img = np.full((100, 160, 3), 255, dtype=np.uint8)
        crop = ocr_local.DocCrop(
            img_native=img,
            img_ocr=img,
            bbox=(0, 0, 160, 100),
            doc_type="cccd_front",
            confidence=0.99,
        )

        with mock.patch.object(ocr_local, "_preprocess", return_value=img), mock.patch.object(
            ocr_local, "_detect_documents", return_value=[crop]
        ), mock.patch.object(ocr_local, "_pick_primary_crop", return_value=crop), mock.patch.object(
            ocr_local,
            "_triage_crop_orientation",
            return_value={
                "orientation_angle": 0,
                "triage_state": ocr_local.TRIAGE_STATE_UNKNOWN,
                "face_detected": False,
                "qr_detected": False,
                "mrz_score": 0.0,
                "triage_confidence": 0.0,
                "triage_ms": 0.0,
                "qr_detect_ms": 0.0,
                "triage_path": "legacy",
                "blob_side": "unknown",
                "blob_confidence": 0.0,
                "blob_markers": [],
                "angle_candidates": [],
            },
        ), mock.patch.object(ocr_local, "_rapidocr_detect_boxes") as rapid_det_mock:
            prepared = ocr_local._analyze_image_prepare(
                index=0,
                filename="unknown.jpg",
                raw_bytes=make_image_bytes(img),
                seeded_qr_text="",
                client_qr_failed=True,
                trace_id="test-unknown",
            )

        rapid_det_mock.assert_not_called()
        self.assertEqual(prepared["triage_state"], ocr_local.TRIAGE_STATE_UNKNOWN)
        self.assertEqual(prepared["ocr_box_count"], 0)
        self.assertEqual(prepared["id_source"], "none")

    def test_qr_rescue_promotes_front_new_row_to_front_old(self):
        img = np.full((100, 160, 3), 255, dtype=np.uint8)
        crop = ocr_local.DocCrop(
            img_native=img,
            img_ocr=img,
            bbox=(0, 0, 160, 100),
            doc_type="cccd_front",
            confidence=0.99,
        )
        qr_data = {
            "so_giay_to": "036065001407",
            "ho_ten": "NGO VAN TAN",
            "ngay_sinh": "17/06/1965",
            "gioi_tinh": "Nam",
            "dia_chi": "TO DAN PHO SO 8",
            "ngay_cap": "21/05/2025",
        }

        with mock.patch.object(ocr_local, "_preprocess", return_value=img), mock.patch.object(
            ocr_local, "_detect_documents", return_value=[crop]
        ), mock.patch.object(ocr_local, "_pick_primary_crop", return_value=crop), mock.patch.object(
            ocr_local,
            "_triage_crop_orientation",
            return_value={
                "orientation_angle": 0,
                "triage_state": ocr_local.TRIAGE_STATE_FRONT_NEW,
                "face_detected": True,
                "qr_detected": False,
                "mrz_score": 0.1,
                "triage_confidence": 0.6,
                "triage_ms": 0.0,
                "qr_detect_ms": 0.0,
                "triage_path": "blob_front",
                "blob_side": "front",
                "blob_confidence": 0.8,
                "blob_markers": ["chip"],
                "angle_candidates": [],
            },
        ), mock.patch.object(ocr_local, "_rapidocr_detect_boxes", return_value=([], 0.0)), mock.patch.object(
            ocr_local,
            "_extract_primary_id",
            return_value=("", "none", "", 0.0, 0, 0),
        ), mock.patch.object(
            ocr_local,
            "_try_qr_data_from_crop",
            return_value=(qr_data, "036065001407|..."),
        ):
            prepared = ocr_local._analyze_image_prepare(
                index=0,
                filename="front-qr.jpg",
                raw_bytes=make_image_bytes(img),
                seeded_qr_text="",
                client_qr_failed=True,
                trace_id="test-qr-rescue-front",
            )

        self.assertEqual(prepared["source_type"], "QR")
        self.assertEqual(prepared["triage_state"], ocr_local.TRIAGE_STATE_FRONT_OLD)
        self.assertEqual(prepared["profile"], ocr_local.DOC_PROFILE_FRONT_OLD)
        self.assertEqual(prepared["side"], "front")
        self.assertEqual(prepared["id_source"], "qr")
        self.assertEqual(prepared["id_12"], "036065001407")

    def test_try_qr_data_from_crop_uses_sharpened_variant_when_native_fails(self):
        img = np.full((120, 180, 3), 220, dtype=np.uint8)
        crop = ocr_local.DocCrop(
            img_native=img,
            img_ocr=img,
            bbox=(0, 0, 180, 120),
            doc_type="cccd_back",
            confidence=0.99,
        )
        qr_text = "036084011825|162440815|Nguyễn Huy Hoàng|09121984|Nam|Thôn Hoàng Mẫu, Yên Lương, Ý Yên, Nam Định|06012025||||"
        timing = {}

        with mock.patch.object(ocr_local, "try_decode_qr", side_effect=["", qr_text]):
            qr_data, decoded_text = ocr_local._try_qr_data_from_crop(crop, timing=timing)

        self.assertTrue(ocr_local._is_valid_qr_data(qr_data))
        self.assertEqual(decoded_text, qr_text)
        self.assertEqual(timing.get("result"), "backend_qr")
        self.assertEqual(timing.get("variant"), "sharp_gray")
        self.assertGreaterEqual(len(timing.get("variant_attempts", [])), 2)

    def test_qr_rescue_retries_other_rotations_for_back_row(self):
        img = np.full((100, 160, 3), 255, dtype=np.uint8)
        crop = ocr_local.DocCrop(
            img_native=img,
            img_ocr=img,
            bbox=(0, 0, 160, 100),
            doc_type="cccd_back",
            confidence=0.99,
        )
        qr_data = {
            "so_giay_to": "036084011825",
            "ho_ten": "NGUYEN HUY HOANG",
            "ngay_sinh": "09/12/1984",
            "gioi_tinh": "Nam",
            "dia_chi": "THON HOANG MAU",
            "ngay_cap": "06/01/2025",
        }

        with mock.patch.object(ocr_local, "_preprocess", return_value=img), mock.patch.object(
            ocr_local, "_detect_documents", return_value=[crop]
        ), mock.patch.object(ocr_local, "_pick_primary_crop", return_value=crop), mock.patch.object(
            ocr_local,
            "_triage_crop_orientation",
            return_value={
                "orientation_angle": 90,
                "triage_state": ocr_local.TRIAGE_STATE_BACK_NEW,
                "face_detected": False,
                "qr_detected": True,
                "mrz_score": 0.9,
                "triage_confidence": 0.64,
                "triage_ms": 0.0,
                "qr_detect_ms": 0.0,
                "triage_path": "legacy",
                "blob_side": "front",
                "blob_confidence": 1.0,
                "blob_markers": ["chip"],
                "angle_candidates": [],
            },
        ), mock.patch.object(ocr_local, "_rapidocr_detect_boxes", return_value=([], 0.0)), mock.patch.object(
            ocr_local,
            "_extract_primary_id",
            return_value=("", "none", "", 0.0, 0, 0),
        ), mock.patch.object(
            ocr_local,
            "_try_qr_data_from_crop",
            side_effect=[(None, ""), (None, ""), (qr_data, "036084011825|...")],
        ):
            prepared = ocr_local._analyze_image_prepare(
                index=0,
                filename="back-qr.jpg",
                raw_bytes=make_image_bytes(img),
                seeded_qr_text="",
                client_qr_failed=True,
                trace_id="test-qr-rescue-back",
            )

        self.assertEqual(prepared["source_type"], "QR")
        self.assertEqual(prepared["triage_state"], ocr_local.TRIAGE_STATE_BACK_NEW)
        self.assertEqual(prepared["profile"], ocr_local.DOC_PROFILE_BACK_NEW)
        self.assertEqual(prepared["side"], "back")
        self.assertEqual(prepared["orientation_angle"], 0)
        self.assertEqual(prepared["id_source"], "qr")
        self.assertEqual(prepared["id_12"], "036084011825")

    def test_back_old_still_attempts_qr_rescue_before_ocr_when_qr_proxy_misses(self):
        img = np.full((100, 160, 3), 255, dtype=np.uint8)
        crop = ocr_local.DocCrop(
            img_native=img,
            img_ocr=img,
            bbox=(0, 0, 160, 100),
            doc_type="cccd_back",
            confidence=0.99,
        )
        qr_data = {
            "so_giay_to": "036084011825",
            "ho_ten": "NGUYEN HUY HOANG",
            "ngay_sinh": "09/12/1984",
            "gioi_tinh": "Nam",
            "dia_chi": "THON HOANG MAU",
            "ngay_cap": "06/01/2025",
        }

        with mock.patch.object(ocr_local, "_preprocess", return_value=img), mock.patch.object(
            ocr_local, "_detect_documents", return_value=[crop]
        ), mock.patch.object(ocr_local, "_pick_primary_crop", return_value=crop), mock.patch.object(
            ocr_local,
            "_triage_crop_orientation",
            return_value={
                "orientation_angle": 180,
                "triage_state": ocr_local.TRIAGE_STATE_BACK_OLD,
                "face_detected": False,
                "qr_detected": False,
                "mrz_score": 1.0,
                "triage_confidence": 0.46,
                "triage_ms": 0.0,
                "qr_detect_ms": 0.0,
                "triage_path": "legacy",
                "blob_side": "front",
                "blob_confidence": 1.0,
                "blob_markers": ["chip"],
                "angle_candidates": [],
            },
        ), mock.patch.object(
            ocr_local,
            "_try_qr_data_from_rotations",
            return_value=(qr_data, "036084011825|...", 0),
        ), mock.patch.object(ocr_local, "_rapidocr_detect_boxes") as rapid_det_mock:
            prepared = ocr_local._analyze_image_prepare(
                index=0,
                filename="back-old-missed-qr.jpg",
                raw_bytes=make_image_bytes(img),
                seeded_qr_text="",
                client_qr_failed=True,
                trace_id="test-back-old-qr-rescue",
            )

        rapid_det_mock.assert_not_called()
        self.assertEqual(prepared["source_type"], "QR")
        self.assertEqual(prepared["triage_state"], ocr_local.TRIAGE_STATE_BACK_NEW)
        self.assertEqual(prepared["profile"], ocr_local.DOC_PROFILE_BACK_NEW)
        self.assertEqual(prepared["side"], "back")
        self.assertEqual(prepared["orientation_angle"], 0)
        self.assertEqual(prepared["id_source"], "qr")
        self.assertEqual(prepared["id_12"], "036084011825")


class BatchReviewTests(unittest.TestCase):
    def test_image_refs_follow_front_back_pair_and_unknown_stays_in_image_results(self):
        img = np.full((24, 24, 3), 255, dtype=np.uint8)
        base_timing = {
            "decode_ms": 0.0,
            "preprocess_ms": 0.0,
            "detect_ms": 0.0,
            "triage_ms": 0.0,
            "qr_detect_ms": 0.0,
            "qr_decode_ms": 0.0,
            "rapidocr_det_ms": 0.0,
            "id_extract_ms": 0.0,
            "targeted_extract_ms": 0.0,
            "merge_ms": 0.0,
            "total_ms": 0.0,
        }
        prepared_rows = [
            {
                "index": 0,
                "filename": "front.jpg",
                "img_native": img,
                "img_ocr": img,
                "det_boxes": [],
                "source_type": "OCR",
                "side": "front",
                "profile": ocr_local.DOC_PROFILE_FRONT_NEW,
                "doc_type": "cccd_front",
                "triage_state": ocr_local.TRIAGE_STATE_FRONT_NEW,
                "orientation_angle": 0,
                "face_detected": True,
                "qr_detected": False,
                "mrz_score": 0.0,
                "triage_path": "legacy",
                "triage_confidence": 0.8,
                "blob_side": "unknown",
                "blob_confidence": 0.0,
                "blob_markers": [],
                "qr_text": "",
                "qr_data": {},
                "data": ocr_local._empty_person_data(),
                "id_12": "",
                "id_source": "none",
                "raw_text": "",
                "client_qr_failed": True,
                "timing_ms": dict(base_timing),
                "ocr_box_count": 0,
                "line_count": 0,
            },
            {
                "index": 1,
                "filename": "back.jpg",
                "img_native": img,
                "img_ocr": img,
                "det_boxes": [],
                "source_type": "QR",
                "side": "back",
                "profile": ocr_local.DOC_PROFILE_BACK_NEW,
                "doc_type": "cccd_back",
                "triage_state": ocr_local.TRIAGE_STATE_BACK_NEW,
                "orientation_angle": 0,
                "face_detected": False,
                "qr_detected": True,
                "mrz_score": 0.0,
                "triage_path": "legacy",
                "triage_confidence": 0.9,
                "blob_side": "unknown",
                "blob_confidence": 0.0,
                "blob_markers": [],
                "qr_text": "seeded",
                "qr_data": {"so_giay_to": "012345678901"},
                "data": {
                    "so_giay_to": "012345678901",
                    "ho_ten": "",
                    "ngay_sinh": "",
                    "gioi_tinh": "",
                    "dia_chi": "25 NGUYEN TRAI",
                    "ngay_cap": "03/04/2021",
                    "ngay_het_han": "",
                },
                "id_12": "012345678901",
                "id_source": "qr",
                "raw_text": "",
                "client_qr_failed": False,
                "timing_ms": dict(base_timing),
                "ocr_box_count": 0,
                "line_count": 0,
            },
            {
                "index": 2,
                "filename": "unknown.jpg",
                "img_native": img,
                "img_ocr": img,
                "det_boxes": [],
                "source_type": "OCR",
                "side": "unknown",
                "profile": ocr_local.DOC_PROFILE_UNKNOWN,
                "doc_type": "unknown",
                "triage_state": ocr_local.TRIAGE_STATE_UNKNOWN,
                "orientation_angle": 0,
                "face_detected": False,
                "qr_detected": False,
                "mrz_score": 0.0,
                "triage_path": "legacy",
                "triage_confidence": 0.0,
                "blob_side": "unknown",
                "blob_confidence": 0.0,
                "blob_markers": [],
                "qr_text": "",
                "qr_data": {},
                "data": ocr_local._empty_person_data(),
                "id_12": "",
                "id_source": "none",
                "raw_text": "",
                "client_qr_failed": True,
                "timing_ms": dict(base_timing),
                "ocr_box_count": 0,
                "line_count": 0,
            },
        ]

        def fake_prepare(*_args, **_kwargs):
            return prepared_rows.pop(0)

        with mock.patch.object(ocr_local, "_ensure_local_ocr_dependencies"), mock.patch.object(
            ocr_local, "_get_rapidocr_engine", return_value=object()
        ), mock.patch.object(ocr_local, "_analyze_image_prepare", side_effect=fake_prepare), mock.patch.object(
            ocr_local,
            "_run_detail_phase",
            return_value=(
                {
                    "so_giay_to": "012345678901",
                    "ho_ten": "NGUYEN VAN AN",
                    "ngay_sinh": "01/02/1990",
                    "gioi_tinh": "Nam",
                    "dia_chi": "",
                    "ngay_cap": "",
                    "ngay_het_han": "",
                },
                "front detail text",
                5.0,
                ocr_local.DOC_PROFILE_FRONT_NEW,
            ),
        ):
            result = ocr_local._local_ocr_batch_from_inputs_triage_v2(
                file_items=[
                    {"index": 0, "filename": "front.jpg", "bytes": b"a"},
                    {"index": 1, "filename": "back.jpg", "bytes": b"b"},
                    {"index": 2, "filename": "unknown.jpg", "bytes": b"c"},
                ],
                trace_id="batch-review",
            )

        self.assertEqual(len(result["persons"]), 1)
        refs = result["persons"][0]["image_refs"]
        self.assertEqual([ref["side"] for ref in refs], ["front", "back"])
        self.assertEqual(result["persons"][0]["data"]["so_giay_to"], "012345678901")
        self.assertEqual(len(result["image_results"]), 3)
        self.assertEqual(result["image_results"][1]["profile"], ocr_local.DOC_PROFILE_BACK_NEW)
        self.assertEqual(result["image_results"][2]["triage_state"], ocr_local.TRIAGE_STATE_UNKNOWN)

    def test_detail_phase_can_flip_row_to_back_without_losing_row_profile(self):
        img = np.full((24, 24, 3), 255, dtype=np.uint8)
        base_timing = {
            "decode_ms": 0.0,
            "preprocess_ms": 0.0,
            "detect_ms": 0.0,
            "triage_ms": 0.0,
            "qr_detect_ms": 0.0,
            "qr_decode_ms": 0.0,
            "rapidocr_det_ms": 0.0,
            "id_extract_ms": 0.0,
            "targeted_extract_ms": 0.0,
            "merge_ms": 0.0,
            "total_ms": 0.0,
        }
        prepared_rows = [
            {
                "index": 0,
                "filename": "back-like.jpg",
                "img_native": img,
                "img_ocr": img,
                "det_boxes": [],
                "source_type": "OCR",
                "side": "front",
                "profile": ocr_local.DOC_PROFILE_FRONT_NEW,
                "doc_type": "cccd_front",
                "triage_state": ocr_local.TRIAGE_STATE_FRONT_NEW,
                "orientation_angle": 0,
                "face_detected": True,
                "qr_detected": False,
                "mrz_score": 1.0,
                "triage_path": "legacy",
                "triage_confidence": 0.6,
                "blob_side": "front",
                "blob_confidence": 0.7,
                "blob_markers": ["emblem"],
                "qr_text": "",
                "qr_data": {},
                "data": ocr_local._empty_person_data(),
                "id_12": "",
                "id_source": "none",
                "raw_text": "",
                "client_qr_failed": True,
                "timing_ms": dict(base_timing),
                "ocr_box_count": 0,
                "line_count": 0,
            },
            {
                "index": 1,
                "filename": "front.jpg",
                "img_native": img,
                "img_ocr": img,
                "det_boxes": [],
                "source_type": "OCR",
                "side": "front",
                "profile": ocr_local.DOC_PROFILE_FRONT_OLD,
                "doc_type": "cccd_front",
                "triage_state": ocr_local.TRIAGE_STATE_FRONT_OLD,
                "orientation_angle": 0,
                "face_detected": True,
                "qr_detected": True,
                "mrz_score": 0.0,
                "triage_path": "legacy",
                "triage_confidence": 0.9,
                "blob_side": "front",
                "blob_confidence": 0.9,
                "blob_markers": ["emblem", "chip"],
                "qr_text": "",
                "qr_data": {},
                "data": ocr_local._empty_person_data(),
                "id_12": "036185021354",
                "id_source": "front_roi",
                "raw_text": "",
                "client_qr_failed": True,
                "timing_ms": dict(base_timing),
                "ocr_box_count": 0,
                "line_count": 0,
            },
        ]

        def fake_prepare(*_args, **_kwargs):
            return prepared_rows.pop(0)

        detail_results = [
            (
                {
                    "so_giay_to": "036185021354",
                    "ho_ten": "",
                    "ngay_sinh": "",
                    "gioi_tinh": "",
                    "dia_chi": "",
                    "ngay_cap": "18/08/2022",
                    "ngay_het_han": "",
                },
                "back detail text",
                7.5,
                ocr_local.DOC_PROFILE_BACK_OLD,
            ),
            (
                {
                    "so_giay_to": "036185021354",
                    "ho_ten": "NGUYEN THI OANH",
                    "ngay_sinh": "09/05/1985",
                    "gioi_tinh": "Nữ",
                    "dia_chi": "",
                    "ngay_cap": "",
                    "ngay_het_han": "",
                },
                "front detail text",
                5.0,
                ocr_local.DOC_PROFILE_FRONT_OLD,
            ),
        ]

        def fake_detail(*_args, **_kwargs):
            return detail_results.pop(0)

        with mock.patch.object(ocr_local, "_ensure_local_ocr_dependencies"), mock.patch.object(
            ocr_local, "_get_rapidocr_engine", return_value=object()
        ), mock.patch.object(ocr_local, "_analyze_image_prepare", side_effect=fake_prepare), mock.patch.object(
            ocr_local,
            "_run_detail_phase",
            side_effect=fake_detail,
        ):
            result = ocr_local._local_ocr_batch_from_inputs_triage_v2(
                file_items=[
                    {"index": 0, "filename": "back-like.jpg", "bytes": b"a"},
                    {"index": 1, "filename": "front.jpg", "bytes": b"b"},
                ],
                trace_id="batch-row-profile",
            )

        self.assertEqual(len(result["persons"]), 1)
        self.assertEqual(
            [ref["triage_state"] for ref in result["persons"][0]["image_refs"]],
            [ocr_local.TRIAGE_STATE_BACK_OLD, ocr_local.TRIAGE_STATE_FRONT_OLD],
        )
        self.assertEqual(result["image_results"][0]["side"], "back")
        self.assertEqual(result["image_results"][0]["triage_state"], ocr_local.TRIAGE_STATE_BACK_OLD)
        self.assertEqual(result["image_results"][0]["profile"], ocr_local.DOC_PROFILE_BACK_OLD)
        self.assertEqual(result["image_results"][1]["profile"], ocr_local.DOC_PROFILE_FRONT_OLD)

    def test_run_detail_phase_retries_back_rotation_when_current_angle_is_weak(self):
        img = np.full((24, 24, 3), 255, dtype=np.uint8)
        prepared = {
            "filename": "4.jpg",
            "img_native": img,
            "img_ocr": img,
            "det_boxes": [make_box(1, 1, 10, 10)],
            "source_type": "OCR",
            "side": "back",
            "profile": ocr_local.DOC_PROFILE_BACK_NEW,
            "doc_type": "cccd_back",
            "triage_state": ocr_local.TRIAGE_STATE_BACK_NEW,
            "orientation_angle": 270,
            "id_12": "",
            "ocr_box_count": 1,
        }
        weak_candidate = (
            {
                "so_giay_to": "038919333595",
                "ho_ten": "",
                "ngay_sinh": "",
                "gioi_tinh": "",
                "dia_chi": "",
                "ngay_cap": "",
                "ngay_het_han": "",
            },
            "03891933359595959wyndnvadxnianin",
            3.0,
            ocr_local.DOC_PROFILE_BACK_OLD,
            {
                "angle": 270,
                "selected_box_count": 10,
                "recognized_count": 8,
                "score": 8.4,
                "raw_text_preview": "038919333595",
                "final_profile": ocr_local.DOC_PROFILE_BACK_OLD,
                "inferred_profile": ocr_local.DOC_PROFILE_BACK_OLD,
                "id_12": "038919333595",
            },
        )
        weak_zero = (
            ocr_local._empty_person_data(),
            "",
            1.0,
            ocr_local.DOC_PROFILE_BACK_NEW,
            {
                "angle": 0,
                "selected_box_count": 0,
                "recognized_count": 0,
                "score": 0.0,
                "raw_text_preview": "",
                "final_profile": ocr_local.DOC_PROFILE_BACK_NEW,
                "inferred_profile": ocr_local.DOC_PROFILE_UNKNOWN,
                "id_12": "",
            },
        )
        strong_ninety = (
            {
                "so_giay_to": "036082000989",
                "ho_ten": "",
                "ngay_sinh": "",
                "gioi_tinh": "Nam",
                "dia_chi": "",
                "ngay_cap": "",
                "ngay_het_han": "",
            },
            "Dac diem nhan dang /Personal identification:\nIDVNM0820009892036082000989<<7",
            4.0,
            ocr_local.DOC_PROFILE_BACK_OLD,
            {
                "angle": 90,
                "selected_box_count": 8,
                "recognized_count": 8,
                "score": 18.7,
                "raw_text_preview": "IDVNM0820009892036082000989<<7",
                "final_profile": ocr_local.DOC_PROFILE_BACK_OLD,
                "inferred_profile": ocr_local.DOC_PROFILE_BACK_OLD,
                "id_12": "036082000989",
            },
        )
        weak_one_eighty = (
            ocr_local._empty_person_data(),
            "1 5 1 E 1 1 L 1",
            1.5,
            ocr_local.DOC_PROFILE_BACK_OLD,
            {
                "angle": 180,
                "selected_box_count": 4,
                "recognized_count": 3,
                "score": 1.1,
                "raw_text_preview": "1 5 1 E 1 1 L 1",
                "final_profile": ocr_local.DOC_PROFILE_BACK_OLD,
                "inferred_profile": ocr_local.DOC_PROFILE_BACK_OLD,
                "id_12": "",
            },
        )

        with mock.patch.object(ocr_local, "_ensure_detection"), mock.patch.object(
            ocr_local,
            "_run_detail_phase_once",
            side_effect=[weak_candidate, weak_zero, strong_ninety, weak_one_eighty],
        ), mock.patch.object(
            ocr_local,
            "_rapidocr_detect_boxes",
            side_effect=[([], 1.0), ([], 1.5), ([], 2.0)],
        ):
            parsed, raw_text, detail_ms, final_profile = ocr_local._run_detail_phase(prepared, {"data": {}})

        self.assertEqual(parsed["so_giay_to"], "036082000989")
        self.assertEqual(raw_text, "Dac diem nhan dang /Personal identification:\nIDVNM0820009892036082000989<<7")
        self.assertEqual(final_profile, ocr_local.DOC_PROFILE_BACK_OLD)
        self.assertEqual(prepared["orientation_angle"], 90)
        self.assertEqual(prepared["ocr_box_count"], 0)
        self.assertAlmostEqual(detail_ms, 14.0)


class _FakeQuery:
    def __init__(self, job):
        self.job = job

    def filter(self, *_args, **_kwargs):
        return self

    def first(self):
        return self.job

    def all(self):
        return [self.job] if self.job else []


class _FakeDB:
    def __init__(self, job):
        self.job = job
        self.committed = False

    def query(self, _model):
        return _FakeQuery(self.job)

    def commit(self):
        self.committed = True

    def close(self):
        return None


@unittest.skipIf(ocr_local.cv2 is None or ocr_local.np is None, "opencv not available")
class SessionRouteTests(unittest.TestCase):
    def setUp(self):
        self.app = FastAPI()
        self.app.include_router(ocr_local.router, prefix="/api/ocr")
        self.client = TestClient(self.app)

    def test_image_route_serves_retained_session_and_delete_purges_it(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            img_bytes = make_image_bytes(np.full((32, 48, 3), 255, dtype=np.uint8))
            image_path = os.path.join(tmpdir, "0000.jpg")
            with open(image_path, "wb") as fw:
                fw.write(img_bytes)
            ocr_local._write_local_ocr_session_manifest(
                tmpdir,
                "job-session",
                [{"index": 0, "filename": "front.jpg", "stored_name": "0000.jpg"}],
            )

            job = SimpleNamespace(
                id="job-session",
                temp_file_path=tmpdir,
                status="completed",
                result_json=None,
                error_message=None,
                updated_at=ocr_local.datetime.utcnow(),
            )
            fake_db = _FakeDB(job)

            with mock.patch.object(ocr_local, "SessionLocal", return_value=fake_db):
                get_resp = self.client.get("/api/ocr/local/image/job-session/0")
                self.assertEqual(get_resp.status_code, 200)
                self.assertGreater(len(get_resp.content), 0)

                delete_resp = self.client.delete("/api/ocr/local/session/job-session")
                self.assertEqual(delete_resp.status_code, 200)
                self.assertFalse(os.path.exists(tmpdir))
                self.assertIsNone(job.temp_file_path)

                not_found_resp = self.client.get("/api/ocr/local/image/job-session/0")
                self.assertEqual(not_found_resp.status_code, 404)


if __name__ == "__main__":
    unittest.main()
