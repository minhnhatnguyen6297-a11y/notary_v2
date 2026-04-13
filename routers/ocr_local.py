"""
Local OCR V4:
1) Detect document crop and triage orientation
2) QR first for primary key
3) RapidOCR detection-only for text boxes
4) VietOCR batch recognition for Vietnamese text
"""

from __future__ import annotations

import io
import json
import logging
import os
import re
import shutil
import traceback
import unicodedata
import uuid
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from time import perf_counter
from typing import Any, Dict, Iterable, List, Optional, Tuple

from fastapi import APIRouter, Body, File, Form, HTTPException, UploadFile

_LOCAL_OCR_IMPORT_ERROR = None
try:
    import cv2
    import numpy as np
    from PIL import Image, ImageOps
except ImportError as exc:
    cv2 = None
    np = None
    Image = None
    ImageOps = None
    _LOCAL_OCR_IMPORT_ERROR = str(exc)

try:
    import torch
except ImportError as exc:
    torch = None
    if _LOCAL_OCR_IMPORT_ERROR is None:
        _LOCAL_OCR_IMPORT_ERROR = str(exc)
    else:
        _LOCAL_OCR_IMPORT_ERROR = f"{_LOCAL_OCR_IMPORT_ERROR}; {exc}"

try:
    import zxingcpp
except ImportError:
    zxingcpp = None

from database import SessionLocal
from models import ExtractedDocument, OCRJob

router = APIRouter()
_logger = logging.getLogger("ocr_local")

LOCAL_OCR_SMART_CROP_MIN_CONF = float(os.getenv("LOCAL_OCR_SMART_CROP_MIN_CONF", "0.22"))
LOCAL_OCR_TIMING_LOG = os.getenv("LOCAL_OCR_TIMING_LOG", "1").strip().lower() not in {"0", "false", "no", "off"}
LOCAL_OCR_TIMING_SLOW_MS = float(os.getenv("LOCAL_OCR_TIMING_SLOW_MS", "1500"))
LOCAL_OCR_DEBUG_LOG = os.getenv("LOCAL_OCR_DEBUG_LOG", "1").strip().lower() not in {"0", "false", "no", "off"}
LOCAL_OCR_DEBUG_MAX_BOX_LOG = max(1, int(os.getenv("LOCAL_OCR_DEBUG_MAX_BOX_LOG", "8")))
LOCAL_OCR_TRIAGE_PROXY_MAX_SIDE = int(os.getenv("LOCAL_OCR_TRIAGE_PROXY_MAX_SIDE", "720"))
LOCAL_OCR_TRIAGE_MRZ_MIN_SCORE = float(os.getenv("LOCAL_OCR_TRIAGE_MRZ_MIN_SCORE", "0.20"))
LOCAL_OCR_DET_MAX_SIDE_LEN = int(os.getenv("LOCAL_OCR_DET_MAX_SIDE_LEN", "3000"))
LOCAL_OCR_VIETOCR_MODEL = os.getenv("LOCAL_OCR_VIETOCR_MODEL", "vgg_transformer").strip() or "vgg_transformer"
LOCAL_OCR_VIETOCR_BATCH_SIZE = max(1, int(os.getenv("LOCAL_OCR_VIETOCR_BATCH_SIZE", "24")))
LOCAL_OCR_TORCH_THREADS = max(1, int(os.getenv("LOCAL_OCR_TORCH_THREADS", "2")))
LOCAL_OCR_DENOISE = os.getenv("LOCAL_OCR_DENOISE", "1").strip().lower() not in {"0", "false", "no", "off"}
LOCAL_OCR_REC_PAD_RATIO = max(0.0, float(os.getenv("LOCAL_OCR_REC_PAD_RATIO", "0.10")))
LOCAL_OCR_REC_MIN_HEIGHT = max(16, int(os.getenv("LOCAL_OCR_REC_MIN_HEIGHT", "48")))
LOCAL_OCR_REC_MAX_SCALE = max(1.0, float(os.getenv("LOCAL_OCR_REC_MAX_SCALE", "3.0")))

_rapidocr_detector = None
_vietocr_engine = None
_rapidocr_runtime_label = "RapidOCR det + VietOCR rec (CPU)"
_vietocr_rec_mode = LOCAL_OCR_VIETOCR_MODEL
_face_cascade = None
_qr_detector = None
_legacy_local_ocr_env_warned = False

DOC_PROFILE_FRONT_OLD = "cccd_front_old"
DOC_PROFILE_BACK_OLD = "cccd_back_old"
DOC_PROFILE_FRONT_NEW = "cccd_front_new"
DOC_PROFILE_BACK_NEW = "cccd_back_new"
DOC_PROFILE_UNKNOWN = "unknown"

TRIAGE_STATE_FRONT_OLD = "front_old"
TRIAGE_STATE_FRONT_NEW = "front_new"
TRIAGE_STATE_BACK_NEW = "back_new"
TRIAGE_STATE_BACK_OLD = "back_old"
TRIAGE_STATE_UNKNOWN = "unknown"

_PROFILE_PRIORITY = {
    DOC_PROFILE_FRONT_OLD: 4,
    DOC_PROFILE_FRONT_NEW: 3,
    DOC_PROFILE_BACK_NEW: 2,
    DOC_PROFILE_BACK_OLD: 1,
    DOC_PROFILE_UNKNOWN: 0,
}

_CRITICAL_WARNING_FIELDS = ("ho_ten", "so_giay_to", "ngay_sinh", "gioi_tinh", "dia_chi", "ngay_cap")
_PHASE_REQUIRED_FIELDS = {
    DOC_PROFILE_FRONT_OLD: ("so_giay_to", "ho_ten", "ngay_sinh", "gioi_tinh", "dia_chi"),
    DOC_PROFILE_FRONT_NEW: ("so_giay_to", "ho_ten", "ngay_sinh", "gioi_tinh"),
    DOC_PROFILE_BACK_NEW: ("so_giay_to", "ngay_cap", "dia_chi"),
    DOC_PROFILE_BACK_OLD: ("so_giay_to", "ngay_cap"),
    DOC_PROFILE_UNKNOWN: ("so_giay_to", "ho_ten", "ngay_sinh", "gioi_tinh", "ngay_cap"),
}
_ROI_PRESETS = {
    "id_front": (0.24, 0.16, 0.96, 0.46),
    "id_back": (0.05, 0.70, 0.98, 0.98),
    f"{TRIAGE_STATE_FRONT_OLD}:detail": (0.22, 0.20, 0.98, 0.92),
    f"{TRIAGE_STATE_FRONT_NEW}:detail": (0.22, 0.20, 0.98, 0.80),
    f"{TRIAGE_STATE_BACK_NEW}:detail": (0.06, 0.18, 0.98, 0.94),
    f"{TRIAGE_STATE_BACK_OLD}:detail": (0.06, 0.18, 0.98, 0.96),
    f"{TRIAGE_STATE_UNKNOWN}:detail": (0.08, 0.14, 0.98, 0.96),
}


@dataclass
class DocCrop:
    img_native: np.ndarray
    img_ocr: np.ndarray
    bbox: Tuple[int, int, int, int]
    doc_type: str
    confidence: float


def _ms(seconds: float) -> float:
    return round(max(0.0, float(seconds)) * 1000.0, 2)


def _log_timing(event: str, level: str = "info", **fields) -> None:
    if not LOCAL_OCR_TIMING_LOG:
        return
    payload = {"event": event, **fields}
    try:
        message = json.dumps(payload, ensure_ascii=False, default=str)
    except Exception:
        message = str(payload)
    if level == "warning":
        _logger.warning("[OCR_LOCAL_TIMING] %s", message)
    else:
        _logger.info("[OCR_LOCAL_TIMING] %s", message)


def _zxing_decode_qr_local(image_obj) -> str | None:
    if zxingcpp is None:
        return None
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


def _cv_to_pil_gray_local(gray_img):
    if Image is None or cv2 is None:
        return None
    try:
        if gray_img.ndim == 2:
            return Image.fromarray(gray_img)
        rgb = cv2.cvtColor(gray_img, cv2.COLOR_BGR2RGB)
        return Image.fromarray(rgb)
    except Exception:
        return None


def _qr_variants_local(file_bytes: bytes) -> list[Image.Image]:
    variants: list[Image.Image] = []
    if Image is None:
        return variants
    try:
        pil_img = Image.open(io.BytesIO(file_bytes))
        pil_img = ImageOps.exif_transpose(pil_img)
        if pil_img.mode not in ("RGB", "L"):
            pil_img = pil_img.convert("RGB")
        variants.append(pil_img)
    except Exception:
        pass

    if cv2 is None or np is None:
        return variants

    try:
        arr = np.frombuffer(file_bytes, dtype=np.uint8)
        img_bgr = cv2.imdecode(arr, cv2.IMREAD_COLOR)
        if img_bgr is None:
            return variants

        gray = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY)
        h, w = gray.shape[:2]
        scale = 2.0
        nw, nh = int(w * scale), int(h * scale)
        if nw <= 2600 and nh <= 2600:
            upscaled = cv2.resize(gray, (nw, nh), interpolation=cv2.INTER_CUBIC)
            pil_var = _cv_to_pil_gray_local(upscaled)
            if pil_var is not None:
                variants.append(pil_var)
            base_for_thresh = upscaled
        else:
            base_for_thresh = gray

        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8)).apply(base_for_thresh)
        sharpen = cv2.filter2D(
            clahe,
            -1,
            np.array([[0, -1, 0], [-1, 5, -1], [0, -1, 0]], dtype=np.float32),
        )
        adaptive = cv2.adaptiveThreshold(
            sharpen,
            255,
            cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
            cv2.THRESH_BINARY,
            31,
            7,
        )
        pil_var = _cv_to_pil_gray_local(adaptive)
        if pil_var is not None:
            variants.append(pil_var)
    except Exception:
        pass

    return variants


def try_decode_qr(file_bytes: bytes) -> str | None:
    for candidate in _qr_variants_local(file_bytes):
        decoded = _zxing_decode_qr_local(candidate)
        if decoded:
            return decoded

    if cv2 is None or np is None:
        return None

    detector = _get_qr_detector()
    if detector is None:
        return None

    try:
        arr = np.frombuffer(file_bytes, dtype=np.uint8)
        img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
        if img is None:
            return None
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        decoded, _, _ = detector.detectAndDecode(gray)
        if decoded:
            return decoded.strip()
    except Exception:
        pass
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


def _log_debug(event: str, level: str = "info", **fields) -> None:
    if not LOCAL_OCR_DEBUG_LOG:
        return
    payload = {"event": event, **fields}
    try:
        message = json.dumps(payload, ensure_ascii=False, default=str)
    except Exception:
        message = str(payload)
    if level == "warning":
        _logger.warning("[OCR_LOCAL_DEBUG] %s", message)
    else:
        _logger.info("[OCR_LOCAL_DEBUG] %s", message)


def _ensure_local_ocr_dependencies() -> None:
    if _LOCAL_OCR_IMPORT_ERROR:
        raise HTTPException(
            status_code=503,
            detail=(
                "Local OCR chua duoc cai dat day du. "
                "Local: chay run.bat. VPS: bash install_vps.sh. "
                f"Chi tiet: {_LOCAL_OCR_IMPORT_ERROR}"
            ),
        )


def _warn_legacy_local_ocr_env() -> None:
    global _legacy_local_ocr_env_warned
    if _legacy_local_ocr_env_warned:
        return
    legacy_keys = [key for key in ("LOCAL_OCR_REC_MODEL_PATH", "LOCAL_OCR_REC_KEYS_PATH") if os.getenv(key)]
    if not legacy_keys:
        return
    _legacy_local_ocr_env_warned = True
    _logger.warning(
        "Legacy RapidOCR recognition env vars are set but ignored by OCR V4 pipeline: %s. Current recognizer uses VietOCR model '%s'.",
        ", ".join(legacy_keys),
        LOCAL_OCR_VIETOCR_MODEL,
    )


def _ascii_fold(text: str) -> str:
    text = unicodedata.normalize("NFKD", text or "")
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return text.replace("đ", "d").replace("Đ", "D")


def _normalize_ocr_line(text: str) -> str:
    folded = _ascii_fold(text or "").lower()
    folded = re.sub(r"[^a-z0-9:/<\\-]+", " ", folded)
    return re.sub(r"\s+", " ", folded).strip()


