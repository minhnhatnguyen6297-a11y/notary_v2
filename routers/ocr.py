"""
OCR Router — nhận ảnh giấy tờ, nhận diện loại, trích xuất dữ liệu.

Pipeline:
  1. Client gửi n ảnh (thứ tự bất kỳ)
  2. Quét QR hàng loạt (Python, miễn phí) → qr_by_cccd keyed by số CCCD
  3. Gộp tất cả vào 1 lần gọi AI → tiết kiệm token
  4. Gắn QR vào AI result theo số CCCD (không theo index)
  5. Gom nhóm: ghép mặt trước/sau CCCD theo số CCCD từ MRZ
  6. Trả về persons[], properties[], marriages[]
"""

import base64, io, json, os, re
from typing import List

import httpx
import zxingcpp
from dotenv import load_dotenv
from fastapi import APIRouter, File, HTTPException, UploadFile
from PIL import Image

router = APIRouter(prefix="/api/ocr", tags=["OCR"])

# ─── Config — đọc động từ file .env để không cần restart khi đổi key ──────────
_ENV_PATH = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".env"))

def _read_env() -> dict:
    """Đọc thẳng file .env, không phụ thuộc os.environ."""
    from dotenv import dotenv_values
    return dotenv_values(_ENV_PATH)

def _get_api_key() -> str:
    key = os.getenv("OPENAI_API_KEY", "")
    if not key:
        key = _read_env().get("OPENAI_API_KEY", "")
    return key

def _get_model() -> str:
    return os.getenv("OCR_MODEL", "") or _read_env().get("OCR_MODEL", "gpt-4o-mini")

MAX_IMAGE_PX = 1000
JPEG_QUALITY = 82

# ─── QR decode — trước AI, miễn phí, chính xác 100% ─────────────────────────
def try_decode_qr(file_bytes: bytes) -> str | None:
    """Thử giải mã QR code từ ảnh. Trả về text hoặc None."""
    try:
        img = Image.open(io.BytesIO(file_bytes))
        if img.mode not in ("RGB", "L"):
            img = img.convert("RGB")
        results = zxingcpp.read_barcodes(img)
        for r in results:
            if r.format in (zxingcpp.BarcodeFormat.QRCode, zxingcpp.BarcodeFormat.MicroQRCode):
                return r.text
    except Exception:
        pass
    return None


def parse_cccd_qr(text: str) -> dict | None:
    """
    Parse QR CCCD (pipe-separated).
    Format thường: so_cccd|so_cu|ngay_sinh_ddmmyyyy|ngay_het_han_ddmmyyyy|ho_ten|dia_chi[|gioi_tinh...]
    Linh hoạt: tìm field đầu tiên là 12 chữ số trong 3 field đầu.
    """
    parts = text.strip().split("|")
    if len(parts) < 6:
        return None

    # Tìm số CCCD (12 chữ số) trong 3 field đầu
    cccd = ""
    cccd_idx = -1
    for i, p in enumerate(parts[:3]):
        if re.fullmatch(r"\d{12}", p.strip()):
            cccd = p.strip()
            cccd_idx = i
            break
    if not cccd:
        return None

    def fmt_date(s: str) -> str:
        s = s.strip()
        if re.fullmatch(r"\d{8}", s):
            return f"{s[0:2]}/{s[2:4]}/{s[4:8]}"
        return s

    # Lấy field tương đối từ vị trí cccd_idx
    # Format chuẩn từ cccd_idx: [cccd, old_id, dob, doe, name, address, gender...]
    def get(offset: int) -> str:
        i = cccd_idx + offset
        return parts[i].strip() if i < len(parts) else ""

    gioi_tinh_raw = get(6).lower()
    gioi_tinh = "Nam" if gioi_tinh_raw == "nam" else ("Nữ" if gioi_tinh_raw in ("nữ", "nu") else "")

    return {
        "so_giay_to":   cccd,
        "ngay_sinh":    fmt_date(get(2)),
        "ngay_het_han": fmt_date(get(3)),
        "ho_ten":       get(4),
        "dia_chi":      get(5),
        "gioi_tinh":    gioi_tinh,
    }


