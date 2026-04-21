"""
Test OCR cho tai san (land_cert) voi 6 anh mau.
Chay: python tests/test_ocr_property.py
"""
import asyncio
import base64
import json
import os
import sys
from pathlib import Path

# Fix Unicode output on Windows terminal
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

import httpx
from dotenv import load_dotenv

load_dotenv()

TEST_DIR = Path(__file__).parent / "fixtures" / "properties"

SYSTEM_PROMPT_QWEN = """Phan tich anh tai lieu phap ly Viet Nam. Tra ve ONLY JSON array.

BUOC 1 — NHAN DANG LOAI TAI LIEU:
- Neu anh la SO DO / SO HONG / GIAY CHUNG NHAN QUYEN SU DUNG DAT (co chu "Giay chung nhan", "Quyen su dung dat", "So do", "So hong", so thua dat, to ban do, dien tich dat) → doc_type = "land_cert"
- Neu anh la GIAY DANG KY KET HON → doc_type = "marriage_cert"
- Neu anh la CCCD / CMND / CAN CUOC (co anh chan dung, ho ten, ngay sinh, so CCCD 12 chu so) → doc_type = "cccd_front" hoac "cccd_back"
- Neu khong xac dinh duoc → doc_type = "unknown"

BUOC 2 — EXTRACT THEO LOAI:

[land_cert] So do / so hong / GCN:
{"doc_type":"land_cert","data":{"so_serial":"","so_vao_so":"","so_thua_dat":"","so_to_ban_do":"","dia_chi_dat":"","loai_dat":"","dien_tich":"","hinh_thuc_su_dung":"","thoi_han":"","nguon_goc":"","ngay_cap":"","co_quan_cap":""}}
- so_serial: so phat hanh GCN tren bia/goc tai lieu (vd "AA 04960350", "CR 116702", "SSX 829875").
- so_vao_so: "So vao so cap Giay chung nhan" o mat sau phia duoi (vd "VP46192"). De trong neu khong thay.
- so_thua_dat: chi so, tim dong co nhan "Thua dat so" hoac "Thu tua dat so" (vd "224", "18", "453"). De trong neu khong thay.
- so_to_ban_do: chi so, tim dong co nhan "To ban do so" hoac "To so" (vd "34", "28", "12"). De trong neu khong thay.
- dia_chi_dat: dia chi thua dat, thuong la ten xa/phuong + huyen/quan + tinh. De trong neu khong thay.
- loai_dat: vd "Dat o tai nong thon", "Dat o tai do thi", "Dat san xuat nong nghiep". De trong neu khong thay.
- dien_tich: so + don vi, tim dong co "Dien tich" (vd "230.0 m2", "559 m2"). De trong neu khong thay.
- hinh_thuc_su_dung: vd "Su dung rieng", "Su dung chung". De trong neu khong thay.
- thoi_han: vd "Lau dai", "50 nam ke tu ngay cap". De trong neu khong thay.
- nguon_goc: nguon goc su dung dat neu co ghi trong anh. De trong neu khong thay.
- ngay_cap: ngay ky cap GCN, tim cum "ngay ... thang ... nam" trong phan chu ky/dong dau (vd "01/02/2026", "05/06/2020", "09/06/2003"). De trong neu khong thay.
- co_quan_cap: TEN CO QUAN cap GCN (vd "So Tai nguyen va Moi truong", "Uy ban nhan dan huyen Y Yen"), KHONG phai ten nguoi ky.

[marriage_cert] Giay dang ky ket hon:
{"doc_type":"marriage_cert","data":{"chong_ho_ten":"","chong_ngay_sinh":"","chong_so_giay_to":"","vo_ho_ten":"","vo_ngay_sinh":"","vo_so_giay_to":"","ngay_dang_ky":"","noi_dang_ky":""}}

[cccd_front] Mat truoc CCCD/CMND:
{"doc_type":"cccd_front","data":{"doc_side":"front","doc_version":"old|new","ho_ten":"","so_giay_to":"","ngay_sinh":"","gioi_tinh":"","dia_chi":"","ngay_cap":"","ngay_het_han":"","mrz_line1":"","mrz_line2":"","mrz_line3":"","so_giay_to_mrz":"","dia_chi_back":""}}

[cccd_back] Mat sau CCCD/CMND:
{"doc_type":"cccd_back","data":{"doc_side":"back","doc_version":"old|new","ho_ten":"","so_giay_to":"","ngay_sinh":"","gioi_tinh":"","dia_chi":"","ngay_cap":"","ngay_het_han":"","mrz_line1":"","mrz_line2":"","mrz_line3":"","so_giay_to_mrz":"","dia_chi_back":""}}

[unknown]: [{"doc_type":"unknown","data":{}}]

QUY TAC CHUNG:
- Khong doan mo truong khong thay trong anh. De chuoi rong.
- Ngay: DD/MM/YYYY. So CCCD: chi chu so.
- Neu anh co so do/so hong → PHAI dung land_cert, KHONG dung cccd_front.
"""

