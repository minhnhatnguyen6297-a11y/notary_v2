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

import asyncio
import base64, io, json, logging, os, re, unicodedata
import multiprocessing
from concurrent.futures import ProcessPoolExecutor, TimeoutError as FuturesTimeoutError, as_completed
from datetime import datetime
from time import perf_counter
from typing import Any, List

import httpx
import zxingcpp
from dotenv import load_dotenv
from fastapi import APIRouter, File, HTTPException, UploadFile
from PIL import Image, ImageOps
try:
    import cv2
    import numpy as np
except Exception:
    cv2 = None
    np = None

router = APIRouter(tags=["OCR"])
_logger = logging.getLogger("ocr_api")
_local_ocr_module = None
_local_ocr_import_attempted = False
_face_cascade = None
_PREPROCESS_POOL: ProcessPoolExecutor | None = None
_PREPROCESS_POOL_WORKERS = 0

# ─── Config — đọc động từ file .env để không cần restart khi đổi key ──────────
_ENV_PATH = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".env"))

def _read_env() -> dict:
    """Đọc thẳng file .env, không phụ thuộc os.environ."""
    from dotenv import dotenv_values
    return dotenv_values(_ENV_PATH)

def _get_env_value(name: str, default: str) -> str:
    value = os.getenv(name, "")
    if value:
        return value
    env_value = _read_env().get(name)
    if env_value in (None, ""):
        return default
    return str(env_value)

def _get_env_int(name: str, default: int, *, minimum: int = 0) -> int:
    raw = _get_env_value(name, str(default))
    try:
        value = int(raw)
    except (TypeError, ValueError):
        value = default
    return max(minimum, value)

def _get_env_float(name: str, default: float, *, minimum: float = 0.0) -> float:
    raw = _get_env_value(name, str(default))
    try:
        value = float(raw)
    except (TypeError, ValueError):
        value = default
    return max(minimum, value)

def _get_env_flag(name: str, default: bool) -> bool:
    raw = _get_env_value(name, "1" if default else "0")
    return raw.strip().lower() not in {"0", "false", "no", "off"}

def _get_api_key(model: str) -> str:
    key_name = "GEMINI_API_KEY" if "gemini" in model.lower() else "OPENAI_API_KEY"
    return _get_env_value(key_name, "")

def _get_model() -> str:
    return _get_env_value("OCR_MODEL", "gemini-1.5-flash")

def _get_primary_model() -> str:
    explicit = _get_env_value("AI_OCR_PRIMARY_MODEL", "")
    if explicit:
        return explicit
    legacy = _get_env_value("OCR_MODEL", "")
    if legacy:
        return legacy
    return "gpt-4o-mini"

def _get_escalation_model() -> str:
    explicit = _get_env_value("AI_OCR_ESCALATION_MODEL", "")
    if explicit:
        return explicit
    primary = _get_primary_model()
    return "gpt-4o" if primary == "gpt-4o-mini" else primary

def _get_ai_ocr_settings() -> dict[str, Any]:
    return {
        "batch_size": _get_env_int("AI_OCR_BATCH_SIZE", 3, minimum=1),
        "max_concurrency": _get_env_int("AI_OCR_MAX_CONCURRENCY", 2, minimum=1),
        "timeout_seconds": _get_env_float("AI_OCR_TIMEOUT_SECONDS", 120.0, minimum=5.0),
        "retry_count": _get_env_int("AI_OCR_RETRY_COUNT", 2, minimum=0),
        "retry_base_delay_ms": _get_env_int("AI_OCR_RETRY_BASE_DELAY_MS", 800, minimum=100),
        "openai_max_tokens_per_image": _get_env_int("AI_OCR_OPENAI_MAX_TOKENS_PER_IMAGE", 500, minimum=128),
        "timing_log": _get_env_flag("AI_OCR_TIMING_LOG", True),
        "timing_slow_ms": _get_env_float("AI_OCR_TIMING_SLOW_MS", 2500.0, minimum=100.0),
        "enable_targeted_fields": _get_env_flag("AI_OCR_ENABLE_TARGETED_FIELDS", True),
        "enable_mrz_local": _get_env_flag("AI_OCR_ENABLE_MRZ_LOCAL", True),
        "preprocess_workers": _get_env_int("AI_OCR_PREPROCESS_WORKERS", 2, minimum=0),
        "preprocess_warmup": _get_env_flag("AI_OCR_PREPROCESS_WARMUP", True),
    }


def _parse_mrz_crop_ratio() -> float:
    try:
        value = float(_get_env_value("AI_OCR_MRZ_CROP_RATIO", "0.65"))
    except (TypeError, ValueError):
        return 0.65
    return max(0.4, min(0.9, value))


MAX_IMAGE_PX = 1000
JPEG_QUALITY = 82
MRZ_BOTTOM_CROP_RATIO = _parse_mrz_crop_ratio()
MRZ_CROP_FILTER_Y_MAX = 0.6
MRZ_CROP_MIN_WIDTH_RATIO = 0.5
MRZ_CROP_MAX_HEIGHT_RATIO = 0.12

DOC_PROFILE_FRONT_OLD = "cccd_front_old"
DOC_PROFILE_BACK_OLD = "cccd_back_old"
DOC_PROFILE_FRONT_NEW = "cccd_front_new"
DOC_PROFILE_BACK_NEW = "cccd_back_new"
DOC_PROFILE_UNKNOWN = "unknown"

TRIAGE_STATE_FRONT_OLD = "front_old"
TRIAGE_STATE_FRONT_NEW = "front_new"
TRIAGE_STATE_BACK_NEW = "back_new"
TRIAGE_STATE_BACK_OLD = "back_old"
TRIAGE_STATE_FRONT_UNKNOWN = "front_unknown"
TRIAGE_STATE_UNKNOWN = "unknown"

_SYSTEM_REQUIRED_FIELDS = ("ho_ten", "so_giay_to", "ngay_sinh", "gioi_tinh", "dia_chi", "ngay_cap")
_PROFILE_REQUIRED_FIELDS = {
    DOC_PROFILE_FRONT_OLD: ("so_giay_to", "ho_ten", "ngay_sinh", "gioi_tinh", "dia_chi"),
    DOC_PROFILE_FRONT_NEW: ("so_giay_to", "ho_ten", "ngay_sinh", "gioi_tinh"),
    DOC_PROFILE_BACK_NEW: ("so_giay_to", "dia_chi", "ngay_cap"),
    DOC_PROFILE_BACK_OLD: ("so_giay_to", "ngay_cap"),
    DOC_PROFILE_UNKNOWN: _SYSTEM_REQUIRED_FIELDS,
}
_PROFILE_TO_DOC_TYPE = {
    DOC_PROFILE_FRONT_OLD: "cccd_front",
    DOC_PROFILE_FRONT_NEW: "cccd_front",
    DOC_PROFILE_BACK_NEW: "cccd_back",
    DOC_PROFILE_BACK_OLD: "cccd_back",
    DOC_PROFILE_UNKNOWN: "unknown",
}
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
_TARGETED_CROP_PRESETS = {
    TRIAGE_STATE_FRONT_OLD: (0.18, 0.16, 0.98, 0.95),
    TRIAGE_STATE_FRONT_NEW: (0.18, 0.16, 0.96, 0.82),
    TRIAGE_STATE_BACK_NEW: (0.04, 0.05, 0.98, 0.68),
    TRIAGE_STATE_BACK_OLD: (0.04, 0.05, 0.86, 0.52),
    TRIAGE_STATE_FRONT_UNKNOWN: (0.0, 0.0, 1.0, 1.0),
    TRIAGE_STATE_UNKNOWN: (0.0, 0.0, 1.0, 1.0),
}

# ─── QR decode — trước AI, miễn phí, chính xác 100% ─────────────────────────
def _zxing_decode_qr(image_obj) -> str | None:
    try:
        results = zxingcpp.read_barcodes(image_obj)
        for r in results:
            if r.format in (zxingcpp.BarcodeFormat.QRCode, zxingcpp.BarcodeFormat.MicroQRCode):
                txt = (r.text or "").strip()
                if txt:
                    return txt
    except Exception:
        return None
    return None


def _cv_to_pil_gray(gray_img):
    if cv2 is None or np is None:
        return None
    try:
        if gray_img.ndim == 2:
            return Image.fromarray(gray_img)
        rgb = cv2.cvtColor(gray_img, cv2.COLOR_BGR2RGB)
        return Image.fromarray(rgb)
    except Exception:
        return None


def _rotate_gray(gray_img, angle: int):
    if angle == 0:
        return gray_img
    if cv2 is None:
        return gray_img
    if angle == 90:
        return cv2.rotate(gray_img, cv2.ROTATE_90_CLOCKWISE)
    if angle == 180:
        return cv2.rotate(gray_img, cv2.ROTATE_180)
    if angle == 270:
        return cv2.rotate(gray_img, cv2.ROTATE_90_COUNTERCLOCKWISE)
    return gray_img


def _qr_variants(file_bytes: bytes):
    variants = []
    try:
        pil_img = Image.open(io.BytesIO(file_bytes))
        if pil_img.mode not in ("RGB", "L"):
            pil_img = pil_img.convert("RGB")
        variants.append(pil_img)
        # Try cheap PIL rotations before heavier OpenCV variants.
        for angle in (90, 180, 270):
            try:
                variants.append(pil_img.rotate(-angle, expand=True))
            except Exception:
                pass
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
        if os.getenv("AI_OCR_QR_UPSCALE", "0") == "1":
            h, w = gray.shape[:2]
            scale = 2.0
            nw, nh = int(w * scale), int(h * scale)
            if nw <= 2600 and nh <= 2600:
                upscaled = cv2.resize(gray, (nw, nh), interpolation=cv2.INTER_CUBIC)
                pil_var = _cv_to_pil_gray(upscaled)
                if pil_var is not None:
                    variants.append(pil_var)

    except Exception:
        pass
    return variants


def try_decode_qr(file_bytes: bytes) -> str | None:
    """Thử giải mã QR code đa bước (nhưng đã rút gọn còn 3-4 variants cực nhanh)."""
    for candidate in _qr_variants(file_bytes):
        decoded = _zxing_decode_qr(candidate)
        if decoded:
            return decoded

    if cv2 is None or np is None:
        return None
    try:
        arr = np.frombuffer(file_bytes, dtype=np.uint8)
        img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
        if img is None:
            return None
        detector = cv2.QRCodeDetector()
        
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        decoded, _, _ = detector.detectAndDecode(gray)
        if decoded:
            return decoded.strip()
    except Exception:
        pass
    return None