# ─── Prompt — mô tả rõ layout từng loại thẻ để AI không nhầm trường ──────────
SYSTEM_PROMPT = """Vietnamese CCCD/legal doc OCR. Return one JSON object per document. If image shows BOTH sides → return 2 objects. Return JSON array.

CARD TYPES AND FIELD LAYOUT:
1. Old CCCD "CĂN CƯỚC CÔNG DÂN" (pre-2024): front has QR code top-right corner.
   Front fields top→bottom: Họ tên → Ngày sinh → [Giới tính + Quốc tịch on SAME LINE] → Quê quán → Nơi thường trú → Có giá trị đến
   IMPORTANT: "Quốc tịch: Việt Nam" is on the SAME LINE as Giới tính — it is NATIONALITY, NOT an address. IGNORE it for dia_chi.
   dia_chi = "Nơi thường trú" ONLY (the LAST address field at bottom, labeled "Nơi thường trú"). NEVER use "Quê quán" (the field just above it) and NEVER use "Quốc tịch" value.
   Back: fingerprints + date + MRZ lines (no QR, no address text).

2. New CĂN CƯỚC (from 2024, title "CĂN CƯỚC" without "CÔNG DÂN"): front has NO QR code.
   Front fields: Số → Họ tên → Ngày sinh → [Giới tính + Quốc tịch on SAME LINE]. NO address on front → dia_chi = "".
   Back: QR code top-right + chip + "Nơi cư trú" text at top (2 lines) + Ngày cấp + Ngày hết hạn + MRZ lines.
   dia_chi_back = "Nơi cư trú" text from top of back (first address field visible on back).

cccd_front→{"doc_type":"cccd_front","data":{"ho_ten":"NGUYỄN VĂN AN","so_giay_to":"12digits","ngay_sinh":"DD/MM/YYYY","gioi_tinh":"Nam|Nữ","dia_chi":"Nơi thường trú (old card bottom field) or empty string (new card or if no address visible)","ngay_het_han":"DD/MM/YYYY or empty"}}
cccd_back→{"doc_type":"cccd_back","data":{"mrz_line1":"full IDVNM... line","so_giay_to_mrz":"12digits","ngay_cap":"DD/MM/YYYY","dia_chi_back":"Nơi cư trú from top of back (new card only) or empty"}}
marriage_cert→{"doc_type":"marriage_cert","data":{"chong_ho_ten":"","chong_ngay_sinh":"DD/MM/YYYY","chong_so_giay_to":"","vo_ho_ten":"","vo_ngay_sinh":"DD/MM/YYYY","vo_so_giay_to":"","ngay_dang_ky":"DD/MM/YYYY","noi_dang_ky":""}}
land_cert→{"doc_type":"land_cert","data":{"so_serial":"","so_thua_dat":"","so_to_ban_do":"","dia_chi_dat":"","loai_dat":"","ngay_cap":"DD/MM/YYYY","co_quan_cap":""}}
unknown→{"doc_type":"unknown","data":{}}

Rules: ho_ten EXACTLY as printed with Vietnamese diacritics (e.g. NGUYỄN VĂN AN not NGUYEN VAN AN). Dates DD/MM/YYYY. ID digits only. "" if unreadable. Return ONLY JSON array."""

# ─── Image helpers ─────────────────────────────────────────────────────────────
def resize_to_base64(file_bytes: bytes, max_px: int = MAX_IMAGE_PX) -> str:
    img = Image.open(io.BytesIO(file_bytes))
    if img.mode not in ("RGB", "L"):
        img = img.convert("RGB")
    w, h = img.size
    scale = min(1.0, max_px / max(w, h))
    if scale < 1.0:
        img = img.resize((int(w * scale), int(h * scale)), Image.LANCZOS)
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=JPEG_QUALITY)
    return base64.b64encode(buf.getvalue()).decode()


def extract_cccd_from_mrz(mrz_line1: str) -> str:
    """Trích 12 số CCCD từ dòng MRZ 1 (IDVNM...)."""
    raw = re.sub(r"\s", "", str(mrz_line1 or ""))
    m = re.search(r"(\d{12})<<\d", raw)
    if m:
        return m.group(1)
    m2 = re.search(r"(\d{12})<<", raw)
    return m2.group(1) if m2 else ""


def parse_json_safe(text: str):
    """Parse JSON từ AI response, strip markdown fence nếu có."""
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip(), flags=re.MULTILINE).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        # Cố tìm array hoặc object trong text
        m = re.search(r"(\[[\s\S]+\]|\{[\s\S]+\})", text)
        if m:
            try:
                return json.loads(m.group())
            except Exception:
                pass
    return None