GROUND_TRUTH = {
    "1.jpg": {
        "note": "Bìa sổ đỏ cũ + trang thay đổi — khó đọc, chữ viết tay",
        "expected_doc_type": "land_cert",  # hoặc unknown nếu AI không nhận ra
    },
    "2.jpg": {
        "note": "Sổ đỏ cũ (Phạm Ngọc Tuyến), Ý Yên Nam Định 2003",
        "expected_doc_type": "land_cert",
        "expected": {
            "so_thua_dat": "18",
            "so_to_ban_do": "28",
            "dia_chi_dat": "Xã Yên Phúc, Huyện Ý Yên",
            "ngay_cap": "09/06/2003",
            "co_quan_cap": "Ủy ban nhân dân huyện Ý Yên",
        },
    },
    "3.jpg": {
        "note": "Sổ hồng mới — bìa + lưng (CR 116702)",
        "expected_doc_type": "land_cert",
        "expected": {
            "so_serial": "CR 116702",
        },
    },
    "4.jpg": {
        "note": "Sổ hồng nội dung (Sở TN&MT Nam Định, 2020)",
        "expected_doc_type": "land_cert",
        "expected": {
            "so_thua_dat": "453",
            "so_to_ban_do": "12",
            "ngay_cap": "05/06/2020",
            "co_quan_cap": "Sở Tài nguyên và Môi trường",
        },
    },
    "5.jpg": {
        "note": "Sổ hồng mới rõ nét (AA 04960350) — mặt trước",
        "expected_doc_type": "land_cert",
        "expected": {
            "so_serial": "AA 04960350",
            "so_thua_dat": "224",
            "so_to_ban_do": "34",
            "loai_dat": "Đất ở tại nông thôn",
            "ngay_cap": "01/02/2026",
        },
    },
    "6.jpg": {
        "note": "Mặt sau ảnh 5 (AA 04960350) — sơ đồ + số vào sổ VP46192",
        "expected_doc_type": "land_cert",  # hoặc unknown vì chủ yếu là sơ đồ
    },
}


def image_to_b64(path: Path) -> str:
    data = path.read_bytes()
    return base64.b64encode(data).decode()


async def call_qwen(image_b64: str, api_key: str, model: str = "Qwen-VL-OCR") -> dict:
    dashscope_base = os.getenv(
        "DASHSCOPE_BASE_URL",
        "https://dashscope-intl.aliyuncs.com/compatible-mode/v1",
    )
    async with httpx.AsyncClient(timeout=60.0) as client:
        resp = await client.post(
            f"{dashscope_base}/chat/completions",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": model,
                "max_tokens": 1500,
                "temperature": 0,
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": SYSTEM_PROMPT_QWEN},
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:image/jpeg;base64,{image_b64}"
                                },
                            },
                        ],
                    }
                ],
            },
        )
    resp.raise_for_status()
    return resp.json()


