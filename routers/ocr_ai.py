"""
Cloud OCR router.

Fast path:
1. Try QR once on the server using raw image bytes.
2. Preprocess image lightly.
3. If QR fails, send the image straight to AI OCR.
4. Canonicalize extracted identity data and pair images after extraction.

Cloud OCR stays QR-first and avoids heavy local MRZ OCR, but it still performs
post-extract grouping so front/back images do not leak out as separate persons.
"""

from __future__ import annotations

import asyncio
import base64
import io
import json
import logging
import os
import re
import unicodedata
from datetime import datetime
from time import perf_counter
from typing import Any, List

import httpx
import zxingcpp
from dotenv import dotenv_values
from fastapi import APIRouter, File, HTTPException, UploadFile
from PIL import Image, ImageFilter, ImageOps


router = APIRouter(tags=["OCR"])
_logger = logging.getLogger("ocr_ai")

_ENV_PATH = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".env"))

MAX_IMAGE_PX = 1000
MAX_IMAGE_PX_QWEN = int(os.getenv("QWEN_MAX_IMAGE_PX", "1600"))
JPEG_QUALITY = 82
AI_TIMEOUT_SECONDS = 120.0
AI_CONCURRENCY = 4

DOC_PROFILE_FRONT_OLD = "cccd_front_old"
DOC_PROFILE_BACK_OLD = "cccd_back_old"
DOC_PROFILE_FRONT_NEW = "cccd_front_new"
DOC_PROFILE_BACK_NEW = "cccd_back_new"
DOC_PROFILE_UNKNOWN = "unknown"

_PROFILE_TO_SIDE_LABEL = {
    DOC_PROFILE_FRONT_OLD: "front_old_cccd",
    DOC_PROFILE_FRONT_NEW: "front_new_cc",
    DOC_PROFILE_BACK_NEW: "back_new_cc",
    DOC_PROFILE_BACK_OLD: "back_old_cccd",
    DOC_PROFILE_UNKNOWN: "unknown",
}

_FIELD_SOURCE_PRIORITY = {
    "so_giay_to": {"qr": 3, "mrz": 2, "ai": 1},
    "ngay_sinh": {"qr": 3, "mrz": 2, "ai": 1},
    "gioi_tinh": {"qr": 3, "mrz": 2, "ai": 1},
    "ho_ten": {"qr": 3, "ai": 2, "mrz": 1},
    "dia_chi": {"qr": 3, "ai": 2},
    "ngay_cap": {"qr": 3, "ai": 2},
    "ngay_het_han": {"qr": 3, "mrz": 2, "ai": 1},
}


def _ms(seconds: float) -> float:
    return round(max(0.0, float(seconds)) * 1000.0, 2)


def _log_ocr_ai(event: str, level: str = "info", **fields: Any) -> None:
    payload = {"event": event, **fields}
    try:
        message = json.dumps(payload, ensure_ascii=False, default=str)
    except Exception:
        message = str(payload)
    if level == "warning":
        _logger.warning("[OCR_AI] %s", message)
    else:
        _logger.info("[OCR_AI] %s", message)


def _read_env() -> dict[str, str]:
    return dict(dotenv_values(_ENV_PATH))


def _get_api_key(model: str) -> str:
    m = model.lower()
    if "qwen" in m:
        key_name = "QWEN_API_KEY"
        fallback = "DASHSCOPE_API_KEY"
        env = _read_env()
        return os.getenv(key_name, "") or env.get(key_name, "") or os.getenv(fallback, "") or env.get(fallback, "")
    key_name = "GEMINI_API_KEY" if "gemini" in m else "OPENAI_API_KEY"
    return os.getenv(key_name, "") or _read_env().get(key_name, "")


def _get_model() -> str:
    configured = os.getenv("OCR_MODEL", "") or _read_env().get("OCR_MODEL", "gpt-4o-mini")
    normalized = str(configured or "").strip()
    if normalized.startswith("models/"):
        normalized = normalized.split("/", 1)[1]
    if normalized == "gemini-2.0-flash":
        return "gemini-2.5-flash"
    return normalized or "gpt-4o-mini"


def _zxing_decode_qr(image_obj) -> str | None:
    try:
        results = zxingcpp.read_barcodes(image_obj)
        for result in results:
            if result.format in (zxingcpp.BarcodeFormat.QRCode, zxingcpp.BarcodeFormat.MicroQRCode):
                text = (result.text or "").strip()
                if text:
                    return text
    except Exception:
        return None
    return None


def _qr_variants(file_bytes: bytes) -> list[Image.Image]:
    variants: list[Image.Image] = []
    try:
        pil_img = Image.open(io.BytesIO(file_bytes))
        pil_img = ImageOps.exif_transpose(pil_img)
        if pil_img.mode not in ("RGB", "L"):
            pil_img = pil_img.convert("RGB")
        variants.append(pil_img)
    except Exception:
        pass

    return variants


def try_decode_qr(file_bytes: bytes) -> str | None:
    for candidate in _qr_variants(file_bytes):
        decoded = _zxing_decode_qr(candidate)
        if decoded:
            return decoded
    return None


