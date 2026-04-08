from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tools.upload_lab.extract_contract import extract


SAMPLE_TRANSFER_TEXT = """HỢP ĐỒNG CHUYỂN NHƯỢNG QUYỀN SỬ DỤNG ĐẤT
Số công chứng 274/2026/CCGD
I. BÊN CHUYỂN NHƯỢNG: (Bên A)
1. Ông: Đỗ Văn Tích Sinh ngày: 16/11/1980
Căn cước công dân số: 036080009365 do Cục Cảnh sát quản lý hành chính về trật tự xã hội cấp ngày 26/10/2023
2. Và vợ là Bà: Hoàng Thu Hiền Sinh ngày: 28/09/1980
Căn cước công dân số: 037180007485 do Cục Cảnh sát quản lý hành chính về trật tự xã hội cấp ngày 19/11/2022
Cả hai ông bà cùng thường trú tại: xã Yên Xá, huyện Ý Yên, tỉnh Nam Định.
II. BÊN NHẬN CHUYỂN NHƯỢNG: (Bên B)
1. Ông: Dương Trọng Lượng Sinh ngày: 15/02/1975
Căn cước công dân số: 036075003598 do Cục Cảnh sát quản lý hành chính về trật tự xã hội cấp ngày 02/07/2021
2. Và vợ là Bà: Phùng Thị Dung Sinh ngày: 15/06/1984
Căn cước công dân số: 036184005556 do Cục Cảnh sát quản lý hành chính về trật tự xã hội cấp ngày 23/05/2024
Thường trú tại: thôn Tây Tống Xá, xã Ý Yên, tỉnh Ninh Bình.
Hai bên tự nguyện lập và ký Hợp đồng này.
ĐIỀU 1
Đối tượng của Hợp đồng này là toàn bộ quyền sử dụng đất tại thôn Đông Tống Xá, xã Ý Yên, tỉnh Ninh Bình.
- Thửa đất số: 12
- Diện tích: 100 m2
1.2 Giá chuyển nhượng là ...
LỜI CHỨNG
Hôm nay, ngày 27 tháng 02 năm 2026, tại Văn phòng công chứng ...
"""

SAMPLE_LOAN_TEXT = """HỢP ĐỒNG VAY TIỀN
Số công chứng 289/2026/CCGD
I. BÊN CHO VAY (BÊN A):
Ông: Nguyễn Thanh Tùng Sinh ngày: 24/06/1971
Căn cước công dân số: 036071011466 do Cục Cảnh sát quản lý hành chính về trật tự xã hội cấp ngày 10/05/2021
Thường trú tại: xã Ý Yên, tỉnh Ninh Bình.
II. BÊN VAY (BÊN B):
1. Ông: Dương Trọng Lượng Sinh ngày: 15/02/1975
Căn cước công dân số: 036075003598 do Cục Cảnh sát quản lý hành chính về trật tự xã hội cấp ngày 02/07/2021
2. Và vợ là bà: Phùng Thị Dung Sinh ngày: 15/06/1984
Căn cước công dân số: 036184005556 do Cục Cảnh sát quản lý hành chính về trật tự xã hội cấp ngày 23/05/2024
Thường trú tại: thôn Tây Tống Xá, xã Ý Yên, tỉnh Ninh Bình.
Các bên tự nguyện lập và ký vào bản Hợp đồng vay tiền này với các điều khoản sau đây:
ĐIỀU 1: SỐ TIỀN VAY
Bên A đồng ý cho Bên B vay số tiền là 1.300.000.000 VNĐ.
LỜI CHỨNG
Hôm nay, ngày 04 tháng 03 năm 2026...
"""

SAMPLE_TRANSFER_PREAMBLE_TEXT = """HỢP ĐỒNG CHUYỂN NHƯỢNG QUYỀN SỬ DỤNG ĐẤT
Số công chứng 274/2026/CCGD
Chúng tôi gồm có:
1. Ông: Đỗ Văn Tích Sinh ngày: 16/11/1980
Căn cước công dân số: 036080009365 do Cục Cảnh sát quản lý hành chính về trật tự xã hội cấp ngày 26/10/2023
2. Và vợ là Bà: Hoàng Thu Hiền Sinh ngày: 28/09/1980
Căn cước công dân số: 037180007485 do Cục Cảnh sát quản lý hành chính về trật tự xã hội cấp ngày 19/11/2022
Cả hai ông bà cùng thường trú tại: xã Yên Xá, huyện Ý Yên, tỉnh Nam Định.
II. BÊN NHẬN CHUYỂN NHƯỢNG: (Bên B)
1. Ông: Dương Trọng Lượng Sinh ngày: 15/02/1975
Căn cước công dân số: 036075003598 do Cục Cảnh sát quản lý hành chính về trật tự xã hội cấp ngày 02/07/2021
2. Và vợ là bà: Phùng Thị Dung Sinh ngày: 15/06/1984
Căn cước công dân số: 036184005556 do Cục Cảnh sát quản lý hành chính về trật tự xã hội cấp ngày 23/05/2024
Thường trú tại: thôn Tây Tống Xá, xã Ý Yên, tỉnh Ninh Bình.
Hai bên tự nguyện lập và ký Hợp đồng này.
ĐIỀU 1: ĐỐI TƯỢNG CỦA HỢP ĐỒNG
Đối tượng của Hợp đồng này là toàn bộ quyền sử dụng đất.
LỜI CHỨNG
Hôm nay, ngày 27 tháng 02 năm 2026...
"""

