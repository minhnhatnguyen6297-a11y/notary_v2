"""
TRICH XUAT HOP DONG CONG CHUNG -> JSON CHO WEB FORM
===================================================
Cach dung:
    python extract_contract.py "hop_dong.docx"

Ket qua:
    - In JSON ra man hinh
    - Luu file .json cung thu muc

Cai dat:
    pip install python-docx
"""

from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path
from typing import Iterable


# ============================================================
# CAU HINH MAC DINH — sua tai day cho phu hop van phong
# ============================================================
DEFAULT_CCV = "Phạm Minh Chi"
DEFAULT_THU_KY = "Nguyễn Nhật Minh"
CONTRACT_YEAR = "2026"
CONTRACT_NO_REGEX = re.compile(rf"\b(\d+/{re.escape(CONTRACT_YEAR)}/CCGD)\b", re.IGNORECASE)
CONTRACT_KEYWORDS = ("hợp đồng", "hop dong", "hđ", "hd")

NHOM_HD_MAP = {
    "chuyển nhượng": "Chuyển nhượng - Mua bán",
    "mua bán": "Chuyển nhượng - Mua bán",
    "tặng cho": "Tặng, cho tài sản",
    "tặng, cho": "Tặng, cho tài sản",
    "thế chấp": "Cầm cố - Thế chấp - Vay",
    "cầm cố": "Cầm cố - Thế chấp - Vay",
    "vay": "Cầm cố - Thế chấp - Vay",
    "ủy quyền": "Ủy quyền",
    "ủy quền": "Ủy quyền",
    "di chúc": "Di chúc",
    "đặt cọc": "Đặt cọc",
    "thỏa thuận": "Thỏa thuận - Cam kết",
    "cam kết": "Thỏa thuận - Cam kết",
    "góp vốn": "Góp vốn - Hợp tác",
    "hợp tác": "Góp vốn - Hợp tác",
    "thừa kế": "Thừa kế (khai nhận - phân chia di sản thừa kế )",
    "khai nhận": "Thừa kế (khai nhận - phân chia di sản thừa kế )",
    "phân chia": "Thừa kế (khai nhận - phân chia di sản thừa kế )",
    "từ chối nhận di sản": "Từ chối nhận di sản thừa kế",
    "phụ lục": "Phụ lục hợp đồng - văn bản sửa đổi",
    "thuê": "Thuê - Mượn tài sản",
    "mượn": "Thuê - Mượn tài sản",
}


def _append_text_lines(lines: list[str], values: Iterable[str]) -> None:
    for raw in values:
        text = str(raw or "").strip()
        if text:
            lines.append(text)


def _append_table_lines(lines: list[str], tables) -> None:
    for table in tables:
        for row in table.rows:
            row_values = []
            for cell in row.cells:
                cell_text = " ".join(
                    p.text.strip()
                    for p in cell.paragraphs
                    if p.text and p.text.strip()
                ).strip()
                if cell_text:
                    row_values.append(cell_text)
            if row_values:
                lines.append(" | ".join(row_values))


# ============================================================
# DOCX HELPERS
# ============================================================
def read_docx(filepath):
    """Doc .docx -> text thuan, bao gom paragraph, bang, header, footer."""
    from docx import Document

    doc = Document(str(filepath))
    lines: list[str] = []
    _append_text_lines(lines, (p.text for p in doc.paragraphs))
    _append_table_lines(lines, doc.tables)
    for section in doc.sections:
        _append_text_lines(lines, (p.text for p in section.header.paragraphs))
        _append_text_lines(lines, (p.text for p in section.footer.paragraphs))
    return "\n".join(lines)


def _normalize_contract_no(contract_no: str) -> str:
    return str(contract_no or "").strip().upper()


def find_contract_numbers(text: str) -> list[str]:
    return [_normalize_contract_no(match.group(1)) for match in CONTRACT_NO_REGEX.finditer(text or "")]


def has_contract_keyword(text: str, file_name: str = "") -> bool:
    haystack = f"{file_name}\n{text}".lower()
    return any(keyword in haystack for keyword in CONTRACT_KEYWORDS)


def scan_docx_for_contract_no(filepath):
    """Tim so cong chung trong noi dung file docx."""
    path = Path(filepath)
    try:
        text = read_docx(path)
    except Exception as exc:
        return {
            "is_contract": False,
            "contract_no": "",
            "reason": f"Khong doc duoc file: {exc}",
        }

    matches = find_contract_numbers(text)
    if matches:
        contract_no = matches[-1]
        return {
            "is_contract": True,
            "contract_no": contract_no,
            "reason": f"Tim thay so CC: {contract_no}",
        }

    if has_contract_keyword(text, path.name):
        return {
            "is_contract": False,
            "contract_no": "",
            "reason": "Co keyword hop dong nhung khong thay so cong chung",
        }

    return {
        "is_contract": False,
        "contract_no": "",
        "reason": "Khong thay so cong chung",
    }


# ============================================================
# TRICH XUAT TUNG TRUONG
# ============================================================
def find_ten_hop_dong(text):
    m = re.search(r"(HỢP ĐỒNG\s+[^\n]+)", text)
    if m:
        raw = m.group(1).strip()
        return raw[0] + raw[1:].lower()
    return ""