def parse_cccd_qr(text: str) -> dict | None:
    raw = (text or "").strip()
    if not raw:
        return None

    parts = [part.strip() for part in re.split(r"[|\r\n;]+", raw) if part and part.strip()]
    if not parts:
        return None

    now_year = datetime.now().year

    def fold(value: str) -> str:
        normalized = unicodedata.normalize("NFKD", value or "")
        normalized = "".join(ch for ch in normalized if not unicodedata.combining(ch))
        return normalized.replace("đ", "d").replace("Đ", "D").lower()

    def is_name_candidate(value: str) -> bool:
        if not value or re.search(r"\d", value):
            return False
        words = value.split()
        if not (2 <= len(words) <= 6):
            return False
        folded = fold(value)
        return not re.search(
            r"bo cong an|ministry|public security|cong hoa|socialist|identity|citizen|can cuoc|"
            r"noi thuong tru|noi cu tru|place of|date of|quoc tich|nationality|que quan",
            folded,
        )

    def is_address_candidate(value: str) -> bool:
        folded = fold(value)
        return len(value) >= 10 and (
            "," in value or re.search(r"\b(thon|to dan pho|xa|phuong|huyen|quan|tinh|thanh pho|tp)\b", folded)
        )

    def parse_date(raw_date: str) -> str:
        compact = re.sub(r"\s+", "", raw_date or "")
        if not compact:
            return ""
        match = re.match(r"^(\d{1,2})[/-](\d{1,2})[/-](\d{4})$", compact)
        if match:
            dd = int(match.group(1))
            mm = int(match.group(2))
            yyyy = int(match.group(3))
            if 1 <= dd <= 31 and 1 <= mm <= 12 and 1900 <= yyyy <= 2100:
                return f"{dd:02d}/{mm:02d}/{yyyy:04d}"
            return ""
        if re.fullmatch(r"\d{8}", compact):
            dd = int(compact[0:2])
            mm = int(compact[2:4])
            yyyy = int(compact[4:8])
            if 1 <= dd <= 31 and 1 <= mm <= 12 and 1900 <= yyyy <= 2100:
                return f"{dd:02d}/{mm:02d}/{yyyy:04d}"
            yyyy = int(compact[0:4])
            mm = int(compact[4:6])
            dd = int(compact[6:8])
            if 1 <= dd <= 31 and 1 <= mm <= 12 and 1900 <= yyyy <= 2100:
                return f"{dd:02d}/{mm:02d}/{yyyy:04d}"
        return ""

    def collect_dates(part: str) -> list[str]:
        out: list[str] = []
        compact = re.sub(r"\s+", "", part or "")
        for match in re.findall(r"\d{1,2}[/-]\d{1,2}[/-]\d{4}", compact):
            parsed = parse_date(match)
            if parsed:
                out.append(parsed)
        for match in re.findall(r"\d{8}", compact):
            parsed = parse_date(match)
            if parsed:
                out.append(parsed)
        if re.fullmatch(r"\d{16}", compact):
            first = parse_date(compact[:8])
            second = parse_date(compact[8:])
            if first:
                out.append(first)
            if second:
                out.append(second)
        seen: set[str] = set()
        deduped: list[str] = []
        for value in out:
            if value not in seen:
                seen.add(value)
                deduped.append(value)
        return deduped

    cccd = ""
    cccd_idx = -1
    for idx, part in enumerate(parts):
        match = re.search(r"(?<!\d)(\d{12})(?!\d)", part)
        if match:
            cccd = match.group(1)
            cccd_idx = idx
            break
    if not cccd:
        return None

    name = ""
    birth = ""
    issue = ""
    expiry = ""
    gender = ""
    address = ""

    for idx, part in enumerate(parts):
        folded = fold(part)
        label_value = part.split(":", 1)[1].strip() if ":" in part else part
        if not name and re.search(r"ho va ten|ho ten|full name", folded):
            if is_name_candidate(label_value):
                name = label_value
            elif idx + 1 < len(parts) and is_name_candidate(parts[idx + 1]):
                name = parts[idx + 1]
        if not gender and re.search(r"\b(nam|nu|nữ|male|female)\b", folded):
            if re.search(r"\b(nam|male)\b", folded):
                gender = "Nam"
            elif re.search(r"\b(nu|nữ|female)\b", folded):
                gender = "Nữ"
        if not address and re.search(r"noi thuong tru|noi cu tru|place of residence", folded):
            if label_value:
                address = label_value
            elif idx + 1 < len(parts):
                address = parts[idx + 1].strip()
        date_values = collect_dates(part)
        if date_values:
            if re.search(r"ngay sinh|date of birth", folded) and not birth:
                birth = date_values[0]
            if re.search(r"ngay cap|date of issue", folded) and not issue:
                issue = date_values[0]
            if re.search(r"ngay het han|date of expiry|co gia tri den|có giá trị đến", folded) and not expiry:
                expiry = date_values[-1]

    if not name:
        preferred: list[str] = []
        if 0 <= cccd_idx + 1 < len(parts):
            preferred.append(parts[cccd_idx + 1])
        if 0 <= cccd_idx + 2 < len(parts):
            preferred.append(parts[cccd_idx + 2])
        for part in preferred + parts:
            if is_name_candidate(part):
                name = part
                break

    if not gender:
        for part in parts:
            folded = fold(part)
            if re.search(r"\b(nam|male)\b", folded):
                gender = "Nam"
                break
            if re.search(r"\b(nu|nữ|female)\b", folded):
                gender = "Nữ"
                break

    if not address:
        address_candidates = [part for part in parts if is_address_candidate(part)]
        if address_candidates:
            address_candidates.sort(key=len, reverse=True)
            address = address_candidates[0]

    all_dates: list[str] = []
    for part in parts:
        all_dates.extend(collect_dates(part))

    def year_of(value: str) -> int:
        return int(value.split("/")[-1]) if value else 0

    if all_dates:
        if not birth:
            birth_candidates = [value for value in all_dates if 1900 <= year_of(value) <= now_year]
            if birth_candidates:
                birth = sorted(birth_candidates, key=year_of)[0]
        if not issue:
            issue_candidates = [value for value in all_dates if 2000 <= year_of(value) <= now_year + 1 and value != birth]
            if issue_candidates:
                issue = sorted(issue_candidates, key=year_of)[0]
        if not expiry:
            expiry_candidates = [value for value in all_dates if year_of(value) >= now_year]
            if expiry_candidates:
                expiry = sorted(expiry_candidates, key=year_of)[-1]

    if address:
        folded_address = fold(address)
        if re.search(r"bo cong an|ministry|public security|quoc tich|nationality", folded_address):
            address = ""

    return {
        "so_giay_to": cccd,
        "ho_ten": (name or "").strip(),
        "ngay_sinh": (birth or "").strip(),
        "gioi_tinh": gender,
        "dia_chi": (address or "").strip(),
        "ngay_cap": (issue or "").strip(),
        "ngay_het_han": (expiry or "").strip(),
    }


SYSTEM_PROMPT = """Extract structured data from a single uploaded image of Vietnamese legal documents.
Return ONLY a JSON array.

Each item must be an object with:
- "doc_type": one of "person", "marriage_cert", "land_cert", "unknown"
- "data": an object

For "person", use:
{"ho_ten":"","so_giay_to":"","ngay_sinh":"","gioi_tinh":"","dia_chi":"","ngay_cap":"","ngay_het_han":""}

For "marriage_cert", use:
{"chong_ho_ten":"","chong_ngay_sinh":"","chong_so_giay_to":"","vo_ho_ten":"","vo_ngay_sinh":"","vo_so_giay_to":"","ngay_dang_ky":"","noi_dang_ky":""}

For "land_cert", use:
{"so_serial":"","so_thua_dat":"","so_to_ban_do":"","dia_chi_dat":"","loai_dat":"","ngay_cap":"","co_quan_cap":""}

Rules:
- Do not classify card side, old/new generation, or front/back.
- Do not infer fields that are not visible in the image.
- Use empty string for unreadable or missing fields.
- Dates must be DD/MM/YYYY when visible.
- ID numbers must contain digits only.
- Keep Vietnamese diacritics if readable.
- If the image contains multiple separate documents, return multiple objects.
- If the image is not one of the supported document types, return [{"doc_type":"unknown","data":{}}].
"""

SYSTEM_PROMPT_QWEN = """Phan tich anh tai lieu phap ly Viet Nam va tra ve JSON array.

Moi item la object gom:
- "doc_type": "person" | "marriage_cert" | "land_cert" | "unknown"
- "side": "front" | "back" | "unknown"  (chi dung cho doc_type=person)
- "data": object chua cac truong

Voi "person" (CCCD/CMND):
{"ho_ten":"","so_giay_to":"","ngay_sinh":"","gioi_tinh":"","dia_chi":"","ngay_cap":"","ngay_het_han":""}

Voi "marriage_cert":
{"chong_ho_ten":"","chong_ngay_sinh":"","chong_so_giay_to":"","vo_ho_ten":"","vo_ngay_sinh":"","vo_so_giay_to":"","ngay_dang_ky":"","noi_dang_ky":""}

Voi "land_cert":
{"so_serial":"","so_thua_dat":"","so_to_ban_do":"","dia_chi_dat":"","loai_dat":"","ngay_cap":"","co_quan_cap":""}

Quy tac:
- Mat truoc CCCD (side=front): co ho ten, ngay sinh, anh chan dung.
- Mat sau CCCD moi (side=back): co "Noi cu tru" hoac van tay + MRZ.
- Mat sau CCCD cu (side=back): co "Dac diem nhan dang" + dau van tay.
- Ngay theo dinh dang DD/MM/YYYY.
- So giay to chi gom chu so.
- Giu dau tieng Viet neu doc duoc.
- Anh khong phai tai lieu phap ly → [{"doc_type":"unknown","data":{}}].
- Truong khong doc duoc → chuoi rong, khong doan mo.
- Tra ve ONLY JSON array, khong them text khac.
"""


def _clean_text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