def parse_cccd_qr(text: str) -> dict | None:
    """Parse QR CCCD linh hoạt theo pattern thay vì map cứng theo index."""
    raw = (text or "").strip()
    if not raw:
        return None

    parts = [p.strip() for p in re.split(r"[|\r\n;]+", raw) if p and p.strip()]
    if not parts:
        return None

    now_year = datetime.now().year

    def fold(s: str) -> str:
        s = unicodedata.normalize("NFKD", s or "")
        s = "".join(ch for ch in s if not unicodedata.combining(ch))
        return s.replace("đ", "d").replace("Đ", "D").lower()

    def is_name_candidate(s: str) -> bool:
        if not s:
            return False
        if re.search(r"\d", s):
            return False
        words = s.split()
        if not (2 <= len(words) <= 6):
            return False
        fs = fold(s)
        if re.search(
            r"bo cong an|ministry|public security|cong hoa|socialist|identity|citizen|can cuoc|"
            r"noi thuong tru|noi cu tru|place of|date of|quoc tich|nationality|que quan",
            fs,
        ):
            return False
        return True

    def is_address_candidate(s: str) -> bool:
        fs = fold(s)
        return (
            len(s) >= 10
            and (
                "," in s
                or re.search(r"\b(thon|to dan pho|xa|phuong|huyen|quan|tinh|thanh pho|tp)\b", fs)
            )
        )

    def parse_date(raw_date: str) -> str:
        s = re.sub(r"\s+", "", raw_date or "")
        if not s:
            return ""
        m = re.match(r"^(\d{1,2})[/-](\d{1,2})[/-](\d{4})$", s)
        if m:
            dd = int(m.group(1))
            mm = int(m.group(2))
            yyyy = int(m.group(3))
            if 1 <= dd <= 31 and 1 <= mm <= 12 and 1900 <= yyyy <= 2100:
                return f"{dd:02d}/{mm:02d}/{yyyy:04d}"
            return ""
        if re.fullmatch(r"\d{8}", s):
            # ddmmyyyy
            dd = int(s[0:2])
            mm = int(s[2:4])
            yyyy = int(s[4:8])
            if 1 <= dd <= 31 and 1 <= mm <= 12 and 1900 <= yyyy <= 2100:
                return f"{dd:02d}/{mm:02d}/{yyyy:04d}"
            # yyyymmdd fallback
            yyyy = int(s[0:4])
            mm = int(s[4:6])
            dd = int(s[6:8])
            if 1 <= dd <= 31 and 1 <= mm <= 12 and 1900 <= yyyy <= 2100:
                return f"{dd:02d}/{mm:02d}/{yyyy:04d}"
        return ""

    def collect_dates(part: str) -> list[str]:
        out = []
        compact = re.sub(r"\s+", "", part or "")
        for m in re.findall(r"\d{1,2}[/-]\d{1,2}[/-]\d{4}", compact):
            d = parse_date(m)
            if d:
                out.append(d)
        for m in re.findall(r"\d{8}", compact):
            d = parse_date(m)
            if d:
                out.append(d)
        if re.fullmatch(r"\d{16}", compact):
            d1 = parse_date(compact[:8])
            d2 = parse_date(compact[8:])
            if d1:
                out.append(d1)
            if d2:
                out.append(d2)
        # dedupe preserve order
        seen = set()
        uniq = []
        for d in out:
            if d not in seen:
                seen.add(d)
                uniq.append(d)
        return uniq

    cccd = ""
    cccd_idx = -1
    for idx, part in enumerate(parts):
        m = re.search(r"(?<!\d)(\d{12})(?!\d)", part)
        if m:
            cccd = m.group(1)
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

    # Label-first extraction
    for i, part in enumerate(parts):
        fs = fold(part)
        label_val = part
        if ":" in part:
            label_val = part.split(":", 1)[1].strip()
        if not name and re.search(r"ho va ten|ho ten|full name", fs) and label_val:
            if is_name_candidate(label_val):
                name = label_val
            elif i + 1 < len(parts) and is_name_candidate(parts[i + 1]):
                name = parts[i + 1]
        if not gender and re.search(r"\b(nam|nu|nữ|male|female)\b", fs):
            if re.search(r"\b(nam|male)\b", fs):
                gender = "Nam"
            elif re.search(r"\b(nu|nữ|female)\b", fs):
                gender = "Nữ"
        if not address and re.search(r"noi thuong tru|noi cu tru|place of residence", fs):
            if label_val:
                address = label_val
            elif i + 1 < len(parts):
                address = parts[i + 1].strip()
        dvals = collect_dates(part)
        if dvals:
            if re.search(r"ngay sinh|date of birth", fs) and not birth:
                birth = dvals[0]
            if re.search(r"ngay cap|date of issue", fs) and not issue:
                issue = dvals[0]
            if re.search(r"ngay het han|date of expiry|co gia tri den|có giá trị đến", fs) and not expiry:
                expiry = dvals[-1]

    # Heuristic extraction
    if not name:
        preferred = []
        if 0 <= cccd_idx + 1 < len(parts):
            preferred.append(parts[cccd_idx + 1])
        if 0 <= cccd_idx + 2 < len(parts):
            preferred.append(parts[cccd_idx + 2])
        for p in preferred + parts:
            if is_name_candidate(p):
                name = p
                break

    if not gender:
        for part in parts:
            fs = fold(part)
            if re.search(r"\b(nam|male)\b", fs):
                gender = "Nam"
                break
            if re.search(r"\b(nu|nữ|female)\b", fs):
                gender = "Nữ"
                break

    if not address:
        addr_candidates = [p for p in parts if is_address_candidate(p)]
        if addr_candidates:
            addr_candidates.sort(key=len, reverse=True)
            address = addr_candidates[0]

    all_dates = []
    for part in parts:
        all_dates.extend(collect_dates(part))

    def to_year(d: str) -> int:
        return int(d.split("/")[-1]) if d else 0

    if all_dates:
        if not birth:
            birth_candidates = [d for d in all_dates if 1900 <= to_year(d) <= now_year]
            if birth_candidates:
                birth = sorted(birth_candidates, key=to_year)[0]
        if not issue:
            issue_candidates = [d for d in all_dates if 2000 <= to_year(d) <= now_year + 1 and d != birth]
            if issue_candidates:
                issue = sorted(issue_candidates, key=to_year)[0]
        if not expiry:
            expiry_candidates = [d for d in all_dates if to_year(d) >= now_year]
            if expiry_candidates:
                expiry = sorted(expiry_candidates, key=to_year)[-1]

    # Keep only meaningful address text
    if address:
        fs_addr = fold(address)
        if re.search(r"bo cong an|ministry|public security|quoc tich|nationality", fs_addr):
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


def _ascii_fold(text: str) -> str:
    normalized = unicodedata.normalize("NFKD", text or "")
    normalized = "".join(ch for ch in normalized if not unicodedata.combining(ch))
    return normalized.replace("đ", "d").replace("Đ", "D")


def _normalize_text_space(text: str) -> str:
    return re.sub(r"\s+", " ", str(text or "")).strip(" \t\r\n,:;.-")


def _clean_doc_number(value: str) -> str:
    digits = re.sub(r"\D", "", str(value or ""))
    if len(digits) >= 12:
        return digits[:12]
    return digits


def _normalize_date(value: str) -> str:
    raw = str(value or "").replace("-", "/").replace(".", "/")
    match = re.search(r"(?<!\d)(\d{1,2})/(\d{1,2})/(\d{4})(?!\d)", raw)
    if not match:
        return ""
    dd = int(match.group(1))
    mm = int(match.group(2))
    yyyy = int(match.group(3))
    if not (1 <= dd <= 31 and 1 <= mm <= 12 and 1900 <= yyyy <= 2100):
        return ""
    return f"{dd:02d}/{mm:02d}/{yyyy:04d}"


def _normalize_expiry_value(value: str) -> str:
    raw = _normalize_text_space(value)
    if not raw:
        return ""
    if re.search(r"khong\s+thoi\s+han|không\s+thời\s+hạn|indefinite|no\s+expiry", _ascii_fold(raw).lower()):
        return ""
    return _normalize_date(raw)


def _normalize_gender(value: str) -> str:
    folded = _ascii_fold(str(value or "")).lower()
    if re.search(r"\b(nu|female)\b", folded):
        return "Nữ"
    if re.search(r"\b(nam|male)\b", folded):
        return "Nam"
    return ""


def _count_vietnamese_diacritics(text: str) -> int:
    total = 0
    for ch in text or "":
        if ch in {"đ", "Đ"}:
            total += 1
            continue
        if any(unicodedata.combining(c) for c in unicodedata.normalize("NFD", ch)):
            total += 1
    return total


def _empty_person_data() -> dict[str, str]:
    return {
        "so_giay_to": "",
        "ho_ten": "",
        "ngay_sinh": "",
        "gioi_tinh": "",
        "dia_chi": "",
        "ngay_cap": "",
        "ngay_het_han": "",
    }


def _field_rank(field_name: str, source: str) -> int:
    return _FIELD_SOURCE_PRIORITY.get(field_name, {}).get(str(source or "").lower(), 0)


def _profile_expects_address(profile: str) -> bool:
    return profile in {DOC_PROFILE_FRONT_OLD, DOC_PROFILE_BACK_NEW}


def _normalize_system_field(field_name: str, value: Any) -> str:
    if value is None:
        return ""
    text = _normalize_text_space(str(value))
    if not text:
        return ""
    if field_name == "so_giay_to":
        return _clean_doc_number(text)
    if field_name in {"ngay_sinh", "ngay_cap"}:
        return _normalize_date(text)
    if field_name == "ngay_het_han":
        return _normalize_expiry_value(text)
    if field_name == "gioi_tinh":
        return _normalize_gender(text)
    return text


def _candidate_beats_current(field_name: str, incoming_val: str, incoming_source: str, current_val: str, current_source: str) -> bool:
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
    if field_name == "dia_chi":
        return len(incoming_val) > len(current_val)
    if field_name == "so_giay_to":
        return len(_clean_doc_number(incoming_val)) > len(_clean_doc_number(current_val))
    return len(incoming_val) > len(current_val)


def _merge_field_value(
    target_data: dict[str, str],
    field_sources: dict[str, str],
    *,
    field_name: str,
    value: Any,
    source: str,
    profile: str,
) -> None:
    normalized = _normalize_system_field(field_name, value)
    if not normalized:
        return
    source = str(source or "").lower()
    if field_name == "dia_chi" and source != "qr" and not _profile_expects_address(profile):
        return
    if field_name == "ngay_cap" and source != "qr" and profile not in {DOC_PROFILE_BACK_NEW, DOC_PROFILE_BACK_OLD, DOC_PROFILE_UNKNOWN}:
        return

    current_val = target_data.get(field_name, "")
    current_source = field_sources.get(field_name, "")
    if _candidate_beats_current(field_name, normalized, source, current_val, current_source):
        target_data[field_name] = normalized
        field_sources[field_name] = source


def _apply_source_merge(
    target_data: dict[str, str],
    field_sources: dict[str, str],
    incoming: dict[str, Any] | None,
    *,
    source: str,
    profile: str,
) -> None:
    if not incoming:
        return

    alias_map = {
        "so_giay_to_mrz": "so_giay_to",
        "dia_chi_back": "dia_chi",
    }
    for raw_field, value in incoming.items():
        field_name = alias_map.get(raw_field, raw_field)
        if field_name not in _empty_person_data():
            continue
        _merge_field_value(
            target_data,
            field_sources,
            field_name=field_name,
            value=value,
            source=source,
            profile=profile,
        )


def _infer_deterministic_state(*, has_qr: bool, has_mrz: bool) -> str:
    if has_qr and not has_mrz:
        return TRIAGE_STATE_FRONT_OLD
    if has_qr and has_mrz:
        return TRIAGE_STATE_BACK_NEW
    if has_mrz and not has_qr:
        return TRIAGE_STATE_BACK_OLD
    return TRIAGE_STATE_FRONT_UNKNOWN


def _state_to_profile(state: str) -> str:
    mapping = {
        TRIAGE_STATE_FRONT_OLD: DOC_PROFILE_FRONT_OLD,
        TRIAGE_STATE_FRONT_NEW: DOC_PROFILE_FRONT_NEW,
        TRIAGE_STATE_BACK_NEW: DOC_PROFILE_BACK_NEW,
        TRIAGE_STATE_BACK_OLD: DOC_PROFILE_BACK_OLD,
    }
    return mapping.get(state, DOC_PROFILE_UNKNOWN)


def _state_to_doc_type(state: str) -> str:
    if state in {TRIAGE_STATE_FRONT_OLD, TRIAGE_STATE_FRONT_NEW}:
        return "cccd_front"
    if state in {TRIAGE_STATE_BACK_NEW, TRIAGE_STATE_BACK_OLD}:
        return "cccd_back"
    return "unknown"


def _normalize_pair_stem(filename: str) -> str:
    stem = os.path.splitext(os.path.basename(filename or ""))[0].lower()
    stem = _ascii_fold(stem)
    stem = re.sub(
        r"\b(front|back|truoc|sau|mat[\s_-]*truoc|mat[\s_-]*sau|anh|image|cccd|can[\s_-]*cuoc|chip)\b",
        " ",
        stem,
    )
    stem = re.sub(r"[_\-\s]+", " ", stem)
    return stem.strip()


def _mrz_date_to_display(value: str, *, birth: bool) -> str:
    raw = re.sub(r"[^0-9<]", "", str(value or ""))
    if len(raw) < 6:
        return ""
    if raw.startswith("<<<<<<"):
        return ""
    yy = int(raw[0:2])
    mm = int(raw[2:4])
    dd = int(raw[4:6])
    if not (1 <= mm <= 12 and 1 <= dd <= 31):
        return ""
    current_year = datetime.now().year
    if birth:
        century = 1900 if yy > current_year % 100 else 2000
    else:
        century = 2000
    return f"{dd:02d}/{mm:02d}/{century + yy:04d}"


def _normalize_mrz_line(value: str) -> str:
    cleaned = _ascii_fold(str(value or "")).upper()
    cleaned = cleaned.replace("`", "<")
    return re.sub(r"[^A-Z0-9<]", "", cleaned)