def _normalize_ocr_lines(lines: Iterable[str]) -> List[str]:
    return [_normalize_ocr_line(line) for line in lines if (line or "").strip()]


def _normalize_date(value: str) -> str:
    raw = (value or "").replace("-", "/").replace(".", "/")
    match = re.search(r"(?<!\d)(\d{1,2})/(\d{1,2})/(\d{4})(?!\d)", raw)
    if not match:
        return ""
    dd = int(match.group(1))
    mm = int(match.group(2))
    yyyy = int(match.group(3))
    if not (1 <= dd <= 31 and 1 <= mm <= 12 and 1900 <= yyyy <= 2100):
        return ""
    return f"{dd:02d}/{mm:02d}/{yyyy:04d}"


def _count_vietnamese_diacritics(text: str) -> int:
    total = 0
    for ch in text or "":
        if ch in {"đ", "Đ"}:
            total += 1
            continue
        if any(unicodedata.combining(c) for c in unicodedata.normalize("NFD", ch)):
            total += 1
    return total


def _clean_doc_number(value: str) -> str:
    return re.sub(r"\D", "", str(value or ""))


def _clean_name_candidate(text: str) -> str:
    cleaned = re.sub(r"(?i)\b(ho\s*(va)?\s*ten|full\s*name)\b", " ", text or "")
    cleaned = cleaned.replace("<", " ")
    cleaned = re.sub(r"[^0-9A-Za-zÀ-ỹà-ỹ\s]", " ", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" .,:;-")
    return cleaned.upper()


def _is_likely_name(candidate: str) -> bool:
    if not candidate or re.search(r"\d", candidate):
        return False
    words = [word for word in candidate.split() if word]
    if not (2 <= len(words) <= 8):
        return False
    folded = _ascii_fold(candidate)
    return not re.search(
        r"\b(CONG HOA|SOCIALIST|CAN CUOC|CITIZEN|IDENTITY|GIOI TINH|SEX|"
        r"NOI THUONG TRU|NOI CU TRU|DATE OF|QUE QUAN|NATIONALITY|QUOC TICH)\b",
        folded,
        re.IGNORECASE,
    )


def _build_raw_text(lines: List[str]) -> str:
    return "\n".join([line for line in lines if line])


def _preview_text(text: str, limit: int = 180) -> str:
    cleaned = re.sub(r"\s+", " ", str(text or "")).strip()
    if len(cleaned) <= limit:
        return cleaned
    return f"{cleaned[: max(0, limit - 3)]}..."


def _numeric_stats(values: Iterable[float], digits: int = 2) -> dict:
    nums = sorted(float(value) for value in values if value is not None)
    if not nums:
        return {}
    mid = len(nums) // 2
    median = nums[mid] if len(nums) % 2 else (nums[mid - 1] + nums[mid]) / 2.0
    return {
        "count": len(nums),
        "min": round(nums[0], digits),
        "median": round(median, digits),
        "max": round(nums[-1], digits),
    }


def _print_rapidocr_raw_text(raw_text: str, context: str = "") -> None:
    text = (raw_text or "").strip()
    if not text:
        return
    _log_debug(
        "raw_text",
        context=context,
        line_count=len([line for line in text.splitlines() if line.strip()]),
        raw_text=text,
        preview=_preview_text(text, limit=320),
    )


def _safe_filename(filename: str, index: int) -> str:
    base = os.path.basename(filename or f"image_{index + 1}.jpg")
    base = re.sub(r"[^A-Za-z0-9._-]+", "_", base).strip("._")
    if not base:
        base = f"image_{index + 1}.jpg"
    return base


def _empty_person_data() -> dict:
    return {
        "so_giay_to": "",
        "ho_ten": "",
        "ngay_sinh": "",
        "gioi_tinh": "",
        "dia_chi": "",
        "ngay_cap": "",
        "ngay_het_han": "",
    }


def _build_qr_person_data(qr_data: dict) -> dict:
    return {
        "so_giay_to": qr_data.get("so_giay_to", ""),
        "ho_ten": (qr_data.get("ho_ten", "") or "").strip(),
        "ngay_sinh": qr_data.get("ngay_sinh", ""),
        "gioi_tinh": qr_data.get("gioi_tinh", ""),
        "dia_chi": qr_data.get("dia_chi", ""),
        "ngay_cap": qr_data.get("ngay_cap", ""),
        "ngay_het_han": qr_data.get("ngay_het_han", ""),
    }


def _address_expected(profile: str) -> bool:
    return profile in {DOC_PROFILE_FRONT_OLD, DOC_PROFILE_BACK_NEW}


def _collect_warnings(data: dict, profile: str = DOC_PROFILE_UNKNOWN) -> List[str]:
    warnings: List[str] = []
    for key in _CRITICAL_WARNING_FIELDS:
        if key == "dia_chi" and not _address_expected(profile):
            continue
        if not (data.get(key) or "").strip():
            warnings.append(key)
    ho_ten = (data.get("ho_ten") or "").strip()
    if ho_ten and _count_vietnamese_diacritics(ho_ten) < 2 and "ho_ten" not in warnings:
        warnings.append("ho_ten")
    return warnings


def _build_field_sources(source_type: str, data: dict) -> dict:
    tag = "qr" if str(source_type or "").upper() == "QR" else "ocr"
    out: Dict[str, str] = {}
    for key in ("ho_ten", "so_giay_to", "ngay_sinh", "gioi_tinh", "dia_chi", "ngay_cap"):
        if (data.get(key) or "").strip():
            out[key] = tag
    return out


def _infer_side(profile: str, doc_type: str = "unknown") -> str:
    if profile.startswith("cccd_front_"):
        return "front"
    if profile.startswith("cccd_back_"):
        return "back"
    if doc_type == "cccd_front":
        return "front"
    if doc_type == "cccd_back":
        return "back"
    return "unknown"


def _merge_side(current: str, incoming: str) -> str:
    cur = (current or "unknown").lower()
    inc = (incoming or "unknown").lower()
    if cur == "unknown":
        return inc
    if inc == "unknown":
        return cur
    if cur == inc:
        return cur
    if "front" in {cur, inc}:
        return "front"
    return cur


def _merge_profile(current: str, incoming: str) -> str:
    cur = current or DOC_PROFILE_UNKNOWN
    inc = incoming or DOC_PROFILE_UNKNOWN
    return inc if _PROFILE_PRIORITY.get(inc, 0) > _PROFILE_PRIORITY.get(cur, 0) else cur


def _merge_person_data(
    base_data: dict,
    incoming_data: dict,
    field_sources: dict,
    incoming_source_type: str,
    fill_missing_only: bool = False,
) -> None:
    source_tag = "qr" if str(incoming_source_type or "").upper() == "QR" else "ocr"
    for key in ("so_giay_to", "ho_ten", "ngay_sinh", "gioi_tinh", "dia_chi", "ngay_cap", "ngay_het_han"):
        incoming_val = (incoming_data.get(key) or "").strip() if isinstance(incoming_data.get(key), str) else incoming_data.get(key)
        if not incoming_val:
            continue
        current_val = (base_data.get(key) or "").strip() if isinstance(base_data.get(key), str) else base_data.get(key)
        current_source = field_sources.get(key, "")
        if source_tag == "qr":
            base_data[key] = incoming_val
            field_sources[key] = "qr"
            continue
        if not current_val:
            base_data[key] = incoming_val
            field_sources[key] = source_tag
            continue
        if fill_missing_only or current_source == "qr":
            continue
        if key == "ho_ten":
            cur_marks = _count_vietnamese_diacritics(str(current_val))
            in_marks = _count_vietnamese_diacritics(str(incoming_val))
            if in_marks > cur_marks or (in_marks == cur_marks and len(str(incoming_val)) > len(str(current_val)) + 2):
                base_data[key] = incoming_val
                field_sources[key] = source_tag
            continue
        if key == "dia_chi":
            if len(str(incoming_val)) > len(str(current_val)):
                base_data[key] = incoming_val
                field_sources[key] = source_tag
            continue
        if key == "ngay_cap":
            if not _normalize_date(str(current_val)) and _normalize_date(str(incoming_val)):
                base_data[key] = incoming_val
                field_sources[key] = source_tag
            continue
        if key == "so_giay_to":
            if len(_clean_doc_number(str(incoming_val))) == 12:
                base_data[key] = incoming_val
                field_sources[key] = source_tag
            continue


def _apply_delta_merge(merged_data: dict, records: List[dict]) -> None:
    if not records:
        return

    name_candidates = []
    addr_candidates = []
    issue_candidates = []
    for rec in records:
        src = str(rec.get("source_type", "OCR")).upper()
        side = rec.get("side", "unknown")
        profile = rec.get("profile", DOC_PROFILE_UNKNOWN)
        data = rec.get("data", {}) or {}
        source_rank = 2 if src == "QR" else 1
        front_rank = 2 if side == "front" else 1
        if (data.get("ho_ten") or "").strip():
            name_candidates.append((source_rank, front_rank, _count_vietnamese_diacritics(data["ho_ten"]), len(data["ho_ten"]), data["ho_ten"]))
        if (data.get("dia_chi") or "").strip() and profile in {DOC_PROFILE_FRONT_OLD, DOC_PROFILE_BACK_NEW}:
            addr_candidates.append((source_rank, len(data["dia_chi"]), data["dia_chi"]))
        if (data.get("ngay_cap") or "").strip():
            issue_candidates.append((2 if side == "back" else 1, source_rank, data["ngay_cap"]))

    if name_candidates:
        name_candidates.sort(reverse=True)
        merged_data["ho_ten"] = name_candidates[0][4]
    if addr_candidates:
        addr_candidates.sort(reverse=True)
        merged_data["dia_chi"] = addr_candidates[0][2]
    if issue_candidates:
        issue_candidates.sort(reverse=True)
        merged_data["ngay_cap"] = issue_candidates[0][2]


def _append_person_raw_text(record: dict, raw_text: str, filename: str = "") -> None:
    text = (raw_text or "").strip()
    if not text:
        return
    if filename:
        text = f"[{filename}]\n{text}"
    raw_texts = record.setdefault("raw_texts", [])
    if text not in raw_texts:
        raw_texts.append(text)


def _should_run_detail_phase(person_data: dict, profile: str) -> bool:
    required = _PHASE_REQUIRED_FIELDS.get(profile or DOC_PROFILE_UNKNOWN, _PHASE_REQUIRED_FIELDS[DOC_PROFILE_UNKNOWN])
    return any(not (person_data.get(key) or "").strip() for key in required)


def _normalize_qr_texts(qr_texts: Optional[List[str]], total: int) -> List[str]:
    out = ["" for _ in range(total)]
    if not isinstance(qr_texts, list):
        return out
    for index in range(min(total, len(qr_texts))):
        out[index] = str(qr_texts[index] or "").strip()
    return out


def _normalize_qr_failed_flags(flags: Optional[List[Any]], total: int) -> List[bool]:
    out = [False for _ in range(total)]
    if not isinstance(flags, list):
        return out
    for index in range(min(total, len(flags))):
        value = flags[index]
        if isinstance(value, bool):
            out[index] = value
        elif isinstance(value, str):
            out[index] = value.strip().lower() in {"1", "true", "yes", "y"}
        else:
            out[index] = bool(value)
    return out


def _is_valid_qr_data(qr_data: Optional[dict]) -> bool:
    if not qr_data:
        return False
    cccd = re.sub(r"\D", "", str(qr_data.get("so_giay_to") or ""))
    if len(cccd) != 12:
        return False
    signals = 0
    for key in ("ho_ten", "ngay_sinh", "gioi_tinh"):
        if (qr_data.get(key) or "").strip():
            signals += 1
    return signals >= 2