SYSTEM_PROMPT = """Vietnamese legal document OCR. One image = one document side. Return ONLY a JSON array.

For CCCD/person images, return exactly one object:
{
  "doc_type":"cccd_front|cccd_back|person|unknown",
  "data":{
    "doc_side":"front|back|unknown",
    "doc_version":"old|new|unknown",
    "ho_ten":"",
    "so_giay_to":"",
    "ngay_sinh":"",
    "gioi_tinh":"",
    "dia_chi":"",
    "ngay_cap":"",
    "ngay_het_han":"",
    "mrz_line1":"",
    "mrz_line2":"",
    "mrz_line3":"",
    "so_giay_to_mrz":"",
    "dia_chi_back":""
  }
}

For "marriage_cert", use:
{"doc_type":"marriage_cert","data":{"chong_ho_ten":"","chong_ngay_sinh":"","chong_so_giay_to":"","vo_ho_ten":"","vo_ngay_sinh":"","vo_so_giay_to":"","ngay_dang_ky":"","noi_dang_ky":""}}

For "land_cert", use:
{"doc_type":"land_cert","data":{"so_serial":"","so_thua_dat":"","so_to_ban_do":"","dia_chi_dat":"","loai_dat":"","ngay_cap":"","co_quan_cap":""}}

Rules:
- Identify CCCD front/back when visible. Set doc_side and doc_version.
- Old CCCD "CĂN CƯỚC CÔNG DÂN" front may show address. Front fields can include Họ tên, Ngày sinh, Giới tính, Quê quán, Nơi thường trú, Có giá trị đến.
- On old CCCD front, dia_chi MUST be "Nơi thường trú". Never use "Quê quán" or "Quốc tịch" as dia_chi.
- New CĂN CƯỚC front has no address. dia_chi must be empty on new front.
- New CĂN CƯỚC back may show QR, chip, "Nơi cư trú", ngày cấp, ngày hết hạn, and MRZ. Put residence text into dia_chi_back.
- Old CCCD back usually has fingerprints, ngày cấp, and MRZ. Prefer ngay_cap from the back side.
- If MRZ is visible, copy mrz_line1/2/3 and extract so_giay_to_mrz if readable.
- Do not pair documents together and do not infer hidden fields from another image.
- Use empty string for unreadable or missing fields.
- Dates must be DD/MM/YYYY when visible.
- ID values must contain digits only.
- Keep Vietnamese diacritics if readable.
- If unsupported, return [{"doc_type":"unknown","data":{}}].
"""


SYSTEM_PROMPT_QWEN = """Phan tich mot anh tai lieu phap ly Viet Nam va tra ve ONLY JSON array.

Voi CCCD/giay to nhan than, tra ve:
{
  "doc_type":"cccd_front|cccd_back|person|unknown",
  "data":{
    "doc_side":"front|back|unknown",
    "doc_version":"old|new|unknown",
    "ho_ten":"",
    "so_giay_to":"",
    "ngay_sinh":"",
    "gioi_tinh":"",
    "dia_chi":"",
    "ngay_cap":"",
    "ngay_het_han":"",
    "mrz_line1":"",
    "mrz_line2":"",
    "mrz_line3":"",
    "so_giay_to_mrz":"",
    "dia_chi_back":""
  }
}

Quy tac:
- Neu thay mat truoc thi dat doc_side=front.
- Neu thay mat sau thi dat doc_side=back.
- Neu thay MRZ thi copy day du mrz_line1/2/3 va so_giay_to_mrz neu doc duoc.
- Khong doan mo truong khong thay.
- So giay to chi gom chu so.
- Ngay theo dinh dang DD/MM/YYYY.
- Neu khong phai tai lieu ho tro thi tra ve [{"doc_type":"unknown","data":{}}].
"""


def _ascii_fold(text: str) -> str:
    normalized = unicodedata.normalize("NFKD", str(text or ""))
    without_marks = "".join(ch for ch in normalized if not unicodedata.combining(ch))
    return without_marks.replace("đ", "d").replace("Đ", "D")


def _normalize_text_space(text: Any) -> str:
    return re.sub(r"\s+", " ", str(text or "")).strip()


def _clean_doc_number(value: Any) -> str:
    digits = re.sub(r"\D", "", str(value or ""))
    if len(digits) >= 12:
        return digits[:12]
    return digits


def _normalize_mrz_line(value: Any) -> str:
    cleaned = _ascii_fold(str(value or "")).upper().replace("`", "<")
    return re.sub(r"[^A-Z0-9<]", "", cleaned)


def _extract_canonical_cccd_from_mrz_line1(normalized_line1: str) -> str:
    if not normalized_line1.startswith("IDVNM"):
        return ""
    digits_after_prefix = "".join(ch for ch in normalized_line1[5:] if ch.isdigit())
    if len(digits_after_prefix) < 22:
        return ""
    return digits_after_prefix[:22][10:22]


def _extract_cccd_from_mrz_lines(*values: Any) -> str:
    normalized_lines = [_normalize_mrz_line(value) for value in values if _normalize_mrz_line(value)]
    for line in normalized_lines:
        canonical = _extract_canonical_cccd_from_mrz_line1(line)
        if canonical:
            return canonical
    for line in normalized_lines:
        match = re.search(r"(?<!\d)(\d{12})(?:<<\d)?(?!\d)", line)
        if match:
            return match.group(1)
    return ""


def _validated_mrz_cccd(data: dict[str, Any]) -> str:
    line1 = _normalize_mrz_line(data.get("mrz_line1"))
    line2 = _normalize_mrz_line(data.get("mrz_line2"))
    line3 = _normalize_mrz_line(data.get("mrz_line3"))
    derived = _extract_cccd_from_mrz_lines(line1, line2, line3)
    if derived:
        return derived
    explicit = _valid_cccd_candidate(data.get("so_giay_to_mrz"))
    if explicit and not any((line1, line2, line3)):
        return explicit
    return ""


def extract_cccd_from_mrz(mrz_line1: Any) -> str:
    normalized = _normalize_mrz_line(mrz_line1)
    canonical = _extract_canonical_cccd_from_mrz_line1(normalized)
    if canonical:
        return canonical
    match = re.search(r"(\d{12})<<\d", normalized)
    if match:
        return match.group(1)
    match = re.search(r"(\d{12})<<", normalized)
    return match.group(1) if match else ""


def _mrz_date_to_display(value: Any, *, birth: bool) -> str:
    raw = re.sub(r"[^0-9<]", "", str(value or ""))
    if len(raw) < 6 or raw.startswith("<<<<<<"):
        return ""
    candidate = raw[:6]
    if not re.fullmatch(r"\d{6}", candidate):
        return ""
    yy = int(candidate[0:2])
    mm = int(candidate[2:4])
    dd = int(candidate[4:6])
    if not (1 <= mm <= 12 and 1 <= dd <= 31):
        return ""
    current_year = datetime.now().year
    century = 1900 if birth and yy > current_year % 100 else 2000
    return f"{dd:02d}/{mm:02d}/{century + yy:04d}"


def _extract_name_from_mrz_line(value: Any) -> str:
    line = _normalize_mrz_line(value)
    if not line or "<" not in line:
        return ""
    alpha_count = sum(1 for ch in line if "A" <= ch <= "Z")
    digit_count = sum(1 for ch in line if ch.isdigit())
    if alpha_count < 4 or alpha_count <= digit_count:
        return ""
    name = line.rstrip("<").replace("<<", " ").replace("<", " ").strip()
    name = re.sub(r"\s+", " ", name)
    if len(name.split()) < 2:
        return ""
    return name


def _extract_digit_candidates(*values: Any) -> list[str]:
    seen: list[str] = []
    for value in values:
        text = _normalize_mrz_line(value) if value is not None else ""
        for match in re.findall(r"\d{8,12}", text):
            if match not in seen:
                seen.append(match)
    return seen


def _parse_mrz_fields(data: dict[str, Any]) -> dict[str, str]:
    line1 = _normalize_mrz_line(data.get("mrz_line1"))
    line2 = _normalize_mrz_line(data.get("mrz_line2"))
    line3 = _normalize_mrz_line(data.get("mrz_line3"))
    if not any((line1, line2, line3)):
        return {}
    name = _extract_name_from_mrz_line(line3)
    return {
        "so_giay_to": _validated_mrz_cccd(data),
        "ho_ten": name,
        "ngay_sinh": _mrz_date_to_display(line2[0:6] if len(line2) >= 6 else "", birth=True),
        "gioi_tinh": _normalize_gender("Nam" if len(line2) >= 8 and line2[7:8] == "M" else ("Nữ" if len(line2) >= 8 and line2[7:8] == "F" else "")),
        "ngay_het_han": _mrz_date_to_display(line2[8:14] if len(line2) >= 14 else "", birth=False),
    }