def find_so_cong_chung(text):
    m = re.search(r"Số công chứng\s*(\d+)\s*/\s*(\d{4})\s*/\s*([A-Za-z]+)", text)
    if m:
        return _normalize_contract_no(f"{m.group(1)}/{m.group(2)}/{m.group(3)}")

    idx = text.find("Số công chứng")
    if idx >= 0:
        fallback = re.search(r"(\d+)/(\d{4})", text[idx: idx + 100])
        if fallback:
            return _normalize_contract_no(f"{fallback.group(1)}/{fallback.group(2)}/CCGD")

    matches = find_contract_numbers(text)
    if matches:
        return matches[-1]
    return ""


def find_ngay_cong_chung(text):
    idx = text.find("LỜI CHỨNG")
    sub = text[idx:] if idx >= 0 else text
    m = re.search(r"ngày\s+(\d{1,2})\s+tháng\s+(\d{1,2})\s+năm\s+(\d{4})", sub)
    if m:
        return f"{m.group(1).zfill(2)}/{m.group(2).zfill(2)}/{m.group(3)}"
    return ""


def find_ccv(text):
    m = re.search(r"Tôi,\s+([^,]+),\s+Công chứng viên", text)
    return m.group(1).strip() if m else DEFAULT_CCV


def find_persons(section):
    """Tim tat ca nguoi trong 1 doan (Ben A hoac Ben B)."""
    persons = []
    names = list(re.finditer(r"(Ông|[Bb]à)\s+([^;]+?)\s*;", section))

    for idx, nm in enumerate(names):
        start = nm.start()
        end = names[idx + 1].start() if idx + 1 < len(names) else len(section)
        chunk = section[start:end]

        person = {
            "gioi_tinh": nm.group(1).capitalize(),
            "ho_ten": nm.group(2).strip(),
        }

        m = re.search(r"Sinh ngày:?\s*(\d{2}/\d{2}/\d{4})", chunk)
        person["ngay_sinh"] = m.group(1) if m else ""

        m = re.search(r"(?:Căn cước|CCCD|CMND)(?:\s+công dân)?\s*(?:số:?\s*)(\d+)", chunk)
        person["cccd"] = m.group(1) if m else ""

        m = re.search(r"do\s+(.+?)\s+cấp ngày", chunk, re.DOTALL)
        person["noi_cap"] = re.sub(r"\s+", " ", m.group(1)).strip() if m else ""

        m = re.search(r"cấp ngày\s*(\d{2}/\d{2}/\d{4})", chunk)
        person["ngay_cap_cccd"] = m.group(1) if m else ""

        persons.append(person)

    return persons


def find_dia_chi(section):
    m = re.search(r"cùng (?:cư trú|thường trú) tại:?\s*(.+?)\.", section, re.DOTALL)
    return re.sub(r"\s+", " ", m.group(1)).strip() if m else ""


def find_tai_san(text):
    """Lay toan bo mo ta tai san (Dieu 1, khoan 1.1)."""
    start = text.find("Đối tượng của Hợp đồng")
    if start < 0:
        start = text.find("ĐIỀU 1")

    end = -1
    for marker in ["1.2", "Bằng Hợp đồng này", "ĐIỀU 2"]:
        pos = text.find(marker, start) if start >= 0 else -1
        if pos > start:
            end = pos
            break

    if start >= 0 and end >= 0:
        raw = text[start:end].strip()
        lines = [line.strip() for line in raw.split("\n") if line.strip()]
        return "\n".join(lines)
    return ""


def guess_nhom_hd(ten_hd):
    lower = ten_hd.lower()
    for kw, nhom in NHOM_HD_MAP.items():
        if kw in lower:
            return nhom
    return "Khác"


def guess_loai_tai_san(tai_san, ten_hd):
    combined = (tai_san + " " + ten_hd).lower()

    if "quyền sử dụng đất" in combined:
        indicators = [
            "và nhà ở",
            "và tài sản",
            "nhà ở gắn liền",
            "công trình xây dựng",
            "tài sản trên đất",
        ]
        title_lower = ten_hd.lower()
        if any(keyword in title_lower for keyword in indicators):
            return "Đất đai có tài sản"
        return "Đất đai không có tài sản"

    keywords = [
        ("ô tô", "Ô tô"),
        ("xe máy", "Xe máy"),
        ("tàu", "Tàu, thuyền"),
        ("thuyền", "Tàu, thuyền"),
        ("sổ tiết kiệm", "Sổ tiết kiệm"),
        ("cổ phần", "Cổ phần"),
        ("cổ phiếu", "Cổ phiếu"),
        ("chứng khoán", "Chứng khoán"),
        ("thẻ atm", "Thẻ ATM"),
    ]
    for kw, loai in keywords:
        if kw in combined:
            return loai
    return "Tài sản khác"