def _get_rapidocr_engine():
    _ensure_local_ocr_dependencies()
    global _rapidocr_detector
    if _rapidocr_detector is not None:
        return _rapidocr_detector

    t_start = perf_counter()
    try:
        import yaml
        import rapidocr_onnxruntime
        from rapidocr_onnxruntime.ch_ppocr_det import TextDetector
    except ImportError:
        raise HTTPException(
            status_code=500,
            detail="Chua cai RapidOCR detector. Local: chay run.bat; VPS: bash install_vps.sh",
        )

    try:
        cfg_path = Path(rapidocr_onnxruntime.__file__).with_name("config.yaml")
        config = yaml.safe_load(cfg_path.read_text(encoding="utf-8"))
        det_cfg = dict(config.get("Det", {}))
        model_path = Path(str(det_cfg.get("model_path", "")))
        if model_path and not model_path.is_absolute():
            det_cfg["model_path"] = str((cfg_path.parent / model_path).resolve())
        det_cfg["limit_side_len"] = LOCAL_OCR_DET_MAX_SIDE_LEN
        det_cfg["limit_type"] = "max"
        det_cfg["use_cuda"] = False
        det_cfg["use_dml"] = False
        det_cfg["intra_op_num_threads"] = LOCAL_OCR_TORCH_THREADS
        det_cfg["inter_op_num_threads"] = 1
        _rapidocr_detector = TextDetector(det_cfg)
        _log_timing(
            "engine_init",
            ms=_ms(perf_counter() - t_start),
            runtime=_rapidocr_runtime_label,
            rec_model_mode=_vietocr_rec_mode,
        )
        return _rapidocr_detector
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Khong the khoi dong RapidOCR detector: {exc}")


def _get_vietocr_engine():
    _ensure_local_ocr_dependencies()
    _warn_legacy_local_ocr_env()
    global _vietocr_engine
    if _vietocr_engine is not None:
        return _vietocr_engine

    try:
        from vietocr.tool.config import Cfg
        from vietocr.tool.predictor import Predictor
    except ImportError:
        raise HTTPException(
            status_code=500,
            detail="Chua cai VietOCR. Local: chay run.bat; VPS: bash install_vps.sh",
        )

    try:
        torch.set_num_threads(LOCAL_OCR_TORCH_THREADS)
        torch.set_num_interop_threads(1)
    except Exception:
        pass

    try:
        config = Cfg.load_config_from_name(LOCAL_OCR_VIETOCR_MODEL)
        config["device"] = "cpu"
        predictor_cfg = config.get("predictor")
        if isinstance(predictor_cfg, dict):
            predictor_cfg["beamsearch"] = False
        _vietocr_engine = Predictor(config)
        return _vietocr_engine
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Khong the khoi dong VietOCR: {exc}")


_rapidocr_recognizer = None

def _get_rapidocr_recognizer():
    _ensure_local_ocr_dependencies()
    global _rapidocr_recognizer
    if _rapidocr_recognizer is not None:
        return _rapidocr_recognizer

    t_start = perf_counter()
    try:
        import yaml
        import rapidocr_onnxruntime
        from rapidocr_onnxruntime.ch_ppocr_rec import TextRecognizer
    except ImportError:
        raise HTTPException(status_code=500, detail="Chua cai RapidOCR recognizer")

    try:
        cfg_path = Path(rapidocr_onnxruntime.__file__).with_name("config.yaml")
        config = yaml.safe_load(cfg_path.read_text(encoding="utf-8"))
        rec_cfg = dict(config.get("Rec", {}))
        model_path = Path(str(rec_cfg.get("model_path", "")))
        if model_path and not model_path.is_absolute():
            rec_cfg["model_path"] = str((cfg_path.parent / model_path).resolve())
        rec_cfg["use_cuda"] = False
        rec_cfg["use_dml"] = False
        rec_cfg["intra_op_num_threads"] = LOCAL_OCR_TORCH_THREADS
        rec_cfg["inter_op_num_threads"] = 1
        _rapidocr_recognizer = TextRecognizer(rec_cfg)
        _log_timing("engine_init_rec", ms=_ms(perf_counter() - t_start))
        return _rapidocr_recognizer
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Khong khoi dong duoc RapidOCR recognizer: {exc}")


def warmup_local_ocr() -> tuple[bool, str]:
    try:
        _ensure_local_ocr_dependencies()
        _get_rapidocr_engine()
        _get_vietocr_engine()
        return True, ""
    except Exception as exc:
        _logger.exception("Local OCR warmup failed: %s", exc)
        return False, str(exc)


def _preprocess(img_bgr: np.ndarray) -> np.ndarray:
    gray = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY)
    clahe = cv2.createCLAHE(clipLimit=2.2, tileGridSize=(8, 8))
    gray = clahe.apply(gray)
    if LOCAL_OCR_DENOISE:
        gray = cv2.fastNlMeansDenoising(gray, None, h=7, templateWindowSize=7, searchWindowSize=21)
    blur = cv2.GaussianBlur(gray, (0, 0), sigmaX=1.0)
    sharpened = cv2.addWeighted(gray, 1.6, blur, -0.6, 0)
    return cv2.cvtColor(sharpened, cv2.COLOR_GRAY2BGR)


def _opencv_smart_crop(img_bgr: np.ndarray) -> tuple[np.ndarray, Tuple[int, int, int, int], float] | None:
    h, w = img_bgr.shape[:2]
    img_area = float(max(1, h * w))
    gray = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY)
    blur = cv2.GaussianBlur(gray, (5, 5), 0)
    edges = cv2.Canny(blur, 50, 150)
    kernel = np.ones((3, 3), np.uint8)
    edges = cv2.dilate(edges, kernel, iterations=1)
    edges = cv2.morphologyEx(edges, cv2.MORPH_CLOSE, kernel, iterations=1)

    contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        return None

    best_bbox = None
    best_score = 0.0
    for contour in contours:
        area = float(cv2.contourArea(contour))
        if area < img_area * 0.06:
            continue
        x, y, bw, bh = cv2.boundingRect(contour)
        if bw < 40 or bh < 40:
            continue
        rect_area = float(max(1, bw * bh))
        fill_ratio = max(0.0, min(1.0, area / rect_area))
        ratio = bw / float(max(1, bh))
        ratio = ratio if ratio >= 1.0 else (1.0 / ratio)
        ratio_score = 1.0 - min(abs(ratio - 1.58), 1.58) / 1.58
        area_score = min(1.0, rect_area / img_area)
        score = (area_score * 0.45) + (ratio_score * 0.35) + (fill_ratio * 0.20)
        if score > best_score:
            best_score = score
            best_bbox = (x, y, x + bw, y + bh)

    if best_bbox is None:
        return None

    x1, y1, x2, y2 = best_bbox
    pad_x = int((x2 - x1) * 0.03)
    pad_y = int((y2 - y1) * 0.03)
    x1 = max(0, x1 - pad_x)
    y1 = max(0, y1 - pad_y)
    x2 = min(w, x2 + pad_x)
    y2 = min(h, y2 + pad_y)
    if x2 <= x1 or y2 <= y1:
        return None
    crop = img_bgr[y1:y2, x1:x2]
    if crop is None or crop.size == 0:
        return None
    return crop, (x1, y1, x2, y2), float(best_score)


def _detect_documents(img_native: np.ndarray, img_ocr: np.ndarray) -> List[DocCrop]:
    h, w = img_native.shape[:2]
    full = DocCrop(
        img_native=img_native,
        img_ocr=img_ocr,
        bbox=(0, 0, w, h),
        doc_type="unknown",
        confidence=0.0,
    )
    try:
        smart = _opencv_smart_crop(img_native)
        if smart is None:
            return [full]
        _, bbox, confidence = smart
        if confidence < LOCAL_OCR_SMART_CROP_MIN_CONF:
            return [full]
        x1, y1, x2, y2 = bbox
        return [
            DocCrop(
                img_native=img_native[y1:y2, x1:x2],
                img_ocr=img_ocr[y1:y2, x1:x2],
                bbox=bbox,
                doc_type="unknown",
                confidence=confidence,
            )
        ]
    except Exception:
        return [full]


def _pick_primary_crop(crops: List[DocCrop]) -> DocCrop:
    if not crops:
        raise ValueError("Khong phat hien crop hop le")
    return max(
        crops,
        key=lambda crop: (
            float(crop.confidence or 0.0),
            max(1, (crop.bbox[2] - crop.bbox[0])) * max(1, (crop.bbox[3] - crop.bbox[1])),
        ),
    )


def _normalize_box_points(box) -> np.ndarray | None:
    if box is None:
        return None
    arr = np.array(box, dtype=np.float32)
    if arr.size == 4 and arr.ndim == 1:
        x1, y1, x2, y2 = arr.tolist()
        arr = np.array([[x1, y1], [x2, y1], [x2, y2], [x1, y2]], dtype=np.float32)
    if arr.ndim != 2 or arr.shape[1] != 2:
        return None
    if arr.shape[0] == 2:
        (x1, y1), (x2, y2) = arr.tolist()
        arr = np.array([[x1, y1], [x2, y1], [x2, y2], [x1, y2]], dtype=np.float32)
    return arr


def _iter_detected_boxes(raw_boxes) -> List[Any]:
    if raw_boxes is None:
        return []
    if isinstance(raw_boxes, np.ndarray):
        if raw_boxes.ndim == 2 and raw_boxes.shape[1] == 2:
            return [raw_boxes]
        if raw_boxes.ndim >= 3:
            return [raw_boxes[i] for i in range(raw_boxes.shape[0])]
        return []
    if isinstance(raw_boxes, (list, tuple)):
        return list(raw_boxes)
    try:
        return list(raw_boxes)
    except TypeError:
        return []


def _box_bounds(box: np.ndarray) -> Tuple[float, float, float, float]:
    xs = box[:, 0]
    ys = box[:, 1]
    return float(xs.min()), float(ys.min()), float(xs.max()), float(ys.max())


def _box_center_ratio(box: np.ndarray, img_shape: Tuple[int, int]) -> Tuple[float, float]:
    h, w = img_shape[:2]
    x1, y1, x2, y2 = _box_bounds(box)
    return ((x1 + x2) * 0.5 / max(1.0, float(w)), (y1 + y2) * 0.5 / max(1.0, float(h)))


def _box_area_ratio(box: np.ndarray, img_shape: Tuple[int, int]) -> float:
    h, w = img_shape[:2]
    x1, y1, x2, y2 = _box_bounds(box)
    return max(0.0, (x2 - x1) * (y2 - y1)) / float(max(1, h * w))


def _box_height_ratio(box: np.ndarray, img_shape: Tuple[int, int]) -> float:
    h = img_shape[0]
    _, y1, _, y2 = _box_bounds(box)
    return max(0.0, y2 - y1) / float(max(1, h))