def _extract_canonical_cccd_from_mrz_line1(normalized_line1: str) -> str:
    # [WHY] Canonical VN ID MRZ rule: after `IDVNM`, ignore separators like `<`,
    # keep digit order, take the first 22 digits, then use digits 11..22 as the CCCD.
    # [RISK] Taking the first 12 digits after `IDVNM` creates wrong back-side keys and breaks front/back pairing.
    if not normalized_line1.startswith("IDVNM"):
        return ""
    digits_after_prefix = "".join(ch for ch in normalized_line1[5:] if ch.isdigit())
    if len(digits_after_prefix) < 22:
        return ""
    return digits_after_prefix[:22][10:22]


def _parse_cccd_mrz_lines(lines: list[str]) -> dict[str, Any]:
    normalized_lines = [_normalize_mrz_line(line) for line in lines if _normalize_mrz_line(line)]
    if not normalized_lines:
        return {}

    line1 = next((line for line in normalized_lines if line.startswith("IDVNM")), "")
    others = [line for line in normalized_lines if line != line1]
    line2 = next((line for line in others if re.match(r"^\d{6}.", line)), "")
    remaining = [line for line in others if line != line2]
    line3 = remaining[0] if remaining else ""

    if not line1 and len(normalized_lines) >= 1:
        line1 = normalized_lines[0]
    if not line2 and len(normalized_lines) >= 2:
        line2 = normalized_lines[1]
    if not line3 and len(normalized_lines) >= 3:
        line3 = normalized_lines[2]

    # [WHY] Always try the canonical 22-digit MRZ rule first so pairing never uses the first 12 digits by mistake.
    so_giay_to = _extract_canonical_cccd_from_mrz_line1(line1)
    if not so_giay_to and (match := re.search(r"(\d{12})<<\d", line1)):
        so_giay_to = match.group(1)
    elif not so_giay_to and (match := re.search(r"IDVNM\d{10}(\d{12})", line1)):
        so_giay_to = match.group(1)

    ho_ten = ""
    if line3:
        ho_ten = line3.rstrip("<").replace("<<", " ").replace("<", " ").strip()
        ho_ten = re.sub(r"\s+", " ", ho_ten)

    return {
        "mrz_line1": line1,
        "mrz_line2": line2,
        "mrz_line3": line3,
        "so_giay_to": so_giay_to,
        "so_giay_to_mrz": so_giay_to,
        "ho_ten": ho_ten,
        "ho_ten_ascii": ho_ten,
        "ngay_sinh": _mrz_date_to_display(line2[0:6] if len(line2) >= 6 else "", birth=True),
        "gioi_tinh": _normalize_gender("Nam" if len(line2) >= 8 and line2[7:8] == "M" else ("Nữ" if len(line2) >= 8 and line2[7:8] == "F" else "")),
        "ngay_het_han": _mrz_date_to_display(line2[8:14] if len(line2) >= 14 else "", birth=False),
    }


# ─── Prompt — mô tả rõ layout từng loại thẻ để AI không nhầm trường ──────────
SYSTEM_PROMPT = """Vietnamese CCCD/legal doc OCR fast path. Each input image is one document side. Return JSON array.

For every image, return exactly one object with:
{"source_image_index":0,"doc_type":"cccd_front|cccd_back|marriage_cert|land_cert|unknown","data":{"doc_side":"front|back|unknown","doc_version":"old|new|unknown","ho_ten":"","so_giay_to":"","ngay_sinh":"","gioi_tinh":"","dia_chi":"","ngay_cap":"","ngay_het_han":"","mrz_line1":"","mrz_line2":"","mrz_line3":"","so_giay_to_mrz":"","dia_chi_back":""}}

Vietnamese ID card rules:
1. Old CCCD "CĂN CƯỚC CÔNG DÂN" (pre-2024)
- Front usually has QR code.
- Front fields: Họ tên, Ngày sinh, Giới tính, Quốc tịch, Quê quán, Nơi thường trú, Có giá trị đến.
- dia_chi on old front MUST be "Nơi thường trú". Never use "Quê quán" or "Quốc tịch".
- Back usually has fingerprints, ngày cấp, and MRZ lines.

2. New CĂN CƯỚC (2024+, title "CĂN CƯỚC")
- Front has no address. dia_chi = "" on front.
- Back may show QR, chip, "Nơi cư trú", ngày cấp, ngày hết hạn, and MRZ.
- dia_chi_back is the residence text from back if visible.

Rules:
- ho_ten must preserve Vietnamese diacritics exactly as printed.
- Dates must be DD/MM/YYYY.
- ID fields must contain digits only.
- If MRZ is visible, copy full MRZ lines into mrz_line1/2/3 and extract so_giay_to_mrz if readable.
- If unsure about side/version, set doc_side/doc_version to "unknown".
- Never pair documents together, never infer data from another image, never invent missing text.
- Return ONLY JSON array."""

# ─── Image helpers ─────────────────────────────────────────────────────────────
def _load_normalized_image(file_bytes: bytes) -> Image.Image:
    img = Image.open(io.BytesIO(file_bytes))
    img = ImageOps.exif_transpose(img)
    if img.mode not in ("RGB", "L"):
        img = img.convert("RGB")
    return img


def _encode_image_to_base64(img: Image.Image, max_px: int = MAX_IMAGE_PX) -> str:
    w, h = img.size
    scale = min(1.0, max_px / max(w, h))
    if scale < 1.0:
        img = img.resize((int(w * scale), int(h * scale)), Image.LANCZOS)
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=JPEG_QUALITY)
    return base64.b64encode(buf.getvalue()).decode()


def resize_to_base64(file_bytes: bytes, max_px: int = MAX_IMAGE_PX) -> str:
    return _encode_image_to_base64(_load_normalized_image(file_bytes), max_px=max_px)


def _crop_image_to_base64(img: Image.Image, ratios: tuple[float, float, float, float], max_px: int = MAX_IMAGE_PX) -> str:
    width, height = img.size
    left = max(0, min(width - 1, int(width * ratios[0])))
    top = max(0, min(height - 1, int(height * ratios[1])))
    right = max(left + 1, min(width, int(width * ratios[2])))
    bottom = max(top + 1, min(height, int(height * ratios[3])))
    return _encode_image_to_base64(img.crop((left, top, right, bottom)), max_px=max_px)


def extract_cccd_from_mrz(mrz_line1: str) -> str:
    """Trích 12 số CCCD từ dòng MRZ 1 (IDVNM...)."""
    normalized = _normalize_mrz_line(mrz_line1)
    # [WHY] Canonical rule first; regex fallback only handles partial/noisy OCR when the 22-digit block is incomplete.
    canonical = _extract_canonical_cccd_from_mrz_line1(normalized)
    if canonical:
        return canonical
    m = re.search(r"(\d{12})<<\d", normalized)
    if m:
        return m.group(1)
    m2 = re.search(r"(\d{12})<<", normalized)
    return m2.group(1) if m2 else ""


def _try_import_local_ocr_module():
    global _local_ocr_module, _local_ocr_import_attempted
    if _local_ocr_import_attempted:
        return _local_ocr_module
    _local_ocr_import_attempted = True
    try:
        from . import ocr_local as ocr_local_module
        _local_ocr_module = ocr_local_module
    except Exception as exc:
        _logger.info("[AI_OCR_LOCAL_HELPER] local OCR helper unavailable: %s", exc)
        _local_ocr_module = None
    return _local_ocr_module


def _preprocess_for_mrz(img_bgr: "np.ndarray") -> "np.ndarray":
    """Mirror local OCR preprocess for MRZ crop only.

    This is an intentional fork from ocr_local._preprocess so AI OCR can preprocess
    just the bottom crop without changing Local OCR behavior.
    """
    if cv2 is None or np is None:
        return img_bgr
    gray = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY)
    clahe = cv2.createCLAHE(clipLimit=2.2, tileGridSize=(8, 8))
    gray = clahe.apply(gray)
    if _get_env_flag("LOCAL_OCR_DENOISE", True):
        gray = cv2.fastNlMeansDenoising(gray, None, h=7, templateWindowSize=7, searchWindowSize=21)
    blur = cv2.GaussianBlur(gray, (0, 0), sigmaX=1.0)
    sharpened = cv2.addWeighted(gray, 1.6, blur, -0.6, 0)
    return cv2.cvtColor(sharpened, cv2.COLOR_GRAY2BGR)


def _filter_mrz_boxes_in_crop(
    boxes: list[dict[str, Any]],
    crop_shape: tuple[int, int],
    *,
    y_min: float = 0.0,
    y_max: float = MRZ_CROP_FILTER_Y_MAX,
) -> list[dict[str, Any]]:
    """Keep only MRZ-like candidates in crop coordinate space."""
    if np is None:
        return list(boxes or [])

    h = float(max(1, crop_shape[0]))
    w = float(max(1, crop_shape[1]))
    result: list[dict[str, Any]] = []
    for item in boxes or []:
        box = item.get("box")
        if box is None:
            continue
        arr = np.asarray(box, dtype=np.float32)
        center_y = float(arr[:, 1].mean()) / h
        box_w = float(arr[:, 0].max() - arr[:, 0].min()) / w
        box_h = float(arr[:, 1].max() - arr[:, 1].min()) / h
        if (
            y_min <= center_y <= y_max
            and box_w > MRZ_CROP_MIN_WIDTH_RATIO
            and box_h < MRZ_CROP_MAX_HEIGHT_RATIO
        ):
            result.append(item)
    return result


def _extract_local_mrz_data(
    file_bytes: bytes,
    *,
    has_qr: bool,
    settings: dict[str, Any] | None = None,
    filename: str = "",
) -> dict[str, Any]:
    runtime_settings = settings or _get_ai_ocr_settings()
    if not runtime_settings.get("enable_mrz_local", True) or cv2 is None or np is None:
        return {}

    ocr_local = _try_import_local_ocr_module()
    if ocr_local is None:
        return {}

    t_total = perf_counter()
    smart_crop_ms = 0.0
    preprocess_ms = 0.0
    detect_ms = 0.0
    filter_ms = 0.0
    recognize_ms = 0.0
    group_ms = 0.0
    parse_ms = 0.0
    selected_count = 0
    recognized_count = 0
    path_label = "full_image"

    def log_mrz_timing() -> None:
        if not runtime_settings.get("timing_log", True):
            return
        _logger.info(
            "[MRZ_TIMING] %s path=%s selected=%s recognized=%s smart_crop_ms=%.2f preprocess_ms=%.2f "
            "detect_ms=%.2f filter_ms=%.2f recognize_ms=%.2f group_ms=%.2f parse_ms=%.2f total_ms=%.2f",
            filename or "unknown",
            path_label,
            selected_count,
            recognized_count,
            smart_crop_ms,
            preprocess_ms,
            detect_ms,
            filter_ms,
            recognize_ms,
            group_ms,
            parse_ms,
            round((perf_counter() - t_total) * 1000.0, 2),
        )

    try:
        img_arr = np.frombuffer(file_bytes, dtype=np.uint8)
        img_bgr = cv2.imdecode(img_arr, cv2.IMREAD_COLOR)
        if img_bgr is None:
            log_mrz_timing()
            return {}

        use_bottom_crop = False
        crop_result = getattr(ocr_local, "_opencv_smart_crop", None)
        if callable(crop_result):
            t_step = perf_counter()
            smart = crop_result(img_bgr)
            smart_crop_ms = round((perf_counter() - t_step) * 1000.0, 2)
            if smart is not None:
                smart_img, smart_bbox, smart_conf = smart
                x1, y1, x2, y2 = smart_bbox
                crop_area = max(1, x2 - x1) * max(1, y2 - y1)
                full_area = max(1, img_bgr.shape[0] * img_bgr.shape[1])
                area_ratio = float(crop_area) / float(full_area)
                min_conf = float(getattr(ocr_local, "LOCAL_OCR_SMART_CROP_MIN_CONF", 0.22))
                touches_bottom = y2 >= (img_bgr.shape[0] - 5)
                if smart_conf >= min_conf and area_ratio < 0.98 and not touches_bottom:
                    img_bgr = smart_img
                    use_bottom_crop = True

        detect_boxes = getattr(ocr_local, "_rapidocr_detect_boxes", None)
        recognize = getattr(ocr_local, "_recognize_target_boxes_rapidocr", None)
        group_lines = getattr(ocr_local, "_group_lines", None)
        if not all(callable(fn) for fn in (detect_boxes, recognize, group_lines)):
            log_mrz_timing()
            return {}

        triage_state = TRIAGE_STATE_BACK_NEW if has_qr else TRIAGE_STATE_BACK_OLD

        if use_bottom_crop:
            path_label = "bottom_crop"
            h_full = img_bgr.shape[0]
            crop_y = max(0, min(h_full - 1, int(h_full * MRZ_BOTTOM_CROP_RATIO)))
            img_crop_raw = img_bgr[crop_y:, :]
            if img_crop_raw is None or img_crop_raw.size == 0:
                log_mrz_timing()
                return {}

            t_step = perf_counter()
            img_ocr = _preprocess_for_mrz(img_crop_raw)
            preprocess_ms = round((perf_counter() - t_step) * 1000.0, 2)

            t_step = perf_counter()
            boxes, _ = detect_boxes(img_ocr)
            detect_ms = round((perf_counter() - t_step) * 1000.0, 2)

            t_step = perf_counter()
            selected = _filter_mrz_boxes_in_crop(boxes or [], img_ocr.shape[:2])
            filter_ms = round((perf_counter() - t_step) * 1000.0, 2)
        else:
            path_label = "full_image"
            t_step = perf_counter()
            img_ocr = _preprocess_for_mrz(img_bgr)
            preprocess_ms = round((perf_counter() - t_step) * 1000.0, 2)

            t_step = perf_counter()
            boxes, _ = detect_boxes(img_ocr)
            detect_ms = round((perf_counter() - t_step) * 1000.0, 2)

            t_step = perf_counter()
            selected = _filter_mrz_boxes_in_crop(boxes or [], img_ocr.shape[:2], y_min=0.5, y_max=0.67)
            filter_ms = round((perf_counter() - t_step) * 1000.0, 2)

        selected_count = len(selected or [])
        if not selected:
            log_mrz_timing()
            return {}

        t_step = perf_counter()
        recognized, _ = recognize(img_ocr, selected, context=f"ai_ocr:{triage_state}:mrz")
        recognize_ms = round((perf_counter() - t_step) * 1000.0, 2)
        recognized_count = len(recognized or [])

        t_step = perf_counter()
        lines = group_lines(recognized)
        group_ms = round((perf_counter() - t_step) * 1000.0, 2)

        t_step = perf_counter()
        parsed = _parse_cccd_mrz_lines(lines)
        parse_ms = round((perf_counter() - t_step) * 1000.0, 2)
        if parsed.get("so_giay_to"):
            parsed["raw_text"] = "\n".join(lines)
            log_mrz_timing()
            return parsed
    except Exception as exc:
        _logger.info("[AI_OCR_LOCAL_HELPER] MRZ local extract skipped: %s", exc)
    log_mrz_timing()
    return {}


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
def _get_face_cascade():
    global _face_cascade
    if _face_cascade is not None:
        return _face_cascade
    if cv2 is None:
        return None
    try:
        cascade_path = os.path.join(cv2.data.haarcascades, "haarcascade_frontalface_default.xml")
        cascade = cv2.CascadeClassifier(cascade_path)
        if cascade.empty():
            return None
        _face_cascade = cascade
    except Exception:
        _face_cascade = None
    return _face_cascade