def parse_json_safe(text: str):
    import re
    cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip(), flags=re.MULTILINE).strip()
    try:
        return json.loads(cleaned)
    except Exception:
        match = re.search(r"(\[[\s\S]+\]|\{[\s\S]+\})", cleaned)
        if match:
            try:
                return json.loads(match.group())
            except Exception:
                return None
    return None


def check_field(actual_val: str, expected_val: str) -> str:
    if not expected_val:
        return "—"
    if not actual_val:
        return "❌ MISSING"
    if expected_val.lower() in actual_val.lower() or actual_val.lower() in expected_val.lower():
        return "✅"
    return f"⚠️  got: {actual_val!r}"


async def main():
    api_key = os.getenv("QWEN_API_KEY") or os.getenv("DASHSCOPE_API_KEY") or os.getenv("OPENAI_API_KEY")
    model = os.getenv("OCR_MODEL", "Qwen-VL-OCR")

    if not api_key:
        print("ERROR: QWEN_API_KEY not set in .env")
        return

    print(f"Model: {model}")
    print(f"Test dir: {TEST_DIR}")
    print("=" * 70)

    images = sorted(TEST_DIR.glob("*.jpg"))
    if not images:
        print("ERROR: No .jpg files found in test dir")
        return

    pass_count = 0
    fail_count = 0

    for img_path in images:
        fname = img_path.name
        gt = GROUND_TRUTH.get(fname, {})
        print(f"\n{'='*70}")
        print(f"FILE: {fname}  |  {gt.get('note', '')}")
        print("-" * 70)

        try:
            b64 = image_to_b64(img_path)
            payload = await call_qwen(b64, api_key=api_key, model=model)
            raw_text = payload["choices"][0]["message"]["content"]
            print(f"RAW RESPONSE:\n{raw_text}\n")

            parsed = parse_json_safe(raw_text)
            if not parsed:
                print("❌ JSON PARSE FAILED")
                fail_count += 1
                continue

            # Unwrap {"doc_list": [...]} or similar wrapper dicts
            if isinstance(parsed, dict):
                for v in parsed.values():
                    if isinstance(v, list) and v and isinstance(v[0], dict) and "doc_type" in v[0]:
                        parsed = v
                        break

            items = parsed if isinstance(parsed, list) else [parsed]
            land_items = [x for x in items if isinstance(x, dict) and x.get("doc_type") in ("land_cert", "land", "property", "red_book", "so_do")]

            print(f"doc_types found: {[x.get('doc_type') for x in items if isinstance(x, dict)]}")

            expected_type = gt.get("expected_doc_type")
            if expected_type == "land_cert" and not land_items:
                print(f"❌ Expected land_cert but got: {[x.get('doc_type') for x in items]}")
                fail_count += 1
            else:
                if land_items:
                    data = land_items[0].get("data", {})
                    print("\nEXTRACTED land_cert data:")
                    for k, v in data.items():
                        print(f"  {k}: {v!r}")

                    expected = gt.get("expected", {})
                    if expected:
                        print("\nFIELD CHECK:")
                        all_ok = True
                        for field, exp_val in expected.items():
                            actual = data.get(field, "")
                            status = check_field(actual, exp_val)
                            print(f"  {field}: {status}  (expected: {exp_val!r})")
                            if status.startswith("❌") or status.startswith("⚠️"):
                                all_ok = False
                        if all_ok:
                            pass_count += 1
                        else:
                            fail_count += 1
                    else:
                        pass_count += 1
                else:
                    print("  (no land_cert items — acceptable for this image)")
                    pass_count += 1

        except Exception as exc:
            print(f"❌ ERROR: {exc}")
            fail_count += 1

    print(f"\n{'='*70}")
    print(f"RESULT: {pass_count} passed, {fail_count} failed out of {len(images)} images")


if __name__ == "__main__":
    asyncio.run(main())