# ─── AI call — gộp tất cả ảnh vào 1 request ──────────────────────────────────
async def call_vision_batch(images_b64: list[str]) -> list[dict]:
    """
    Gửi n ảnh trong 1 lần gọi. Prompt chỉ tốn 1 lần.
    Không pad/trim kết quả — ảnh 2 mặt có thể trả >n objects.
    """
    api_key = _get_api_key()
    if not api_key:
        raise HTTPException(status_code=500, detail="Server chưa cấu hình OPENAI_API_KEY")

    content = [{"type": "text", "text": SYSTEM_PROMPT}]
    for b64 in images_b64:
        content.append({
            "type": "image_url",
            "image_url": {
                "url": f"data:image/jpeg;base64,{b64}",
                "detail": "high"
            }
        })

    try:
        async with httpx.AsyncClient(timeout=120.0) as client:
            resp = await client.post(
                "https://api.openai.com/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": _get_model(),
                    "max_tokens": 500 * len(images_b64),   # ~500 tokens mỗi ảnh
                    "temperature": 0,
                    "messages": [{"role": "user", "content": content}]
                },
            )
    except httpx.RequestError as e:
        raise HTTPException(status_code=502, detail=f"Không thể kết nối tới OpenAI: {str(e)}")

    if not resp.is_success:
        raise HTTPException(status_code=502, detail=f"OpenAI lỗi: {resp.text[:300]}")

    raw = resp.json()["choices"][0]["message"]["content"]
    parsed = parse_json_safe(raw)

    # Không pad/trim — ảnh 2 mặt có thể trả nhiều hơn số ảnh gửi lên
    if isinstance(parsed, list) and parsed:
        return parsed

    if isinstance(parsed, dict):
        return [parsed]

    # Fallback
    return [{"doc_type": "unknown", "data": {}} for _ in images_b64]