def _detect_face_signal(file_bytes: bytes) -> bool:
    cascade = _get_face_cascade()
    if cascade is None or cv2 is None or np is None:
        return False
    try:
        arr = np.frombuffer(file_bytes, dtype=np.uint8)
        img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
        if img is None:
            return False
        h, w = img.shape[:2]
        longest = max(h, w)
        if longest > 720:
            scale = 720.0 / float(longest)
            img = cv2.resize(img, (max(1, int(w * scale)), max(1, int(h * scale))), interpolation=cv2.INTER_AREA)
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        faces = cascade.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=4, minSize=(24, 24))
        return bool(len(faces))
    except Exception:
        return False


def _build_targeted_prompt(state: str, fields: tuple[str, ...]) -> str:
    requested = ", ".join(fields)
    if state == TRIAGE_STATE_FRONT_OLD:
        return (
            "Vietnamese CCCD OCR. This crop is ONLY the FRONT side of old 'CĂN CƯỚC CÔNG DÂN'. "
            f"Extract ONLY these fields: {requested}. "
            "Return JSON array. Schema: "
            '[{"source_image_index":0,"doc_type":"cccd_front","data":{"ho_ten":"","so_giay_to":"","ngay_sinh":"","gioi_tinh":"","dia_chi":""}}]. '
            "dia_chi MUST be 'Nơi thường trú', never 'Quê quán' or 'Quốc tịch'. Dates DD/MM/YYYY. ID digits only."
        )
    if state == TRIAGE_STATE_FRONT_NEW:
        return (
            "Vietnamese CCCD OCR. This crop is ONLY the FRONT side of new 'CĂN CƯỚC'. "
            f"Extract ONLY these fields: {requested}. "
            "Return JSON array. Schema: "
            '[{"source_image_index":0,"doc_type":"cccd_front","data":{"ho_ten":"","so_giay_to":"","ngay_sinh":"","gioi_tinh":""}}]. '
            "Do NOT invent dia_chi because new card front has no address."
        )
    if state == TRIAGE_STATE_BACK_NEW:
        return (
            "Vietnamese CCCD OCR. This crop is ONLY the BACK side of new 'CĂN CƯỚC'. "
            f"Extract ONLY these fields: {requested}. "
            "Return JSON array. Schema: "
            '[{"source_image_index":0,"doc_type":"cccd_back","data":{"dia_chi_back":"","ngay_cap":""}}]. '
            "dia_chi_back MUST be 'Nơi cư trú'. Dates DD/MM/YYYY."
        )
    if state == TRIAGE_STATE_BACK_OLD:
        return (
            "Vietnamese CCCD OCR. This crop is ONLY the BACK side of old 'CĂN CƯỚC CÔNG DÂN'. "
            f"Extract ONLY these fields: {requested}. "
            "Return JSON array. Schema: "
            '[{"source_image_index":0,"doc_type":"cccd_back","data":{"ngay_cap":""}}]. '
            "Dates DD/MM/YYYY. Do not return MRZ again."
        )
    return SYSTEM_PROMPT


def _build_empty_row(index: int, filename: str) -> dict[str, Any]:
    return {
        "index": index,
        "filename": filename,
        "data": _empty_person_data(),
        "field_sources": {},
        "qr_text": "",
        "qr_data": None,
        "mrz_data": {},
        "has_qr": False,
        "has_mrz": False,
        "face_detected": False,
        "state": TRIAGE_STATE_UNKNOWN,
        "profile": DOC_PROFILE_UNKNOWN,
        "doc_type": "unknown",
        "pair_key": "",
        "pair_key_source": "",
        "paired_back_index": None,
        "ai_plan": None,
        "ai_models_run": [],
        "image": None,
        "preprocess_timing": {},
        "_side": "unknown",
    }


def _derive_pair_key(row: dict[str, Any]) -> tuple[str, str]:
    qr_data = row.get("qr_data") or {}
    mrz_data = row.get("mrz_data") or {}
    data = row.get("data") or {}
    field_sources = row.get("field_sources") or {}

    qr_key = _clean_doc_number(qr_data.get("so_giay_to", ""))
    if len(qr_key) == 12:
        return qr_key, "qr"

    mrz_key = _clean_doc_number(
        mrz_data.get("so_giay_to")
        or mrz_data.get("so_giay_to_mrz")
        or data.get("so_giay_to_mrz")
        or extract_cccd_from_mrz(mrz_data.get("mrz_line1", "") or data.get("mrz_line1", ""))
    )
    if len(mrz_key) == 12:
        return mrz_key, "mrz"

    ai_key = _clean_doc_number(data.get("so_giay_to", ""))
    if len(ai_key) == 12:
        return ai_key, str(field_sources.get("so_giay_to", "ai")).lower() or "ai"
    return "", ""


def _sync_row_identity(row: dict[str, Any]) -> None:
    if (
        row.get("profile", DOC_PROFILE_UNKNOWN) == DOC_PROFILE_UNKNOWN
        and row.get("state") in {TRIAGE_STATE_FRONT_OLD, TRIAGE_STATE_FRONT_NEW, TRIAGE_STATE_BACK_NEW, TRIAGE_STATE_BACK_OLD}
    ):
        row["profile"] = _state_to_profile(row["state"])
    row["doc_type"] = _PROFILE_TO_DOC_TYPE.get(row.get("profile", DOC_PROFILE_UNKNOWN), _state_to_doc_type(row.get("state", "")))
    row["_side"] = _PROFILE_TO_SIDE_LABEL.get(row.get("profile", DOC_PROFILE_UNKNOWN), "unknown")
    pair_key, pair_key_source = _derive_pair_key(row)
    row["pair_key"] = pair_key
    row["pair_key_source"] = pair_key_source


def _infer_profile_from_data_hints(data: dict[str, Any]) -> str:
    side = _normalize_text_space(data.get("doc_side", "")).lower()
    version = _normalize_text_space(data.get("doc_version", "")).lower()
    dia_chi = _normalize_text_space(data.get("dia_chi", "") or data.get("dia_chi_back", ""))
    mrz_hint = _normalize_text_space(
        data.get("mrz_line1", "") or data.get("so_giay_to_mrz", "") or data.get("ngay_cap", "")
    )
    has_identity = any(
        _normalize_text_space(data.get(field_name, ""))
        for field_name in ("ho_ten", "so_giay_to", "ngay_sinh", "gioi_tinh")
    )

    if side == "back":
        if version == "new" or dia_chi:
            return DOC_PROFILE_BACK_NEW
        return DOC_PROFILE_BACK_OLD
    if side == "front":
        if version == "old" or dia_chi:
            return DOC_PROFILE_FRONT_OLD
        return DOC_PROFILE_FRONT_NEW
    if mrz_hint:
        if dia_chi:
            return DOC_PROFILE_BACK_NEW
        return DOC_PROFILE_BACK_OLD
    if has_identity:
        return DOC_PROFILE_FRONT_OLD if dia_chi else DOC_PROFILE_FRONT_NEW
    return DOC_PROFILE_UNKNOWN


def _build_initial_ai_snapshot_sync(index: int, filename: str, file_bytes: bytes, settings_snapshot: dict[str, Any]) -> dict[str, Any]:
    row = _build_empty_row(index, filename)
    t_total = perf_counter()
    face_ms = 0.0
    t_qr = perf_counter()
    row["qr_text"] = try_decode_qr(file_bytes) or ""
    qr_ms = round((perf_counter() - t_qr) * 1000.0, 2)
    row["has_qr"] = bool(row["qr_text"])
    row["qr_data"] = parse_cccd_qr(row["qr_text"]) if row["qr_text"] else None
    mrz_ms = 0.0
    row["mrz_data"] = {}
    row["has_mrz"] = False
    row["state"] = TRIAGE_STATE_UNKNOWN if row["has_qr"] else TRIAGE_STATE_FRONT_UNKNOWN
    row["profile"] = DOC_PROFILE_UNKNOWN
    row["doc_type"] = "unknown"
    _apply_source_merge(row["data"], row["field_sources"], row["qr_data"], source="qr", profile=row["profile"])
    _sync_row_identity(row)
    total_ms = round((perf_counter() - t_total) * 1000.0, 2)
    return {
        "index": row["index"],
        "filename": row["filename"],
        "data": dict(row["data"]),
        "field_sources": dict(row["field_sources"]),
        "qr_text": row["qr_text"],
        "qr_data": dict(row["qr_data"] or {}) if row["qr_data"] else None,
        "has_qr": row["has_qr"],
        "mrz_data": dict(row["mrz_data"] or {}),
        "has_mrz": row["has_mrz"],
        "face_detected": row["face_detected"],
        "state": row["state"],
        "profile": row["profile"],
        "doc_type": row["doc_type"],
        "pair_key": row["pair_key"],
        "pair_key_source": row["pair_key_source"],
        "preprocess_timing": {
            "face_ms": face_ms,
            "qr_ms": qr_ms,
            "mrz_ms": mrz_ms,
            "total_ms": total_ms,
        },
    }