def _sort_box_dicts(items: List[dict]) -> List[dict]:
    if not items:
        return []
    sortable = []
    for item in items:
        x1, y1, x2, y2 = _box_bounds(item["box"])
        sortable.append({"item": item, "x": x1, "y": y1, "h": max(1.0, y2 - y1)})
    sortable.sort(key=lambda row: (row["y"], row["x"]))
    median_h = sorted(row["h"] for row in sortable)[len(sortable) // 2]
    line_gap = max(10.0, median_h * 0.6)
    ordered: List[dict] = []
    current: List[dict] = []
    cur_y = None
    for row in sortable:
        if cur_y is None or abs(row["y"] - cur_y) <= line_gap:
            current.append(row)
            cur_y = row["y"] if cur_y is None else (cur_y + row["y"]) / 2
        else:
            current.sort(key=lambda value: value["x"])
            ordered.extend(value["item"] for value in current)
            current = [row]
            cur_y = row["y"]
    if current:
        current.sort(key=lambda value: value["x"])
        ordered.extend(value["item"] for value in current)
    return ordered


def _group_lines(items: List[dict]) -> List[str]:
    if not items:
        return []
    sortable = []
    for item in items:
        x1, y1, x2, y2 = _box_bounds(item["box"])
        sortable.append({"text": item["text"], "x": x1, "y": y1, "h": max(1.0, y2 - y1)})
    sortable.sort(key=lambda row: (row["y"], row["x"]))
    median_h = sorted(row["h"] for row in sortable)[len(sortable) // 2]
    line_gap = max(10.0, median_h * 0.6)
    lines: List[str] = []
    current: List[dict] = []
    cur_y = None
    for row in sortable:
        if cur_y is None or abs(row["y"] - cur_y) <= line_gap:
            current.append(row)
            cur_y = row["y"] if cur_y is None else (cur_y + row["y"]) / 2
        else:
            current.sort(key=lambda value: value["x"])
            lines.append(" ".join(value["text"] for value in current if value["text"]).strip())
            current = [row]
            cur_y = row["y"]
    if current:
        current.sort(key=lambda value: value["x"])
        lines.append(" ".join(value["text"] for value in current if value["text"]).strip())
    return [line for line in lines if line]


def _order_box_points(box: np.ndarray) -> np.ndarray:
    points = np.array(box, dtype=np.float32)
    sums = points.sum(axis=1)
    diffs = np.diff(points, axis=1).reshape(-1)
    top_left = points[np.argmin(sums)]
    bottom_right = points[np.argmax(sums)]
    top_right = points[np.argmin(diffs)]
    bottom_left = points[np.argmax(diffs)]
    return np.array([top_left, top_right, bottom_right, bottom_left], dtype=np.float32)


def _prepare_recognition_crop(crop: np.ndarray) -> np.ndarray | None:
    if crop is None or crop.size == 0:
        return None
    h, w = crop.shape[:2]
    if h <= 0 or w <= 0:
        return None
    scale = min(LOCAL_OCR_REC_MAX_SCALE, max(1.0, LOCAL_OCR_REC_MIN_HEIGHT / float(max(1, h))))
    if scale > 1.01:
        crop = cv2.resize(crop, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)
    return crop


def _crop_box_image(img_bgr: np.ndarray, box: np.ndarray, pad_ratio: float = LOCAL_OCR_REC_PAD_RATIO) -> np.ndarray | None:
    box = _normalize_box_points(box)
    if box is None:
        return None
    ordered = _order_box_points(box)
    width_top = np.linalg.norm(ordered[1] - ordered[0])
    width_bottom = np.linalg.norm(ordered[2] - ordered[3])
    height_right = np.linalg.norm(ordered[2] - ordered[1])
    height_left = np.linalg.norm(ordered[3] - ordered[0])
    warp_w = int(round(max(width_top, width_bottom)))
    warp_h = int(round(max(height_right, height_left)))
    if warp_w >= 4 and warp_h >= 4:
        pad_x = int(round(warp_w * max(0.0, pad_ratio)))
        pad_y = int(round(warp_h * max(0.0, pad_ratio)))
        dst = np.array(
            [
                [pad_x, pad_y],
                [pad_x + warp_w - 1, pad_y],
                [pad_x + warp_w - 1, pad_y + warp_h - 1],
                [pad_x, pad_y + warp_h - 1],
            ],
            dtype=np.float32,
        )
        matrix = cv2.getPerspectiveTransform(ordered, dst)
        out_w = max(1, warp_w + pad_x * 2)
        out_h = max(1, warp_h + pad_y * 2)
        warped = cv2.warpPerspective(img_bgr, matrix, (out_w, out_h), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REPLICATE)
        return _prepare_recognition_crop(warped)

    x1, y1, x2, y2 = _box_bounds(box)
    pad_x = int((x2 - x1) * pad_ratio)
    pad_y = int((y2 - y1) * pad_ratio)
    x1 = max(0, int(x1) - pad_x)
    y1 = max(0, int(y1) - pad_y)
    x2 = min(img_bgr.shape[1], int(x2) + pad_x)
    y2 = min(img_bgr.shape[0], int(y2) + pad_y)
    if x2 <= x1 or y2 <= y1:
        return None
    crop = img_bgr[y1:y2, x1:x2]
    if crop is None or crop.size == 0:
        return None
    return _prepare_recognition_crop(crop)


def _vietocr_predict_batch(images: List[np.ndarray]) -> List[dict]:
    if not images:
        return []
    predictor = _get_vietocr_engine()
    pil_images = [Image.fromarray(cv2.cvtColor(img, cv2.COLOR_BGR2RGB)) for img in images]

    if hasattr(predictor, "predict_batch"):
        attempts = [
            {"batch_size": LOCAL_OCR_VIETOCR_BATCH_SIZE, "return_prob": True},
            {"return_prob": True},
            {"batch_size": LOCAL_OCR_VIETOCR_BATCH_SIZE, "return_prob": False},
            {"return_prob": False},
            {},
        ]
        raw_result = None
        for kwargs in attempts:
            try:
                raw_result = predictor.predict_batch(pil_images, **kwargs)
                break
            except TypeError:
                continue
        if raw_result is None:
            raise HTTPException(status_code=500, detail="Khong goi duoc VietOCR predict_batch")
    else:
        raw_result = [predictor.predict(image, return_prob=True) for image in pil_images]

    raw_texts = raw_result
    raw_probs: List[Any] = []
    if isinstance(raw_result, tuple):
        raw_texts = raw_result[0] if len(raw_result) >= 1 else []
        raw_probs = list(raw_result[1]) if len(raw_result) >= 2 and isinstance(raw_result[1], (list, tuple)) else []

    outputs: List[dict] = []
    for index, item in enumerate(raw_texts or []):
        score = raw_probs[index] if index < len(raw_probs) else None
        if isinstance(item, (list, tuple)) and item:
            text = item[0]
            if score is None and len(item) >= 2 and isinstance(item[1], (int, float)):
                score = item[1]
        else:
            text = item
        outputs.append(
            {
                "text": str(text or "").strip(),
                "score": round(float(score), 4) if isinstance(score, (int, float)) else None,
            }
        )
    return outputs


def _rapidocr_detect_boxes(img_bgr: np.ndarray) -> tuple[List[dict], float]:
    detector = _get_rapidocr_engine()
    boxes, elapsed = detector(img_bgr)
    out: List[dict] = []
    for box in _iter_detected_boxes(boxes):
        norm_box = _normalize_box_points(box)
        if norm_box is not None:
            out.append({"box": norm_box})
    return out, _ms(elapsed)


def filter_target_boxes(boxes: List[dict], img_shape: Tuple[int, int], triage_state: str, phase: str) -> List[dict]:
    if phase == "id":
        preset = _ROI_PRESETS["id_front"] if triage_state in {TRIAGE_STATE_FRONT_OLD, TRIAGE_STATE_FRONT_NEW} else _ROI_PRESETS["id_back"]
    elif phase == "id_front":
        preset = _ROI_PRESETS["id_front"]
    elif phase == "id_back":
        preset = _ROI_PRESETS["id_back"]
    else:
        preset = _ROI_PRESETS.get(f"{triage_state}:detail", _ROI_PRESETS[f"{TRIAGE_STATE_UNKNOWN}:detail"])

    x_min, y_min, x_max, y_max = preset
    filtered: List[dict] = []
    for item in boxes or []:
        box = item.get("box")
        if box is None:
            continue
        center_x, center_y = _box_center_ratio(box, img_shape)
        if not (x_min <= center_x <= x_max and y_min <= center_y <= y_max):
            continue
        if _box_area_ratio(box, img_shape) < 0.0008:
            continue
        if _box_height_ratio(box, img_shape) < 0.018:
            continue
        if center_x <= 0.02 or center_x >= 0.98 or center_y <= 0.02 or center_y >= 0.98:
            continue
        filtered.append({"box": box})
    return _sort_box_dicts(filtered)


def _recognize_target_boxes(img_ocr: np.ndarray, boxes: List[dict], context: str = "") -> tuple[List[dict], float]:
    if not boxes:
        return [], 0.0

    t_start = perf_counter()
    crops: List[np.ndarray] = []
    valid_boxes: List[dict] = []
    crop_shapes: List[Tuple[int, int]] = []
    for item in boxes:
        crop = _crop_box_image(img_ocr, item["box"])
        if crop is None:
            continue
        valid_boxes.append(item)
        crops.append(crop)
        crop_shapes.append((int(crop.shape[1]), int(crop.shape[0])))

    texts: List[dict] = []
    for start in range(0, len(crops), LOCAL_OCR_VIETOCR_BATCH_SIZE):
        texts.extend(_vietocr_predict_batch(crops[start:start + LOCAL_OCR_VIETOCR_BATCH_SIZE]))

    recognized: List[dict] = []
    debug_samples: List[dict] = []
    for index, (item, output) in enumerate(zip(valid_boxes, texts)):
        text = str((output or {}).get("text") or "").strip()
        score = (output or {}).get("score")
        if text:
            recognized.append({"box": item["box"], "text": text, "score": 0.0 if score is None else float(score)})
        if index < LOCAL_OCR_DEBUG_MAX_BOX_LOG:
            width, height = crop_shapes[index] if index < len(crop_shapes) else (0, 0)
            debug_samples.append(
                {
                    "index": index,
                    "crop_size": f"{width}x{height}",
                    "score": score,
                    "diacritics": _count_vietnamese_diacritics(text),
                    "text": _preview_text(text, limit=140),
                }
            )

    elapsed_ms = _ms(perf_counter() - t_start)
    _log_debug(
        "recognize_boxes",
        context=context,
        requested_box_count=len(boxes),
        valid_crop_count=len(crops),
        recognized_count=len(recognized),
        crop_width_stats=_numeric_stats(width for width, _ in crop_shapes),
        crop_height_stats=_numeric_stats(height for _, height in crop_shapes),
        score_stats=_numeric_stats(item.get("score") for item in texts if isinstance(item.get("score"), (int, float))),
        elapsed_ms=elapsed_ms,
        samples=debug_samples,
    )
    return recognized, elapsed_ms

def _recognize_target_boxes_rapidocr(img_ocr: np.ndarray, boxes: List[dict], context: str = "") -> tuple[List[dict], float]:
    if not boxes:
        return [], 0.0

    t_start = perf_counter()
    recognizer = _get_rapidocr_recognizer()
    valid_boxes = []
    crops = []
    for item in boxes:
        crop = _crop_box_image(img_ocr, item["box"])
        if crop is not None:
            valid_boxes.append(item)
            crops.append(crop)

    recognized = []
    if crops:
        for idx, crop in enumerate(crops):
            try:
                res, _ = recognizer(crop)
                if res and res[0] and res[0][0]:
                    text, score = res[0][0], res[0][1]
                    if str(text).strip():
                        recognized.append({"box": valid_boxes[idx]["box"], "text": str(text).strip(), "score": float(score)})
            except Exception:
                pass

    elapsed_ms = _ms(perf_counter() - t_start)
    return recognized, elapsed_ms



def _extract_id_12_from_text(text: str) -> str:
    if not text:
        return ""
    if match := re.search(r"(?<!\d)(\d{12})(?!\d)", text):
        return match.group(1)
    digits = re.sub(r"\D", "", text)
    if len(digits) >= 12:
        return digits[:12]
    return ""


def _extract_id_12_from_mrz_text(text: str) -> str:
    normalized = re.sub(r"\s+", "", _ascii_fold(text or "").upper())
    if not normalized:
        return ""
    if match := re.search(r"IDVNM\d{10}(\d{12})", normalized):
        return match.group(1)
    if match := re.search(r"IDVNM(?:\d|<){0,18}(\d{12})", normalized):
        return match.group(1)
    if match := re.search(r"(\d{12})<<\d", normalized):
        return match.group(1)
    return ""


def _extract_dates(text: str) -> List[str]:
    matches = re.findall(r"\d{1,2}[./-]\d{1,2}[./-]\d{4}", text or "")
    dates: List[str] = []
    for match in matches:
        normalized = _normalize_date(match)
        if normalized and normalized not in dates:
            dates.append(normalized)
    return dates


def _extract_anchor_block(full_text: str, label_pattern: str, stop_pattern: str) -> str:
    pattern = rf"(?:{label_pattern})\s*[:\-]?\s*([\s\S]+?)(?=(?:{stop_pattern})\s*[:\-]?|$)"
    match = re.search(pattern, full_text or "", flags=re.IGNORECASE)
    if not match:
        return ""
    block = match.group(1)
    parts = [re.sub(r"\s+", " ", part).strip(" .,:;-") for part in re.split(r"[\r\n]+", block) if part.strip()]
    return ", ".join(part for part in parts if part)


def _extract_date_after_label(full_text: str, label_pattern: str) -> str:
    pattern = rf"(?:{label_pattern})[\s:;\-]*([\s\S]{{0,48}})"
    match = re.search(pattern, full_text or "", flags=re.IGNORECASE)
    if not match:
        return ""
    return _normalize_date(match.group(1))


def _extract_gender_from_text(full_text: str) -> str:
    match = re.search(r"(gioi\s*tinh|sex)\s*[:\-]?\s*([^\n\r]{0,30})", full_text or "", flags=re.IGNORECASE)
    candidate = match.group(2) if match else (full_text or "")
    folded = _ascii_fold(candidate).lower()
    if re.search(r"\bnu\b|\bfemale\b", folded):
        return "Nữ"
    if re.search(r"\bnam\b|\bmale\b", folded):
        return "Nam"
    return ""


def _is_back_profile(profile: str) -> bool:
    return profile in {DOC_PROFILE_BACK_NEW, DOC_PROFILE_BACK_OLD}


def _parse_cccd_fulltext(full_text: str, profile: str) -> dict:
    data = _empty_person_data()
    text = (full_text or "").strip()
    if not text:
        return data

    stop_labels = (
        r"ngay\s*sinh|date\s*of\s*birth|gioi\s*tinh|sex|quoc\s*tich|nationality|"
        r"que\s*quan|place\s*of\s*origin|noi\s*thuong\s*tru|noi\s*cu\s*tru|"
        r"place\s*of\s*residence|ngay\s*cap|ngay\s*thang\s*nam\s*cap|date\s*of\s*issue|"
        r"co\s*gia\s*tri|ngay\s*het\s*han|date\s*of\s*expiry|idvnm"
    )

    data["so_giay_to"] = _extract_id_12_from_mrz_text(text) or _extract_id_12_from_text(text)

    name_block = _extract_anchor_block(text, r"ho\s*(?:va)?\s*ten|full\s*name", stop_labels)
    name_candidate = _clean_name_candidate(name_block)
    if _is_likely_name(name_candidate):
        data["ho_ten"] = name_candidate

    data["ngay_sinh"] = _extract_date_after_label(text, r"ngay\s*sinh|date\s*of\s*birth")
    data["ngay_cap"] = _extract_date_after_label(text, r"ngay\s*cap|ngay\s*thang\s*nam\s*cap|date\s*of\s*issue")
    data["ngay_het_han"] = _extract_date_after_label(text, r"co\s*gia\s*tri|ngay\s*het\s*han|date\s*of\s*expiry")
    data["gioi_tinh"] = _extract_gender_from_text(text)

    if profile == DOC_PROFILE_FRONT_OLD:
        data["dia_chi"] = _extract_anchor_block(
            text,
            r"noi\s*thuong\s*tru|place\s*of\s*residence",
            r"ngay\s*cap|ngay\s*thang\s*nam\s*cap|date\s*of\s*issue|co\s*gia\s*tri|ngay\s*het\s*han|date\s*of\s*expiry|idvnm",
        )
    elif profile == DOC_PROFILE_BACK_NEW:
        data["dia_chi"] = _extract_anchor_block(
            text,
            r"noi\s*cu\s*tru|place\s*of\s*residence",
            r"ngay\s*cap|ngay\s*thang\s*nam\s*cap|date\s*of\s*issue|co\s*gia\s*tri|ngay\s*het\s*han|date\s*of\s*expiry|idvnm",
        )
    elif profile == DOC_PROFILE_UNKNOWN:
        data["dia_chi"] = _extract_anchor_block(
            text,
            r"noi\s*thuong\s*tru|noi\s*cu\s*tru|place\s*of\s*residence",
            r"ngay\s*cap|ngay\s*thang\s*nam\s*cap|date\s*of\s*issue|co\s*gia\s*tri|ngay\s*het\s*han|date\s*of\s*expiry|idvnm",
        )

    if _is_back_profile(profile):
        dates = _extract_dates(text)
        if not data["ngay_cap"] and dates:
            data["ngay_cap"] = dates[0]
        if not data["ngay_het_han"] and len(dates) >= 2:
            data["ngay_het_han"] = dates[1]

    return data


def _coarse_doc_type_from_profile(profile: str, model_doc_type: str = "unknown") -> str:
    if profile.startswith("cccd_front_"):
        return "cccd_front"
    if profile.startswith("cccd_back_"):
        return "cccd_back"
    if model_doc_type in {"cccd_front", "cccd_back"}:
        return model_doc_type
    return "unknown"


def _infer_doc_profile(normalized_lines: List[str], model_doc_type: str = "unknown") -> str:
    full_norm = " ".join([line for line in normalized_lines if line])
    has_mrz = "idvnm" in full_norm
    has_back_signals = has_mrz or any(
        token in full_norm
        for token in (
            "ngon tro",
            "dau ngon",
            "dac diem nhan dang",
            "date of issue",
            "date of expiry",
            "ngay thang nam cap",
            "personal identification",
            "left index finger",
            "right index finger",
        )
    )
    has_noi_cu_tru = bool(re.search(r"\bnoi\s*cu\s*tru\b|\bplace\s*of\s*residence\b", full_norm))
    has_noi_thuong_tru = bool(re.search(r"\bnoi\s*thuong\s*tru\b|\bplace\s*of\s*residence\b", full_norm))
    has_que_quan = bool(re.search(r"\bque\s*quan\b|\bplace\s*of\s*origin\b", full_norm))
    has_can_cuoc = bool(re.search(r"\bcan\s*cuoc\b|\bidentity\s*card\b", full_norm))
    has_cong_dan = bool(re.search(r"\bcong\s*dan\b|\bcitizen\s*identity\s*card\b", full_norm))

    if has_back_signals:
        return DOC_PROFILE_BACK_NEW if has_noi_cu_tru else DOC_PROFILE_BACK_OLD
    if has_can_cuoc:
        if has_cong_dan or has_noi_thuong_tru or has_que_quan:
            return DOC_PROFILE_FRONT_OLD
        return DOC_PROFILE_FRONT_NEW
    if model_doc_type == "cccd_back":
        return DOC_PROFILE_BACK_NEW if has_noi_cu_tru else DOC_PROFILE_BACK_OLD
    if model_doc_type == "cccd_front":
        if has_cong_dan or has_noi_thuong_tru or has_que_quan:
            return DOC_PROFILE_FRONT_OLD
        return DOC_PROFILE_FRONT_NEW
    return DOC_PROFILE_UNKNOWN


def _triage_state_from_signals(face_detected: bool, qr_detected: bool, mrz_score: float) -> str:
    if face_detected and qr_detected:
        return TRIAGE_STATE_FRONT_OLD
    if face_detected and not qr_detected:
        return TRIAGE_STATE_FRONT_NEW
    if (not face_detected) and qr_detected:
        return TRIAGE_STATE_BACK_NEW
    if (not face_detected) and (not qr_detected):
        return TRIAGE_STATE_BACK_OLD if mrz_score >= LOCAL_OCR_TRIAGE_MRZ_MIN_SCORE else TRIAGE_STATE_UNKNOWN
    return TRIAGE_STATE_UNKNOWN


def _triage_profile_from_state(state: str) -> str:
    mapping = {
        TRIAGE_STATE_FRONT_OLD: DOC_PROFILE_FRONT_OLD,
        TRIAGE_STATE_FRONT_NEW: DOC_PROFILE_FRONT_NEW,
        TRIAGE_STATE_BACK_NEW: DOC_PROFILE_BACK_NEW,
        TRIAGE_STATE_BACK_OLD: DOC_PROFILE_BACK_OLD,
    }
    return mapping.get(state, DOC_PROFILE_UNKNOWN)


def _triage_side_from_state(state: str) -> str:
    if state in {TRIAGE_STATE_FRONT_OLD, TRIAGE_STATE_FRONT_NEW}:
        return "front"
    if state in {TRIAGE_STATE_BACK_NEW, TRIAGE_STATE_BACK_OLD}:
        return "back"
    return "unknown"


def _triage_state_has_qr(state: str) -> bool:
    return state in {TRIAGE_STATE_FRONT_OLD, TRIAGE_STATE_BACK_NEW}


def _rotate_by_angle(img_bgr: np.ndarray, angle: int) -> np.ndarray:
    angle = int(angle) % 360
    if angle == 90:
        return cv2.rotate(img_bgr, cv2.ROTATE_90_CLOCKWISE)
    if angle == 180:
        return cv2.rotate(img_bgr, cv2.ROTATE_180)
    if angle == 270:
        return cv2.rotate(img_bgr, cv2.ROTATE_90_COUNTERCLOCKWISE)
    return img_bgr


def _make_proxy_image(img_bgr: np.ndarray, max_side: int) -> np.ndarray:
    h, w = img_bgr.shape[:2]
    longest = max(h, w)
    if longest <= max_side or max_side <= 0:
        return img_bgr
    scale = max_side / float(longest)
    nw = max(1, int(round(w * scale)))
    nh = max(1, int(round(h * scale)))
    return cv2.resize(img_bgr, (nw, nh), interpolation=cv2.INTER_AREA)


def _get_face_cascade():
    global _face_cascade
    if _face_cascade is not None:
        return _face_cascade
    try:
        cascade_path = os.path.join(cv2.data.haarcascades, "haarcascade_frontalface_default.xml")
        cascade = cv2.CascadeClassifier(cascade_path)
        if cascade.empty():
            return None
        _face_cascade = cascade
    except Exception:
        _face_cascade = None
    return _face_cascade


def _get_qr_detector():
    global _qr_detector
    if _qr_detector is not None:
        return _qr_detector
    try:
        _qr_detector = cv2.QRCodeDetector()
    except Exception:
        _qr_detector = None
    return _qr_detector


def _detect_face_proxy(proxy_img: np.ndarray) -> bool:
    cascade = _get_face_cascade()
    if cascade is None:
        return False
    try:
        gray = cv2.cvtColor(proxy_img, cv2.COLOR_BGR2GRAY) if proxy_img.ndim == 3 else proxy_img
        faces = cascade.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=4, minSize=(24, 24))
        return bool(len(faces))
    except Exception:
        return False


def _detect_qr_proxy(proxy_img: np.ndarray) -> bool:
    detector = _get_qr_detector()
    if detector is None:
        return False
    try:
        detected, points = detector.detect(proxy_img)
        return bool(detected and points is not None)
    except Exception:
        return False


def _mrz_likelihood_score(proxy_img: np.ndarray) -> float:
    try:
        gray = cv2.cvtColor(proxy_img, cv2.COLOR_BGR2GRAY) if proxy_img.ndim == 3 else proxy_img
        h, w = gray.shape[:2]
        if h < 30 or w < 30:
            return 0.0
        y0 = int(h * 0.62)
        band = gray[y0:, :]
        if band.size == 0:
            return 0.0

        rect_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (13, 5))
        sq_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (21, 21))
        blackhat = cv2.morphologyEx(band, cv2.MORPH_BLACKHAT, rect_kernel)
        grad_x = cv2.Sobel(blackhat, cv2.CV_32F, 1, 0, ksize=-1)
        grad_x = np.absolute(grad_x)
        min_v = float(grad_x.min())
        max_v = float(grad_x.max())
        if (max_v - min_v) < 1e-6:
            return 0.0
        grad_x = ((grad_x - min_v) / (max_v - min_v) * 255.0).astype("uint8")
        grad_x = cv2.morphologyEx(grad_x, cv2.MORPH_CLOSE, rect_kernel)
        thresh = cv2.threshold(grad_x, 0, 255, cv2.THRESH_BINARY | cv2.THRESH_OTSU)[1]
        thresh = cv2.morphologyEx(thresh, cv2.MORPH_CLOSE, sq_kernel)

        coverage = float(np.count_nonzero(thresh)) / float(max(1, thresh.size))
        contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        max_rect_score = 0.0
        for contour in contours:
            x, y, bw, bh = cv2.boundingRect(contour)
            if bw < int(w * 0.20) or bh < 10:
                continue
            ratio = bw / float(max(1, bh))
            if ratio < 4.0:
                continue
            area_ratio = (bw * bh) / float(max(1, band.shape[0] * band.shape[1]))
            max_rect_score = max(max_rect_score, min(1.0, area_ratio * 6.0))
        score = min(1.0, coverage * 5.0 + max_rect_score * 0.6)
        return float(max(0.0, score))
    except Exception:
        return 0.0