def _normalize_date(value: Any) -> str:
    raw = _clean_text(value).replace("-", "/").replace(".", "/")
    match = re.search(r"(?<!\d)(\d{1,2})/(\d{1,2})/(\d{4})(?!\d)", raw)
    if not match:
        return ""
    dd = int(match.group(1))
    mm = int(match.group(2))
    yyyy = int(match.group(3))
    if not (1 <= dd <= 31 and 1 <= mm <= 12 and 1900 <= yyyy <= 2100):
        return ""
    return f"{dd:02d}/{mm:02d}/{yyyy:04d}"


def _normalize_gender(value: Any) -> str:
    folded = _clean_text(value).lower()
    if folded in {"nam", "male"}:
        return "Nam"
    if folded in {"nữ", "nu", "female"}:
        return "Nữ"
    return _clean_text(value)


def _field_sources(data: dict[str, str], source: str) -> dict[str, str]:
    return {key: source for key, value in data.items() if _clean_text(value)}


def _normalize_person_data(data: dict[str, Any]) -> dict[str, str]:
    return {
        "ho_ten": _clean_text(data.get("ho_ten")),
        "so_giay_to": re.sub(r"\D", "", _clean_text(data.get("so_giay_to"))),
        "ngay_sinh": _normalize_date(data.get("ngay_sinh")),
        "gioi_tinh": _normalize_gender(data.get("gioi_tinh")),
        "dia_chi": _clean_text(data.get("dia_chi")),
        "ngay_cap": _normalize_date(data.get("ngay_cap")),
        "ngay_het_han": _normalize_date(data.get("ngay_het_han")),
    }


def _normalize_marriage_data(data: dict[str, Any]) -> dict[str, str]:
    return {
        "chong_ho_ten": _clean_text(data.get("chong_ho_ten")),
        "chong_ngay_sinh": _normalize_date(data.get("chong_ngay_sinh")),
        "chong_so_giay_to": re.sub(r"\D", "", _clean_text(data.get("chong_so_giay_to"))),
        "vo_ho_ten": _clean_text(data.get("vo_ho_ten")),
        "vo_ngay_sinh": _normalize_date(data.get("vo_ngay_sinh")),
        "vo_so_giay_to": re.sub(r"\D", "", _clean_text(data.get("vo_so_giay_to"))),
        "ngay_dang_ky": _normalize_date(data.get("ngay_dang_ky")),
        "noi_dang_ky": _clean_text(data.get("noi_dang_ky")),
    }


def _normalize_land_data(data: dict[str, Any]) -> dict[str, str]:
    return {
        "so_serial": _clean_text(data.get("so_serial")),
        "so_thua_dat": _clean_text(data.get("so_thua_dat")),
        "so_to_ban_do": _clean_text(data.get("so_to_ban_do")),
        "dia_chi_dat": _clean_text(data.get("dia_chi_dat")),
        "loai_dat": _clean_text(data.get("loai_dat")),
        "ngay_cap": _normalize_date(data.get("ngay_cap")),
        "co_quan_cap": _clean_text(data.get("co_quan_cap")),
    }


def _normalize_expiry_value(value: Any) -> str:
    raw = _normalize_text_space(value)
    if not raw:
        return ""
    if re.search(r"khong\s+thoi\s+han|không\s+thời\s+hạn|indefinite|no\s+expiry", _ascii_fold(raw).lower()):
        return ""
    return _normalize_date(raw)


def _normalize_gender(value: Any) -> str:
    folded = _ascii_fold(_clean_text(value)).lower()
    if folded in {"nam", "male"}:
        return "Nam"
    if folded in {"nu", "female"}:
        return "Nữ"
    return ""


def _normalize_person_data(data: dict[str, Any]) -> dict[str, str]:
    return {
        "ho_ten": _clean_text(data.get("ho_ten")),
        "so_giay_to": _digits_only(data.get("so_giay_to")),
        "ngay_sinh": _normalize_date(data.get("ngay_sinh")),
        "gioi_tinh": _normalize_gender(data.get("gioi_tinh")),
        "dia_chi": _clean_text(data.get("dia_chi")),
        "ngay_cap": _normalize_date(data.get("ngay_cap")),
        "ngay_het_han": _normalize_expiry_value(data.get("ngay_het_han")),
    }


def _normalize_person_metadata(data: dict[str, Any]) -> dict[str, str]:
    side = _normalize_text_space(data.get("doc_side", "")).lower()
    version = _normalize_text_space(data.get("doc_version", "")).lower()
    return {
        "doc_side": side if side in {"front", "back"} else "unknown",
        "doc_version": version if version in {"old", "new"} else "unknown",
        "mrz_line1": _normalize_mrz_line(data.get("mrz_line1")),
        "mrz_line2": _normalize_mrz_line(data.get("mrz_line2")),
        "mrz_line3": _normalize_mrz_line(data.get("mrz_line3")),
        "so_giay_to_mrz": _validated_mrz_cccd(data),
        "dia_chi_back": _clean_text(data.get("dia_chi_back")),
    }


def _coerce_doc_type(value: Any) -> str:
    raw = _clean_text(value).lower()
    if raw in {"cccd_front", "citizen_card_front", "id_card_front", "identity_card_front"}:
        return "cccd_front"
    if raw in {"cccd_back", "citizen_card_back", "id_card_back", "identity_card_back"}:
        return "cccd_back"
    if raw in {"person", "cccd", "citizen_card", "id_card", "identity_card"}:
        return "person"
    if raw in {"marriage", "marriage_cert", "marriage_certificate", "ket_hon"}:
        return "marriage_cert"
    if raw in {"land", "land_cert", "land_certificate", "property", "red_book", "so_do"}:
        return "land_cert"
    return "unknown"


def _normalize_ai_item(item: Any, filename: str) -> dict[str, Any]:
    if not isinstance(item, dict):
        return {"doc_type": "unknown", "data": {}, "filename": filename, "side": "unknown", "field_sources": {}}

    data = item.get("data")
    if not isinstance(data, dict):
        data = {}

    doc_type = _coerce_doc_type(item.get("doc_type"))
    if doc_type in {"person", "cccd_front", "cccd_back"}:
        normalized_data = {**_normalize_person_data(data), **_normalize_person_metadata(data)}
    elif doc_type == "marriage_cert":
        normalized_data = _normalize_marriage_data(data)
    elif doc_type == "land_cert":
        normalized_data = _normalize_land_data(data)
    else:
        normalized_data = {}

    side_raw = _normalize_text_space(item.get("side") or data.get("doc_side", "")).lower()
    side = side_raw if side_raw in ("front", "back") else "unknown"
    source = "ai"
    field_sources = _field_sources(_normalize_person_data(data), source) if doc_type in {"person", "cccd_front", "cccd_back"} else {}
    return {
        "doc_type": doc_type,
        "data": normalized_data,
        "filename": filename,
        "side": side,
        "field_sources": field_sources,
    }


def _prepare_image_bytes(file_bytes: bytes, max_px: int = MAX_IMAGE_PX) -> bytes:
    img = Image.open(io.BytesIO(file_bytes))
    img = ImageOps.exif_transpose(img)
    if img.mode not in ("RGB", "L"):
        img = img.convert("RGB")
    if img.mode == "L":
        img = img.convert("RGB")

    width, height = img.size
    scale = min(1.0, max_px / max(width, height))
    if scale < 1.0:
        img = img.resize((int(width * scale), int(height * scale)), Image.LANCZOS)

    img = ImageOps.autocontrast(img)
    img = img.filter(ImageFilter.UnsharpMask(radius=1, percent=130, threshold=3))

    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=JPEG_QUALITY)
    return buf.getvalue()


def resize_to_base64(file_bytes: bytes, max_px: int = MAX_IMAGE_PX) -> str:
    return base64.b64encode(_prepare_image_bytes(file_bytes, max_px=max_px)).decode()