# ─── Grouping ─────────────────────────────────────────────────────────────────
def group_documents(results: list) -> dict:
    fronts    = [r for r in results if r.get("doc_type") == "cccd_front"]
    backs     = [r for r in results if r.get("doc_type") == "cccd_back"]
    marriages = [r for r in results if r.get("doc_type") == "marriage_cert"]
    lands     = [r for r in results if r.get("doc_type") == "land_cert"]
    unknowns  = [r for r in results if r.get("doc_type") == "unknown"]

    # Quốc tịch "Việt Nam" hay bị AI nhầm vào dia_chi — lọc bỏ
    _NATIONALITY = {"việt nam", "viet nam", "vietnam"}
    def _valid_addr(s: str) -> str:
        return "" if (s or "").strip().lower() in _NATIONALITY else (s or "")

    persons = []
    matched_backs = set()

    for front in fronts:
        fd   = front.get("data", {})
        cccd = re.sub(r"\D", "", str(fd.get("so_giay_to") or ""))
        # Fallback: nếu AI không trích được so_giay_to (hay gặp với CĂN CƯỚC mới),
        # dùng QR data đã gắn trước đó để lấy CCCD cho việc ghép mặt sau
        if not cccd:
            qr_pre = front.get("qr_data")
            if qr_pre:
                cccd = qr_pre.get("so_giay_to", "")

        back_match = None
        for i, back in enumerate(backs):
            if i in matched_backs:
                continue
            bd = back.get("data", {})
            mrz_cccd = re.sub(r"\D", "", str(bd.get("so_giay_to_mrz") or ""))
            if not mrz_cccd:
                mrz_cccd = extract_cccd_from_mrz(bd.get("mrz_line1", ""))
            if cccd and mrz_cccd == cccd:
                back_match = back
                matched_backs.add(i)
                break

        bd   = back_match.get("data", {}) if back_match else {}
        side = back_match.get("_side", "") if back_match else ""

        # QR ưu tiên cao nhất (chính xác 100%)
        # CC mới: QR ở mặt sau → back_match có qr_data
        # CCCD cũ: QR ở mặt trước → front có qr_data
        qr = back_match.get("qr_data") if back_match else None
        if not qr:
            qr = front.get("qr_data")

        # dia_chi theo thứ tự ưu tiên:
        # 1. QR (authoritative, UTF-8 chính xác)
        # 2. AI mặt trước (chỉ dùng nếu là CCCD cũ — CC mới không có địa chỉ trên mặt trước)
        # 3. dia_chi_back từ mặt sau (CC mới)
        front_ai_addr = _valid_addr(fd.get("dia_chi")) if side != "back_new_cc" else ""
        dia_chi = (
            qr["dia_chi"] if qr and qr.get("dia_chi") else
            front_ai_addr or
            _valid_addr(bd.get("dia_chi_back", ""))
        )

        persons.append({
            "ho_ten":       qr["ho_ten"]       if qr else fd.get("ho_ten", ""),
            "so_giay_to":   qr["so_giay_to"]   if qr else cccd,
            "ngay_sinh":    qr["ngay_sinh"]     if qr else fd.get("ngay_sinh", ""),
            "gioi_tinh":    (qr.get("gioi_tinh") if qr else None) or fd.get("gioi_tinh", ""),
            "dia_chi":      dia_chi,
            "ngay_het_han": qr["ngay_het_han"]  if qr else fd.get("ngay_het_han", ""),
            "ngay_cap":     bd.get("ngay_cap", ""),
            "_source":      "cccd" + ("+back" if back_match else " (thiếu mặt sau)"),
            "_side":        side,
            "_qr":          bool(qr),
            "_files":       [front.get("filename", ""), back_match.get("filename", "") if back_match else ""],
        })

    # Mặt sau chưa ghép được mặt trước
    for i, back in enumerate(backs):
        if i in matched_backs:
            continue
        bd  = back.get("data", {})
        qr  = back.get("qr_data")
        mrz_cccd = re.sub(r"\D", "", str(bd.get("so_giay_to_mrz") or ""))
        if not mrz_cccd:
            mrz_cccd = extract_cccd_from_mrz(bd.get("mrz_line1", ""))

        dia_chi = (
            qr["dia_chi"] if qr and qr.get("dia_chi") else
            _valid_addr(bd.get("dia_chi_back", ""))
        )

        persons.append({
            "ho_ten":       qr["ho_ten"]       if qr else "",
            "so_giay_to":   qr["so_giay_to"]   if qr else mrz_cccd,
            "ngay_sinh":    qr["ngay_sinh"]     if qr else "",
            "gioi_tinh":    qr.get("gioi_tinh", "") if qr else "",
            "dia_chi":      dia_chi,
            "ngay_het_han": qr["ngay_het_han"]  if qr else "",
            "ngay_cap":     bd.get("ngay_cap", ""),
            "_source":      "cccd+back" if qr else "cccd_back only",
            "_qr":          bool(qr),
            "_files":       [back.get("filename", "")],
        })

    marriage_data = []
    for m in marriages:
        md = m.get("data", {})
        marriage_data.append({
            "chong": {
                "ho_ten": md.get("chong_ho_ten", ""),
                "so_giay_to": re.sub(r"\D", "", str(md.get("chong_so_giay_to") or "")),
                "ngay_sinh": md.get("chong_ngay_sinh", ""),
                "gioi_tinh": "Nam", "dia_chi": "",
            },
            "vo": {
                "ho_ten": md.get("vo_ho_ten", ""),
                "so_giay_to": re.sub(r"\D", "", str(md.get("vo_so_giay_to") or "")),
                "ngay_sinh": md.get("vo_ngay_sinh", ""),
                "gioi_tinh": "Nữ", "dia_chi": "",
            },
            "ngay_dang_ky":  md.get("ngay_dang_ky", ""),
            "noi_dang_ky":   md.get("noi_dang_ky", ""),
            "_file": m.get("filename", ""),
        })

    properties = []
    for land in lands:
        ld = land.get("data", {})
        properties.append({
            "so_serial":    ld.get("so_serial", ""),
            "so_thua_dat":  ld.get("so_thua_dat", ""),
            "so_to_ban_do": ld.get("so_to_ban_do", ""),
            "dia_chi":      ld.get("dia_chi_dat", ""),
            "loai_dat":     ld.get("loai_dat", ""),
            "ngay_cap":     ld.get("ngay_cap", ""),
            "co_quan_cap":  ld.get("co_quan_cap", ""),
            "_file": land.get("filename", ""),
        })

    return {
        "persons":    persons,
        "properties": properties,
        "marriages":  marriage_data,
        "raw_results": results,
        "summary": {
            "total_images":    len(results),
            "cccd_fronts":     len(fronts),
            "cccd_backs":      len(backs),
            "matched_pairs":   len(matched_backs),
            "marriages":       len(marriages),
            "land_certs":      len(lands),
            "unknowns":        len(unknowns),
        },
    }