def _row_from_snapshot(snapshot: dict[str, Any], *, path: str) -> dict[str, Any]:
    row = _build_empty_row(int(snapshot["index"]), str(snapshot.get("filename") or "unknown"))
    row["data"] = dict(snapshot.get("data") or {})
    row["field_sources"] = dict(snapshot.get("field_sources") or {})
    row["qr_text"] = str(snapshot.get("qr_text") or "")
    row["qr_data"] = dict(snapshot["qr_data"]) if isinstance(snapshot.get("qr_data"), dict) else snapshot.get("qr_data")
    row["has_qr"] = bool(snapshot.get("has_qr", False))
    row["mrz_data"] = dict(snapshot.get("mrz_data") or {})
    row["has_mrz"] = bool(snapshot.get("has_mrz", False))
    row["face_detected"] = bool(snapshot.get("face_detected", False))
    row["state"] = str(snapshot.get("state") or TRIAGE_STATE_UNKNOWN)
    row["profile"] = str(snapshot.get("profile") or DOC_PROFILE_UNKNOWN)
    row["doc_type"] = str(snapshot.get("doc_type") or "unknown")
    row["pair_key"] = str(snapshot.get("pair_key") or "")
    row["pair_key_source"] = str(snapshot.get("pair_key_source") or "")
    row["preprocess_timing"] = dict(snapshot.get("preprocess_timing") or {})
    row["preprocess_timing"]["path"] = path
    _sync_row_identity(row)
    return row


def _build_initial_ai_row(index: int, filename: str, file_bytes: bytes, settings: dict[str, Any], *, path: str = "fallback") -> dict[str, Any]:
    snapshot = _build_initial_ai_snapshot_sync(index, filename, file_bytes, settings)
    return _row_from_snapshot(snapshot, path=path)


def _warmup_ai_preprocess_worker() -> int:
    return os.getpid()


def init_ai_preprocess_pool(n_workers: int) -> None:
    global _PREPROCESS_POOL, _PREPROCESS_POOL_WORKERS
    if n_workers <= 1:
        shutdown_ai_preprocess_pool()
        return
    if _PREPROCESS_POOL is not None and _PREPROCESS_POOL_WORKERS == n_workers:
        return
    shutdown_ai_preprocess_pool()
    mp_context = multiprocessing.get_context("spawn")
    _PREPROCESS_POOL = ProcessPoolExecutor(max_workers=n_workers, mp_context=mp_context)
    _PREPROCESS_POOL_WORKERS = n_workers


def warmup_ai_preprocess_pool(timeout_seconds: float = 90.0) -> None:
    pool = _PREPROCESS_POOL
    if pool is None or _PREPROCESS_POOL_WORKERS <= 1:
        return

    unique_pids: set[int] = set()
    max_attempts = max(_PREPROCESS_POOL_WORKERS * 4, _PREPROCESS_POOL_WORKERS)
    attempts = 0
    t_deadline = perf_counter() + timeout_seconds

    while len(unique_pids) < _PREPROCESS_POOL_WORKERS and attempts < max_attempts and perf_counter() < t_deadline:
        remaining = max_attempts - attempts
        batch_size = min(_PREPROCESS_POOL_WORKERS, remaining)
        futures = [pool.submit(_warmup_ai_preprocess_worker) for _ in range(batch_size)]
        attempts += batch_size
        wait_timeout = max(0.1, t_deadline - perf_counter())
        try:
            for future in as_completed(futures, timeout=wait_timeout):
                try:
                    unique_pids.add(int(future.result()))
                except Exception as exc:
                    _logger.warning("[AI_OCR_POOL] worker warmup failed: %s", exc)
        except FuturesTimeoutError:
            _logger.warning("[AI_OCR_POOL] worker warmup timed out while waiting for result")
            break

    if len(unique_pids) < _PREPROCESS_POOL_WORKERS:
        _logger.warning(
            "[AI_OCR_POOL] warmup incomplete expected_workers=%s warmed_workers=%s attempts=%s",
            _PREPROCESS_POOL_WORKERS,
            len(unique_pids),
            attempts,
        )
        return

    _logger.info(
        "[AI_OCR_POOL] warmup ok workers=%s warmed_pids=%s",
        _PREPROCESS_POOL_WORKERS,
        ",".join(str(pid) for pid in sorted(unique_pids)),
    )


def shutdown_ai_preprocess_pool() -> None:
    global _PREPROCESS_POOL, _PREPROCESS_POOL_WORKERS
    if _PREPROCESS_POOL is not None:
        _PREPROCESS_POOL.shutdown(wait=False, cancel_futures=True)
    _PREPROCESS_POOL = None
    _PREPROCESS_POOL_WORKERS = 0


def _resolve_front_new_pairs(rows: list[dict[str, Any]]) -> None:
    def assign_pairs(back_state: str, front_state: str, front_profile: str) -> None:
        front_unknown_rows = [
            row
            for row in rows
            if row.get("state") in {TRIAGE_STATE_FRONT_UNKNOWN, TRIAGE_STATE_FRONT_NEW}
            and not row.get("pair_key")
            and not row.get("has_mrz")
        ]
        unmatched_back_rows = [row for row in rows if row.get("state") == back_state and row.get("pair_key")]
        if not front_unknown_rows or not unmatched_back_rows:
            return

        used_back_indexes: set[int] = set()
        back_by_stem: dict[str, list[dict[str, Any]]] = {}
        for row in unmatched_back_rows:
            back_by_stem.setdefault(_normalize_pair_stem(row.get("filename", "")), []).append(row)

        for front_row in front_unknown_rows:
            stem = _normalize_pair_stem(front_row.get("filename", ""))
            candidates = [row for row in back_by_stem.get(stem, []) if row["index"] not in used_back_indexes]
            if not candidates:
                continue
            chosen = sorted(candidates, key=lambda item: abs(item["index"] - front_row["index"]))[0]
            used_back_indexes.add(chosen["index"])
            front_row["state"] = front_state
            front_row["profile"] = front_profile
            front_row["paired_back_index"] = chosen["index"]
            front_row["pair_key"] = chosen.get("pair_key", "")
            front_row["pair_key_source"] = chosen.get("pair_key_source", "")
            front_row["doc_type"] = "cccd_front"
            front_row["_side"] = _PROFILE_TO_SIDE_LABEL[front_profile]

        remaining_fronts = [row for row in front_unknown_rows if row.get("state") == TRIAGE_STATE_FRONT_UNKNOWN]
        remaining_backs = [row for row in unmatched_back_rows if row["index"] not in used_back_indexes]
        if remaining_fronts and remaining_backs and len(remaining_fronts) == len(remaining_backs):
            for front_row, back_row in zip(sorted(remaining_fronts, key=lambda item: item["index"]), sorted(remaining_backs, key=lambda item: item["index"])):
                front_row["state"] = front_state
                front_row["profile"] = front_profile
                front_row["paired_back_index"] = back_row["index"]
                front_row["pair_key"] = back_row.get("pair_key", "")
                front_row["pair_key_source"] = back_row.get("pair_key_source", "")
                front_row["doc_type"] = "cccd_front"
                front_row["_side"] = _PROFILE_TO_SIDE_LABEL[front_profile]

    assign_pairs(TRIAGE_STATE_BACK_NEW, TRIAGE_STATE_FRONT_NEW, DOC_PROFILE_FRONT_NEW)
    assign_pairs(TRIAGE_STATE_BACK_OLD, TRIAGE_STATE_FRONT_OLD, DOC_PROFILE_FRONT_OLD)


def _is_field_valid(field_name: str, value: str, profile: str) -> bool:
    text = _normalize_text_space(value)
    if field_name == "so_giay_to":
        return len(_clean_doc_number(text)) == 12
    if field_name in {"ngay_sinh", "ngay_cap"}:
        return bool(_normalize_date(text))
    if field_name == "ngay_het_han":
        return text == "" or bool(_normalize_expiry_value(text))
    if field_name == "gioi_tinh":
        return bool(_normalize_gender(text))
    if field_name == "dia_chi":
        return True if not _profile_expects_address(profile) else bool(text)
    return bool(text)


def _row_is_complete(row: dict[str, Any]) -> bool:
    profile = row.get("profile", DOC_PROFILE_UNKNOWN)
    required = _PROFILE_REQUIRED_FIELDS.get(profile, _PROFILE_REQUIRED_FIELDS[DOC_PROFILE_UNKNOWN])
    data = row.get("data") or {}
    for field_name in required:
        if not _is_field_valid(field_name, data.get(field_name, ""), profile):
            return False
    return True


def _field_budget_for_targets(targets: tuple[str, ...], *, full_mode: bool) -> int | None:
    if full_mode:
        return None
    if len(targets) <= 1:
        return 96
    if len(targets) <= 2:
        return 160
    return 220


def _plan_crop_ratios(state: str) -> tuple[float, float, float, float]:
    crop_key = TRIAGE_STATE_FRONT_UNKNOWN if state == TRIAGE_STATE_FRONT_UNKNOWN else state
    return _TARGETED_CROP_PRESETS.get(crop_key, (0.0, 0.0, 1.0, 1.0))


def _missing_required_fields(row: dict[str, Any]) -> list[str]:
    profile = row.get("profile", DOC_PROFILE_UNKNOWN)
    required = _PROFILE_REQUIRED_FIELDS.get(profile, _PROFILE_REQUIRED_FIELDS[DOC_PROFILE_UNKNOWN])
    data = row.get("data") or {}
    return [field_name for field_name in required if not _is_field_valid(field_name, data.get(field_name, ""), profile)]


def _short_mrz_marker(value: str) -> str:
    text = _normalize_text_space(value)
    if not text:
        return ""
    return text[:20]


def _log_ai_ocr_diag(message: str, *, settings: dict[str, Any] | None = None) -> None:
    runtime_settings = settings or _get_ai_ocr_settings()
    if not runtime_settings.get("timing_log", False):
        return
    _logger.info("[AI_OCR_DIAG] %s", message)


def _build_ai_plan(rows: list[dict[str, Any]], settings: dict[str, Any]) -> list[dict[str, Any]]:
    if not rows:
        return []

    plans: list[dict[str, Any]] = []

    for row in rows:
        profile = row.get("profile", DOC_PROFILE_UNKNOWN)
        state = row.get("state", TRIAGE_STATE_UNKNOWN)
        missing_before = tuple(_missing_required_fields(row))
        plan = {"mode": "full", "targets": ()}
        plan.update(
            {
                "record_index": row["index"],
                "model": _get_primary_model(),
                "prompt": SYSTEM_PROMPT,
                "image_detail": "high",
                "max_tokens_per_image": _field_budget_for_targets(plan["targets"], full_mode=True),
                "crop_ratios": None,
            }
        )
        row["_diag_missing_before"] = list(missing_before)
        row["ai_plan"] = plan
        plans.append(plan)
        _log_ai_ocr_diag(
            (
                "phase=plan img#%s file=%s mode=full state=%s profile=%s pair_key=%s pair_key_source=%s "
                "has_qr=%s has_mrz=%s face_detected=%s missing=%s"
            )
            % (
                row["index"],
                row.get("filename", "unknown"),
                state,
                profile,
                row.get("pair_key", ""),
                row.get("pair_key_source", ""),
                row.get("has_qr", False),
                row.get("has_mrz", False),
                row.get("face_detected", False),
                ",".join(missing_before) or "-",
            ),
            settings=settings,
        )

    return plans


def _infer_profile_from_ai(current_profile: str, ai_doc_type: str, ai_data: dict[str, Any]) -> str:
    if ai_doc_type == "cccd_back":
        if _normalize_text_space(ai_data.get("doc_version", "")).lower() == "new":
            return DOC_PROFILE_BACK_NEW
        if _normalize_text_space(ai_data.get("dia_chi_back") or ai_data.get("dia_chi") or ""):
            return DOC_PROFILE_BACK_NEW
        if current_profile in {DOC_PROFILE_UNKNOWN, DOC_PROFILE_BACK_OLD, DOC_PROFILE_BACK_NEW}:
            return DOC_PROFILE_BACK_OLD if current_profile == DOC_PROFILE_UNKNOWN else current_profile
        return current_profile
    if ai_doc_type == "cccd_front":
        if _normalize_text_space(ai_data.get("doc_version", "")).lower() == "old":
            return DOC_PROFILE_FRONT_OLD
        if _normalize_text_space(ai_data.get("dia_chi", "")):
            return DOC_PROFILE_FRONT_OLD
        if current_profile in {DOC_PROFILE_UNKNOWN, DOC_PROFILE_FRONT_NEW, DOC_PROFILE_FRONT_OLD}:
            return DOC_PROFILE_FRONT_NEW if current_profile == DOC_PROFILE_UNKNOWN else current_profile
        return current_profile
    hinted = _infer_profile_from_data_hints(ai_data)
    if hinted != DOC_PROFILE_UNKNOWN:
        return hinted
    return DOC_PROFILE_UNKNOWN