def parse_json_safe(text: str):
    cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip(), flags=re.MULTILINE).strip()
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        match = re.search(r"(\[[\s\S]+\]|\{[\s\S]+\})", cleaned)
        if match:
            try:
                return json.loads(match.group())
            except Exception:
                return None
    return None


async def _call_vision_single(
    client: httpx.AsyncClient,
    *,
    model: str,
    api_key: str,
    image_b64: str,
) -> list[dict]:
    m = model.lower()
    is_gemini = "gemini" in m
    is_qwen = "qwen" in m

    try:
        if is_gemini:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
            resp = await client.post(
                url,
                json={
                    "contents": [
                        {
                            "parts": [
                                {"text": SYSTEM_PROMPT},
                                {"inline_data": {"mime_type": "image/jpeg", "data": image_b64}},
                            ]
                        }
                    ],
                    "generationConfig": {"temperature": 0.0},
                },
            )
        elif is_qwen:
            dashscope_base = os.getenv("DASHSCOPE_BASE_URL", "https://dashscope-intl.aliyuncs.com/compatible-mode/v1")
            resp = await client.post(
                f"{dashscope_base}/chat/completions",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": model,
                    "max_tokens": 900,
                    "temperature": 0,
                    "messages": [
                        {
                            "role": "user",
                            "content": [
                                {"type": "text", "text": SYSTEM_PROMPT_QWEN},
                                {
                                    "type": "image_url",
                                    "image_url": {"url": f"data:image/jpeg;base64,{image_b64}"},
                                },
                            ],
                        }
                    ],
                },
            )
        else:
            resp = await client.post(
                "https://api.openai.com/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": model,
                    "max_tokens": 700,
                    "temperature": 0,
                    "messages": [
                        {
                            "role": "user",
                            "content": [
                                {"type": "text", "text": SYSTEM_PROMPT},
                                {
                                    "type": "image_url",
                                    "image_url": {
                                        "url": f"data:image/jpeg;base64,{image_b64}",
                                        "detail": "high",
                                    },
                                },
                            ],
                        }
                    ],
                },
            )
    except httpx.RequestError as exc:
        raise HTTPException(status_code=502, detail=f"Khong the ket noi toi OCR AI: {exc}") from exc

    if not resp.is_success:
        raise HTTPException(status_code=502, detail=f"OCR AI loi ({model}): {resp.text[:300]}")

    payload = resp.json()
    if is_gemini:
        try:
            raw_text = payload["candidates"][0]["content"]["parts"][0]["text"]
        except (KeyError, IndexError):
            raw_text = ""
    else:
        try:
            raw_text = payload["choices"][0]["message"]["content"]
        except (KeyError, IndexError):
            raw_text = ""

    parsed = parse_json_safe(raw_text)
    if isinstance(parsed, list) and parsed:
        return [item for item in parsed if isinstance(item, dict)] or [{"doc_type": "unknown", "data": {}}]
    if isinstance(parsed, dict):
        return [parsed]
    return [{"doc_type": "unknown", "data": {}}]


async def call_vision_images(items: list[dict[str, str]]) -> list[list[dict] | Exception]:
    model = _get_model()
    api_key = _get_api_key(model)
    if not api_key:
        raise HTTPException(status_code=500, detail=f"Server chua cau hinh khoa API cho model {model}")

    event_name = "qwen_call" if "qwen" in model.lower() else "vision_call"
    semaphore = asyncio.Semaphore(AI_CONCURRENCY)
    async with httpx.AsyncClient(timeout=AI_TIMEOUT_SECONDS) as client:
        async def worker(item: dict[str, str]):
            async with semaphore:
                filename = item.get("filename") or "unknown"
                t_start = perf_counter()
                try:
                    result = await _call_vision_single(
                        client,
                        model=model,
                        api_key=api_key,
                        image_b64=item["image_b64"],
                    )
                except Exception as exc:
                    detail = exc.detail if isinstance(exc, HTTPException) else str(exc)
                    _log_ocr_ai(
                        event_name,
                        level="warning",
                        filename=filename,
                        model=model,
                        latency_ms=_ms(perf_counter() - t_start),
                        status="error",
                        error=str(detail)[:300],
                    )
                    raise
                _log_ocr_ai(
                    event_name,
                    filename=filename,
                    model=model,
                    latency_ms=_ms(perf_counter() - t_start),
                    status="ok",
                    doc_count=len(result),
                )
                return result

        return await asyncio.gather(*(worker(item) for item in items), return_exceptions=True)


def _append_qr_person(
    *,
    persons: list[dict],
    raw_results: list[dict],
    filename: str,
    qr_text: str,
    qr_data: dict[str, Any],
) -> None:
    normalized = _normalize_person_data(qr_data)
    person = {
        **normalized,
        "_source": "QR",
        "source_type": "QR",
        "side": "unknown",
        "_files": [filename],
        "_qr": True,
        "field_sources": _field_sources(normalized, "qr"),
        "warnings": [],
        "_qr_text": qr_text,
    }
    persons.append(person)
    raw_results.append(
        {
            "doc_type": "person",
            "data": normalized,
            "filename": filename,
            "source_type": "QR",
            "side": "unknown",
            "field_sources": _field_sources(normalized, "qr"),
            "_qr": True,
        }
    )


def _append_ai_doc(
    *,
    doc: dict[str, Any],
    persons: list[dict],
    properties: list[dict],
    marriages: list[dict],
    raw_results: list[dict],
) -> None:
    raw_results.append({**doc, "source_type": "AI"})
    doc_type = doc.get("doc_type")
    data = doc.get("data") if isinstance(doc.get("data"), dict) else {}
    filename = doc.get("filename") or "unknown"

    if doc_type in {"person", "cccd_front", "cccd_back"}:
        side = doc.get("side", "unknown")
        persons.append(
            {
                **data,
                "_source": "AI",
                "source_type": "AI",
                "side": side,
                "_files": [filename],
                "_qr": False,
                "field_sources": dict(doc.get("field_sources") or _field_sources(_normalize_person_data(data), "ai")),
                "warnings": [],
            }
        )
        return

    if doc_type == "land_cert":
        properties.append(
            {
                "so_serial": data.get("so_serial", ""),
                "so_thua_dat": data.get("so_thua_dat", ""),
                "so_to_ban_do": data.get("so_to_ban_do", ""),
                "dia_chi": data.get("dia_chi_dat", ""),
                "loai_dat": data.get("loai_dat", ""),
                "ngay_cap": data.get("ngay_cap", ""),
                "co_quan_cap": data.get("co_quan_cap", ""),
                "_file": filename,
            }
        )
        return

    if doc_type == "marriage_cert":
        marriages.append(
            {
                "chong": {
                    "ho_ten": data.get("chong_ho_ten", ""),
                    "so_giay_to": data.get("chong_so_giay_to", ""),
                    "ngay_sinh": data.get("chong_ngay_sinh", ""),
                    "gioi_tinh": "Nam",
                    "dia_chi": "",
                },
                "vo": {
                    "ho_ten": data.get("vo_ho_ten", ""),
                    "so_giay_to": data.get("vo_so_giay_to", ""),
                    "ngay_sinh": data.get("vo_ngay_sinh", ""),
                    "gioi_tinh": "Nữ",
                    "dia_chi": "",
                },
                "ngay_dang_ky": data.get("ngay_dang_ky", ""),
                "noi_dang_ky": data.get("noi_dang_ky", ""),
                "_file": filename,
            }
        )


def _merge_cccd_pair_legacy_unused(group: list[dict]) -> dict:
    """Merge mang front+back cua cung 1 CCCD. Thu tu uu tien: QR > front > back."""
    front = next((p for p in group if p.get("side") == "front"), None)
    back = next((p for p in group if p.get("side") == "back"), None)
    qr_hit = next((p for p in group if p.get("source_type") == "QR"), None)

    base = dict(qr_hit or front or group[0])
    base["paired"] = True
    base["_files"] = [f for p in group for f in (p.get("_files") or [])]

    # Mat sau CCCD moi co "Noi cu tru" → ghi de dia_chi tren base neu base chua co
    if back:
        back_addr = (back.get("dia_chi") or "").strip()
        if back_addr and not (base.get("dia_chi") or "").strip():
            base["dia_chi"] = back_addr

    return base