def _triage_confidence(face_detected: bool, qr_detected: bool, mrz_score: float, state: str) -> float:
    score = 0.0
    if face_detected:
        score += 0.52
    if qr_detected:
        score += 0.34
    if not face_detected:
        score += min(0.22, mrz_score * 0.5)
    if state == TRIAGE_STATE_BACK_OLD:
        score += min(0.16, mrz_score * 0.4)
    if state == TRIAGE_STATE_UNKNOWN:
        score *= 0.4
    else:
        score += 0.08
    return float(max(0.0, min(1.0, score)))


def _triage_crop_orientation(crop_img: np.ndarray) -> dict:
    t_triage = perf_counter()
    proxy = _make_proxy_image(crop_img, LOCAL_OCR_TRIAGE_PROXY_MAX_SIDE)
    angle_rows: List[dict] = []
    total_qr_detect_ms = 0.0

    for angle in (0, 90, 180, 270):
        rotated_proxy = _rotate_by_angle(proxy, angle)
        face_detected = _detect_face_proxy(rotated_proxy)
        t_qr = perf_counter()
        qr_detected = _detect_qr_proxy(rotated_proxy)
        total_qr_detect_ms += _ms(perf_counter() - t_qr)
        mrz_score = _mrz_likelihood_score(rotated_proxy)
        state = _triage_state_from_signals(face_detected, qr_detected, mrz_score)
        confidence = _triage_confidence(face_detected, qr_detected, mrz_score, state)
        angle_rows.append(
            {
                "angle": angle,
                "face_detected": bool(face_detected),
                "qr_detected": bool(qr_detected),
                "mrz_score": round(float(mrz_score), 4),
                "triage_state": state,
                "confidence": round(float(confidence), 4),
            }
        )

    if not angle_rows:
        oriented_img = crop_img
        best = {
            "angle": 0,
            "face_detected": False,
            "qr_detected": False,
            "mrz_score": 0.0,
            "triage_state": TRIAGE_STATE_UNKNOWN,
            "confidence": 0.0,
        }
    else:
        best = max(
            angle_rows,
            key=lambda row: (
                float(row.get("confidence", 0.0)),
                1 if row.get("qr_detected") else 0,
                1 if row.get("face_detected") else 0,
                float(row.get("mrz_score", 0.0)),
            ),
        )
        oriented_img = _rotate_by_angle(crop_img, int(best.get("angle", 0)))

    triage_ms = _ms(perf_counter() - t_triage)
    return {
        "oriented_img": oriented_img,
        "orientation_angle": int(best.get("angle", 0)),
        "triage_state": str(best.get("triage_state", TRIAGE_STATE_UNKNOWN)),
        "face_detected": bool(best.get("face_detected", False)),
        "qr_detected": bool(best.get("qr_detected", False)),
        "mrz_score": float(best.get("mrz_score", 0.0)),
        "triage_confidence": float(best.get("confidence", 0.0)),
        "triage_ms": triage_ms,
        "qr_detect_ms": round(float(total_qr_detect_ms), 2),
        "angle_candidates": angle_rows,
    }