def _apply_ai_rows_to_record(row: dict[str, Any], ai_rows: list[dict[str, Any]], *, model: str) -> None:
    if not ai_rows:
        return
    before_profile = row.get("profile", DOC_PROFILE_UNKNOWN)
    before_state = row.get("state", TRIAGE_STATE_UNKNOWN)
    before_pair_key = row.get("pair_key", "")
    before_pair_key_source = row.get("pair_key_source", "")
    before_missing = tuple(_missing_required_fields(row))
    ai_identity_rows: list[dict[str, Any]] = []
    for ai_row in ai_rows:
        ai_data = dict(ai_row.get("data") or {})
        ai_identity_rows.append(
            {
                "doc_type": ai_row.get("doc_type", "unknown"),
                "so_giay_to": _clean_doc_number(ai_data.get("so_giay_to", "")),
                "so_giay_to_mrz": _clean_doc_number(ai_data.get("so_giay_to_mrz", "")),
                "mrz_line1": _short_mrz_marker(ai_data.get("mrz_line1", "")),
                "dia_chi": bool(_normalize_text_space(ai_data.get("dia_chi", "") or ai_data.get("dia_chi_back", ""))),
                "ngay_cap": bool(_normalize_date(ai_data.get("ngay_cap", ""))),
            }
        )
        if "dia_chi_back" in ai_data and not ai_data.get("dia_chi"):
            ai_data["dia_chi"] = ai_data.get("dia_chi_back", "")
        row["profile"] = _infer_profile_from_ai(row.get("profile", DOC_PROFILE_UNKNOWN), ai_row.get("doc_type", "unknown"), ai_data)
        if row["profile"] == DOC_PROFILE_FRONT_NEW:
            row["state"] = TRIAGE_STATE_FRONT_NEW
        elif row["profile"] == DOC_PROFILE_FRONT_OLD:
            row["state"] = TRIAGE_STATE_FRONT_OLD
        elif row["profile"] == DOC_PROFILE_BACK_NEW:
            row["state"] = TRIAGE_STATE_BACK_NEW
        elif row["profile"] == DOC_PROFILE_BACK_OLD:
            row["state"] = TRIAGE_STATE_BACK_OLD
        _apply_source_merge(row["data"], row["field_sources"], ai_data, source="ai", profile=row.get("profile", DOC_PROFILE_UNKNOWN))
        if ai_data.get("mrz_line1") or ai_data.get("so_giay_to_mrz"):
            row["mrz_data"] = {
                **row.get("mrz_data", {}),
                "mrz_line1": ai_data.get("mrz_line1", "") or row.get("mrz_data", {}).get("mrz_line1", ""),
                "so_giay_to_mrz": ai_data.get("so_giay_to_mrz", "")
                or row.get("mrz_data", {}).get("so_giay_to_mrz", ""),
            }
            row["has_mrz"] = bool(
                row["mrz_data"].get("mrz_line1") or row["mrz_data"].get("so_giay_to_mrz")
            )
        row["doc_type"] = ai_row.get("doc_type") or row.get("doc_type", "unknown")
    row["ai_models_run"].append(model)
    _sync_row_identity(row)
    after_missing = tuple(_missing_required_fields(row))
    should_log = (
        (row.get("ai_plan") or {}).get("mode") == "full"
        or model == _get_escalation_model()
        or before_pair_key_source != row.get("pair_key_source", "")
        or before_profile != row.get("profile", DOC_PROFILE_UNKNOWN)
    )
    if should_log:
        ai_debug = ";".join(
            (
                f"{item['doc_type']}"
                f":so={item['so_giay_to'] or '-'}"
                f":mrz_so={item['so_giay_to_mrz'] or '-'}"
                f":mrz={item['mrz_line1'] or '-'}"
                f":dia_chi={int(item['dia_chi'])}"
                f":ngay_cap={int(item['ngay_cap'])}"
            )
            for item in ai_identity_rows
        ) or "-"
        _log_ai_ocr_diag(
            (
                "phase=apply img#%s file=%s model=%s mode=%s before_state=%s before_profile=%s after_state=%s "
                "after_profile=%s before_pair_key=%s before_pair_key_source=%s after_pair_key=%s after_pair_key_source=%s "
                "missing_before=%s missing_after=%s ai=%s"
            )
            % (
                row.get("index"),
                row.get("filename", "unknown"),
                model,
                (row.get("ai_plan") or {}).get("mode", "none"),
                before_state,
                before_profile,
                row.get("state", TRIAGE_STATE_UNKNOWN),
                row.get("profile", DOC_PROFILE_UNKNOWN),
                before_pair_key,
                before_pair_key_source,
                row.get("pair_key", ""),
                row.get("pair_key_source", ""),
                ",".join(before_missing) or "-",
                ",".join(after_missing) or "-",
                ai_debug,
            )
        )

def _load_cached_ai_image(record_index: int, file_bytes_map: dict[int, bytes], image_cache: dict[int, Image.Image]) -> Image.Image:
    image = image_cache.get(record_index)
    if image is not None:
        return image
    file_bytes = file_bytes_map.get(record_index)
    if file_bytes is None:
        raise KeyError(f"Missing file bytes for record_index={record_index}")
    image = _load_normalized_image(file_bytes)
    image_cache[record_index] = image
    return image


def _materialize_ai_plan_payloads(
    plans: list[dict[str, Any]],
    file_bytes_map: dict[int, bytes],
    image_cache: dict[int, Image.Image],
) -> list[dict[str, Any]]:
    payloads: list[dict[str, Any]] = []
    for plan in plans:
        record_index = int(plan["record_index"])
        image = _load_cached_ai_image(record_index, file_bytes_map, image_cache)
        payload = dict(plan)
        crop_ratios = payload.pop("crop_ratios", None)
        if payload["mode"] == "full":
            payload["image_b64"] = _encode_image_to_base64(image)
        else:
            payload["image_b64"] = _crop_image_to_base64(image, crop_ratios or (0.0, 0.0, 1.0, 1.0))
        payloads.append(payload)
    return payloads


async def _execute_ai_plans(
    plans: list[dict[str, Any]],
    *,
    file_bytes_map: dict[int, bytes],
    image_cache: dict[int, Image.Image],
) -> dict[int, list[dict[str, Any]]]:
    grouped: dict[tuple[str, str, str, int | None], list[dict[str, Any]]] = {}
    for plan in _materialize_ai_plan_payloads(plans, file_bytes_map, image_cache):
        key = (plan["model"], plan["prompt"], plan["image_detail"], plan.get("max_tokens_per_image"))
        grouped.setdefault(key, []).append(plan)

    results_by_index: dict[int, list[dict[str, Any]]] = {}
    for (model, prompt, image_detail, max_tokens_per_image), group in grouped.items():
        rows = await call_vision_batch_v2(
            [item["image_b64"] for item in group],
            prompt=prompt,
            model=model,
            source_indexes=[item["record_index"] for item in group],
            image_detail=image_detail,
            openai_max_tokens_per_image=max_tokens_per_image,
        )
        for row in rows:
            record_index = row.get("_source_image_index")
            if isinstance(record_index, int):
                results_by_index.setdefault(record_index, []).append(row)
    return results_by_index