def _pair_persons_legacy_unused(persons: list[dict]) -> list[dict]:
    """Ghep cap front+back theo so_giay_to 12 so. So khong hop le → giu nguyen, paired=False."""
    from collections import defaultdict

    groups: dict[str, list[dict]] = defaultdict(list)
    ungrouped: list[dict] = []

    for p in persons:
        id_no = re.sub(r"\D", "", p.get("so_giay_to") or "")
        if len(id_no) == 12:
            groups[id_no].append(p)
        else:
            ungrouped.append(p)

    result: list[dict] = []
    for group in groups.values():
        if len(group) == 1:
            group[0]["paired"] = False
            result.append(group[0])
        else:
            result.append(_merge_cccd_pair_legacy_unused(group))

    for p in ungrouped:
        p["paired"] = False
        result.append(p)

    return result


def _mark_unpaired_persons(persons: list[dict]) -> list[dict]:
    result: list[dict] = []
    for person in persons:
        current = dict(person)
        current["paired"] = False
        if not isinstance(current.get("_files"), list) or not current.get("_files"):
            current["_files"] = []
        result.append(current)
    return result


def _empty_person_data() -> dict[str, str]:
    return {
        "ho_ten": "",
        "so_giay_to": "",
        "ngay_sinh": "",
        "gioi_tinh": "",
        "dia_chi": "",
        "ngay_cap": "",
        "ngay_het_han": "",
    }


def _digits_only(value: Any) -> str:
    return re.sub(r"\D", "", str(value or ""))


def _valid_cccd_candidate(value: Any) -> str:
    digits = _digits_only(value)
    return digits if len(digits) == 12 else ""


def _count_vietnamese_diacritics(text: str) -> int:
    total = 0
    for ch in text or "":
        if ch in {"đ", "Đ"}:
            total += 1
            continue
        if any(unicodedata.combining(c) for c in unicodedata.normalize("NFD", ch)):
            total += 1
    return total


def _field_rank(field_name: str, source: str) -> int:
    return _FIELD_SOURCE_PRIORITY.get(field_name, {}).get(str(source or "").lower(), 0)


def _candidate_beats_current(
    field_name: str,
    incoming_val: str,
    incoming_source: str,
    current_val: str,
    current_source: str,
) -> bool:
    if not incoming_val:
        return False
    if not current_val:
        return True
    incoming_rank = _field_rank(field_name, incoming_source)
    current_rank = _field_rank(field_name, current_source)
    if incoming_rank > current_rank:
        return True
    if incoming_rank < current_rank:
        return False
    if field_name == "ho_ten":
        incoming_marks = _count_vietnamese_diacritics(incoming_val)
        current_marks = _count_vietnamese_diacritics(current_val)
        if incoming_marks != current_marks:
            return incoming_marks > current_marks
    return len(incoming_val) > len(current_val)


def _normalize_person_field(field_name: str, value: Any) -> str:
    if field_name == "so_giay_to":
        return _digits_only(value)
    if field_name in {"ngay_sinh", "ngay_cap"}:
        return _normalize_date(value)
    if field_name == "ngay_het_han":
        return _normalize_expiry_value(value)
    if field_name == "gioi_tinh":
        return _normalize_gender(value)
    return _clean_text(value)


def _merge_field_value(
    target_data: dict[str, str],
    field_sources: dict[str, str],
    *,
    field_name: str,
    value: Any,
    source: str,
) -> None:
    normalized = _normalize_person_field(field_name, value)
    if not normalized:
        return
    current_val = target_data.get(field_name, "")
    current_source = field_sources.get(field_name, "")
    if _candidate_beats_current(field_name, normalized, source, current_val, current_source):
        target_data[field_name] = normalized
        field_sources[field_name] = source


def _allowed_ai_fields_for_profile(profile: str) -> set[str]:
    if profile == DOC_PROFILE_FRONT_OLD:
        return {"ho_ten", "so_giay_to", "ngay_sinh", "gioi_tinh", "dia_chi", "ngay_het_han"}
    if profile == DOC_PROFILE_FRONT_NEW:
        return {"ho_ten", "so_giay_to", "ngay_sinh", "gioi_tinh"}
    if profile == DOC_PROFILE_BACK_NEW:
        return {"dia_chi", "ngay_cap", "ngay_het_han"}
    if profile == DOC_PROFILE_BACK_OLD:
        return {"ngay_cap"}
    return set(_empty_person_data().keys())


def _infer_profile_from_doc(doc: dict[str, Any]) -> str:
    if str(doc.get("source_type", "")).upper() == "QR":
        return DOC_PROFILE_UNKNOWN

    data = dict(doc.get("data") or {})
    doc_type = str(doc.get("doc_type") or "").lower()
    side = _normalize_text_space(data.get("doc_side") or doc.get("side", "")).lower()
    version = _normalize_text_space(data.get("doc_version", "")).lower()
    has_address = bool(_clean_text(data.get("dia_chi_back") or data.get("dia_chi")))
    has_mrz = bool(
        _validated_mrz_cccd(data)
        or _normalize_mrz_line(data.get("mrz_line1"))
        or _normalize_mrz_line(data.get("mrz_line2"))
        or _normalize_mrz_line(data.get("mrz_line3"))
    )
    has_identity = any(_clean_text(data.get(name)) for name in ("ho_ten", "so_giay_to", "ngay_sinh", "gioi_tinh"))

    if doc_type == "cccd_back" or side == "back":
        return DOC_PROFILE_BACK_NEW if version == "new" or has_address else DOC_PROFILE_BACK_OLD
    if doc_type == "cccd_front" or side == "front":
        return DOC_PROFILE_FRONT_OLD if version == "old" or bool(_clean_text(data.get("dia_chi"))) else DOC_PROFILE_FRONT_NEW
    if has_mrz:
        return DOC_PROFILE_BACK_NEW if has_address else DOC_PROFILE_BACK_OLD
    if has_identity:
        return DOC_PROFILE_FRONT_OLD if bool(_clean_text(data.get("dia_chi"))) else DOC_PROFILE_FRONT_NEW
    return DOC_PROFILE_UNKNOWN


def _derive_pair_key_from_doc(doc: dict[str, Any]) -> tuple[str, str]:
    data = dict(doc.get("data") or {})
    if str(doc.get("source_type", "")).upper() == "QR":
        qr_key = _valid_cccd_candidate(data.get("so_giay_to"))
        if qr_key:
            return qr_key, "qr"

    mrz_key = _validated_mrz_cccd(data)
    if mrz_key:
        return mrz_key, "mrz"

    ai_key = _valid_cccd_candidate(data.get("so_giay_to"))
    if ai_key:
        return ai_key, "ai"
    return "", ""


def _doc_signature(data: dict[str, Any]) -> tuple[str, str]:
    return (_ascii_fold(_clean_text(data.get("ho_ten", ""))).lower(), _normalize_date(data.get("ngay_sinh", "")))


def _derive_pair_hint_from_doc(doc: dict[str, Any]) -> str:
    data = dict(doc.get("data") or {})
    valid_candidate = (
        _valid_cccd_candidate(data.get("so_giay_to"))
        or _valid_cccd_candidate(data.get("so_giay_to_mrz"))
        or _extract_cccd_from_mrz_lines(data.get("mrz_line1"), data.get("mrz_line2"), data.get("mrz_line3"))
    )
    if valid_candidate:
        return valid_candidate

    mrz_digits = _digits_only(data.get("so_giay_to_mrz"))
    if mrz_digits:
        return mrz_digits

    ai_digits = _digits_only(data.get("so_giay_to"))
    if ai_digits:
        return ai_digits

    line1_digits = _digits_only(data.get("mrz_line1"))
    if line1_digits:
        return line1_digits

    line_candidates = _extract_digit_candidates(data.get("mrz_line2"), data.get("mrz_line3"))
    return max(line_candidates, key=len, default="")