def _try_qr_data_from_crop(
    crop: DocCrop,
    seeded_qr_text: str | None = None,
    timing: Optional[dict] = None,
) -> tuple[dict | None, str]:
    t_total = perf_counter()
    qr_text = (seeded_qr_text or "").strip()
    t_seed = perf_counter()
    qr_data = parse_cccd_qr(qr_text) if qr_text else None
    seed_parse_ms = _ms(perf_counter() - t_seed)
    if _is_valid_qr_data(qr_data):
        if isinstance(timing, dict):
            timing.update(
                {
                    "seed_parse_ms": seed_parse_ms,
                    "encode_ms": 0.0,
                    "decode_ms": 0.0,
                    "detected_parse_ms": 0.0,
                    "result": "seeded_qr",
                    "total_ms": _ms(perf_counter() - t_total),
                }
            )
        return qr_data, qr_text

    encode_ms = 0.0
    decode_ms = 0.0
    detected_parse_ms = 0.0
    try:
        t_enc = perf_counter()
        success, encoded_img = cv2.imencode(".jpg", crop.img_native)
        encode_ms = _ms(perf_counter() - t_enc)
        if not success:
            if isinstance(timing, dict):
                timing.update(
                    {
                        "seed_parse_ms": seed_parse_ms,
                        "encode_ms": encode_ms,
                        "decode_ms": decode_ms,
                        "detected_parse_ms": detected_parse_ms,
                        "result": "encode_failed",
                        "total_ms": _ms(perf_counter() - t_total),
                    }
                )
            return None, ""
        t_dec = perf_counter()
        detected = try_decode_qr(encoded_img.tobytes()) or ""
        decode_ms = _ms(perf_counter() - t_dec)
        t_parse = perf_counter()
        parsed = parse_cccd_qr(detected) if detected else None
        detected_parse_ms = _ms(perf_counter() - t_parse)
        if _is_valid_qr_data(parsed):
            if isinstance(timing, dict):
                timing.update(
                    {
                        "seed_parse_ms": seed_parse_ms,
                        "encode_ms": encode_ms,
                        "decode_ms": decode_ms,
                        "detected_parse_ms": detected_parse_ms,
                        "result": "backend_qr",
                        "total_ms": _ms(perf_counter() - t_total),
                    }
                )
            return parsed, detected
    except Exception:
        pass

    if isinstance(timing, dict):
        timing.update(
            {
                "seed_parse_ms": seed_parse_ms,
                "encode_ms": encode_ms,
                "decode_ms": decode_ms,
                "detected_parse_ms": detected_parse_ms,
                "result": "no_qr",
                "total_ms": _ms(perf_counter() - t_total),
            }
        )
    return None, ""


def _extract_primary_id(
    img_rec: np.ndarray,
    boxes: List[dict],
    triage_state: str,
    context: str = "",
) -> tuple[str, str, str, float, int, int]:
    attempts: List[tuple[str, str]] = []
    if triage_state in {TRIAGE_STATE_FRONT_OLD, TRIAGE_STATE_FRONT_NEW}:
        attempts = [("id", "front_roi")]
    elif triage_state in {TRIAGE_STATE_BACK_NEW, TRIAGE_STATE_BACK_OLD}:
        attempts = [("id", "mrz")]
    else:
        attempts = [("id_front", "front_roi"), ("id_back", "mrz"), ("detail", "wide_roi")]

    total_ms = 0.0
    total_box_count = 0
    total_line_count = 0
    for phase, source in attempts:
        selected = filter_target_boxes(boxes, img_rec.shape[:2], triage_state, phase)
        if not selected:
            _log_debug("primary_id_attempt", context=context, phase=phase, source=source, selected_box_count=0)
            continue
        recognized, rec_ms = _recognize_target_boxes_rapidocr(img_rec, selected, context=f"{context}:{phase}" if context else phase)
        total_ms += rec_ms
        total_box_count += len(selected)
        lines = _group_lines(recognized)
        total_line_count += len(lines)
        raw_text = _build_raw_text(lines)
        _print_rapidocr_raw_text(raw_text, context=f"primary_id_{triage_state}_{phase}")
        if phase == "id_back" or source == "mrz":
            id_12 = _extract_id_12_from_mrz_text(raw_text) or _extract_id_12_from_text(raw_text)
        else:
            id_12 = _extract_id_12_from_text(raw_text)
        _log_debug(
            "primary_id_attempt",
            context=context,
            phase=phase,
            source=source,
            selected_box_count=len(selected),
            line_count=len(lines),
            elapsed_ms=rec_ms,
            extracted_id=id_12,
            raw_text_preview=_preview_text(raw_text),
        )
        if id_12:
            return id_12, source, raw_text, total_ms, total_box_count, total_line_count
    return "", "none", "", total_ms, total_box_count, total_line_count


def _merge_record_into(target: dict, incoming: dict) -> None:
    _merge_person_data(target["data"], incoming["data"], target["field_sources"], incoming.get("source_type", "OCR"), fill_missing_only=False)
    target["side"] = _merge_side(target.get("side", "unknown"), incoming.get("side", "unknown"))
    target["profile"] = _merge_profile(target.get("profile", DOC_PROFILE_UNKNOWN), incoming.get("profile", DOC_PROFILE_UNKNOWN))
    if str(incoming.get("source_type", "OCR")).upper() == "QR":
        target["source_type"] = "QR"
    for name in incoming.get("files", []):
        if name not in target["files"]:
            target["files"].append(name)
    for index in incoming.get("indexes", []):
        if index not in target["indexes"]:
            target["indexes"].append(index)
    for raw_text in incoming.get("raw_texts", []):
        if raw_text not in target["raw_texts"]:
            target["raw_texts"].append(raw_text)
    target["analyses"].extend(incoming.get("analyses", []))


def _ensure_person_record(persons_map: Dict[str, dict], person_order: List[str], key: str, filename: str, index: int) -> dict:
    if key not in persons_map:
        persons_map[key] = {
            "data": _empty_person_data(),
            "source_type": "OCR",
            "side": "unknown",
            "profile": DOC_PROFILE_UNKNOWN,
            "field_sources": {},
            "files": [filename] if filename else [],
            "indexes": [index],
            "raw_texts": [],
            "analyses": [],
        }
        person_order.append(key)
    record = persons_map[key]
    if filename and filename not in record["files"]:
        record["files"].append(filename)
    if index not in record["indexes"]:
        record["indexes"].append(index)
    return record


def _rekey_person_record(persons_map: Dict[str, dict], person_order: List[str], old_key: str, new_key: str) -> str:
    if old_key == new_key or old_key not in persons_map:
        return new_key
    incoming = persons_map.pop(old_key)
    if new_key in persons_map:
        _merge_record_into(persons_map[new_key], incoming)
        person_order[:] = [key for key in person_order if key != old_key]
        return new_key
    persons_map[new_key] = incoming
    person_order[:] = [new_key if key == old_key else key for key in person_order]
    return new_key


def _analyze_image_prepare(
    index: int,
    filename: str,
    raw_bytes: bytes,
    seeded_qr_text: str,
    client_qr_failed: bool,
    trace_id: str | None = None,
) -> dict:
    t_total = perf_counter()
    t_decode = perf_counter()
    img_np = np.frombuffer(raw_bytes, np.uint8)
    img_native = cv2.imdecode(img_np, cv2.IMREAD_COLOR)
    decode_ms = _ms(perf_counter() - t_decode)
    if img_native is None:
        raise ValueError("Khong doc duoc anh")

    t_pre = perf_counter()
    img_ocr = _preprocess(img_native)
    preprocess_ms = _ms(perf_counter() - t_pre)

    t_detect_doc = perf_counter()
    crops = _detect_documents(img_native, img_ocr)
    detect_ms = _ms(perf_counter() - t_detect_doc)
    crop = _pick_primary_crop(crops)

    triage = _triage_crop_orientation(crop.img_native)
    triage_state = str(triage.get("triage_state", TRIAGE_STATE_UNKNOWN))
    profile = _triage_profile_from_state(triage_state)
    side = _triage_side_from_state(triage_state)

    oriented_native = _rotate_by_angle(crop.img_native, triage.get("orientation_angle", 0))
    oriented_ocr = _rotate_by_angle(crop.img_ocr, triage.get("orientation_angle", 0))
    oriented_crop = DocCrop(
        img_native=oriented_native,
        img_ocr=oriented_ocr,
        bbox=crop.bbox,
        doc_type=crop.doc_type,
        confidence=crop.confidence,
    )

    qr_timing: Dict[str, Any] = {}
    qr_data = None
    qr_text = ""
    if _triage_state_has_qr(triage_state) or seeded_qr_text.strip():
        qr_data, qr_text = _try_qr_data_from_crop(oriented_crop, seeded_qr_text, timing=qr_timing)

    source_type = "QR" if _is_valid_qr_data(qr_data) else "OCR"
    data = _build_qr_person_data(qr_data or {}) if source_type == "QR" else _empty_person_data()
    id_12 = _clean_doc_number(data.get("so_giay_to", ""))
    id_source = "qr" if id_12 else "none"
    det_boxes: List[dict] = []
    rapidocr_det_ms = 0.0
    id_extract_ms = 0.0
    raw_text = ""
    ocr_box_count = 0
    line_count = 0

    if source_type != "QR":
        det_boxes, rapidocr_det_ms = _rapidocr_detect_boxes(oriented_ocr)
        ocr_box_count = len(det_boxes)
        id_12, id_source, raw_text, id_extract_ms, _, line_count = _extract_primary_id(
            oriented_native,
            det_boxes,
            triage_state,
            context=f"{filename}:{index}",
        )
        if id_12:
            data["so_giay_to"] = id_12

    total_ms = _ms(perf_counter() - t_total)
    _log_debug(
        "image_prepare",
        trace_id=trace_id,
        index=index,
        filename=filename,
        image_shape=f"{img_native.shape[1]}x{img_native.shape[0]}",
        crop_bbox=list(crop.bbox),
        crop_confidence=round(float(crop.confidence or 0.0), 4),
        triage_state=triage_state,
        orientation_angle=int(triage.get("orientation_angle", 0)),
        triage_confidence=round(float(triage.get("triage_confidence", 0.0) or 0.0), 4),
        face_detected=bool(triage.get("face_detected", False)),
        qr_detected=bool(triage.get("qr_detected", False)),
        mrz_score=round(float(triage.get("mrz_score", 0.0) or 0.0), 4),
        angle_candidates=triage.get("angle_candidates", []),
        qr_seeded=bool(seeded_qr_text.strip()),
        qr_text_preview=_preview_text(qr_text, limit=120),
        source_type=source_type,
        det_box_count=len(det_boxes),
        det_box_width_stats=_numeric_stats(_box_bounds(item["box"])[2] - _box_bounds(item["box"])[0] for item in det_boxes),
        det_box_height_stats=_numeric_stats(_box_bounds(item["box"])[3] - _box_bounds(item["box"])[1] for item in det_boxes),
        id_source=id_source,
        id_12=id_12,
        raw_text_preview=_preview_text(raw_text),
        timing_ms={
            "decode_ms": decode_ms,
            "preprocess_ms": preprocess_ms,
            "detect_ms": detect_ms,
            "triage_ms": triage.get("triage_ms", 0.0),
            "qr_detect_ms": triage.get("qr_detect_ms", 0.0),
            "qr_decode_ms": qr_timing.get("total_ms", 0.0),
            "rapidocr_det_ms": rapidocr_det_ms,
            "id_extract_ms": id_extract_ms,
            "total_ms": total_ms,
        },
    )
    return {
        "index": index,
        "filename": filename,
        "img_native": oriented_native,
        "img_ocr": oriented_ocr,
        "det_boxes": det_boxes,
        "source_type": source_type,
        "side": side,
        "profile": profile,
        "doc_type": _coarse_doc_type_from_profile(profile, crop.doc_type),
        "triage_state": triage_state,
        "orientation_angle": int(triage.get("orientation_angle", 0)),
        "face_detected": bool(triage.get("face_detected", False)),
        "qr_detected": bool(triage.get("qr_detected", False)),
        "mrz_score": float(triage.get("mrz_score", 0.0)),
        "qr_text": qr_text,
        "qr_data": qr_data or {},
        "data": data,
        "id_12": id_12,
        "id_source": id_source,
        "raw_text": raw_text,
        "client_qr_failed": bool(client_qr_failed),
        "timing_ms": {
            "decode_ms": decode_ms,
            "preprocess_ms": preprocess_ms,
            "detect_ms": detect_ms,
            "triage_ms": triage.get("triage_ms", 0.0),
            "qr_detect_ms": triage.get("qr_detect_ms", 0.0),
            "qr_decode_ms": qr_timing.get("total_ms", 0.0),
            "rapidocr_det_ms": rapidocr_det_ms,
            "id_extract_ms": id_extract_ms,
            "targeted_extract_ms": 0.0,
            "merge_ms": 0.0,
            "total_ms": total_ms,
        },
        "ocr_box_count": ocr_box_count,
        "line_count": line_count,
    }