SAMPLE_COMMITMENT_TEXT = """VĂN BẢN CAM KẾT TÀI SẢN RIÊNG
Số công chứng 407/2026/CCGD
Chúng tôi gồm có:
1. Ông: Nguyễn Văn A Sinh ngày: 01/01/1980
Căn cước công dân số: 012345678901 do Cục Cảnh sát quản lý hành chính về trật tự xã hội cấp ngày 01/01/2023
2. Và vợ là Bà: Trần Thị B Sinh ngày: 02/02/1982
Căn cước công dân số: 012345678902 do Cục Cảnh sát quản lý hành chính về trật tự xã hội cấp ngày 02/02/2023
Cả hai ông bà cùng thường trú tại: xã Yên Xá, huyện Ý Yên, tỉnh Nam Định.
Ông Nguyễn Văn A hiện đang sở hữu Tài Sản là quyền sử dụng đất theo Giấy chứng nhận quyền sử dụng đất số AB 123456.
Thửa đất số: 88
Địa chỉ: xã Yên Xá, huyện Ý Yên, tỉnh Nam Định
Diện tích: 120 m2
Tài sản gắn liền với thửa đất nói trên là nhà ở 02 tầng.
Các quyền, lợi ích, khoản thanh toán mà ông A có thể nhận được liên quan tới quyền sử dụng đất nêu trên cũng là tài sản riêng.
Bằng văn bản này chúng tôi xác định:
Đây là tài sản riêng của ông Nguyễn Văn A.
LỜI CHỨNG
Hôm nay, ngày 31 tháng 03 năm 2026...
"""

SAMPLE_CANCELLATION_TEXT = """VĂN BẢN THỎA THUẬN VỀ VIỆC HỦY BỎ HỢP ĐỒNG CHUYỂN NHƯỢNG QUYỀN SỬ DỤNG ĐẤT VÀ TÀI SẢN GẮN LIỀN VỚI ĐẤT
Số công chứng 320/2026/CCGD
I. BÊN A:
Ông: Nguyễn Văn A Sinh ngày: 01/01/1980
Căn cước công dân số: 012345678901 do Cục Cảnh sát quản lý hành chính về trật tự xã hội cấp ngày 01/01/2023
II. BÊN B:
Bà: Trần Thị B Sinh ngày: 02/02/1982
Căn cước công dân số: 012345678902 do Cục Cảnh sát quản lý hành chính về trật tự xã hội cấp ngày 02/02/2023
Điều 1. Hai bên thống nhất hủy bỏ Hợp đồng chuyển nhượng quyền sử dụng đất và tài sản gắn liền với đất có địa chỉ tại: thôn Đông Tống Xá, xã Yên Xá, huyện Ý Yên, tỉnh Nam Định; Giấy chứng nhận quyền sử dụng đất số AB 123456, số vào sổ cấp GCN: CS 99999, cấp ngày 01/01/2020, cập nhật biến động ngày 02/02/2024 và được Công chứng viên Văn phòng công chứng Nam Định chứng nhận.
Điều 2. Hai bên không còn quyền, nghĩa vụ nào khác.
LỜI CHỨNG
Hôm nay, ngày 23 tháng 03 năm 2026...
"""


class ExtractContractTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tempdir.cleanup)
        self.root = Path(self.tempdir.name)

    def test_extract_doc_transfer_uses_fast_plain_text_path(self):
        doc_path = self.root / "hop_dong.doc"
        doc_path.write_text("placeholder", encoding="utf-8")

        with patch("tools.upload_lab.extract_contract.read_doc_via_ifilter", return_value=SAMPLE_TRANSFER_TEXT) as ifilter_mock:
            payload = extract(doc_path)

        self.assertEqual(payload["web_form"]["so_cong_chung"], "274/2026")
        self.assertEqual(payload["web_form"]["ten_hop_dong"], "Hợp đồng chuyển nhượng quyền sử dụng đất")
        self.assertEqual(payload["web_form"]["ngay_cong_chung"], "27/02/2026")
        self.assertEqual(payload["web_form"]["nhom_hop_dong"], "Chuyển nhượng - Mua bán")
        self.assertEqual(payload["web_form"]["loai_tai_san"], "Đất đai không có tài sản")
        self.assertIn("Dương Trọng Lượng", payload["web_form"]["nguoi_yeu_cau"])
        self.assertIn("Phùng Thị Dung", payload["web_form"]["duong_su"])
        self.assertIn("Đối tượng của Hợp đồng này là toàn bộ quyền sử dụng đất", payload["web_form"]["tai_san"])
        self.assertNotIn("1.2 Giá chuyển nhượng", payload["web_form"]["tai_san"])
        self.assertEqual(payload["raw"]["document_kind"], "transfer_contract")
        self.assertEqual(payload["raw"]["extract_mode"], "plain_text_doc")
        self.assertFalse(payload["raw"]["extract_is_partial"])
        self.assertEqual(payload["raw"]["missing_web_form_fields"], [])
        self.assertGreaterEqual(ifilter_mock.call_count, 1)

    def test_extract_docx_parses_generic_loan_parties(self):
        docx_path = self.root / "hop_dong_vay.docx"
        docx_path.write_text("placeholder", encoding="utf-8")

        with patch("tools.upload_lab.extract_contract.read_docx", return_value=SAMPLE_LOAN_TEXT):
            payload = extract(docx_path)

        self.assertEqual(payload["web_form"]["so_cong_chung"], "289/2026")
        self.assertIn("Dương Trọng Lượng", payload["web_form"]["nguoi_yeu_cau"])
        self.assertIn("Nguyễn Thanh Tùng", payload["web_form"]["duong_su"])
        self.assertIn("Phùng Thị Dung", payload["web_form"]["duong_su"])
        self.assertEqual(payload["raw"]["extract_mode"], "structured_docx")

    def test_extract_doc_parses_first_party_from_preamble_when_ben_a_heading_missing(self):
        doc_path = self.root / "hop_dong_preamble.doc"
        doc_path.write_text("placeholder", encoding="utf-8")

        with patch("tools.upload_lab.extract_contract.read_doc_via_ifilter", return_value=SAMPLE_TRANSFER_PREAMBLE_TEXT):
            payload = extract(doc_path)

        self.assertEqual(payload["web_form"]["so_cong_chung"], "274/2026")
        self.assertIn("Đỗ Văn Tích", payload["web_form"]["duong_su"])
        self.assertIn("Hoàng Thu Hiền", payload["web_form"]["duong_su"])
        self.assertIn("Dương Trọng Lượng", payload["web_form"]["duong_su"])

    def test_extract_doc_detects_asset_commitment_rules(self):
        doc_path = self.root / "cam_ket_tai_san.doc"
        doc_path.write_text("placeholder", encoding="utf-8")

        with patch("tools.upload_lab.extract_contract.read_doc_via_ifilter", return_value=SAMPLE_COMMITMENT_TEXT):
            payload = extract(doc_path)

        self.assertEqual(payload["web_form"]["so_cong_chung"], "407/2026")
        self.assertEqual(payload["web_form"]["ten_hop_dong"], "Văn bản cam kết tài sản riêng")
        self.assertEqual(payload["raw"]["document_kind"], "asset_commitment")
        self.assertIn("Nguyễn Văn A", payload["web_form"]["nguoi_yeu_cau"])
        self.assertIn("Nguyễn Văn A", payload["web_form"]["duong_su"])
        self.assertIn("Trần Thị B", payload["web_form"]["duong_su"])
        self.assertIn("Ông Nguyễn Văn A hiện đang sở hữu Tài Sản là quyền sử dụng đất", payload["web_form"]["tai_san"])
        self.assertIn("Tài sản gắn liền với thửa đất nói trên là nhà ở 02 tầng", payload["web_form"]["tai_san"])
        self.assertIn("Các quyền, lợi ích, khoản thanh toán", payload["web_form"]["tai_san"])
        self.assertNotIn("Bằng văn bản này chúng tôi xác định", payload["web_form"]["tai_san"])
        self.assertEqual(len(payload["raw"]["ben_a"]["nguoi"]), 1)
        self.assertEqual(payload["raw"]["ben_a"]["nguoi"][0]["ho_ten"], "Nguyễn Văn A")

    def test_extract_doc_detects_transfer_cancellation_rules(self):
        doc_path = self.root / "huy_hop_dong_chuyen_nhuong.doc"
        doc_path.write_text("placeholder", encoding="utf-8")

        with patch("tools.upload_lab.extract_contract.read_doc_via_ifilter", return_value=SAMPLE_CANCELLATION_TEXT):
            payload = extract(doc_path)

        self.assertEqual(payload["web_form"]["so_cong_chung"], "320/2026")
        self.assertEqual(
            payload["web_form"]["ten_hop_dong"],
            "Văn bản thỏa thuận về việc hủy bỏ hợp đồng chuyển nhượng quyền sử dụng đất và tài sản gắn liền với đất",
        )
        self.assertEqual(payload["raw"]["document_kind"], "transfer_cancellation")
        self.assertIn("có địa chỉ tại: thôn Đông Tống Xá", payload["web_form"]["tai_san"])
        self.assertIn("Giấy chứng nhận quyền sử dụng đất số AB 123456", payload["web_form"]["tai_san"])
        self.assertNotIn("và được Công chứng viên", payload["web_form"]["tai_san"])


if __name__ == "__main__":
    unittest.main()
