from __future__ import annotations

import tempfile
import unicodedata
import unittest
from pathlib import Path

from docx import Document

from tools.upload_lab.extract_contract import extract, find_tai_san


def make_docx(path: Path, *paragraphs: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    doc = Document()
    for paragraph in paragraphs:
        doc.add_paragraph(paragraph)
    doc.save(str(path))
    return path


class UploadLabExtractContractTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tempdir.cleanup)
        self.root = Path(self.tempdir.name)

    def test_transfer_title_ignores_body_huy_bo_clause(self):
        docx_path = make_docx(
            self.root / "transfer.docx",
            "HỢP ĐỒNG CHUYỂN NHƯỢNG QUYỀN SỬ DỤNG ĐẤT",
            "Chúng tôi gồm có:",
            "I. BÊN CHUYỂN NHƯỢNG: (Bên A)",
            "Ông: Nguyễn Văn A Sinh ngày: 01/01/1980",
            "Căn cước công dân số: 012345678901 do Bộ Công an cấp ngày 01/01/2024;",
            "Thường trú tại: thôn A, xã B.",
            "II. BÊN NHẬN CHUYỂN NHƯỢNG: (Bên B)",
            "Ông: Nguyễn Văn B Sinh ngày: 02/02/1981",
            "Căn cước công dân số: 012345678902 do Bộ Công an cấp ngày 02/02/2024;",
            "Thường trú tại: thôn C, xã D.",
            "ĐIỀU 1: ĐỐI TƯỢNG CỦA HỢP ĐỒNG",
            "Đối tượng của Hợp đồng này là toàn bộ quyền sử dụng đất của bên A có địa chỉ tại: thôn A, xã B.",
            "- Thửa đất số: 10",
            "ĐIỀU 8: ĐIỀU KHOẢN CUỐI CÙNG",
            "Việc sửa đổi, bổ sung hoặc hủy bỏ hợp đồng này chỉ có giá trị khi được hai bên lập thành văn bản.",
            "Số công chứng 428/2026/CCGD",
        )

        payload = extract(docx_path)

        self.assertEqual(payload["raw"]["document_kind"], "transfer_contract")
        self.assertEqual(payload["web_form"]["ten_hop_dong"], "Hợp đồng chuyển nhượng quyền sử dụng đất")

    def test_find_tai_san_commitment_stops_before_cam_ket_xac_nhan(self):
        text = "\n".join(
            [
                "VĂN BẢN CAM KẾT TÀI SẢN RIÊNG",
                "Hiện nay, ông Nguyễn Văn Nam đang làm các thủ tục để nhận chuyển nhượng quyền sử dụng đất có địa chỉ tại: thôn A, xã B.",
                "- Thửa đất số: 20",
                "- Diện tích: 200 m2",
                "- Giấy chứng nhận quyền sử dụng đất quyền sở hữu nhà ở và tài sản khác gắn liền với đất số: AB 123456.",
                "Hai vợ chồng chúng tôi cam kết và xác nhận: Toàn bộ số tiền này là tài sản riêng.",
            ]
        )

        tai_san = find_tai_san(unicodedata.normalize("NFD", text))

        self.assertIn("Thửa đất số: 20", tai_san)
        self.assertNotIn("Hai vợ chồng chúng tôi cam kết", tai_san)

    def test_extract_commitment_keeps_both_spouses_and_asset_type(self):
        docx_path = make_docx(
            self.root / "cam_ket_tai_san_rieng.docx",
            "VĂN BẢN CAM KẾT TÀI SẢN RIÊNG",
            "Chúng tôi gồm có:",
            "- Người chồng – Ông: Nguyễn Văn Nam Sinh ngày: 02/02/1982",
            "Căn cước công dân số: 036082000989 do Bộ Công an cấp ngày 02/07/2021",
            "Thường trú tại: Thôn Hoàng Mẫu, xã Vạn Thắng, tỉnh Ninh Bình;",
            "- Người vợ - Bà: Nguyễn Thị Oanh Sinh ngày: 09/05/1985",
            "Căn cước số: 036185021354 do Bộ Công an cấp ngày 12/02/2025;",
            "Nơi cư trú tại: Thôn Hoàng Mẫu, xã Vạn Thắng, tỉnh Ninh Bình.",
            "Chúng tôi là vợ chồng theo Giấy chứng nhận kết hôn số 17.",
            "Nay chúng tôi lập văn bản này để cam kết và chịu trách nhiệm trước pháp luật về những nội dung sau đây:",
            "Hiện nay, ông Nguyễn Văn Nam đang làm các thủ tục để nhận chuyển nhượng quyền sử dụng đất có địa chỉ tại: thôn Đại Lộc Trung, xã Yên Chính, huyện Ý Yên, tỉnh Nam Định Giấy chứng nhận quyền sử dụng đất quyền sở hữu nhà ở và tài sản khác gắn liền với đất số: CY 921651.",
            "- Thửa đất số: 531; Tờ bản đồ số: 22;",
            "- Diện tích: 660,0 m2;",
            "Hai vợ chồng chúng tôi cam kết và xác nhận: Toàn bộ số tiền này là tài sản riêng của ông Nguyễn Văn Nam.",
            "Số công chứng 161/2026/CCGD",
        )

        payload = extract(docx_path)
        duong_su = payload["web_form"]["duong_su"]
        tai_san = payload["web_form"]["tai_san"]

        self.assertEqual(payload["raw"]["document_kind"], "asset_commitment")
        self.assertEqual(payload["web_form"]["ten_hop_dong"], "Văn bản cam kết tài sản riêng")
        self.assertEqual(payload["web_form"]["loai_tai_san"], "Đất đai có tài sản")
        self.assertIn("Nguyễn Văn Nam", duong_su)
        self.assertIn("Nguyễn Thị Oanh", duong_su)
        self.assertNotIn("Hai vợ chồng chúng tôi cam kết", tai_san)

    def test_generic_title_strips_duoc_giao_ket_boi_suffix(self):
        docx_path = make_docx(
            self.root / "uy_quyen.docx",
            "CHỨNG NHẬN:",
            "Hợp đồng ủy quyền này được giao kết bởi:",
            "I. BÊN ỦY QUYỀN",
            "Bà Tạ Thị Chứ; Sinh ngày: 08/01/1956;",
            "Căn cước công dân số 036156012959 do Bộ Công an cấp ngày 10/01/2023;",
            "Thường trú tại: Thôn Tâm Bình, xã Yên Cường, tỉnh Ninh Bình.",
            "II. BÊN ĐƯỢC ỦY QUYỀN",
            "Ông Nguyễn Đức Hiệp; Sinh ngày: 17/05/1982;",
            "Căn cước công dân số 036082016119 do Bộ Công an cấp ngày 09/08/2021;",
            "Thường trú tại: Thôn Tâm Bình, xã Yên Cường, tỉnh Ninh Bình.",
            "Số công chứng 372/2026/CCGD",
        )

        payload = extract(docx_path)

        self.assertEqual(payload["web_form"]["ten_hop_dong"], "Hợp đồng ủy quyền")

    def test_party_blocks_keep_shared_tru_tai_lines_for_each_person(self):
        docx_path = make_docx(
            self.root / "shared_address.docx",
            "HỢP ĐỒNG CHUYỂN NHƯỢNG QUYỀN SỬ DỤNG ĐẤT VÀ TÀI SẢN GẮN LIỀN VỚI ĐẤT",
            "Chúng tôi gồm có:",
            "I. BÊN CHUYỂN NHƯỢNG: (Bên A)",
            "1. Ông Nguyễn Huy Cận Sinh ngày: 17/12/1979",
            "Căn cước công dân số: 037079010407 do Bộ Công an cấp ngày 19/02/2025;",
            "2. Bà Nguyễn Thị Thu Thủy Sinh ngày: 27/06/1984",
            "Căn cước công dân số: 022184004248 do Bộ Công an cấp ngày 21/10/2025;",
            "Cùng cư trú tại: thôn A, xã B.",
            "II. BÊN NHẬN CHUYỂN NHƯỢNG: (Bên B)",
            "1. Ông Đoàn Văn Khánh Sinh ngày: 07/04/1987",
            "Căn cước công dân số: 036087026862 do Bộ Công an cấp ngày 11/08/2021;",
            "2. Bà Nguyễn Thị Đức Hạnh Sinh ngày: 14/12/1989",
            "Căn cước công dân số: 036189016258 do Bộ Công an cấp ngày 02/05/2022;",
            "Cùng cư trú tại: thôn C, xã D.",
            "ĐIỀU 1: ĐỐI TƯỢNG CỦA HỢP ĐỒNG",
            "Đối tượng của Hợp đồng này là toàn bộ quyền sử dụng đất của bên A có địa chỉ tại: thôn A, xã B.",
            "- Thửa đất số: 99",
            "Số công chứng 500/2026/CCGD",
        )

        payload = extract(docx_path)
        duong_su = payload["web_form"]["duong_su"]
        nguoi_yeu_cau = payload["web_form"]["nguoi_yeu_cau"]

        self.assertEqual(payload["web_form"]["ten_hop_dong"], "Hợp đồng chuyển nhượng quyền sử dụng đất")
        self.assertEqual(duong_su.count("Cùng cư trú tại: thôn A, xã B."), 2)
        self.assertEqual(duong_su.count("Cùng cư trú tại: thôn C, xã D."), 2)
        self.assertIn("Cùng cư trú tại: thôn C, xã D.", nguoi_yeu_cau)


if __name__ == "__main__":
    unittest.main()