def _ensure_detection(prepared: dict) -> None:
    if prepared.get("det_boxes"):
        return
    det_boxes, det_ms = _rapidocr_detect_boxes(prepared["img_ocr"])
    prepared["det_boxes"] = det_boxes
    prepared["ocr_box_count"] = len(det_boxes)
    prepared["timing_ms"]["rapidocr_det_ms"] = round(float(prepared["timing_ms"].get("rapidocr_det_ms", 0.0)) + det_ms, 2)


def _run_detail_phase(prepared: dict, record: dict) -> tuple[dict, str, float]:
    _ensure_detection(prepared)
    selected = filter_target_boxes(prepared.get("det_boxes", []), prepared["img_ocr"].shape[:2], prepared["triage_state"], "detail")
    if not selected:
        _log_debug("detail_phase", context=prepared.get("filename", ""), selected_box_count=0, result="no_boxes")
        return _empty_person_data(), "", 0.0

    recognized, detail_ms = _recognize_target_boxes_rapidocr(
        prepared["img_native"],
        selected,
        context=f"{prepared.get('filename', '')}:detail_fast",
    )
    
    vietocr_boxes = []
    for item in recognized:
        text = item["text"]
        folded = _ascii_fold(text).lower()
        if re.fullmatch(r"[\d\W]+", text): continue
        if len(folded) < 3: continue
        skip_labels = r"^(ho va ten|ho ten|full name|gioi tinh|sex|ngay sinh|date of birth|quoc tich|nationality|que quan|place of origin|noi thuong tru|noi cu tru|place of residence|ngay cap|date of issue|co gia tri|date of expiry|idvnm|can cuoc|cong dan|socialist|republic|independence|freedom|happiness|bo cong an|director|public security)"
        if re.search(skip_labels, folded):
            continue
        vietocr_boxes.append(item)
        
    if vietocr_boxes:
        refined, refined_ms = _recognize_target_boxes(prepared["img_native"], vietocr_boxes, context=f"{prepared.get('filename', '')}:detail_refine")
        detail_ms += refined_ms
        ref_map = { str(_box_bounds(r["box"])): r["text"] for r in refined }
        for item in recognized:
            bnd_str = str(_box_bounds(item["box"]))
            if bnd_str in ref_map:
                item["text"] = ref_map[bnd_str]

    lines = _group_lines(recognized)
    raw_text = _build_raw_text(lines)
    _print_rapidocr_raw_text(raw_text, context=f"detail_{prepared['triage_state']}")
    parsed = _parse_cccd_fulltext(raw_text, prepared["profile"])
    inferred_profile = _infer_doc_profile(_normalize_ocr_lines(lines), prepared.get("doc_type", "unknown"))
    if not parsed.get("so_giay_to") and prepared.get("id_12"):
        parsed["so_giay_to"] = prepared["id_12"]
    _log_debug(
        "detail_phase",
        context=prepared.get("filename", ""),
        selected_box_count=len(selected),
        recognized_count=len(recognized),
        elapsed_ms=detail_ms,
        current_profile=prepared.get("profile"),
        inferred_profile=inferred_profile,
        parsed_fields=[key for key, value in parsed.items() if (value or "").strip()],
        raw_text_preview=_preview_text(raw_text),
    )
    return parsed, raw_text, detail_ms


def _local_engine_name() -> str:
    return _rapidocr_runtime_label


def _finalize_image_rows(image_results: List[dict], persons_map: Dict[str, dict]) -> None:
    for pair_key, record in persons_map.items():
        paired = len(record.get("indexes", [])) >= 2 and re.fullmatch(r"\d{12}", pair_key or "") is not None
        warnings = _collect_warnings(record["data"], record.get("profile", DOC_PROFILE_UNKNOWN))
        for index in record.get("indexes", []):
            if not (0 <= index < len(image_results)):
                continue
            row = image_results[index]
            row["pair_key"] = pair_key if paired else None
            row["paired"] = paired
            row["warnings"] = warnings
            row["profile"] = record.get("profile", DOC_PROFILE_UNKNOWN)


def _build_summary(
    image_results: List[dict],
    persons: List[dict],
    errors: List[dict],
    state_counts: Dict[str, int],
    engine_ms: float,
    total_ms: float,
) -> dict:
    def _sum_phase(key: str) -> float:
        return round(sum(float((row.get("timing_ms") or {}).get(key, 0.0) or 0.0) for row in image_results), 2)

    qr_hits = sum(1 for row in image_results if str(row.get("source_type", "")).upper() == "QR")
    ocr_runs = sum(1 for row in image_results if str(row.get("source_type", "")).upper() == "OCR")
    skipped_by_qr = qr_hits
    paired_count = sum(1 for person in persons if len(person.get("_files", [])) >= 2)
    unpaired_count = max(0, len(persons) - paired_count)
    slowest_images = sorted(image_results, key=lambda row: float((row.get("timing_ms") or {}).get("total_ms", 0.0) or 0.0), reverse=True)[:5]

    return {
        "total_images": len(image_results),
        "qr_hits": qr_hits,
        "ocr_runs": ocr_runs,
        "skipped_by_qr": skipped_by_qr,
        "state_counts": state_counts,
        "pairing": {"paired_count": paired_count, "unpaired_count": unpaired_count},
        "local_engine": _local_engine_name(),
        "rec_model_mode": _vietocr_rec_mode,
        "timing_ms": {
            "total_ms": total_ms,
            "engine_init_ms": engine_ms,
            "decode_total_ms": _sum_phase("decode_ms"),
            "preprocess_total_ms": _sum_phase("preprocess_ms"),
            "detect_total_ms": _sum_phase("detect_ms"),
            "triage_phase_ms": _sum_phase("triage_ms"),
            "qr_detect_phase_ms": _sum_phase("qr_detect_ms"),
            "qr_decode_phase_ms": _sum_phase("qr_decode_ms"),
            "rapidocr_det_phase_ms": _sum_phase("rapidocr_det_ms"),
            "id_extract_phase_ms": _sum_phase("id_extract_ms"),
            "targeted_extract_phase_ms": _sum_phase("targeted_extract_ms"),
            "merge_phase_ms": _sum_phase("merge_ms"),
            "fallback_phase_ms": 0.0,
        },
        "slowest_images": slowest_images,
        "persons": len(persons),
        "errors": len(errors),
    }