# ─── Endpoints ────────────────────────────────────────────────────────────────
@router.post("/analyze")
async def analyze_images(files: List[UploadFile] = File(...)):
    """
    Nhận 1..n ảnh giấy tờ. Gộp vào 1 lần gọi AI để tiết kiệm token.
    QR decode trước AI — kết quả QR gắn vào AI result theo số CCCD (không theo index).
    Trả về persons[], properties[], marriages[].
    """
    if not files:
        raise HTTPException(status_code=400, detail="Chưa có ảnh nào được gửi lên")

    images_b64:  list[str]      = []
    filenames:   list[str]      = []
    errors:      list[dict]     = []
    img_has_qr:  set[int]       = set()   # index ảnh nào có QR (Python scan, không cần AI)
    qr_by_cccd:  dict[str, dict] = {}     # CCCD 12 số → QR data (authoritative)

    for idx, f in enumerate(files):
        try:
            file_bytes = await f.read()

            # Quét QR trước (miễn phí, chính xác — không cần AI)
            qr_text = try_decode_qr(file_bytes)
            if qr_text:
                img_has_qr.add(idx)
                qr_parsed = parse_cccd_qr(qr_text)
                if qr_parsed and qr_parsed.get("so_giay_to"):
                    qr_by_cccd[qr_parsed["so_giay_to"]] = qr_parsed

            b64 = resize_to_base64(file_bytes)
            images_b64.append(b64)
            filenames.append(f.filename or "unknown")
        except Exception as e:
            errors.append({"filename": f.filename, "error": str(e)})

    if not images_b64:
        return {"persons": [], "properties": [], "marriages": [],
                "errors": errors, "summary": {}}

    # 1 lần gọi AI cho tất cả ảnh
    raw_results = await call_vision_batch(images_b64)

    # Gắn filename + QR data; override doc_type dựa trên tín hiệu vật lý
    n_imgs = len(images_b64)
    for i, r in enumerate(raw_results):
        if not isinstance(r, dict):
            r = {"doc_type": "unknown", "data": {}}
            raw_results[i] = r

        # Ảnh 2 mặt trong 1 scan → AI trả >n results; map overflow về ảnh cuối cùng
        img_idx = i if i < n_imgs else n_imgs - 1
        r["filename"] = filenames[img_idx]
        if not isinstance(r.get("data"), dict):
            r["data"] = {}
        d = r["data"]

        # Tín hiệu vật lý 1: MRZ (IDVNM...) chỉ có ở MẶT SAU — override AI classification
        has_mrz = bool(
            d.get("mrz_line1") or
            d.get("so_giay_to_mrz") or
            extract_cccd_from_mrz(d.get("mrz_line1", ""))
        )
        if has_mrz:
            r["doc_type"] = "cccd_back"   # MRZ = chắc chắn mặt sau

        # Tín hiệu vật lý 2: QR trong ảnh nguồn
        r["_img_has_qr"] = (img_idx in img_has_qr)

        # Tag loại thẻ theo bảng phân loại:
        #   MRZ + QR trong ảnh  → mặt sau CC mới  (QR ở mặt sau)
        #   MRZ, không QR       → mặt sau CCCD cũ (không có QR ở mặt sau)
        #   QR, không MRZ       → mặt trước CCCD cũ (QR ở mặt trước)
        #   Không QR, không MRZ → mặt trước CC mới
        if has_mrz and r["_img_has_qr"]:
            r["_side"] = "back_new_cc"
        elif has_mrz:
            r["_side"] = "back_old_cccd"
        elif r["_img_has_qr"]:
            r["_side"] = "front_old_cccd"
        else:
            r["_side"] = "front_new_cc"

        # Gắn QR theo số CCCD — không phụ thuộc index
        doc_cccd = re.sub(r"\D", "", str(d.get("so_giay_to") or d.get("so_giay_to_mrz") or ""))
        if not doc_cccd:
            doc_cccd = extract_cccd_from_mrz(d.get("mrz_line1", ""))
        if doc_cccd and doc_cccd in qr_by_cccd:
            r["qr_data"] = qr_by_cccd[doc_cccd]

    grouped = group_documents(raw_results)
    grouped["errors"] = errors
    return grouped


@router.get("/config")
async def ocr_config():
    return {
        "configured": bool(_get_api_key()),
        "model":      _get_model(),
        "max_image_px": MAX_IMAGE_PX,
    }