def _build_escalation_plans(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    plans: list[dict[str, Any]] = []
    escalation_model = _get_escalation_model()
    for row in rows:
        ai_plan = row.get("ai_plan")
        if not ai_plan or _row_is_complete(row):
            continue
        plan = dict(ai_plan)
        plan["model"] = escalation_model
        plans.append(plan)
        _log_ai_ocr_diag(
            (
                "phase=escalation-plan img#%s file=%s model=%s mode=%s state=%s profile=%s pair_key=%s "
                "pair_key_source=%s missing=%s"
            )
            % (
                row.get("index"),
                row.get("filename", "unknown"),
                escalation_model,
                ai_plan.get("mode", "none"),
                row.get("state", TRIAGE_STATE_UNKNOWN),
                row.get("profile", DOC_PROFILE_UNKNOWN),
                row.get("pair_key", ""),
                row.get("pair_key_source", ""),
                ",".join(_missing_required_fields(row)) or "-",
            )
        )
    return plans


def _log_ai_ocr_timing(message: str, *, level: str = "info", settings: dict[str, Any] | None = None) -> None:
    runtime_settings = settings or _get_ai_ocr_settings()
    if not runtime_settings["timing_log"]:
        return
    logger_method = _logger.warning if level == "warning" else _logger.info
    logger_method("[AI_OCR_TIMING] %s", message)


def _coerce_snapshot_result(
    *,
    index: int,
    filename: str,
    file_bytes: bytes,
    settings: dict[str, Any],
    result: Any,
) -> dict[str, Any]:
    if isinstance(result, BaseException):
        _logger.warning("[AI_OCR_PREPROCESS] img#%s file=%s process_failed=%s fallback=sequential", index, filename, result)
        snapshot = _build_initial_ai_snapshot_sync(index, filename, file_bytes, settings)
        return _row_from_snapshot(snapshot, path="fallback")
    return _row_from_snapshot(dict(result), path="process")


async def _preprocess_ai_file_items(
    file_items: list[dict[str, Any]],
    settings: dict[str, Any],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    if not file_items:
        return [], []

    rows: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    use_pool = settings.get("preprocess_workers", 0) > 1 and _PREPROCESS_POOL is not None

    if not use_pool:
        for item in file_items:
            try:
                rows.append(
                    _build_initial_ai_row(
                        item["index"],
                        item["filename"],
                        item["bytes"],
                        settings,
                        path="fallback",
                    )
                )
            except Exception as exc:
                errors.append({"filename": item["filename"], "error": str(exc)})
        return rows, errors

    loop = asyncio.get_running_loop()
    tasks = [
        loop.run_in_executor(
            _PREPROCESS_POOL,
            _build_initial_ai_snapshot_sync,
            item["index"],
            item["filename"],
            item["bytes"],
            settings,
        )
        for item in file_items
    ]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    for item, result in zip(file_items, results):
        try:
            row = _coerce_snapshot_result(
                index=item["index"],
                filename=item["filename"],
                file_bytes=item["bytes"],
                settings=settings,
                result=result,
            )
            rows.append(row)
        except Exception as exc:
            errors.append({"filename": item["filename"], "error": str(exc)})
    return rows, errors


def _log_ai_ocr_row_timing(row: dict[str, Any], *, settings: dict[str, Any]) -> None:
    if not settings.get("timing_log", False):
        return
    timing = dict(row.get("preprocess_timing") or {})
    total_ms = float(timing.get("total_ms", 0.0) or 0.0)
    level = "warning" if total_ms >= float(settings.get("timing_slow_ms", 2500.0)) else "info"
    message = (
        "img#%s file=%s path=%s state=%s profile=%s pair_key_source=%s "
        "has_qr=%s has_mrz=%s face_detected=%s preprocess_ms=%.2f qr_ms=%.2f mrz_ms=%.2f ai_plan_mode=%s"
        % (
            row.get("index"),
            row.get("filename", "unknown"),
            timing.get("path", "fallback"),
            row.get("state", TRIAGE_STATE_UNKNOWN),
            row.get("profile", DOC_PROFILE_UNKNOWN),
            row.get("pair_key_source", ""),
            row.get("has_qr", False),
            row.get("has_mrz", False),
            row.get("face_detected", False),
            total_ms,
            float(timing.get("qr_ms", 0.0) or 0.0),
            float(timing.get("mrz_ms", 0.0) or 0.0),
            (row.get("ai_plan") or {}).get("mode", "none"),
        )
    )
    _log_ai_ocr_timing(message, level=level, settings=settings)


def _chunk_indexed_images(
    images_b64: list[str],
    batch_size: int,
    *,
    source_indexes: list[int] | None = None,
) -> list[list[tuple[int, str]]]:
    if source_indexes is not None and len(source_indexes) == len(images_b64):
        indexed_images = list(zip(source_indexes, images_b64))
    else:
        indexed_images = list(enumerate(images_b64))
    return [indexed_images[start:start + batch_size] for start in range(0, len(indexed_images), batch_size)]


def _coerce_source_image_index(value: Any, total_images: int) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        candidate = value
    elif isinstance(value, str) and value.strip().isdigit():
        candidate = int(value.strip())
    else:
        return None
    if 0 <= candidate < total_images:
        return candidate
    return None


def _normalize_vision_results(parsed: Any, fallback_indexes: list[int], total_images: int) -> list[dict]:
    if isinstance(parsed, dict):
        parsed_items = [parsed]
    elif isinstance(parsed, list) and parsed:
        parsed_items = parsed
    else:
        return [
            {"doc_type": "unknown", "data": {}, "_source_image_index": image_index}
            for image_index in fallback_indexes
        ]

    normalized: list[dict] = []
    last_fallback = fallback_indexes[-1] if fallback_indexes else 0
    single_fallback = fallback_indexes[0] if len(fallback_indexes) == 1 else None

    for position, item in enumerate(parsed_items):
        row = dict(item) if isinstance(item, dict) else {"doc_type": "unknown", "data": {}}
        source_index = _coerce_source_image_index(row.pop("source_image_index", None), total_images)
        if source_index is None:
            if single_fallback is not None:
                source_index = single_fallback
            elif position < len(fallback_indexes):
                source_index = fallback_indexes[position]
            else:
                source_index = last_fallback
        row["_source_image_index"] = source_index
        if not isinstance(row.get("doc_type"), str) or not row.get("doc_type"):
            row["doc_type"] = "unknown"
        if not isinstance(row.get("data"), dict):
            row["data"] = {}
        normalized.append(row)
    return normalized


def _should_retry_status(status_code: int) -> bool:
    return status_code in {408, 409, 425, 429} or 500 <= status_code < 600


def _retry_delay_seconds(
    attempt_number: int,
    retry_after: str | None,
    *,
    base_delay_ms: int,
) -> float:
    if retry_after:
        try:
            return max(float(retry_after), base_delay_ms / 1000.0)
        except (TypeError, ValueError):
            pass
    return (base_delay_ms / 1000.0) * attempt_number


def _extract_vision_text(resp_json: dict, *, is_gemini: bool) -> str:
    if is_gemini:
        try:
            parts = resp_json["candidates"][0]["content"]["parts"]
        except (KeyError, IndexError, TypeError):
            return ""
        text_parts = [part.get("text", "") for part in parts if isinstance(part, dict) and part.get("text")]
        return "\n".join(text_parts).strip()

    try:
        message_content = resp_json["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError):
        return ""

    if isinstance(message_content, str):
        return message_content
    if isinstance(message_content, list):
        text_parts = []
        for part in message_content:
            if not isinstance(part, dict):
                continue
            if part.get("type") == "text" and part.get("text"):
                text_parts.append(str(part["text"]))
        return "\n".join(text_parts).strip()
    return ""


async def _post_vision_request_with_retry(
    client: httpx.AsyncClient,
    *,
    url: str,
    headers: dict[str, str] | None,
    payload: dict[str, Any],
    model: str,
    settings: dict[str, Any],
    chunk_label: str,
) -> httpx.Response:
    attempts = settings["retry_count"] + 1
    last_error = ""

    for attempt in range(1, attempts + 1):
        try:
            response = await client.post(url, headers=headers, json=payload)
        except httpx.RequestError as exc:
            last_error = str(exc)
            if attempt >= attempts:
                raise HTTPException(status_code=502, detail=f"Khong the ket noi toi API: {last_error}")
            delay_seconds = _retry_delay_seconds(
                attempt,
                None,
                base_delay_ms=settings["retry_base_delay_ms"],
            )
            _logger.warning(
                "[AI_OCR_RETRY] model=%s chunk=%s attempt=%s/%s reason=request_error delay_s=%.2f error=%s",
                model,
                chunk_label,
                attempt,
                attempts,
                delay_seconds,
                last_error,
            )
            await asyncio.sleep(delay_seconds)
            continue

        if response.is_success:
            return response
        last_error = response.text[:300]
        if attempt >= attempts or not _should_retry_status(response.status_code):
            raise HTTPException(status_code=502, detail=f"API loi ({model}): {last_error}")

        delay_seconds = _retry_delay_seconds(
            attempt,
            response.headers.get("retry-after"),
            base_delay_ms=settings["retry_base_delay_ms"],
        )
        _logger.warning(
            "[AI_OCR_RETRY] model=%s chunk=%s attempt=%s/%s status=%s delay_s=%.2f",
            model,
            chunk_label,
            attempt,
            attempts,
            response.status_code,
            delay_seconds,
        )
        await asyncio.sleep(delay_seconds)

    raise HTTPException(status_code=502, detail=f"API loi ({model}): {last_error}")


async def _call_vision_provider_chunk(
    client: httpx.AsyncClient,
    *,
    chunk: list[tuple[int, str]],
    total_images: int,
    model: str,
    api_key: str,
    is_gemini: bool,
    settings: dict[str, Any],
    prompt: str = SYSTEM_PROMPT,
    image_detail: str = "high",
    openai_max_tokens_per_image: int | None = None,
    allow_split_fallback: bool = True,
) -> list[dict]:
    fallback_indexes = [image_index for image_index, _ in chunk]
    chunk_label = f"{fallback_indexes[0]}-{fallback_indexes[-1]}"
    max_tokens_per_image = openai_max_tokens_per_image or settings["openai_max_tokens_per_image"]

    if is_gemini:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
        parts: list[dict[str, Any]] = [{"text": prompt}]
        for image_index, b64 in chunk:
            parts.append(
                {
                    "text": (
                        f"SOURCE_IMAGE_INDEX: {image_index}\n"
                        f'Return every JSON object for this image with "source_image_index": {image_index}.'
                    )
                }
            )
            parts.append({"inline_data": {"mime_type": "image/jpeg", "data": b64}})
        payload = {
            "contents": [{"parts": parts}],
            "generationConfig": {"temperature": 0.0},
        }
        response = await _post_vision_request_with_retry(
            client,
            url=url,
            headers=None,
            payload=payload,
            model=model,
            settings=settings,
            chunk_label=chunk_label,
        )
    else:
        content: list[dict[str, Any]] = [{"type": "text", "text": prompt}]
        for image_index, b64 in chunk:
            content.append(
                {
                    "type": "text",
                    "text": (
                        f"SOURCE_IMAGE_INDEX: {image_index}\n"
                        f'Return every JSON object for this image with "source_image_index": {image_index}.'
                    ),
                }
            )
            content.append(
                {
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:image/jpeg;base64,{b64}",
                        "detail": image_detail,
                    },
                }
            )
        payload = {
            "model": model,
            "max_tokens": max_tokens_per_image * max(1, len(chunk)),
            "temperature": 0,
            "messages": [{"role": "user", "content": content}],
        }
        response = await _post_vision_request_with_retry(
            client,
            url="https://api.openai.com/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            payload=payload,
            model=model,
            settings=settings,
            chunk_label=chunk_label,
        )

    raw = _extract_vision_text(response.json(), is_gemini=is_gemini)
    parsed = parse_json_safe(raw)

    # [WHY] Ambiguous multi-object answers without explicit source indexes can attach OCR output to the wrong file.
    # [RISK] Once filename mapping drifts, UI status and front/back merge become misleading for operators.
    # [CHANGE RULE] If this fallback changes, rerun regression with mixed one-side and two-side scans.
    if (
        allow_split_fallback
        and len(chunk) > 1
        and isinstance(parsed, list)
        and parsed
        and any(
            _coerce_source_image_index(item.get("source_image_index"), total_images) is None
            for item in parsed
            if isinstance(item, dict)
        )
    ):
        _logger.warning(
            "[AI_OCR_SPLIT_FALLBACK] model=%s chunk=%s parsed_items=%s images=%s",
            model,
            chunk_label,
            len(parsed),
            len(chunk),
        )
        normalized: list[dict] = []
        for image_index, b64 in chunk:
            normalized.extend(
                await _call_vision_provider_chunk(
                    client,
                    chunk=[(image_index, b64)],
                    total_images=total_images,
                    model=model,
                    api_key=api_key,
                    is_gemini=is_gemini,
                    settings=settings,
                    prompt=prompt,
                    image_detail=image_detail,
                    openai_max_tokens_per_image=max_tokens_per_image,
                    allow_split_fallback=False,
                )
            )
        return normalized

    return _normalize_vision_results(parsed, fallback_indexes, total_images)


async def call_vision_batch(images_b64: list[str]) -> list[dict]:
    """
    Gửi n ảnh trong 1 lần gọi. Prompt chỉ tốn 1 lần.
    Không pad/trim kết quả — ảnh 2 mặt có thể trả >n objects.
    """
    model = _get_model()
    is_gemini = "gemini" in model.lower()
    api_key = _get_api_key(model)
    if not api_key:
        raise HTTPException(status_code=500, detail=f"Server chưa cấu hình khóa API cho model {model}")

    try:
        async with httpx.AsyncClient(timeout=120.0) as client:
            if is_gemini:
                url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
                parts = [{"text": SYSTEM_PROMPT}]
                for b64 in images_b64:
                    parts.append({"inline_data": {"mime_type": "image/jpeg", "data": b64}})
                
                resp = await client.post(url, json={
                    "contents": [{"parts": parts}],
                    "generationConfig": {"temperature": 0.0}
                })
            else:
                content = [{"type": "text", "text": SYSTEM_PROMPT}]
                for b64 in images_b64:
                    content.append({
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/jpeg;base64,{b64}",
                            "detail": "high"
                        }
                    })
                
                resp = await client.post(
                    "https://api.openai.com/v1/chat/completions",
                    headers={
                        "Authorization": f"Bearer {api_key}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": model,
                        "max_tokens": 500 * len(images_b64),
                        "temperature": 0,
                        "messages": [{"role": "user", "content": content}]
                    },
                )
    except httpx.RequestError as e:
        raise HTTPException(status_code=502, detail=f"Không thể kết nối tới API: {str(e)}")

    if not resp.is_success:
        raise HTTPException(status_code=502, detail=f"API lỗi ({model}): {resp.text[:300]}")

    resp_json = resp.json()
    if is_gemini:
        try:
            raw = resp_json["candidates"][0]["content"]["parts"][0]["text"]
        except (KeyError, IndexError):
            raw = ""
    else:
        try:
            raw = resp_json["choices"][0]["message"]["content"]
        except (KeyError, IndexError):
            raw = ""

    parsed = parse_json_safe(raw)

    # Không pad/trim — ảnh 2 mặt có thể trả nhiều hơn số ảnh gửi lên
    if isinstance(parsed, list) and parsed:
        return parsed

    if isinstance(parsed, dict):
        return [parsed]

    # Fallback
    return [{"doc_type": "unknown", "data": {}} for _ in images_b64]


# ─── Grouping ─────────────────────────────────────────────────────────────────
async def call_vision_batch_v2(
    images_b64: list[str],
    *,
    prompt: str = SYSTEM_PROMPT,
    model: str | None = None,
    source_indexes: list[int] | None = None,
    image_detail: str = "high",
    openai_max_tokens_per_image: int | None = None,
) -> list[dict]:
    if not images_b64:
        return []

    model = model or _get_primary_model()
    is_gemini = "gemini" in model.lower()
    api_key = _get_api_key(model)
    if not api_key:
        raise HTTPException(status_code=500, detail=f"Server chua cau hinh khoa API cho model {model}")

    settings = _get_ai_ocr_settings()
    chunks = _chunk_indexed_images(images_b64, settings["batch_size"], source_indexes=source_indexes)
    semaphore = asyncio.Semaphore(settings["max_concurrency"])
    started_at = perf_counter()
    total_images = max(source_indexes) + 1 if source_indexes else len(images_b64)

    async with httpx.AsyncClient(timeout=httpx.Timeout(settings["timeout_seconds"])) as client:
        async def run_chunk(chunk: list[tuple[int, str]]) -> list[dict]:
            chunk_started = perf_counter()
            async with semaphore:
                rows = await _call_vision_provider_chunk(
                    client,
                    chunk=chunk,
                    total_images=total_images,
                    model=model,
                    api_key=api_key,
                    is_gemini=is_gemini,
                    settings=settings,
                    prompt=prompt,
                    image_detail=image_detail,
                    openai_max_tokens_per_image=openai_max_tokens_per_image,
                )
            elapsed_ms = round((perf_counter() - chunk_started) * 1000.0, 2)
            source_range = f"{chunk[0][0]}-{chunk[-1][0]}"
            _log_ai_ocr_timing(
                (
                    f"model={model} chunk={source_range} images={len(chunk)} "
                    f"results={len(rows)} elapsed_ms={elapsed_ms}"
                ),
                level="warning" if elapsed_ms >= settings["timing_slow_ms"] else "info",
                settings=settings,
            )
            return rows

        chunk_results = await asyncio.gather(*(run_chunk(chunk) for chunk in chunks))

    merged_results: list[dict] = []
    for rows in chunk_results:
        merged_results.extend(rows)

    total_elapsed_ms = round((perf_counter() - started_at) * 1000.0, 2)
    _log_ai_ocr_timing(
        (
            f"model={model} total_images={len(images_b64)} batches={len(chunks)} "
            f"batch_size={settings['batch_size']} elapsed_ms={total_elapsed_ms}"
        ),
        level="warning" if total_elapsed_ms >= settings["timing_slow_ms"] * max(1, len(chunks)) else "info",
        settings=settings,
    )
    return merged_results


# ─── Endpoints ────────────────────────────────────────────────────────────────
def group_documents(results: list) -> dict:
    fronts = [r for r in results if r.get("doc_type") == "cccd_front"]
    backs = [r for r in results if r.get("doc_type") == "cccd_back"]
    marriages = [r for r in results if r.get("doc_type") == "marriage_cert"]
    lands = [r for r in results if r.get("doc_type") == "land_cert"]
    unknowns = [r for r in results if r.get("doc_type") == "unknown"]
    identity_unknowns = [
        row
        for row in unknowns
        if _infer_profile_from_data_hints(dict(row.get("data") or {})) != DOC_PROFILE_UNKNOWN
        or len(
            _clean_doc_number(
                (row.get("data") or {}).get("so_giay_to")
                or (row.get("data") or {}).get("so_giay_to_mrz")
                or extract_cccd_from_mrz((row.get("data") or {}).get("mrz_line1", ""))
            )
        )
        == 12
    ]

    persons_map: dict[str, dict[str, Any]] = {}
    person_order: list[str] = []
    reverse_profile_map = {value: key for key, value in _PROFILE_TO_SIDE_LABEL.items()}

    for row in fronts + backs + identity_unknowns:
        data = dict(row.get("data") or {})
        if "dia_chi_back" in data and not data.get("dia_chi"):
            data["dia_chi"] = data.get("dia_chi_back", "")

        profile = row.get("profile", DOC_PROFILE_UNKNOWN)
        if profile == DOC_PROFILE_UNKNOWN:
            profile = reverse_profile_map.get(str(row.get("_side", "")), DOC_PROFILE_UNKNOWN)
        if profile == DOC_PROFILE_UNKNOWN:
            profile = _infer_profile_from_ai(DOC_PROFILE_UNKNOWN, row.get("doc_type", "unknown"), data)
        if profile == DOC_PROFILE_UNKNOWN:
            profile = _infer_profile_from_data_hints(data)

        pair_key = _clean_doc_number(
            row.get("pair_key")
            or data.get("so_giay_to")
            or data.get("so_giay_to_mrz")
            or extract_cccd_from_mrz(data.get("mrz_line1", ""))
        )
        if len(pair_key) != 12:
            pair_key = ""
        group_key = pair_key or f"img:{row.get('_source_image_index', row.get('filename', 'unknown'))}"

        if group_key not in persons_map:
            persons_map[group_key] = {
                "data": _empty_person_data(),
                "field_sources": {},
                "files": [],
                "profiles": set(),
                "has_qr": False,
            }
            person_order.append(group_key)

        group = persons_map[group_key]
        group["profiles"].add(profile)
        if row.get("filename") and row["filename"] not in group["files"]:
            group["files"].append(row["filename"])

        field_sources = dict(row.get("field_sources") or {})
        for field_name in _empty_person_data():
            source = str(field_sources.get(field_name, "")).lower()
            if not source and row.get("qr_data") and _normalize_system_field(field_name, row["qr_data"].get(field_name, "")):
                source = "qr"
            if not source and field_name in {"so_giay_to", "ngay_sinh", "gioi_tinh", "ngay_het_han"} and row.get("mrz_data"):
                source = "mrz"
            if not source:
                continue
            _merge_field_value(
                group["data"],
                group["field_sources"],
                field_name=field_name,
                value=data.get(field_name, ""),
                source=source,
                profile=profile,
            )
            group["has_qr"] = group["has_qr"] or source == "qr"

    persons = []
    matched_pairs = 0
    for key in person_order:
        group = persons_map[key]
        front_present = bool(group["profiles"] & {DOC_PROFILE_FRONT_OLD, DOC_PROFILE_FRONT_NEW})
        back_present = bool(group["profiles"] & {DOC_PROFILE_BACK_OLD, DOC_PROFILE_BACK_NEW})
        if front_present and back_present:
            matched_pairs += 1

        if DOC_PROFILE_BACK_NEW in group["profiles"]:
            side_label = _PROFILE_TO_SIDE_LABEL[DOC_PROFILE_BACK_NEW]
        elif DOC_PROFILE_BACK_OLD in group["profiles"]:
            side_label = _PROFILE_TO_SIDE_LABEL[DOC_PROFILE_BACK_OLD]
        elif DOC_PROFILE_FRONT_OLD in group["profiles"]:
            side_label = _PROFILE_TO_SIDE_LABEL[DOC_PROFILE_FRONT_OLD]
        elif DOC_PROFILE_FRONT_NEW in group["profiles"]:
            side_label = _PROFILE_TO_SIDE_LABEL[DOC_PROFILE_FRONT_NEW]
        else:
            side_label = "unknown"

        if len(_clean_doc_number(key)) == 12:
            group["data"]["so_giay_to"] = _clean_doc_number(key)

        if front_present and back_present:
            source_label = "cccd+back"
        elif back_present:
            source_label = "cccd+back" if group["has_qr"] else "cccd_back only"
        else:
            source_label = "cccd (thiếu mặt sau)"

        is_back_only = back_present and not front_present
        if is_back_only:
            so_giay_to_val = _clean_doc_number(group["data"].get("so_giay_to", ""))
            so_giay_to_source = group.get("field_sources", {}).get("so_giay_to", "")
            if len(so_giay_to_val) != 12 or so_giay_to_source not in ("qr", "mrz"):
                continue

        persons.append(
            {
                "ho_ten": group["data"].get("ho_ten", ""),
                "so_giay_to": group["data"].get("so_giay_to", ""),
                "ngay_sinh": group["data"].get("ngay_sinh", ""),
                "gioi_tinh": group["data"].get("gioi_tinh", ""),
                "dia_chi": group["data"].get("dia_chi", ""),
                "ngay_het_han": group["data"].get("ngay_het_han", ""),
                "ngay_cap": group["data"].get("ngay_cap", ""),
                "_source": source_label,
                "_side": side_label,
                "_qr": group["has_qr"],
                "_files": group["files"],
            }
        )

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
            "ngay_dang_ky": md.get("ngay_dang_ky", ""),
            "noi_dang_ky": md.get("noi_dang_ky", ""),
            "_file": m.get("filename", ""),
        })

    properties = []
    for land in lands:
        ld = land.get("data", {})
        properties.append({
            "so_serial": ld.get("so_serial", ""),
            "so_thua_dat": ld.get("so_thua_dat", ""),
            "so_to_ban_do": ld.get("so_to_ban_do", ""),
            "dia_chi": ld.get("dia_chi_dat", ""),
            "loai_dat": ld.get("loai_dat", ""),
            "ngay_cap": ld.get("ngay_cap", ""),
            "co_quan_cap": ld.get("co_quan_cap", ""),
            "_file": land.get("filename", ""),
        })

    return {
        "persons": persons,
        "properties": properties,
        "marriages": marriage_data,
        "raw_results": results,
        "summary": {
            "total_images": len(results),
            "cccd_fronts": len(fronts),
            "cccd_backs": len(backs),
            "matched_pairs": matched_pairs,
            "marriages": len(marriages),
            "land_certs": len(lands),
            "unknowns": len(unknowns),
        },
    }