def _local_ocr_batch_from_inputs_triage_v2(
    file_items: List[dict],
    qr_texts: Optional[List[str]] = None,
    client_qr_failed: Optional[List[Any]] = None,
    trace_id: str | None = None,
) -> dict:
    if not file_items:
        return {
            "persons": [],
            "properties": [],
            "marriages": [],
            "image_results": [],
            "errors": [],
            "summary": {
                "total_images": 0,
                "qr_hits": 0,
                "ocr_runs": 0,
                "skipped_by_qr": 0,
                "state_counts": {
                    TRIAGE_STATE_FRONT_OLD: 0,
                    TRIAGE_STATE_FRONT_NEW: 0,
                    TRIAGE_STATE_BACK_NEW: 0,
                    TRIAGE_STATE_BACK_OLD: 0,
                    TRIAGE_STATE_UNKNOWN: 0,
                },
                "pairing": {"paired_count": 0, "unpaired_count": 0},
                "local_engine": _local_engine_name(),
                "rec_model_mode": _vietocr_rec_mode,
                "timing_ms": {},
            },
        }

    t_total = perf_counter()
    _ensure_local_ocr_dependencies()
    t_engine = perf_counter()
    _get_rapidocr_engine()
    engine_ms = _ms(perf_counter() - t_engine)

    total = len(file_items)
    qr_text_values = _normalize_qr_texts(qr_texts, total)
    qr_failed_flags = _normalize_qr_failed_flags(client_qr_failed, total)
    state_counts = {
        TRIAGE_STATE_FRONT_OLD: 0,
        TRIAGE_STATE_FRONT_NEW: 0,
        TRIAGE_STATE_BACK_NEW: 0,
        TRIAGE_STATE_BACK_OLD: 0,
        TRIAGE_STATE_UNKNOWN: 0,
    }
    prepared_rows: List[dict] = []
    image_results: List[dict] = []
    errors: List[dict] = []

    _log_timing(
        "batch_v4_start",
        trace_id=trace_id,
        total_images=total,
        qr_texts_count=len(qr_texts or []),
        qr_failed_flags_count=len(client_qr_failed or []),
    )

    for index, item in enumerate(file_items):
        filename = item.get("filename") or f"image_{index + 1}.jpg"
        try:
            prepared = _analyze_image_prepare(
                index=index,
                filename=filename,
                raw_bytes=item.get("bytes") or b"",
                seeded_qr_text=qr_text_values[index],
                client_qr_failed=qr_failed_flags[index],
                trace_id=trace_id,
            )
            state_counts[prepared["triage_state"]] = state_counts.get(prepared["triage_state"], 0) + 1
            prepared_rows.append(prepared)
            image_results.append(
                {
                    "index": index,
                    "filename": filename,
                    "source_type": prepared["source_type"],
                    "side": prepared["side"],
                    "profile": prepared["profile"],
                    "doc_type": prepared["doc_type"],
                    "raw_text": prepared["raw_text"],
                    "warnings": _collect_warnings(prepared["data"], prepared["profile"]),
                    "triage_state": prepared["triage_state"],
                    "orientation_angle": prepared["orientation_angle"],
                    "face_detected": prepared["face_detected"],
                    "qr_detected": prepared["qr_detected"],
                    "mrz_score": prepared["mrz_score"],
                    "id_12": prepared["id_12"],
                    "id_source": prepared["id_source"],
                    "paired": False,
                    "pair_key": None,
                    "timing_ms": dict(prepared["timing_ms"]),
                }
            )
        except Exception as exc:
            errors.append({"index": index, "filename": filename, "error": str(exc)})
            image_results.append(
                {
                    "index": index,
                    "filename": filename,
                    "source_type": "error",
                    "side": "unknown",
                    "profile": DOC_PROFILE_UNKNOWN,
                    "doc_type": "unknown",
                    "raw_text": "",
                    "warnings": list(_CRITICAL_WARNING_FIELDS),
                    "triage_state": TRIAGE_STATE_UNKNOWN,
                    "orientation_angle": 0,
                    "face_detected": False,
                    "qr_detected": False,
                    "mrz_score": 0.0,
                    "id_12": "",
                    "id_source": "none",
                    "paired": False,
                    "pair_key": None,
                    "timing_ms": {"total_ms": 0.0},
                }
            )
            _log_timing(
                "batch_v4_prepare_error",
                level="warning",
                trace_id=trace_id,
                index=index,
                filename=filename,
                error=str(exc),
            )

    persons_map: Dict[str, dict] = {}
    person_order: List[str] = []
    row_key_map: Dict[int, str] = {}

    for prepared in prepared_rows:
        index = prepared["index"]
        filename = prepared["filename"]
        key = prepared["id_12"] if re.fullmatch(r"\d{12}", prepared["id_12"] or "") else f"img:{index}"
        record = _ensure_person_record(persons_map, person_order, key, filename, index)
        record["side"] = _merge_side(record.get("side", "unknown"), prepared["side"])
        record["profile"] = _merge_profile(record.get("profile", DOC_PROFILE_UNKNOWN), prepared["profile"])
        if prepared["source_type"] == "QR":
            record["source_type"] = "QR"
        _merge_person_data(record["data"], prepared["data"], record["field_sources"], prepared["source_type"], fill_missing_only=False)
        record["analyses"].append(
            {
                "source_type": prepared["source_type"],
                "side": prepared["side"],
                "profile": prepared["profile"],
                "data": dict(prepared["data"]),
            }
        )
        if prepared["raw_text"]:
            _append_person_raw_text(record, prepared["raw_text"], filename)
        row_key_map[index] = key

    for prepared in prepared_rows:
        index = prepared["index"]
        current_key = row_key_map.get(index, f"img:{index}")
        record = persons_map.get(current_key)
        if record is None:
            continue

        t_merge = perf_counter()
        if _should_run_detail_phase(record["data"], prepared["profile"]):
            parsed, raw_text, detail_ms = _run_detail_phase(prepared, record)
            prepared["timing_ms"]["targeted_extract_ms"] = detail_ms
            if raw_text:
                _append_person_raw_text(record, raw_text, prepared["filename"])
                _merge_person_data(record["data"], parsed, record["field_sources"], "OCR", fill_missing_only=False)
                record["analyses"].append(
                    {
                        "source_type": "OCR",
                        "side": prepared["side"],
                        "profile": prepared["profile"],
                        "data": dict(parsed),
                    }
                )
                image_results[index]["source_type"] = "OCR"
                image_results[index]["raw_text"] = raw_text
                new_id = _clean_doc_number(parsed.get("so_giay_to", ""))
                if len(new_id) == 12 and current_key != new_id:
                    new_key = _rekey_person_record(persons_map, person_order, current_key, new_id)
                    row_key_map[index] = new_key
                    current_key = new_key
                    record = persons_map[current_key]
                elif len(new_id) == 12:
                    row_key_map[index] = new_id
            else:
                image_results[index]["source_type"] = prepared["source_type"]
        else:
            image_results[index]["source_type"] = prepared["source_type"]

        prepared["timing_ms"]["merge_ms"] = _ms(perf_counter() - t_merge)
        image_results[index]["timing_ms"] = dict(prepared["timing_ms"])
        image_results[index]["id_12"] = _clean_doc_number(record["data"].get("so_giay_to", prepared.get("id_12", "")))
        image_results[index]["id_source"] = prepared["id_source"]

    persons: List[dict] = []
    for key in person_order:
        record = persons_map[key]
        _apply_delta_merge(record["data"], record["analyses"])
        if re.fullmatch(r"\d{12}", key or ""):
            record["data"]["so_giay_to"] = key
        profile = record.get("profile", DOC_PROFILE_UNKNOWN)
        warnings = _collect_warnings(record["data"], profile)
        person_source = "QR" if any(str(item.get("source_type", "OCR")).upper() == "QR" for item in record.get("analyses", [])) else "OCR"
        combined_raw_text = "\n\n".join(record.get("raw_texts", []))
        persons.append(
            {
                "type": "person",
                "data": {**record["data"], "profile": profile},
                "_source": f"{person_source} ({record.get('side', 'unknown')})",
                "source_type": person_source,
                "side": record.get("side", "unknown"),
                "profile": profile,
                "field_sources": record.get("field_sources", {}),
                "warnings": warnings,
                "_files": record.get("files", []),
                "raw_text": combined_raw_text,
            }
        )

    _finalize_image_rows(image_results, persons_map)
    total_ms = _ms(perf_counter() - t_total)
    summary = _build_summary(image_results, persons, errors, state_counts, engine_ms, total_ms)
    _log_timing(
        "batch_v4_done",
        level="warning" if total_ms >= LOCAL_OCR_TIMING_SLOW_MS * max(1, total) else "info",
        trace_id=trace_id,
        summary=summary,
    )
    return {
        "persons": persons,
        "properties": [],
        "marriages": [],
        "errors": errors,
        "image_results": image_results,
        "summary": summary,
    }


def local_ocr_batch_from_inputs(
    file_items: List[dict],
    qr_texts: Optional[List[str]] = None,
    client_qr_failed: Optional[List[Any]] = None,
    trace_id: str | None = None,
) -> dict:
    return _local_ocr_batch_from_inputs_triage_v2(
        file_items=file_items,
        qr_texts=qr_texts,
        client_qr_failed=client_qr_failed,
        trace_id=trace_id,
    )


def local_ocr_from_bytes(
    file_bytes: bytes,
    qr_text: str | None = None,
    client_qr_failed: bool = False,
    trace_id: str | None = None,
) -> dict:
    result = local_ocr_batch_from_inputs(
        [{"index": 0, "filename": "single_upload.jpg", "bytes": file_bytes}],
        qr_texts=[qr_text or ""],
        client_qr_failed=[client_qr_failed],
        trace_id=trace_id,
    )
    persons = result.get("persons") or []
    image_results = result.get("image_results") or []
    if not persons:
        err = (result.get("errors") or [{}])[0].get("error", "Khong nhan dien duoc noi dung")
        raise ValueError(err)

    best = persons[0]
    image_result = image_results[0] if image_results else {}
    profile = best.get("profile", DOC_PROFILE_UNKNOWN)
    raw_text = best.get("raw_text", "")
    data = dict(best.get("data", {}) or {})
    data.pop("profile", None)

    return {
        "persons": [
            {
                "type": "person",
                "data": {**data, "_raw_text": raw_text, "profile": profile},
                "_source": best.get("_source", "OCR (unknown)"),
                "source_type": best.get("source_type", "OCR"),
                "side": best.get("side", "unknown"),
                "profile": profile,
                "field_sources": best.get("field_sources", {}),
                "warnings": best.get("warnings", []),
                "triage_state": image_result.get("triage_state", TRIAGE_STATE_UNKNOWN),
                "orientation_angle": image_result.get("orientation_angle", 0),
                "face_detected": image_result.get("face_detected", False),
                "qr_detected": image_result.get("qr_detected", False),
                "mrz_score": image_result.get("mrz_score", 0.0),
                "id_12": image_result.get("id_12", ""),
                "id_source": image_result.get("id_source", "none"),
            }
        ],
        "properties": [],
        "marriages": [],
        "raw_text": raw_text,
        "doc_type": image_result.get("doc_type", "unknown"),
        "timing_ms": (result.get("summary", {}) or {}).get("timing_ms", {}),
    }


@router.post("/analyze-local")
async def analyze_images_local(files: List[UploadFile] = File(...)):
    if not files:
        raise HTTPException(status_code=400, detail="Chua co anh nao duoc gui len")
    file_items = []
    for index, upload in enumerate(files):
        raw = await upload.read()
        file_items.append({"index": index, "filename": upload.filename or f"image_{index + 1}.jpg", "bytes": raw})
    return local_ocr_batch_from_inputs(file_items, trace_id=str(uuid.uuid4()))


@router.post("/local/submit")
async def submit_local_job(
    file: UploadFile = File(...),
    qr_text: str | None = Form(None),
    client_qr_failed: bool = Form(False),
):
    if not file:
        raise HTTPException(status_code=400, detail="Chua co file")
    _ensure_local_ocr_dependencies()

    temp_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "tmp", "ocr")
    os.makedirs(temp_dir, exist_ok=True)
    job_id = str(uuid.uuid4())
    ext = os.path.splitext(file.filename or "")[1].lower() or ".jpg"
    temp_path = os.path.join(temp_dir, f"{job_id}{ext}")

    raw = await file.read()
    with open(temp_path, "wb") as fw:
        fw.write(raw)

    db = SessionLocal()
    try:
        job = OCRJob(
            id=job_id,
            status="queued",
            temp_file_path=temp_path,
            result_json=None,
            error_message=None,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )
        db.add(job)
        db.commit()
    finally:
        db.close()

    from tasks import process_ocr_job

    process_ocr_job.delay(job_id, qr_text, client_qr_failed)
    return {"job_id": job_id, "status": "queued"}


@router.post("/local/submit-batch")
async def submit_local_batch_job(
    files: List[UploadFile] = File(...),
    qr_texts_json: str | None = Form(None),
    client_qr_failed_json: str | None = Form(None),
):
    if not files:
        raise HTTPException(status_code=400, detail="Chua co file")
    _ensure_local_ocr_dependencies()

    temp_root = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "tmp", "ocr")
    os.makedirs(temp_root, exist_ok=True)
    job_id = str(uuid.uuid4())
    batch_dir = os.path.join(temp_root, f"batch_{job_id}")
    os.makedirs(batch_dir, exist_ok=True)

    manifest_items = []
    try:
        for index, upload in enumerate(files):
            safe_name = _safe_filename(upload.filename or "", index)
            ext = os.path.splitext(safe_name)[1].lower() or ".jpg"
            stored_name = f"{index:04d}{ext}"
            file_path = os.path.join(batch_dir, stored_name)
            raw = await upload.read()
            with open(file_path, "wb") as fw:
                fw.write(raw)
            manifest_items.append({"index": index, "filename": upload.filename or safe_name, "stored_name": stored_name})

        manifest_path = os.path.join(batch_dir, "manifest.json")
        with open(manifest_path, "w", encoding="utf-8") as fw:
            json.dump({"items": manifest_items}, fw, ensure_ascii=False)

        db = SessionLocal()
        try:
            job = OCRJob(
                id=job_id,
                status="queued",
                temp_file_path=batch_dir,
                result_json=None,
                error_message=None,
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow(),
            )
            db.add(job)
            db.commit()
        finally:
            db.close()
    except Exception:
        shutil.rmtree(batch_dir, ignore_errors=True)
        raise

    from tasks import process_ocr_batch_job

    process_ocr_batch_job.delay(job_id, qr_texts_json or "[]", client_qr_failed_json or "[]")
    return {"job_id": job_id, "status": "queued"}


@router.get("/local/status/{job_id}")
async def get_local_job_status(job_id: str):
    db = SessionLocal()
    try:
        job = db.query(OCRJob).filter(OCRJob.id == job_id).first()
        if not job:
            raise HTTPException(status_code=404, detail="Khong tim thay job")
        return {
            "job_id": job.id,
            "status": job.status,
            "result_json": job.result_json,
            "error_message": job.error_message,
        }
    finally:
        db.close()


@router.post("/local/confirm-save")
async def confirm_save(payload: dict = Body(...)):
    items = payload.get("items")
    if not items:
        items = [
            {
                "parsed_data": payload.get("parsed_data") or {},
                "raw_text": payload.get("raw_text") or "",
                "document_type": payload.get("document_type") or "UNKNOWN",
            }
        ]

    db = SessionLocal()
    try:
        ids = []
        for item in items:
            doc = ExtractedDocument(
                user_id=None,
                document_type=item.get("document_type") or "UNKNOWN",
                raw_text=item.get("raw_text") or "",
                parsed_data=item.get("parsed_data") or {},
            )
            db.add(doc)
            db.flush()
            ids.append(doc.id)
        db.commit()
        return {"ok": True, "ids": ids}
    finally:
        db.close()