def _digit_overlap_score(left: str, right: str) -> int:
    left_digits = _digits_only(left)
    right_digits = _digits_only(right)
    if not left_digits or not right_digits:
        return 0
    shorter, longer = (left_digits, right_digits)
    if len(shorter) > len(longer):
        shorter, longer = longer, shorter
    for size in range(len(shorter), 0, -1):
        for start in range(0, len(shorter) - size + 1):
            chunk = shorter[start : start + size]
            if chunk and chunk in longer:
                return size
    return 0


def _merge_group_into(target: dict[str, Any], source: dict[str, Any]) -> None:
    for field_name in _empty_person_data():
        source_value = source["data"].get(field_name, "")
        source_kind = source["field_sources"].get(field_name, "")
        if source_value and source_kind:
            _merge_field_value(target["data"], target["field_sources"], field_name=field_name, value=source_value, source=source_kind)
    target["profiles"].update(source["profiles"])
    target["has_qr"] = target["has_qr"] or source["has_qr"]
    target["pair_key"] = target["pair_key"] or source["pair_key"]
    target["pair_key_source"] = target["pair_key_source"] or source["pair_key_source"]
    if len(_digits_only(source.get("pair_hint", ""))) > len(_digits_only(target.get("pair_hint", ""))):
        target["pair_hint"] = source["pair_hint"]
    for filename in source["files"]:
        if filename not in target["files"]:
            target["files"].append(filename)


def _build_person_groups(raw_results: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], int]:
    groups: dict[str, dict[str, Any]] = {}
    order: list[str] = []

    for index, doc in enumerate(raw_results):
        if str(doc.get("doc_type") or "").lower() not in {"person", "cccd_front", "cccd_back"}:
            continue

        data = dict(doc.get("data") or {})
        if data.get("dia_chi_back") and not data.get("dia_chi"):
            data["dia_chi"] = data.get("dia_chi_back", "")

        profile = _infer_profile_from_doc({**doc, "data": data})
        pair_key, pair_key_source = _derive_pair_key_from_doc({**doc, "data": data})
        pair_hint = _derive_pair_hint_from_doc({**doc, "data": data})
        group_key = pair_key or f"img:{doc.get('filename', 'unknown')}:{index}"

        if group_key not in groups:
            groups[group_key] = {
                "data": _empty_person_data(),
                "field_sources": {},
                "profiles": set(),
                "files": [],
                "has_qr": False,
                "pair_key": pair_key,
                "pair_key_source": pair_key_source,
                "pair_hint": pair_hint,
            }
            order.append(group_key)

        group = groups[group_key]
        group["profiles"].add(profile)
        group["has_qr"] = group["has_qr"] or str(doc.get("source_type", "")).upper() == "QR"
        if pair_key and not group["pair_key"]:
            group["pair_key"] = pair_key
            group["pair_key_source"] = pair_key_source
        if len(_digits_only(pair_hint)) > len(_digits_only(group.get("pair_hint", ""))):
            group["pair_hint"] = pair_hint
        filename = str(doc.get("filename") or "unknown")
        if filename not in group["files"]:
            group["files"].append(filename)

        field_sources = dict(doc.get("field_sources") or {})
        source_type = "qr" if str(doc.get("source_type", "")).upper() == "QR" else "ai"
        allowed_ai_fields = _allowed_ai_fields_for_profile(profile)
        mrz_fields = _parse_mrz_fields(data)
        for field_name in _empty_person_data():
            if field_name == "so_giay_to":
                mrz_key = _validated_mrz_cccd(data)
                if mrz_key:
                    _merge_field_value(group["data"], group["field_sources"], field_name=field_name, value=mrz_key, source="mrz")
            if mrz_fields.get(field_name):
                _merge_field_value(group["data"], group["field_sources"], field_name=field_name, value=mrz_fields[field_name], source="mrz")
            if source_type != "qr" and field_name not in allowed_ai_fields:
                continue
            source = field_sources.get(field_name, source_type)
            if field_name == "dia_chi" and data.get("dia_chi_back"):
                source = "ai"
            _merge_field_value(group["data"], group["field_sources"], field_name=field_name, value=data.get(field_name, ""), source=source)

    keyed_keys = [key for key in order if len(_valid_cccd_candidate(key)) == 12]
    qr_keys = [key for key in order if groups[key]["has_qr"]]

    for key in list(order):
        source_group = groups.get(key)
        if not source_group or source_group["has_qr"]:
            continue
        name_sig, birth_sig = _doc_signature(source_group["data"])
        if not (name_sig and birth_sig):
            continue
        candidates = [
            candidate
            for candidate in qr_keys
            if candidate != key and _doc_signature(groups[candidate]["data"]) == (name_sig, birth_sig)
        ]
        if len(candidates) != 1:
            continue
        target_key = candidates[0]
        _merge_group_into(groups[target_key], source_group)
        if key in order:
            order.remove(key)
        if key in groups:
            del groups[key]

    keyed_keys = [key for key in order if len(_valid_cccd_candidate(key)) == 12]
    for key in list(order):
        if len(_valid_cccd_candidate(key)) != 12:
            continue
        source_group = groups.get(key)
        if not source_group:
            continue
        source_is_backish = bool(source_group["profiles"] & {DOC_PROFILE_BACK_NEW, DOC_PROFILE_BACK_OLD})
        if not source_is_backish:
            continue
        name_sig, birth_sig = _doc_signature(source_group["data"])
        if not (name_sig and birth_sig):
            continue
        candidates = [
            candidate
            for candidate in keyed_keys
            if candidate != key and _doc_signature(groups[candidate]["data"]) == (name_sig, birth_sig)
        ]
        if len(candidates) != 1:
            continue
        target_key = candidates[0]
        _merge_group_into(groups[target_key], source_group)
        if key in order:
            order.remove(key)
        if key in groups:
            del groups[key]

    keyed_keys = [key for key in order if len(_valid_cccd_candidate(key)) == 12]
    for key in list(order):
        if len(_valid_cccd_candidate(key)) == 12:
            continue
        source_group = groups.get(key)
        if not source_group:
            continue
        name_sig, birth_sig = _doc_signature(source_group["data"])
        candidates: list[str] = []
        if name_sig and birth_sig:
            candidates = [candidate for candidate in keyed_keys if _doc_signature(groups[candidate]["data"]) == (name_sig, birth_sig)]
        if not candidates and name_sig:
            source_is_backish = bool(source_group["profiles"] & {DOC_PROFILE_BACK_NEW, DOC_PROFILE_BACK_OLD})
            if source_is_backish:
                candidates = [
                    candidate
                    for candidate in keyed_keys
                    if _doc_signature(groups[candidate]["data"])[0] == name_sig
                ]
        if len(candidates) != 1:
            continue
        target_key = candidates[0]
        _merge_group_into(groups[target_key], source_group)
        order.remove(key)
        del groups[key]

    signature_pairs: dict[tuple[str, str], dict[str, list[str]]] = {}
    for key in order:
        if len(_valid_cccd_candidate(key)) == 12:
            continue
        group = groups.get(key)
        if not group:
            continue
        signature = _doc_signature(group["data"])
        if not all(signature):
            continue
        frontish = bool(group["profiles"] & {DOC_PROFILE_FRONT_OLD, DOC_PROFILE_FRONT_NEW})
        backish = bool(group["profiles"] & {DOC_PROFILE_BACK_OLD, DOC_PROFILE_BACK_NEW})
        if not (frontish or backish):
            continue
        bucket = signature_pairs.setdefault(signature, {"front": [], "back": []})
        if frontish:
            bucket["front"].append(key)
        if backish:
            bucket["back"].append(key)

    for bucket in signature_pairs.values():
        if len(bucket["front"]) != 1 or len(bucket["back"]) != 1:
            continue
        target_key = bucket["front"][0]
        source_key = bucket["back"][0]
        if target_key == source_key or target_key not in groups or source_key not in groups:
            continue
        _merge_group_into(groups[target_key], groups[source_key])
        if source_key in order:
            order.remove(source_key)
        del groups[source_key]

    keyed_keys = [key for key in order if len(_valid_cccd_candidate(key)) == 12]
    for key in list(order):
        if len(_valid_cccd_candidate(key)) == 12:
            continue
        source_group = groups.get(key)
        if not source_group:
            continue
        source_is_backish = bool(source_group["profiles"] & {DOC_PROFILE_BACK_NEW, DOC_PROFILE_BACK_OLD})
        if not source_is_backish:
            continue
        birth_sig = _doc_signature(source_group["data"])[1]
        pair_hint = _digits_only(source_group.get("pair_hint", ""))
        if not birth_sig or len(pair_hint) < 8:
            continue
        scored_candidates: list[tuple[int, str]] = []
        for candidate in keyed_keys:
            candidate_group = groups[candidate]
            if _doc_signature(candidate_group["data"])[1] != birth_sig:
                continue
            candidate_key = candidate_group.get("pair_key") or candidate_group["data"].get("so_giay_to", "")
            score = _digit_overlap_score(pair_hint, candidate_key)
            if score >= 8:
                scored_candidates.append((score, candidate))
        if not scored_candidates:
            continue
        best_score = max(score for score, _ in scored_candidates)
        best_candidates = [candidate for score, candidate in scored_candidates if score == best_score]
        if len(best_candidates) != 1:
            continue
        target_key = best_candidates[0]
        _merge_group_into(groups[target_key], source_group)
        order.remove(key)
        del groups[key]

    persons: list[dict[str, Any]] = []
    paired_count = 0
    for key in order:
        group = groups[key]
        front_present = bool(group["profiles"] & {DOC_PROFILE_FRONT_OLD, DOC_PROFILE_FRONT_NEW})
        back_present = bool(group["profiles"] & {DOC_PROFILE_BACK_OLD, DOC_PROFILE_BACK_NEW})
        paired = (front_present and back_present) or (group["has_qr"] and len(group["files"]) > 1)
        if paired:
            paired_count += 1

        side_label = "unknown"
        if DOC_PROFILE_BACK_NEW in group["profiles"]:
            side_label = _PROFILE_TO_SIDE_LABEL[DOC_PROFILE_BACK_NEW]
        elif DOC_PROFILE_BACK_OLD in group["profiles"]:
            side_label = _PROFILE_TO_SIDE_LABEL[DOC_PROFILE_BACK_OLD]
        elif DOC_PROFILE_FRONT_OLD in group["profiles"]:
            side_label = _PROFILE_TO_SIDE_LABEL[DOC_PROFILE_FRONT_OLD]
        elif DOC_PROFILE_FRONT_NEW in group["profiles"]:
            side_label = _PROFILE_TO_SIDE_LABEL[DOC_PROFILE_FRONT_NEW]

        final_key = _valid_cccd_candidate(group["pair_key"]) or _valid_cccd_candidate(group["data"].get("so_giay_to"))
        if final_key:
            group["data"]["so_giay_to"] = final_key
            if not group["field_sources"].get("so_giay_to"):
                group["field_sources"]["so_giay_to"] = group["pair_key_source"] or "ai"

        if paired:
            source_label = "cccd+back"
        elif back_present:
            source_label = "cccd_back only"
        else:
            source_label = "cccd (thiếu mặt sau)"

        persons.append(
            {
                "ho_ten": group["data"].get("ho_ten", ""),
                "so_giay_to": group["data"].get("so_giay_to", ""),
                "ngay_sinh": group["data"].get("ngay_sinh", ""),
                "gioi_tinh": group["data"].get("gioi_tinh", ""),
                "dia_chi": group["data"].get("dia_chi", ""),
                "ngay_cap": group["data"].get("ngay_cap", ""),
                "ngay_het_han": group["data"].get("ngay_het_han", ""),
                "_source": source_label,
                "source_type": "QR" if group["has_qr"] else "AI",
                "side": "unknown",
                "_side": side_label,
                "_qr": group["has_qr"],
                "_files": group["files"],
                "field_sources": group["field_sources"],
                "warnings": [],
                "paired": paired,
            }
        )

    return persons, paired_count