# ============================================================
# FORMAT CHO 3 O CKEDITOR TREN WEB
# ============================================================
def fmt_nguoi_yeu_cau(ben_b):
    """Nguoi yeu cau CC = nguoi dau tien ben B."""
    if not ben_b.get("nguoi"):
        return ""
    person = ben_b["nguoi"][0]
    parts = [f"{person.get('gioi_tinh', '')} {person['ho_ten']}"]
    if person.get("ngay_sinh"):
        parts.append(f"Sinh ngày: {person['ngay_sinh']}")
    if person.get("cccd"):
        parts.append(f"Căn cước số: {person['cccd']}")
    if person.get("noi_cap") and person.get("ngay_cap_cccd"):
        parts.append(f"do {person['noi_cap']} cấp ngày {person['ngay_cap_cccd']}")
    if ben_b.get("dia_chi"):
        parts.append(f"Cư trú tại: {ben_b['dia_chi']}")
    return "; ".join(parts)


def fmt_duong_su(ben_a, ben_b):
    """Duong su = toan bo ben A + ben B."""
    lines = ["BÊN A (Bên chuyển nhượng):"]
    for idx, person in enumerate(ben_a.get("nguoi", []), 1):
        line = f"{idx}. {person.get('gioi_tinh', '')} {person['ho_ten']}"
        if person.get("ngay_sinh"):
            line += f"; Sinh ngày: {person['ngay_sinh']}"
        if person.get("cccd"):
            line += f"; CCCD: {person['cccd']}"
        if person.get("noi_cap") and person.get("ngay_cap_cccd"):
            line += f"; do {person['noi_cap']} cấp ngày {person['ngay_cap_cccd']}"
        lines.append(line)
    if ben_a.get("dia_chi"):
        lines.append(f"Cùng cư trú tại: {ben_a['dia_chi']}")

    lines.append("")
    lines.append("BÊN B (Bên nhận chuyển nhượng):")
    for idx, person in enumerate(ben_b.get("nguoi", []), 1):
        line = f"{idx}. {person.get('gioi_tinh', '')} {person['ho_ten']}"
        if person.get("ngay_sinh"):
            line += f"; Sinh ngày: {person['ngay_sinh']}"
        if person.get("cccd"):
            line += f"; CCCD: {person['cccd']}"
        if person.get("noi_cap") and person.get("ngay_cap_cccd"):
            line += f"; do {person['noi_cap']} cấp ngày {person['ngay_cap_cccd']}"
        lines.append(line)
    if ben_b.get("dia_chi"):
        lines.append(f"Cùng cư trú tại: {ben_b['dia_chi']}")

    return "\n".join(lines)


# ============================================================
# HAM CHINH
# ============================================================
def extract(filepath):
    text = read_docx(filepath)
    scan_result = scan_docx_for_contract_no(filepath)

    idx_a = text.find("BÊN CHUYỂN NHƯỢNG")
    idx_b = text.find("BÊN NHẬN CHUYỂN NHƯỢNG")
    idx_end = text.find("Hai bên tự nguyện")

    ben_a_section = text[idx_a:idx_b] if idx_a >= 0 and idx_b >= 0 else ""
    ben_b_section = text[idx_b:idx_end] if idx_b >= 0 and idx_end >= 0 else ""

    ben_a = {"nguoi": find_persons(ben_a_section), "dia_chi": find_dia_chi(ben_a_section)}
    ben_b = {"nguoi": find_persons(ben_b_section), "dia_chi": find_dia_chi(ben_b_section)}

    ten_hd = find_ten_hop_dong(text)
    tai_san = find_tai_san(text)
    so_cong_chung = find_so_cong_chung(text) or scan_result.get("contract_no", "")

    return {
        "web_form": {
            "ten_hop_dong": ten_hd,
            "ngay_cong_chung": find_ngay_cong_chung(text),
            "so_cong_chung": so_cong_chung,
            "nhom_hop_dong": guess_nhom_hd(ten_hd),
            "loai_tai_san": guess_loai_tai_san(tai_san, ten_hd),
            "cong_chung_vien": find_ccv(text),
            "thu_ky": DEFAULT_THU_KY,
            "nguoi_yeu_cau": fmt_nguoi_yeu_cau(ben_b),
            "duong_su": fmt_duong_su(ben_a, ben_b),
            "tai_san": tai_san,
        },
        "raw": {
            "ben_a": ben_a,
            "ben_b": ben_b,
            "file_goc": os.path.abspath(filepath),
            "scan_contract_no": scan_result.get("contract_no", ""),
            "scan_reason": scan_result.get("reason", ""),
        },
    }


def main():
    if len(sys.argv) < 2:
        print("Cách dùng:")
        print('  python extract_contract.py "hop_dong.docx"')
        sys.exit(1)

    fp = sys.argv[1]
    if not os.path.exists(fp):
        print(f"Không tìm thấy file: {fp}")
        sys.exit(1)

    result = extract(fp)
    output = json.dumps(result, ensure_ascii=False, indent=2)
    print(output)

    json_path = fp.rsplit(".", 1)[0] + "_extracted.json"
    with open(json_path, "w", encoding="utf-8") as file_obj:
        file_obj.write(output)
    print(f"\n→ Đã lưu: {json_path}", file=sys.stderr)


if __name__ == "__main__":
    main()
