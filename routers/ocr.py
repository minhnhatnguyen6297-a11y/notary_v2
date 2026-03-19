"""
OCR Router — nhận ảnh giấy tờ, nhận diện loại, trích xuất dữ liệu.

Pipeline:
  1. Client gửi n ảnh (thứ tự bất kỳ)
  2. Gộp tất cả vào 1 lần gọi AI → tiết kiệm (n-1) × prompt tokens
  3. Parse kết quả JSON array
  4. Gom nhóm: ghép mặt trước/sau CCCD theo số CCCD từ MRZ
  5. Trả về persons[], properties[], marriages[]
"""

import base64, io, json, os, re
from typing import List

import httpx
from fastapi import APIRouter, File, HTTPException, UploadFile
from PIL import Image

router = APIRouter(prefix="/api/ocr", tags=["OCR"])

# ─── Config ───────────────────────────────────────────────────────────────────
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_MODEL   = os.getenv("OCR_MODEL", "gpt-4o-mini")
MAX_IMAGE_PX   = 1000
JPEG_QUALITY   = 82

# ─── Prompt ngắn gọn (~160 tokens thay vì ~480) ──────────────────────────────
# Gửi 1 lần cho toàn bộ batch → chỉ tốn prompt 1 lần dù n ảnh
SYSTEM_PROMPT = """Vietnamese legal doc OCR. Analyze ALL images. Return a JSON array, one object per image, same order.
doc_type: cccd_front|cccd_back|marriage_cert|land_cert|unknown

cccd_front→{"doc_type":"cccd_front","data":{"ho_ten":"CAPS","so_giay_to":"12digits","ngay_sinh":"DD/MM/YYYY","gioi_tinh":"Nam|Nữ","dia_chi":"nơi thường trú or nơi cư trú","ngay_het_han":"DD/MM/YYYY"}}
cccd_back→{"doc_type":"cccd_back","data":{"mrz_line1":"IDVNM... full line","so_giay_to_mrz":"12digits","ngay_cap":"DD/MM/YYYY"}}
marriage_cert→{"doc_type":"marriage_cert","data":{"chong_ho_ten":"","chong_ngay_sinh":"DD/MM/YYYY","chong_so_giay_to":"digits","vo_ho_ten":"","vo_ngay_sinh":"DD/MM/YYYY","vo_so_giay_to":"digits","ngay_dang_ky":"DD/MM/YYYY","noi_dang_ky":""}}
land_cert→{"doc_type":"land_cert","data":{"so_serial":"","so_thua_dat":"","so_to_ban_do":"","dia_chi_dat":"","loai_dat":"","ngay_cap":"DD/MM/YYYY","co_quan_cap":""}}
unknown→{"doc_type":"unknown","data":{}}

Rules: ho_ten UPPERCASE, dates DD/MM/YYYY, digits only for ID numbers, "" if unreadable. Return ONLY the JSON array."""

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
    raw = re.sub(r"\s", "", mrz_line1 or "")
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
    Trả về list[dict] cùng độ dài với images_b64.
    """
    if not OPENAI_API_KEY:
        raise HTTPException(status_code=500, detail="Server chưa cấu hình OPENAI_API_KEY")

    # Xây content: text prompt + tất cả ảnh
    content = [{"type": "text", "text": SYSTEM_PROMPT}]
    for b64 in images_b64:
        content.append({
            "type": "image_url",
            "image_url": {
                "url": f"data:image/jpeg;base64,{b64}",
                "detail": "high"
            }
        })

    async with httpx.AsyncClient(timeout=120.0) as client:
        resp = await client.post(
            "https://api.openai.com/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {OPENAI_API_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "model": OPENAI_MODEL,
                "max_tokens": 400 * len(images_b64),   # ~400 tokens output mỗi ảnh
                "temperature": 0,                       # Kết quả ổn định, không random
                "messages": [{"role": "user", "content": content}]
            },
        )

    if not resp.is_success:
        raise HTTPException(status_code=502, detail=f"OpenAI lỗi: {resp.text[:300]}")

    raw = resp.json()["choices"][0]["message"]["content"]
    parsed = parse_json_safe(raw)

    # Đảm bảo trả về list đúng độ dài
    if isinstance(parsed, list):
        # Pad nếu AI trả về ít hơn
        while len(parsed) < len(images_b64):
            parsed.append({"doc_type": "unknown", "data": {}})
        return parsed[:len(images_b64)]

    if isinstance(parsed, dict):
        # AI trả về object thay vì array (chỉ 1 ảnh)
        return [parsed]

    # Fallback: tất cả unknown
    return [{"doc_type": "unknown", "data": {}} for _ in images_b64]


# ─── Grouping ─────────────────────────────────────────────────────────────────
def group_documents(results: list) -> dict:
    fronts    = [r for r in results if r.get("doc_type") == "cccd_front"]
    backs     = [r for r in results if r.get("doc_type") == "cccd_back"]
    marriages = [r for r in results if r.get("doc_type") == "marriage_cert"]
    lands     = [r for r in results if r.get("doc_type") == "land_cert"]
    unknowns  = [r for r in results if r.get("doc_type") == "unknown"]

    persons = []
    matched_backs = set()

    for front in fronts:
        fd   = front.get("data", {})
        cccd = re.sub(r"\D", "", fd.get("so_giay_to") or "")

        back_match = None
        for i, back in enumerate(backs):
            if i in matched_backs:
                continue
            bd = back.get("data", {})
            mrz_cccd = re.sub(r"\D", "", bd.get("so_giay_to_mrz") or "")
            if not mrz_cccd:
                mrz_cccd = extract_cccd_from_mrz(bd.get("mrz_line1", ""))
            if cccd and mrz_cccd == cccd:
                back_match = back
                matched_backs.add(i)
                break

        bd = back_match.get("data", {}) if back_match else {}
        persons.append({
            "ho_ten":        fd.get("ho_ten", ""),
            "so_giay_to":    cccd,
            "ngay_sinh":     fd.get("ngay_sinh", ""),
            "gioi_tinh":     fd.get("gioi_tinh", ""),
            "dia_chi":       fd.get("dia_chi", ""),
            "ngay_het_han":  fd.get("ngay_het_han", ""),
            "ngay_cap":      bd.get("ngay_cap", ""),
            "_source":       "cccd" + ("+back" if back_match else " (thiếu mặt sau)"),
            "_files":        [front.get("filename",""), back_match.get("filename","") if back_match else ""],
        })

    # Mặt sau chưa ghép
    for i, back in enumerate(backs):
        if i in matched_backs:
            continue
        bd = back.get("data", {})
        mrz_cccd = re.sub(r"\D", "", bd.get("so_giay_to_mrz") or "")
        if not mrz_cccd:
            mrz_cccd = extract_cccd_from_mrz(bd.get("mrz_line1", ""))
        persons.append({
            "ho_ten": "", "so_giay_to": mrz_cccd,
            "ngay_sinh": "", "gioi_tinh": "", "dia_chi": "",
            "ngay_cap": bd.get("ngay_cap", ""),
            "_source": "cccd_back only",
            "_files": [back.get("filename", "")],
        })

    marriage_data = []
    for m in marriages:
        md = m.get("data", {})
        marriage_data.append({
            "chong": {
                "ho_ten": md.get("chong_ho_ten", ""),
                "so_giay_to": re.sub(r"\D", "", md.get("chong_so_giay_to") or ""),
                "ngay_sinh": md.get("chong_ngay_sinh", ""),
                "gioi_tinh": "Nam", "dia_chi": "",
            },
            "vo": {
                "ho_ten": md.get("vo_ho_ten", ""),
                "so_giay_to": re.sub(r"\D", "", md.get("vo_so_giay_to") or ""),
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
    Trả về persons[], properties[], marriages[].
    """
    if not files:
        raise HTTPException(status_code=400, detail="Chưa có ảnh nào được gửi lên")

    images_b64 = []
    filenames  = []
    errors     = []

    for f in files:
        try:
            file_bytes = await f.read()
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

    # Gắn filename vào từng kết quả
    for i, r in enumerate(raw_results):
        r["filename"] = filenames[i] if i < len(filenames) else "unknown"
        if "data" not in r:
            r["data"] = {}

    grouped = group_documents(raw_results)
    grouped["errors"] = errors
    return grouped


@router.get("/config")
async def ocr_config():
    return {
        "configured": bool(OPENAI_API_KEY),
        "model":      OPENAI_MODEL,
        "max_image_px": MAX_IMAGE_PX,
    }