@router.post("/analyze")
async def analyze_images(files: List[UploadFile] = File(...)):
    if not files:
        raise HTTPException(status_code=400, detail="Chua co anh nao duoc gui len")

    t_total = perf_counter()
    persons: list[dict] = []
    properties: list[dict] = []
    marriages: list[dict] = []
    raw_results: list[dict] = []
    errors: list[dict] = []
    ai_inputs: list[dict[str, str]] = []
    qr_hits = 0
    qr_ms = 0.0
    prepare_ms = 0.0
    qwen_ms = 0.0

    model = _get_model()
    img_max_px = MAX_IMAGE_PX_QWEN if "qwen" in model.lower() else MAX_IMAGE_PX

    for upload in files:
        filename = upload.filename or "unknown"
        try:
            file_bytes = await upload.read()
            t_qr = perf_counter()
            qr_text = try_decode_qr(file_bytes) or ""
            qr_ms += perf_counter() - t_qr
            qr_data = parse_cccd_qr(qr_text) if qr_text else None
            if qr_data and qr_data.get("so_giay_to"):
                _append_qr_person(
                    persons=persons,
                    raw_results=raw_results,
                    filename=filename,
                    qr_text=qr_text,
                    qr_data=qr_data,
                )
                qr_hits += 1
                continue

            t_prepare = perf_counter()
            ai_inputs.append({"filename": filename, "image_b64": resize_to_base64(file_bytes, max_px=img_max_px)})
            prepare_ms += perf_counter() - t_prepare
        except Exception as exc:
            errors.append({"filename": filename, "error": str(exc)})

    if ai_inputs:
        t_qwen = perf_counter()
        ai_outputs = await call_vision_images(ai_inputs)
        qwen_ms = perf_counter() - t_qwen
        for item, output in zip(ai_inputs, ai_outputs):
            filename = item["filename"]
            if isinstance(output, Exception):
                if isinstance(output, HTTPException):
                    detail = output.detail
                else:
                    detail = str(output)
                errors.append({"filename": filename, "error": str(detail)})
                continue

            for raw_item in output:
                normalized = _normalize_ai_item(raw_item, filename)
                _append_ai_doc(
                    doc=normalized,
                    persons=persons,
                    properties=properties,
                    marriages=marriages,
                    raw_results=raw_results,
                )

    t_pair = perf_counter()
    persons, paired_count = _build_person_groups(raw_results)
    pair_ms = perf_counter() - t_pair
    unknowns = sum(1 for item in raw_results if item.get("doc_type") == "unknown")
    _log_ocr_ai(
        "ocr_ai_done",
        model=model,
        total_images=len(files),
        qr_hits=qr_hits,
        ai_runs=len(ai_inputs),
        total_ms=_ms(perf_counter() - t_total),
        qr_ms=_ms(qr_ms),
        prepare_ms=_ms(prepare_ms),
        qwen_ms=_ms(qwen_ms),
        pair_ms=_ms(pair_ms),
    )
    return {
        "persons": persons,
        "properties": properties,
        "marriages": marriages,
        "raw_results": raw_results,
        "errors": errors,
        "summary": {
            "total_images": len(files),
            "qr_hits": qr_hits,
            "ai_runs": len(ai_inputs),
            "model": model,
            "persons": len(persons),
            "paired_persons": paired_count,
            "properties": len(properties),
            "marriages": len(marriages),
            "unknowns": unknowns,
        },
    }


@router.get("/config")
async def ocr_config():
    model = _get_model()
    img_max_px = MAX_IMAGE_PX_QWEN if "qwen" in model.lower() else MAX_IMAGE_PX
    return {
        "configured": bool(_get_api_key(model)),
        "model": model,
        "max_image_px": img_max_px,
    }