async def _analyze_images_v2(files: List[UploadFile]) -> dict[str, Any]:
    if not files:
        raise HTTPException(status_code=400, detail="Chua co anh nao duoc gui len")

    settings = _get_ai_ocr_settings()
    rows: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    file_bytes_map: dict[int, bytes] = {}
    file_items: list[dict[str, Any]] = []

    for idx, upload in enumerate(files):
        try:
            file_bytes = await upload.read()
            filename = upload.filename or "unknown"
            file_bytes_map[idx] = file_bytes
            file_items.append({"index": idx, "filename": filename, "bytes": file_bytes})
        except Exception as exc:
            errors.append({"filename": upload.filename, "error": str(exc)})

    built_rows, preprocess_errors = await _preprocess_ai_file_items(file_items, settings)
    rows.extend(built_rows)
    errors.extend(preprocess_errors)

    if not rows:
        return {"persons": [], "properties": [], "marriages": [], "errors": errors, "summary": {}}

    primary_plans = _build_ai_plan(rows, settings)
    image_cache: dict[int, Image.Image] = {}
    primary_results = (
        await _execute_ai_plans(primary_plans, file_bytes_map=file_bytes_map, image_cache=image_cache)
        if primary_plans
        else {}
    )
    primary_model = _get_primary_model()
    for row in rows:
        _apply_ai_rows_to_record(row, primary_results.get(row["index"], []), model=primary_model)

    escalation_plans = _build_escalation_plans(rows)
    escalation_results = (
        await _execute_ai_plans(escalation_plans, file_bytes_map=file_bytes_map, image_cache=image_cache)
        if escalation_plans
        else {}
    )
    escalation_model = _get_escalation_model()
    for row in rows:
        _apply_ai_rows_to_record(row, escalation_results.get(row["index"], []), model=escalation_model)

    raw_results: list[dict[str, Any]] = []
    for row in rows:
        data = dict(row.get("data") or {})
        mrz_data = dict(row.get("mrz_data") or {})
        if mrz_data.get("mrz_line1") and not data.get("mrz_line1"):
            data["mrz_line1"] = mrz_data.get("mrz_line1", "")
        if mrz_data.get("so_giay_to_mrz") and not data.get("so_giay_to_mrz"):
            data["so_giay_to_mrz"] = mrz_data.get("so_giay_to_mrz", "")
        if row.get("profile") == DOC_PROFILE_BACK_NEW and data.get("dia_chi") and not data.get("dia_chi_back"):
            data["dia_chi_back"] = data.get("dia_chi", "")

        raw_results.append(
            {
                "doc_type": row.get("doc_type", "unknown"),
                "data": data,
                "filename": row.get("filename", "unknown"),
                "_source_image_index": row["index"],
                "_img_has_qr": row.get("has_qr", False),
                "_side": row.get("_side", "unknown"),
                "profile": row.get("profile", DOC_PROFILE_UNKNOWN),
                "pair_key": row.get("pair_key", ""),
                "pair_key_source": row.get("pair_key_source", ""),
                "qr_data": row.get("qr_data"),
                "mrz_data": mrz_data,
                "field_sources": row.get("field_sources", {}),
                "ai_models_run": row.get("ai_models_run", []),
            }
        )

    skip_ai = sum(1 for row in rows if not row.get("ai_plan"))
    mrz_rows = sum(1 for row in rows if row.get("has_mrz"))
    primary_ai_rows = len({plan["record_index"] for plan in primary_plans})
    escalated_rows = len({plan["record_index"] for plan in escalation_plans})
    ai_encoded = len(primary_plans) + len(escalation_plans)
    for row in rows:
        _log_ai_ocr_row_timing(row, settings=settings)
        tags: list[str] = []
        if row.get("has_mrz"):
            tags.append("mrz_partial")
        if row.get("ai_models_run"):
            tags.append("ai_call")
        elif row.get("has_qr") or row.get("pair_key_source") == "qr":
            tags.append("qr_skip")
        else:
            tags.append("skip_ai")
        if escalation_model in row.get("ai_models_run", []) and escalation_model != primary_model:
            tags.append("escalated")
        _logger.info("[OCR] img#%s: %s", row["index"], "|".join(tags))
    _logger.info(
        "[AI_OCR_FLOW] total=%s skip_ai=%s mrz_rows=%s primary_ai_rows=%s ai_encoded=%s escalated_rows=%s",
        len(rows),
        skip_ai,
        mrz_rows,
        primary_ai_rows,
        ai_encoded,
        escalated_rows,
    )

    grouped = group_documents(raw_results)
    grouped["errors"] = errors
    return grouped


@router.post("/analyze")
async def analyze_images(files: List[UploadFile] = File(...)):
    """
    Nhận 1..n ảnh giấy tờ, áp QR/MRZ-first và trả về persons[], properties[], marriages[].
    Response contract giữ nguyên shape hiện tại của API OCR.
    """
    return await _analyze_images_v2(files)


@router.get("/config")
async def ocr_config():
    model = _get_primary_model()
    return {
        "configured": bool(_get_api_key(model)),
        "model":      model,
        "max_image_px": MAX_IMAGE_PX,
    }
