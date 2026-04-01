import unittest
from unittest import mock

import numpy as np

from routers import ocr_local


def make_box(x1: int, y1: int, x2: int, y2: int) -> dict:
    return {
        "box": np.array(
            [[x1, y1], [x2, y1], [x2, y2], [x1, y2]],
            dtype=np.float32,
        )
    }


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


if __name__ == "__main__":
    unittest.main()
