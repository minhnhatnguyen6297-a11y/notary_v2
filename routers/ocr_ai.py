"""
AI OCR router (cloud path) with native Qwen OCR task.

Design goals:
1) Keep API contract stable: POST /api/ocr/analyze, GET /api/ocr/config.
2) Latency-first: run QR and AI in parallel per image, then prefer QR result.
3) AI is text-only OCR. Field parsing, MRZ parsing, side detection, and pairing
   are deterministic in backend.
4) No fallback waves (no MRZ rescue AI, no chat prompt reasoning loop).
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
from difflib import SequenceMatcher
from time import perf_counter
from typing import Any

import httpx
import zxingcpp
from dotenv import dotenv_values
from fastapi import APIRouter, File, HTTPException, UploadFile
from PIL import Image, ImageOps


router = APIRouter(tags=["OCR"])
_logger = logging.getLogger("ocr_ai")

_ENV_PATH = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".env"))

DEFAULT_MODEL = "qwen-vl-ocr-2025-11-20"
QWEN_OCR_BASE_URL = os.getenv("QWEN_OCR_BASE_URL", "https://dashscope-intl.aliyuncs.com").rstrip("/")
QWEN_OCR_MIN_PIXELS = int(os.getenv("QWEN_OCR_MIN_PIXELS", "3072"))
QWEN_OCR_MAX_PIXELS = int(os.getenv("QWEN_OCR_MAX_PIXELS", "8388608"))
QWEN_OCR_ENABLE_ROTATE = os.getenv("QWEN_OCR_ENABLE_ROTATE", "0").strip().lower() in {"1", "true", "yes", "on"}
OCR_AI_CONCURRENCY = max(1, int(os.getenv("OCR_AI_CONCURRENCY", "6")))
AI_TIMEOUT_SECONDS = float(os.getenv("OCR_AI_TIMEOUT_SECONDS", "90"))
AI_MAX_IMAGE_PX = max(640, int(os.getenv("QWEN_MAX_IMAGE_PX", "1800")))
JPEG_QUALITY = 82
PAIR_FUZZY_MAX_ID_MISMATCH = max(0, min(3, int(os.getenv("OCR_PAIR_FUZZY_MAX_ID_MISMATCH", "1"))))
PAIR_FUZZY_NAME_THRESHOLD = float(os.getenv("OCR_PAIR_FUZZY_NAME_THRESHOLD", "0.95"))


def _ms(seconds: float) -> float:
    return round(max(0.0, float(seconds)) * 1000.0, 2)


def _read_env() -> dict[str, str]:
    return dict(dotenv_values(_ENV_PATH))


def _get_model() -> str:
    configured = (os.getenv("OCR_MODEL", "") or _read_env().get("OCR_MODEL", "")).strip()
    if configured.startswith("models/"):
        configured = configured.split("/", 1)[1]
    model = configured or DEFAULT_MODEL
    return model


def _get_api_key(model: str) -> str:
    model_lower = model.lower()
    env = _read_env()
    if "qwen" in model_lower:
        return (
            os.getenv("QWEN_API_KEY", "")
            or env.get("QWEN_API_KEY", "")
            or os.getenv("DASHSCOPE_API_KEY", "")
            or env.get("DASHSCOPE_API_KEY", "")
        )
    return os.getenv("OPENAI_API_KEY", "") or env.get("OPENAI_API_KEY", "")


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


def _clean_text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _fold_text(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value or "")
    normalized = "".join(ch for ch in normalized if not unicodedata.combining(ch))
    normalized = normalized.lower()
    normalized = (
        normalized.replace("đ", "d")
        .replace("0", "o")
        .replace("1", "l")
        .replace("3", "e")
        .replace("4", "a")
        .replace("5", "s")
        .replace("7", "t")
    )
    return normalized


def _ascii_text(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value or "")
    normalized = "".join(ch for ch in normalized if not unicodedata.combining(ch))
    return normalized.lower().replace("đ", "d")


def _norm_label_key(value: str) -> str:
    return re.sub(r"[^a-z0-9]", "", _fold_text(value))


def _looks_like_label(line: str, labels: list[str], threshold: float = 0.84) -> bool:
    key = _norm_label_key(line)
    if not key:
        return False
    for label in labels:
        target = _norm_label_key(label)
        if not target:
            continue
        if target in key:
            return True
        ratio = SequenceMatcher(None, key[: len(target) + 3], target).ratio()
        if ratio >= threshold:
            return True
    return False


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
    folded = _fold_text(_clean_text(value))
    if re.search(r"\b(nam|male|m)\b", folded):
        return "Nam"
    if re.search(r"\b(nu|female|f)\b", folded):
        return "Nữ"
    return ""


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


def _field_sources(data: dict[str, str], source: str) -> dict[str, str]:
    return {k: source for k, v in data.items() if _clean_text(v)}


def _zxing_decode_qr(image_obj: Image.Image) -> str | None:
    try:
        results = zxingcpp.read_barcodes(image_obj)
    except Exception:
        return None
    for result in results:
        if result.format in (zxingcpp.BarcodeFormat.QRCode, zxingcpp.BarcodeFormat.MicroQRCode):
            text = (result.text or "").strip()
            if text:
                return text
    return None


def _qr_variants(file_bytes: bytes) -> list[Image.Image]:
    # Raw-only policy: one direct decode candidate after exif transpose.
    try:
        img = Image.open(io.BytesIO(file_bytes))
        img = ImageOps.exif_transpose(img)
        if img.mode not in ("RGB", "L"):
            img = img.convert("RGB")
        return [img]
    except Exception:
        return []


def try_decode_qr(file_bytes: bytes) -> str | None:
    for candidate in _qr_variants(file_bytes):
        decoded = _zxing_decode_qr(candidate)
        if decoded:
            return decoded
    return None


def parse_cccd_qr(text: str) -> dict[str, str] | None:
    raw = (text or "").strip()
    if not raw:
        return None
    parts = [p.strip() for p in re.split(r"[|\r\n;]+", raw) if p and p.strip()]
    if not parts:
        return None

    now_year = datetime.now().year

    def collect_dates(part: str) -> list[str]:
        out: list[str] = []
        compact = re.sub(r"\s+", "", part or "")
        for m in re.findall(r"\d{1,2}[/-]\d{1,2}[/-]\d{4}", compact):
            d = _normalize_date(m)
            if d:
                out.append(d)
        for m in re.findall(r"\d{8}", compact):
            ddmmyyyy = f"{m[0:2]}/{m[2:4]}/{m[4:8]}"
            parsed = _normalize_date(ddmmyyyy)
            if parsed:
                out.append(parsed)
        return out

    cccd = ""
    for part in parts:
        m = re.search(r"(?<!\d)(\d{12})(?!\d)", part)
        if m:
            cccd = m.group(1)
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
        folded = _fold_text(part)
        after_colon = part.split(":", 1)[1].strip() if ":" in part else part

        if not name and _looks_like_label(part, ["ho va ten", "ho ten", "full name"]):
            if after_colon and not re.search(r"\d", after_colon):
                name = after_colon
            elif idx + 1 < len(parts) and not re.search(r"\d", parts[idx + 1]):
                name = parts[idx + 1]

        if not gender:
            if re.search(r"\b(nam|male)\b", folded):
                gender = "Nam"
            elif re.search(r"\b(nu|female)\b", folded):
                gender = "Nữ"

        if not address and _looks_like_label(part, ["noi thuong tru", "noi cu tru", "place of residence"]):
            if after_colon:
                address = after_colon
            elif idx + 1 < len(parts):
                address = parts[idx + 1]

        dates = collect_dates(part)
        if dates:
            if not birth and _looks_like_label(part, ["ngay sinh", "date of birth"]):
                birth = dates[0]
            if not issue and _looks_like_label(part, ["ngay cap", "date of issue"]):
                issue = dates[0]
            if not expiry and _looks_like_label(part, ["co gia tri den", "ngay het han", "date of expiry"]):
                expiry = dates[-1]

    # Canonical CCCD QR payload is often positional without labels:
    # new_id|old_id|name|dob(ddmmyyyy)|gender|address|issue(ddmmyyyy)|...
    has_pipe_style = "|" in raw and len(parts) >= 6
    if has_pipe_style:
        if not name and len(parts) >= 3 and not re.search(r"\d", parts[2]):
            name = _clean_text(parts[2])
        if not birth and len(parts) >= 4:
            compact_dob = re.sub(r"\s+", "", parts[3] or "")
            if re.fullmatch(r"\d{8}", compact_dob):
                birth = _normalize_date(f"{compact_dob[0:2]}/{compact_dob[2:4]}/{compact_dob[4:8]}")
        if not gender and len(parts) >= 5:
            g = _normalize_gender(parts[4])
            if g:
                gender = g
        if not address and len(parts) >= 6:
            candidate_addr = _clean_text(parts[5])
            if candidate_addr and not _looks_like_label(candidate_addr, ["bo cong an", "ministry", "public security"]):
                address = candidate_addr
        if not issue and len(parts) >= 7:
            compact_issue = re.sub(r"\s+", "", parts[6] or "")
            if re.fullmatch(r"\d{8}", compact_issue):
                issue = _normalize_date(f"{compact_issue[0:2]}/{compact_issue[2:4]}/{compact_issue[4:8]}")

    all_dates: list[str] = []
    for part in parts:
        all_dates.extend(collect_dates(part))
    all_dates = list(dict.fromkeys(all_dates))

    def year_of(d: str) -> int:
        if not d:
            return 0
        try:
            return int(d.split("/")[-1])
        except Exception:
            return 0

    if all_dates and not birth:
        candidates = [d for d in all_dates if 1900 <= year_of(d) <= now_year]
        if candidates:
            birth = sorted(candidates, key=year_of)[0]
    if all_dates and not issue:
        candidates = [d for d in all_dates if 2000 <= year_of(d) <= now_year + 1 and d != birth]
        if candidates:
            issue = sorted(candidates, key=year_of)[0]
    if all_dates and not expiry:
        candidates = [d for d in all_dates if year_of(d) >= now_year]
        if candidates:
            expiry = sorted(candidates, key=year_of)[-1]

    if not address:
        for part in parts:
            candidate = _clean_text(part)
            if not candidate:
                continue
            folded = _fold_text(candidate)
            if re.search(r"\b(thon|to|to dan pho|tt|xa|phuong|huyen|quan|tinh|thanh pho|tp)\b", folded) or "," in candidate:
                if not re.search(r"bo cong an|ministry|public security|cong hoa|socialist", folded):
                    address = candidate
                    break

    result = _normalize_person_data(
        {
            "ho_ten": name,
            "so_giay_to": cccd,
            "ngay_sinh": birth,
            "gioi_tinh": gender,
            "dia_chi": address,
            "ngay_cap": issue,
            "ngay_het_han": expiry,
        }
    )
    if not result["so_giay_to"]:
        return None
    return result


def _prepare_ai_image_bytes(file_bytes: bytes, max_px: int = AI_MAX_IMAGE_PX) -> bytes:
    try:
        img = Image.open(io.BytesIO(file_bytes))
        img = ImageOps.exif_transpose(img)
        if img.mode not in ("RGB", "L"):
            img = img.convert("RGB")
        if img.mode == "L":
            img = img.convert("RGB")

        width, height = img.size
        max_side = max(width, height)
        if max_side > max_px:
            scale = max_px / float(max_side)
            new_size = (max(1, int(width * scale)), max(1, int(height * scale)))
            img = img.resize(new_size, Image.LANCZOS)

        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=JPEG_QUALITY, optimize=True)
        return buf.getvalue()
    except Exception:
        # Keep flow non-blocking for tests or malformed inputs.
        return file_bytes


def _extract_native_ocr_lines(payload: dict[str, Any]) -> list[str]:
    choices = payload.get("output", {}).get("choices", [])
    if not choices:
        return []
    message = choices[0].get("message", {})
    content = message.get("content")
    raw_text = ""
    if isinstance(content, str):
        raw_text = content
    elif isinstance(content, list):
        chunks: list[str] = []
        for item in content:
            if isinstance(item, dict):
                text = item.get("text")
                if isinstance(text, str) and text.strip():
                    chunks.append(text)
            elif isinstance(item, str) and item.strip():
                chunks.append(item)
        raw_text = "\n".join(chunks)
    elif isinstance(message.get("text"), str):
        raw_text = message.get("text", "")

    lines = []
    raw_text = (raw_text or "").replace("\\n", "\n")
    for line in re.split(r"[\r\n]+", raw_text):
        clean = _clean_text(line)
        if clean:
            lines.append(clean)
    return lines


async def _call_qwen_native_ocr_single(
    client: httpx.AsyncClient,
    *,
    api_key: str,
    model: str,
    image_b64: str,
    filename: str,
    enable_rotate: bool | None = None,
) -> list[str]:
    url = f"{QWEN_OCR_BASE_URL}/api/v1/services/aigc/multimodal-generation/generation"
    rotate_flag = QWEN_OCR_ENABLE_ROTATE if enable_rotate is None else bool(enable_rotate)
    body = {
        "model": model,
        "input": {
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {
                            "image": f"data:image/jpeg;base64,{image_b64}",
                            "min_pixels": QWEN_OCR_MIN_PIXELS,
                            "max_pixels": QWEN_OCR_MAX_PIXELS,
                            "enable_rotate": rotate_flag,
                        }
                    ],
                }
            ]
        },
        "parameters": {"ocr_options": {"task": "text_recognition"}},
    }

    t0 = perf_counter()
    try:
        resp = await client.post(
            url,
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json=body,
        )
    except httpx.RequestError as exc:
        _log_ocr_ai(
            "qwen_call",
            level="warning",
            filename=filename,
            model=model,
            latency_ms=_ms(perf_counter() - t0),
            status="error",
            error=f"network: {exc}",
        )
        raise HTTPException(status_code=502, detail=f"Cannot reach Qwen OCR endpoint: {exc}") from exc

    if not resp.is_success:
        _log_ocr_ai(
            "qwen_call",
            level="warning",
            filename=filename,
            model=model,
            latency_ms=_ms(perf_counter() - t0),
            status="error",
            error=resp.text[:300],
        )
        raise HTTPException(status_code=502, detail=f"Qwen OCR error: {resp.text[:300]}")

    payload = resp.json()
    lines = _extract_native_ocr_lines(payload)
    _log_ocr_ai(
        "qwen_call",
        filename=filename,
        model=model,
        latency_ms=_ms(perf_counter() - t0),
        status="ok",
        line_count=len(lines),
    )
    return lines


def _extract_dates_from_line(line: str) -> list[str]:
    out: list[str] = []
    compact = _clean_text(line)
    for m in re.findall(r"(?<!\d)(\d{1,2}[/-]\d{1,2}[/-]\d{4})(?!\d)", compact):
        d = _normalize_date(m)
        if d:
            out.append(d)
    return list(dict.fromkeys(out))


def _extract_id12(line: str) -> str:
    m = re.search(r"(?<!\d)(\d{12})(?!\d)", line)
    return m.group(1) if m else ""


def _extract_mrz_lines(lines: list[str]) -> list[str]:
    mrz: list[str] = []
    for ln in lines:
        key = _norm_label_key(ln)
        if "idvnm" in key or "<" in ln:
            mrz.append(_clean_text(ln))
    return mrz


def _parse_person_mrz(lines: list[str]) -> dict[str, str]:
    joined = " ".join(lines)
    old_new = re.search(r"IDVNM(\d{9})(\d)(\d{12})", re.sub(r"\s+", "", joined))
    so_giay_to = old_new.group(3) if old_new else ""

    mrz_name = ""
    for ln in lines:
        if "<<" in ln and re.search(r"[A-Z]", ln.upper()):
            cleaned = re.sub(r"[^A-Z<]", "", ln.upper())
            if "IDVNM" in cleaned:
                continue
            candidate = cleaned.replace("<<", " ").replace("<", " ")
            candidate = _clean_text(candidate)
            if candidate and len(candidate.split()) >= 2:
                mrz_name = candidate
                break

    dob = ""
    gioi_tinh = ""
    for ln in lines:
        s = re.sub(r"\s+", "", ln.upper())
        m = re.search(r"(\d{6})\d([MF<])\d{6}", s)
        if m:
            yy, mm, dd = m.group(1)[0:2], m.group(1)[2:4], m.group(1)[4:6]
            year = int(yy)
            now_yy = datetime.now().year % 100
            century = 1900 if year > now_yy else 2000
            dob = f"{dd}/{mm}/{century + year:04d}"
            if m.group(2) == "M":
                gioi_tinh = "Nam"
            elif m.group(2) == "F":
                gioi_tinh = "Nữ"
            break

    return _normalize_person_data(
        {
            "ho_ten": mrz_name,
            "so_giay_to": so_giay_to,
            "ngay_sinh": dob,
            "gioi_tinh": gioi_tinh,
            "dia_chi": "",
            "ngay_cap": "",
            "ngay_het_han": "",
        }
    )


def _detect_side(lines: list[str]) -> str:
    front_score = 0
    back_score = 0
    for line in lines:
        key = _fold_text(line)
        if _looks_like_label(line, ["ho va ten", "full name", "ngay sinh", "date of birth"]):
            front_score += 2
        if "can cuoc" in key or "citizen identity card" in key:
            front_score += 1
        if "idvnm" in key or "dac diem nhan dang" in key:
            back_score += 3
        if _looks_like_label(line, ["noi thuong tru", "noi cu tru", "place of residence", "ngay cap", "date of issue"]):
            back_score += 2
        if "ngon tro trai" in key or "ngon tro phai" in key:
            back_score += 2
    if back_score > front_score:
        return "back"
    if front_score > back_score:
        return "front"
    return "unknown"


def _extract_name_candidate(lines: list[str], side: str) -> str:
    if side == "back":
        return ""

    for idx, line in enumerate(lines):
        if _looks_like_label(line, ["ho va ten", "ho ten", "full name"]):
            after = line.split(":", 1)[1].strip() if ":" in line else ""
            if after and not re.search(r"\d", after):
                return _clean_text(after)
            if idx + 1 < len(lines) and not re.search(r"\d", lines[idx + 1]):
                next_line = _clean_text(lines[idx + 1])
                if len(next_line.split()) >= 2:
                    return next_line

    for line in lines:
        if re.search(r"\d", line):
            continue
        key = _fold_text(line)
        if "cong hoa" in key or "can cuoc" in key or "viet nam" in key:
            continue
        if len(line.split()) >= 2 and len(line) >= 6:
            return _clean_text(line)
    return ""


_ADDRESS_STOP_LABELS = [
    "co quan cap",
    "date of expiry",
    "date of issue",
    "ngay cap",
    "ngay het han",
    "co gia tri den",
    "que quan",
]

# Standalone values from other fields that can be interleaved into the address area
# due to 2-column CCCD layout (e.g. "Không thời hạn" from "Có giá trị đến" column).
# These are skipped when the address is still incomplete, stopped at when complete.
_ADDRESS_SKIP_TOKENS = frozenset(["khong thoi han", "khong co thoi han"])


def _strip_address_noise(value: str) -> str:
    text = _clean_text(value)
    if not text:
        return ""
    noise_patterns = [
        r"\bcơ\s+quan\s+cấp\b",
        r"\bco\s+quan\s+cap\b",
        r"\bdate\s+of\s+expiry\b",
        r"\bdate\s+of\s+issue\b",
        r"\bngày\s+cấp\b",
        r"\bngay\s+cap\b",
        r"\bngày\s+hết\s+hạn\b",
        r"\bngay\s+het\s+han\b",
        r"\bcó\s+giá\s+trị\s+đến\b",
        r"\bco\s+gia\s+tri\s+den\b",
    ]
    for pattern in noise_patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            text = text[: match.start()]
    return _clean_text(text).strip(" ,.;:-")


def _sanitize_address(value: str) -> str:
    raw = _clean_text(value)
    if not raw:
        return ""
    parts: list[str] = []
    for segment in [s.strip() for s in raw.split(",") if s and s.strip()]:
        segment_clean = _strip_address_noise(segment)
        if _looks_like_label(segment, _ADDRESS_STOP_LABELS):
            if segment_clean and not _looks_like_label(segment_clean, _ADDRESS_STOP_LABELS):
                parts.append(segment_clean)
            break
        if segment_clean:
            parts.append(segment_clean)
    merged = _clean_text(", ".join(parts))
    merged = _strip_address_noise(merged)
    return merged


def _extract_address(lines: list[str]) -> str:
    for idx, line in enumerate(lines):
        if not _looks_like_label(line, ["noi thuong tru", "noi cu tru", "place of residence"]):
            continue

        after = _sanitize_address(line.split(":", 1)[1].strip()) if ":" in line else ""

        # Label line already contains a full address (comma = multiple admin levels).
        if after and "," in after:
            return after

        parts = [after] if after else []
        collected = len(parts)

        # Search up to 4 positions ahead to allow skipping interleaved noise lines.
        for offset in range(1, 5):
            ni = idx + offset
            if ni >= len(lines):
                break
            next_line = _clean_text(lines[ni])
            if not next_line:
                continue

            # Stop at any known field label.
            if _looks_like_label(next_line, _ADDRESS_STOP_LABELS):
                break

            # "Không thời hạn" and similar values appear in the left column at the
            # same Y-level as address lines due to CCCD 2-column layout.
            # Skip them when the address is still incomplete; stop when complete.
            if any(tok in _fold_text(next_line) for tok in _ADDRESS_SKIP_TOKENS):
                current = ", ".join(p for p in parts if p)
                if "," not in current:
                    continue
                break

            next_clean = _sanitize_address(next_line)
            if not next_clean:
                continue

            parts.append(next_clean)
            collected += 1
            if collected >= 2:
                break

        return _sanitize_address(", ".join(p for p in parts if p))
    return ""


def _extract_issue_date(lines: list[str], side: str = "unknown") -> str:
    labels = ["ngay cap", "date of issue"]
    if side == "back":
        labels.extend(["ngay thang nam", "date month year"])

    for idx, line in enumerate(lines):
        if _looks_like_label(line, labels):
            dates = _extract_dates_from_line(line)
            if dates:
                return dates[0]
            if idx + 1 < len(lines):
                next_dates = _extract_dates_from_line(lines[idx + 1])
                if next_dates:
                    return next_dates[0]
    return ""


def _extract_birth_date(lines: list[str]) -> str:
    for idx, line in enumerate(lines):
        if _looks_like_label(line, ["ngay sinh", "date of birth"]):
            dates = _extract_dates_from_line(line)
            if dates:
                return dates[0]
            if idx + 1 < len(lines):
                next_dates = _extract_dates_from_line(lines[idx + 1])
                if next_dates:
                    return next_dates[0]
    return ""


def _extract_gender(lines: list[str]) -> str:
    for idx, line in enumerate(lines):
        if _looks_like_label(line, ["gioi tinh", "sex"]):
            g = _normalize_gender(line)
            if g:
                return g
            if idx + 1 < len(lines):
                g_next = _normalize_gender(lines[idx + 1])
                if g_next:
                    return g_next

    # Standalone gender token line (common OCR split case): "Nam", "Nu", "Male", "Female".
    for line in lines:
        compact = re.sub(r"[^a-z]", "", _fold_text(line))
        if compact in {"nam", "male"}:
            return "Nam"
        if compact in {"nu", "female"}:
            return "Nữ"
    return ""


def _extract_id(lines: list[str]) -> str:
    for line in lines:
        id12 = _extract_id12(line)
        if id12:
            return id12
    return ""


_PROPERTY_BOOK_TYPE_OLD = "Giay chung nhan quyen su dung dat"
_PROPERTY_BOOK_TYPE_PINK_FULL = "Giay chung nhan quyen su dung dat, quyen so huu nha o va tai san khac gan lien voi dat"
_PROPERTY_BOOK_TYPE_PINK_SHORT = "Giay chung nhan quyen su dung dat, quyen so huu tai san gan lien voi dat"
_PROPERTY_FRONT_PRIORITY_FIELDS = {"so_serial", "loai_so"}
_PROPERTY_BACK_PRIORITY_FIELDS = {"so_vao_so", "ngay_cap", "co_quan_cap"}
_PROPERTY_REQUIRED_CORE_FIELDS = ["so_serial", "so_vao_so", "dia_chi", "ngay_cap"]
_PROPERTY_FORM_FIELDS = [
    "so_serial",
    "so_vao_so",
    "so_thua_dat",
    "so_to_ban_do",
    "dia_chi",
    "chu_su_dung",
    "loai_so",
    "hinh_thuc_su_dung",
    "nguon_goc",
    "ngay_cap",
    "co_quan_cap",
    "loai_dat",
    "thoi_han",
    "dien_tich",
]
_PROPERTY_LAND_TYPE_CODES = {
    "ONT",
    "ODT",
    "CLN",
    "NTS",
    "LUC",
    "BHK",
    "SKC",
    "TMD",
    "DV",
    "DGT",
    "DKV",
    "DHT",
}

_LAND_NAME_TO_CODE: dict[str, str] = {
    "dat o tai nong thon": "ONT",
    "dat o tai do thi": "ODT",
    "dat o do thi": "ODT",
    "dat trong cay lau nam": "CLN",
    "dat nuoi trong thuy san": "NTS",
    "dat trong lua nuoc": "LUC",
    "dat trong lua": "LUC",
    "dat bang trong cay hang nam khac": "BHK",
    "dat san xuat kinh doanh": "SKC",
    "dat thuong mai dich vu": "TMD",
    "dat dich vu": "DV",
    "dat giao thong": "DGT",
}


def _land_name_to_code(text: str) -> str:
    key = _fold_text(text)
    for name, code in _LAND_NAME_TO_CODE.items():
        if name in key:
            return code
    return ""


def _property_has_value(value: Any) -> bool:
    if isinstance(value, list):
        return len(value) > 0
    return bool(_clean_text(value))


def _looks_like_property_doc(lines: list[str]) -> bool:
    signals: set[str] = set()
    for line in lines:
        key = _ascii_text(line)
        if "giay chung nhan" in key:
            signals.add("title")
        if "quyen su dung dat" in key:
            signals.add("land_right")
        if _looks_like_property_registry_label(line):
            signals.add("registry")
        if re.search(r"\bthua\s*(?:dat|so)?\b", key):
            signals.add("plot")
        if re.search(r"\bto\s*(?:ban\s*do|so)\b", key):
            signals.add("map")
        if "dien tich" in key:
            signals.add("area")
        if "dia chi" in key:
            signals.add("address")
        if "loai dat" in key or "muc dich su dung" in key:
            signals.add("land_type")
        if "nguoi su dung dat" in key or "chu su dung" in key or "chu so huu nha o" in key:
            signals.add("owner")
        if "van phong dang ky" in key or "uy ban nhan dan" in key or "so tai nguyen" in key:
            signals.add("authority")
        if _extract_property_serial_candidates(line):
            signals.add("serial")
    return len(signals) >= 3 or {"title", "serial"}.issubset(signals) or {"registry", "plot"}.issubset(signals)


def _classify_property_book_type(lines: list[str]) -> str:
    joined = " ".join(_fold_text(line) for line in lines)
    if "quyen su dung dat, quyen so huu nha o va tai san khac gan lien voi dat" in joined:
        return _PROPERTY_BOOK_TYPE_PINK_FULL
    if "quyen su dung dat, quyen so huu tai san gan lien voi dat" in joined:
        return _PROPERTY_BOOK_TYPE_PINK_SHORT
    if "quyen su dung dat" in joined:
        return _PROPERTY_BOOK_TYPE_OLD
    return ""


def _clean_property_code(value: str) -> str:
    text = _clean_text(value).strip(" .,:;-")
    text = re.sub(r"\s+", " ", text)
    return text


def _extract_code_like(value: str) -> str:
    text = _clean_text(value)
    if not text:
        return ""
    patterns = [
        r"\b([A-Z]{1,4}\s*\d{4,12}(?:/\d{1,8})?)\b",
        r"\b([A-Z]{1,4}\d{4,12}(?:/\d{1,8})?)\b",
        r"\b([0-9]{4,}[A-Z0-9/]{0,8})\b",
    ]
    upper = text.upper()
    for pattern in patterns:
        m = re.search(pattern, upper)
        if m:
            return _clean_property_code(m.group(1))
    return ""


def _looks_like_property_registry_label(line: str) -> bool:
    key = _norm_label_key(line)
    if not key:
        return False
    direct_labels = [
        "sovaoso",
        "sovaosocapgcn",
        "sovaosocapgiaychungnhan",
        "vaosocapgiaychungnhan",
        "vaosocapgcn",
    ]
    noisy_labels = [
        "sovachsocapgcn",
        "sovansocapgcn",
        "sovochsocapgcn",
        "sovachsocapgiaychungnhan",
        "sovansocapgiaychungnhan",
    ]
    if any(label in key for label in direct_labels):
        return True
    if any(label in key for label in noisy_labels):
        return True
    return "capgcn" in key and ("vaoso" in key or "vachso" in key or "vanso" in key or "vochso" in key)


def _extract_registry_code_like(value: str) -> str:
    text = _clean_text(value)
    if not text:
        return ""
    upper = text.upper()
    patterns = [
        r"\b([A-Z]{1,4}\s*\d{3,12}(?:\s*/\s*\d{1,8})?)\b",
        r"\b([A-Z]{1,4}\s*\d{3,12}\s+\d{1,8})\b",
    ]
    for pattern in patterns:
        m = re.search(pattern, upper)
        if m:
            return _clean_property_code(m.group(1).replace(" / ", "/").replace("/ ", "/").replace(" /", "/"))
    return ""


def _extract_property_serial_candidates(value: str, *, allow_single_letter: bool = False) -> list[str]:
    text = _clean_text(value).upper()
    if not text:
        return []
    patterns = [
        r"\b([A-Z]{2}\s*\d{6,8})\b",
        r"\b([A-Z]{2}\d{6,8})\b",
    ]
    if allow_single_letter:
        patterns.append(r"\b([A-Z]\s*\d{6,8})\b")
    out: list[str] = []
    seen: set[str] = set()
    for pattern in patterns:
        for match in re.finditer(pattern, text):
            candidate = _clean_property_code(match.group(1))
            compact = re.sub(r"\s+", "", candidate)
            if compact in seen:
                continue
            seen.add(compact)
            out.append(candidate)
    return out


def _looks_like_property_serial_label(line: str) -> bool:
    return _looks_like_label(line, ["so phat hanh", "so serial", "serial", "so seri", "ma phoi"])


def _is_property_serial_context(line: str) -> bool:
    key = _ascii_text(line)
    if _looks_like_property_registry_label(line):
        return False
    if _looks_like_property_serial_label(line):
        return True
    if re.match(r"^\s*so\b", key):
        reject_tokens = [
            "so vao so",
            "so thua",
            "so to",
            "so ban do",
            "so nha",
            "so tai",
            "so dien thoai",
        ]
        return not any(token in key for token in reject_tokens)
    return False


def _property_serial_candidate_score(candidate: str, line: str) -> int:
    compact = re.sub(r"\s+", "", _clean_property_code(candidate).upper())
    line_text = _clean_text(line)
    line_ascii = _ascii_text(line_text)
    has_serial_context = _looks_like_property_serial_label(line) or _is_property_serial_context(line)
    score = 0
    if re.fullmatch(r"[A-Z]{2}\d{6,8}", compact):
        score += 10
    elif re.fullmatch(r"[A-Z]\d{6,8}", compact):
        score += 7
    elif re.fullmatch(r"[A-Z]{1,4}\d{4,12}(?:/\d{1,8})?", compact):
        score += 3
    if _looks_like_property_serial_label(line):
        score += 6
    elif _is_property_serial_context(line):
        score += 4
    if _clean_property_code(line_text.upper()) == _clean_property_code(candidate):
        score += 5
    elif line_text.upper().startswith(compact) or line_text.upper().endswith(compact):
        score += 2
    if not has_serial_context and compact.startswith(("VP", "QD", "UB")):
        score -= 8
    if _looks_like_label(line, ["thua dat", "to ban do", "dia chi", "dien tich", "loai dat", "thoi han", "nguon goc"]):
        score -= 5
    if any(token in line_ascii for token in ["van phong dang ky", "uy ban nhan dan", "ngay ", "thang ", "nam "]):
        score -= 3
    if "/" in compact:
        score -= 2
    return score


def _property_registry_candidate_score(candidate: str, line: str, offset: int) -> int:
    compact = re.sub(r"\s+", "", _clean_property_code(candidate).upper())
    score = 0
    if re.fullmatch(r"[A-Z]{1,4}\d{3,12}(?:/\d{1,8})?", compact):
        score += 8
    elif re.fullmatch(r"[A-Z]{1,4}\d{3,12}", compact):
        score += 7
    if "/" in compact:
        score += 1
    if re.fullmatch(r"[A-Z]{2}\d{6,8}", compact):
        score -= 1
    if _looks_like_property_registry_label(line):
        score += 5
    score -= offset
    return score


def _extract_property_serial(lines: list[str]) -> str:
    registry_no = _extract_property_registry_no(lines)
    registry_compact = re.sub(r"\s+", "", _clean_property_code(registry_no).upper())
    best_value = ""
    best_score = -999
    for idx, line in enumerate(lines):
        candidate_lines = [line]
        if _is_property_serial_context(line) and idx + 1 < len(lines):
            candidate_lines.append(lines[idx + 1])
        for candidate_line in candidate_lines:
            allow_single_letter = _is_property_serial_context(line)
            for candidate in _extract_property_serial_candidates(candidate_line, allow_single_letter=allow_single_letter):
                score = _property_serial_candidate_score(candidate, line)
                if registry_compact and re.sub(r"\s+", "", _clean_property_code(candidate).upper()) == registry_compact:
                    score -= 20
                if candidate_line != line:
                    score -= 1
                if score > best_score or (score == best_score and _clean_property_code(candidate) < _clean_property_code(best_value)):
                    best_value = candidate
                    best_score = score
    return best_value if best_score > 0 else ""


def _extract_property_registry_no(lines: list[str]) -> str:
    best_value = ""
    best_score = -999
    for idx, line in enumerate(lines):
        if not _looks_like_property_registry_label(line):
            continue
        candidates: list[tuple[str, int]] = []
        if ":" in line:
            candidates.append((line.split(":", 1)[1], 0))
        candidates.append((line, 0))
        for offset in range(1, 3):
            if idx + offset < len(lines):
                candidates.append((lines[idx + offset], offset))
        for candidate, offset in candidates:
            code = _extract_registry_code_like(candidate)
            if code:
                score = _property_registry_candidate_score(code, line, offset)
                if score > best_score or (score == best_score and _clean_property_code(code) < _clean_property_code(best_value)):
                    best_value = code
                    best_score = score
    return best_value if best_score > 0 else ""


def _extract_first_number(line: str) -> str:
    m = re.search(r"(?<!\d)(\d{1,6})(?!\d)", line)
    return m.group(1) if m else ""


def _extract_number_after_property_label(line: str, label_patterns: list[str]) -> str:
    ascii_line = _ascii_text(line)
    for pattern in label_patterns:
        match = re.search(pattern, ascii_line)
        if match:
            return match.group(1)
    return ""


def _extract_property_number_field(lines: list[str], label_patterns: list[str], labels: list[str]) -> str:
    for idx, line in enumerate(lines):
        number = _extract_number_after_property_label(line, label_patterns)
        if number:
            return number
        if not _looks_like_label(line, labels):
            continue
        if idx + 1 >= len(lines):
            continue
        next_line = lines[idx + 1]
        if _looks_like_label(next_line, labels):
            continue
        number = _extract_first_number(next_line)
        if number:
            return number
    return ""


def _extract_property_plot_no(lines: list[str]) -> str:
    return _extract_property_number_field(
        lines,
        [r"\bthua\s*(?:dat|so)?\b[^0-9]{0,24}(\d{1,6})"],
        ["thua dat", "thua so"],
    )


def _extract_property_map_sheet(lines: list[str]) -> str:
    return _extract_property_number_field(
        lines,
        [r"\bto\s*(?:ban\s*do|so)\b[^0-9]{0,24}(\d{1,6})"],
        ["to ban do", "to so"],
    )
    for line in lines:
        if not _looks_like_label(line, ["to ban do", "to so"]):
            continue
        # Split by ";" to handle combined lines like "Thửa đất số: 342; tờ bản đồ số: 22."
        for seg in re.split(r"[;,]", line):
            if _looks_like_label(seg, ["to ban do", "to so"]):
                number = _extract_first_number(seg)
                if number:
                    return number
        # Fallback
        number = _extract_first_number(line)
        if number:
            return number
    return ""


def _normalize_property_area_number(value: str) -> str:
    text = _clean_text(value)
    if not text:
        return ""
    if "." in text and "," in text:
        if text.rfind(",") > text.rfind("."):
            text = text.replace(".", "").replace(",", ".")
        else:
            text = text.replace(",", "")
    else:
        text = text.replace(",", ".")
    return text


def _extract_property_area(lines: list[str]) -> str:
    for line in lines:
        if not _looks_like_label(line, ["dien tich"]):
            continue
        m = re.search(
            r"(?<!\d)(\d+(?:[.,]\d+)?)(?:\s*(?:m2|m²|m\^2|met vuong))?",
            _clean_text(line),
            flags=re.IGNORECASE,
        )
        if m:
            return _normalize_property_area_number(m.group(1))
    for line in lines:
        if not _looks_like_label(line, ["dien tich"]):
            continue
        m = re.search(r"(?<!\d)(\d+(?:[.,]\d+)?)(?:\s*(?:m2|m²))?", line, flags=re.IGNORECASE)
        if m:
            return m.group(1).replace(",", ".")
    return ""


_PROPERTY_ADDRESS_STOP_LABELS = [
    "so thua",
    "to ban do",
    "dien tich",
    "loai dat",
    "thoi han",
    "nguon goc",
    "hinh thuc su dung",
    "nguoi su dung dat",
    "chu su dung",
    "ngay cap",
    "co quan cap",
    "so vao so",
]


def _property_address_score(value: str) -> int:
    text = _clean_text(value)
    if not text:
        return 0
    key = _ascii_text(text)
    score = text.count(",") + (2 if len(text.split()) >= 4 else 0)
    hints = [
        "thon",
        "to dan pho",
        "ap",
        "xa",
        "phuong",
        "thi tran",
        "huyen",
        "quan",
        "tinh",
        "thanh pho",
        "duong",
    ]
    score += sum(1 for hint in hints if hint in key)
    reject_tokens = [
        "van phong dang ky",
        "uy ban nhan dan",
        "so tai nguyen",
        "ngay ",
        "thang ",
    ]
    if any(token in key for token in reject_tokens):
        score -= 8
    return score


def _strip_property_address_noise(value: str) -> str:
    text = _clean_text(value)
    if not text:
        return ""
    parts: list[str] = []
    for segment in [s.strip() for s in text.split(",") if s and s.strip()]:
        if _looks_like_label(segment, _PROPERTY_ADDRESS_STOP_LABELS):
            break
        parts.append(segment)
    merged = _clean_text(", ".join(parts) if parts else text)
    return merged.strip(" ,.;:-")


def _looks_like_property_footer_date_line(value: str) -> bool:
    text = _clean_text(value)
    if not text:
        return False
    ascii_text = _ascii_text(text)
    has_date = bool(_extract_dates_from_line(text)) or bool(
        re.search(r"\bngay\s+\d{1,2}\s+thang\s+\d{1,2}\s+nam\s+\d{4}\b", ascii_text)
    )
    if not has_date:
        return False
    return bool(re.match(r"^\s*(?:[a-z0-9 .'\-]+,\s*)?ngay\b", ascii_text))


def _extract_property_address(lines: list[str]) -> str:
    labels = ["dia chi", "dia chi thua dat"]
    best_value = ""
    best_score = -999
    for idx, line in enumerate(lines):
        if not _looks_like_label(line, labels):
            continue
        parts: list[str] = []
        if ":" in line:
            parts.append(line.split(":", 1)[1])
        for offset in range(1, 4):
            if idx + offset >= len(lines):
                break
            next_line = lines[idx + offset]
            next_key = _ascii_text(next_line)
            if _looks_like_label(next_line, _PROPERTY_ADDRESS_STOP_LABELS):
                break
            if _looks_like_property_footer_date_line(next_line):
                break
            if any(token in next_key for token in ["van phong dang ky", "uy ban nhan dan", "so tai nguyen"]):
                break
            if offset == 1 or _property_address_score(next_line) > 0:
                parts.append(next_line)
            else:
                break
        address = _strip_property_address_noise(", ".join(_clean_text(p) for p in parts if _clean_text(p)))
        score = _property_address_score(address)
        if score > best_score or (score == best_score and address and address < best_value):
            best_value = address
            best_score = score
    for line in lines:
        address = _strip_property_address_noise(line)
        score = _property_address_score(address)
        if score > best_score and "," in address:
            best_value = address
            best_score = score
    return best_value if best_score > 0 else ""


def _extract_property_field_by_label(lines: list[str], labels: list[str]) -> str:
    for idx, line in enumerate(lines):
        if not _looks_like_label(line, labels):
            continue
        if ":" in line:
            after = _clean_text(line.split(":", 1)[1])
            if after:
                return after
        if idx + 1 < len(lines):
            nxt = _clean_text(lines[idx + 1])
            if nxt and not _looks_like_label(nxt, labels):
                return nxt
    return ""


def _extract_property_block_after_label(lines: list[str], labels: list[str], stop_labels: list[str], max_follow_lines: int = 3) -> str:
    for idx, line in enumerate(lines):
        if not _looks_like_label(line, labels):
            continue
        parts: list[str] = []
        if ":" in line:
            after = _clean_text(line.split(":", 1)[1])
            if after:
                parts.append(after)
        for offset in range(1, max_follow_lines + 1):
            if idx + offset >= len(lines):
                break
            next_line = _clean_text(lines[idx + offset])
            if not next_line:
                continue
            if _looks_like_label(next_line, stop_labels):
                break
            parts.append(next_line)
        value = _clean_text(", ".join(parts))
        if value:
            return value
    return ""


def _extract_property_land_use_form(lines: list[str]) -> str:
    return _extract_property_field_by_label(lines, ["hinh thuc su dung"])


def _property_owner_score(value: str) -> int:
    text = _clean_text(value)
    if not text:
        return 0
    key = _ascii_text(text)
    score = 0
    if len(text.split()) >= 2:
        score += 2
    if "," in text:
        score += 1
    reject_tokens = [
        "van phong dang ky",
        "uy ban nhan dan",
        "so tai nguyen",
        "ngay ",
        "thang ",
        "thua dat",
        "dien tich",
        "loai dat",
        "nguon goc",
    ]
    if any(token in key for token in reject_tokens):
        score -= 5
    return score


def _extract_property_owner(lines: list[str]) -> str:
    labels = [
        "nguoi su dung dat",
        "chu su dung",
        "chu so huu nha o",
    ]
    stop_labels = _PROPERTY_ADDRESS_STOP_LABELS + [
        "giay chung nhan",
        "thua dat",
        "dia chi",
        "trang",
    ]
    value = _extract_property_block_after_label(lines, labels, stop_labels, max_follow_lines=3)
    return value if _property_owner_score(value) > 0 else ""


def _extract_land_rows_from_named_lines(lines: list[str]) -> list[dict[str, str]]:
    """Parse land rows từ GCN format dùng tên đầy đủ:
    'c. Loại đất: Đất ở tại nông thôn 200,0m²; Đất trồng cây lâu năm 247,0m²,'
    'd. Thời hạn sử dụng: Đất ở tại nông thôn: Lâu dài; Đất trồng cây lâu năm: 12/2043,'
    """
    land_line = ""
    term_line = ""
    for line in lines:
        if not land_line and _looks_like_label(line, ["loai dat", "muc dich su dung"]):
            land_line = line
        elif not term_line and _looks_like_label(line, ["thoi han su dung", "thoi han"]):
            term_line = line

    if not land_line:
        return []

    land_content = land_line.split(":", 1)[1] if ":" in land_line else land_line
    rows: list[dict[str, str]] = []
    for seg in re.split(r";", land_content):
        seg = seg.strip(" ,.")
        if not seg:
            continue
        area_m = re.search(r"(\d+(?:[.,]\d+)?)\s*m[²2]", seg, re.IGNORECASE)
        if not area_m:
            continue
        area = area_m.group(1).replace(",", ".")
        name_part = seg[: area_m.start()].strip()
        code = _land_name_to_code(name_part)
        if not code:
            continue
        rows.append({"loai_dat": code, "dien_tich": area, "thoi_han": "", "_name_key": _fold_text(name_part)})

    if not rows:
        return []

    if term_line:
        term_content = term_line.split(":", 1)[1] if ":" in term_line else term_line
        for seg in re.split(r";", term_content):
            seg = seg.strip(" ,.")
            if ":" not in seg:
                continue
            name_part, term_raw = seg.split(":", 1)
            matched_code = _land_name_to_code(name_part.strip())
            term_val = _clean_text(term_raw.strip(" ,."))
            if not term_val or not matched_code:
                continue
            if "lau dai" in _fold_text(term_val):
                term_val = "Lâu dài"
            for row in rows:
                if row.get("loai_dat") == matched_code:
                    row["thoi_han"] = term_val
                    break

    for row in rows:
        row.pop("_name_key", None)
    return rows


def _extract_property_land_rows(lines: list[str]) -> list[dict[str, str]]:
    # Pass 1: parse GCN structured format dùng tên đầy đủ tiếng Việt
    named_rows = _extract_land_rows_from_named_lines(lines)

    # Pass 2: scan từng dòng tìm code rõ ràng (ONT, CLN, ...)
    code_rows: list[dict[str, str]] = []
    existing_codes = {r["loai_dat"] for r in named_rows}
    for line in lines:
        upper = _clean_text(line).upper()
        if not upper:
            continue
        code_match = re.search(r"\b([A-Z]{2,4})\b", upper)
        if not code_match:
            continue
        land_code = code_match.group(1)
        if land_code not in _PROPERTY_LAND_TYPE_CODES:
            continue
        if land_code in existing_codes:
            continue
        area_match = re.search(r"(?<!\d)(\d+(?:[.,]\d+)?)(?:\s*(?:M2|M²))?", upper)
        if not area_match:
            continue
        term = ""
        lower = _fold_text(line)
        if "lau dai" in lower:
            term = "Lâu dài"
        else:
            term_match = re.search(r"(\d{1,3}\s*nam)", lower)
            if term_match:
                term = _clean_text(term_match.group(1))
        code_rows.append(
            {
                "loai_dat": land_code,
                "dien_tich": area_match.group(1).replace(",", "."),
                "thoi_han": term,
            }
        )

    rows = named_rows + code_rows
    unique_rows: list[dict[str, str]] = []
    seen: set[tuple[str, str, str]] = set()
    for row in rows:
        key = (row.get("loai_dat", ""), row.get("dien_tich", ""), row.get("thoi_han", ""))
        if key in seen:
            continue
        seen.add(key)
        unique_rows.append(row)
    return unique_rows


def _sum_land_row_area(rows: list[dict[str, str]]) -> str:
    total = 0.0
    valid = False
    for row in rows:
        raw = str(row.get("dien_tich") or "").replace(",", ".")
        try:
            total += float(raw)
            valid = True
        except Exception:
            continue
    if not valid:
        return ""
    return f"{total:.2f}".rstrip("0").rstrip(".")


def _normalize_property_side(side: str) -> str:
    normalized = _clean_text(side).lower()
    if normalized in {"front", "back"}:
        return normalized
    return "unknown"


def _extract_property_issue_date(lines: list[str]) -> str:
    authority_markers = [
        "uy ban nhan dan",
        "van phong dang ky",
        "so tai nguyen",
        "co quan cap",
        "kt. giam doc",
        "pho giam doc",
    ]
    candidates: list[tuple[int, int, str]] = []

    # Pass 1: định dạng tiếng Việt "ngày DD tháng MM năm YYYY"
    # Dùng NFKD + strip combining (không thay digits như _fold_text làm)
    for idx, line in enumerate(lines):
        nfkd = unicodedata.normalize("NFKD", line)
        stripped = "".join(ch for ch in nfkd if not unicodedata.combining(ch)).lower().replace("đ", "d")
        m = re.search(r"ngay\s+(\d{1,2})\s+thang\s+(\d{1,2})\s+nam\s+(\d{4})", stripped)
        if not m:
            continue
        date_str = f"{int(m.group(1)):02d}/{int(m.group(2)):02d}/{m.group(3)}"
        normalized = _normalize_date(date_str)
        if not normalized:
            continue
        score = 4
        for n in range(max(0, idx - 2), min(len(lines), idx + 3)):
            if any(marker in _fold_text(lines[n]) for marker in authority_markers):
                score += 1
                break
        candidates.append((score, idx, normalized))

    # Pass 2: định dạng số DD/MM/YYYY hoặc DD-MM-YYYY
    for idx, line in enumerate(lines):
        dates = _extract_dates_from_line(line)
        if not dates:
            continue
        score = 0
        key = _fold_text(line)
        if "ngay" in key or "date" in key:
            score += 2
        if any(marker in key for marker in authority_markers):
            score += 2
        for n in range(max(0, idx - 2), min(len(lines), idx + 3)):
            n_key = _fold_text(lines[n])
            if any(marker in n_key for marker in authority_markers):
                score += 1
                break
        for date_val in dates:
            candidates.append((score, idx, date_val))

    if not candidates:
        return ""
    candidates.sort(key=lambda item: (item[0], item[1]), reverse=True)
    return candidates[0][2]


def _extract_year(value: str) -> int:
    m = re.search(r"(\d{4})", _clean_text(value))
    if not m:
        return 0
    try:
        return int(m.group(1))
    except Exception:
        return 0


def _extract_footer_context_year(lines: list[str]) -> int:
    if not lines:
        return 0
    current_year = datetime.now().year + 1
    years: list[int] = []
    for line in lines[-10:]:
        for raw_year in re.findall(r"(?<!\d)(19\d{2}|20\d{2})(?!\d)", _clean_text(line)):
            year = int(raw_year)
            if 1900 <= year <= current_year:
                years.append(year)
    return max(years) if years else 0


def _should_rescue_property_issue_date(doc: dict[str, Any]) -> bool:
    if doc.get("doc_type") != "property":
        return False
    if _normalize_property_side(str(doc.get("side") or "")) == "front":
        return False
    data = doc.get("data") if isinstance(doc.get("data"), dict) else {}
    if not _clean_text(data.get("co_quan_cap")):
        return False
    current_date = _clean_text(data.get("ngay_cap"))
    if not current_date:
        return True
    current_year = _extract_year(current_date)
    footer_year = _extract_footer_context_year(doc.get("text_lines") if isinstance(doc.get("text_lines"), list) else [])
    if not current_year or not footer_year:
        return False
    return footer_year - current_year >= 2


def _property_authority_score(value: str) -> int:
    key = _fold_text(value)
    if not key:
        return 0
    score = 0
    if "van phong dang ky dat dai" in key:
        score += 10
    if "van phong dang ky quyen su dung dat" in key:
        score += 10
    if "so tai nguyen va moi truong" in key:
        score += 10
    if "so tai nguyen moi truong" in key:
        score += 9
    if "uy ban nhan dan" in key:
        score += 8
    if "bo tai nguyen va moi truong" in key:
        score += 8
    if "chi nhanh van phong dang ky dat dai" in key:
        score += 7
    if "dang ky dat dai" in key:
        score += 4
    if "tai nguyen" in key and "moi truong" in key:
        score += 4
    if "ubnd" in key:
        score += 4
    if any(marker in key for marker in ["kt giam doc", "pho giam doc", "giam doc"]):
        score -= 3
    if "co quan cap" in key and score == 0:
        score -= 5
    if len(value) > 120:
        score -= 3
    return score


def _clean_property_authority_value(value: str) -> str:
    text = _clean_text(value)
    if not text:
        return ""
    text = re.sub(r"\b\d{1,2}/\d{1,2}/\d{4}\b", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\bngay\s+\d{1,2}\s+thang\s+\d{1,2}\s+nam\s+\d{4}\b", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\bkt\.?\s*giam\s+doc\b", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\bpho\s+giam\s+doc\b", "", text, flags=re.IGNORECASE)
    text = re.sub(r"^(kt\.?\s*)?pho\s+giam\s+doc\b.*$", "", text, flags=re.IGNORECASE)
    text = re.sub(r"^kt\.?\s*giam\s+doc\b.*$", "", text, flags=re.IGNORECASE)
    text = re.sub(r"^chu\s+tich\b.*$", "", text, flags=re.IGNORECASE)
    return _clean_text(text).strip(" ,.;:-")


def _prepare_property_footer_image_bytes(file_bytes: bytes, max_px: int = 1400) -> bytes:
    try:
        img = Image.open(io.BytesIO(file_bytes))
        img = ImageOps.exif_transpose(img)
        if img.mode not in ("RGB", "L"):
            img = img.convert("RGB")
        if img.mode == "L":
            img = img.convert("RGB")

        width, height = img.size
        top = int(height * 0.58)
        crop = img.crop((0, top, width, height))

        crop_width, crop_height = crop.size
        max_side = max(crop_width, crop_height)
        if max_side > max_px:
            scale = max_px / float(max_side)
            new_size = (max(1, int(crop_width * scale)), max(1, int(crop_height * scale)))
            crop = crop.resize(new_size, Image.LANCZOS)

        buf = io.BytesIO()
        crop.save(buf, format="JPEG", quality=88, optimize=True)
        return buf.getvalue()
    except Exception:
        return b""


def _extract_property_authority(lines: list[str], issue_date: str) -> str:
    date_line_idx = -1
    if issue_date:
        for idx, line in enumerate(lines):
            if issue_date in _extract_dates_from_line(line):
                date_line_idx = idx
                break
    candidates: list[tuple[int, int, str]] = []
    for idx, raw_line in enumerate(lines):
        line = _clean_property_authority_value(raw_line)
        if not line:
            continue
        score = _property_authority_score(line)
        if score <= 0:
            continue
        if date_line_idx >= 0:
            distance = abs(idx - date_line_idx)
            score += max(0, 4 - distance)
        candidates.append((score, -idx, line))
    if not candidates:
        return ""
    candidates.sort(reverse=True)
    return candidates[0][2]


def _normalize_property_land_type_value(value: Any) -> str:
    text = _clean_text(value)
    if not text:
        return ""
    upper = text.upper()
    code_match = re.search(r"\b([A-Z]{2,4})\b", upper)
    if code_match and code_match.group(1) in _PROPERTY_LAND_TYPE_CODES:
        return code_match.group(1)
    mapped = _land_name_to_code(text)
    if mapped:
        return mapped
    text = re.sub(r"(?<!\d)\d+(?:[.,]\d+)?\s*(?:m2|m²|m\^2|met vuong)\b.*$", "", text, flags=re.IGNORECASE)
    return _clean_text(text).strip(" ,.;:-")


def _normalize_property_data(data: dict[str, Any]) -> dict[str, Any]:
    rows_in = data.get("land_rows")
    normalized_rows: list[dict[str, str]] = []
    if isinstance(rows_in, list):
        for row in rows_in:
            if not isinstance(row, dict):
                continue
            loai_dat = _clean_text(row.get("loai_dat")).upper()
            dien_tich = _normalize_property_area_number(_clean_text(row.get("dien_tich")))
            thoi_han = _clean_text(row.get("thoi_han"))
            if not (loai_dat or dien_tich or thoi_han):
                continue
            normalized_rows.append(
                {
                    "loai_dat": loai_dat,
                    "dien_tich": dien_tich,
                    "thoi_han": thoi_han,
                }
            )

    return {
        "loai_so": _clean_text(data.get("loai_so")),
        "so_serial": _clean_property_code(str(data.get("so_serial") or "")),
        "so_vao_so": _clean_property_code(str(data.get("so_vao_so") or "")),
        "so_thua_dat": _clean_text(data.get("so_thua_dat")),
        "so_to_ban_do": _clean_text(data.get("so_to_ban_do")),
        "dien_tich": _normalize_property_area_number(_clean_text(data.get("dien_tich"))),
        "dia_chi": _strip_property_address_noise(str(data.get("dia_chi") or "")),
        "chu_su_dung": _clean_text(data.get("chu_su_dung")),
        "ngay_cap": _normalize_date(data.get("ngay_cap")),
        "co_quan_cap": _clean_text(data.get("co_quan_cap")),
        "loai_dat": _normalize_property_land_type_value(data.get("loai_dat")),
        "thoi_han": _clean_text(data.get("thoi_han")),
        "hinh_thuc_su_dung": _clean_text(data.get("hinh_thuc_su_dung")),
        "nguon_goc": _clean_text(data.get("nguon_goc")),
        "land_rows": normalized_rows,
    }


def _fill_property_from_land_rows(data: dict[str, Any]) -> None:
    rows = data.get("land_rows")
    if not isinstance(rows, list) or not rows:
        return
    if not _clean_text(data.get("dien_tich")):
        total_area = _sum_land_row_area(rows)
        if total_area:
            data["dien_tich"] = total_area
    if not _clean_text(data.get("loai_dat")):
        first_type = _clean_text(rows[0].get("loai_dat")) if isinstance(rows[0], dict) else ""
        if first_type:
            data["loai_dat"] = first_type
    if not _clean_text(data.get("thoi_han")):
        terms: list[str] = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            term = _clean_text(row.get("thoi_han"))
            if term and term not in terms:
                terms.append(term)
        if terms:
            data["thoi_han"] = ", ".join(terms)


def _property_missing_fields(data: dict[str, Any]) -> list[str]:
    missing: list[str] = []
    for key in _PROPERTY_REQUIRED_CORE_FIELDS:
        if not _property_has_value(data.get(key)):
            missing.append(key)
    return missing


def _normalize_property_ocr_doc(lines: list[str], filename: str, side: str = "unknown") -> dict[str, Any]:
    normalized_side = _normalize_property_side(side)
    cleaned_lines = [_clean_text(ln) for ln in lines if _clean_text(ln)]
    if not cleaned_lines:
        return {"doc_type": "unknown", "side": normalized_side, "data": {}, "filename": filename, "text_lines": []}
    looks_like_property = _looks_like_property_doc(cleaned_lines)

    issue_date = _extract_property_issue_date(cleaned_lines)
    land_rows = _extract_property_land_rows(cleaned_lines)
    data = _normalize_property_data(
        {
            "loai_so": _classify_property_book_type(cleaned_lines),
            "so_serial": _extract_property_serial(cleaned_lines),
            "so_vao_so": _extract_property_registry_no(cleaned_lines),
            "so_thua_dat": _extract_property_plot_no(cleaned_lines),
            "so_to_ban_do": _extract_property_map_sheet(cleaned_lines),
            "dien_tich": _extract_property_area(cleaned_lines),
            "dia_chi": _extract_property_address(cleaned_lines),
            "chu_su_dung": _extract_property_owner(cleaned_lines),
            "ngay_cap": issue_date,
            "co_quan_cap": _extract_property_authority(cleaned_lines, issue_date),
            "loai_dat": _extract_property_field_by_label(cleaned_lines, ["loai dat", "muc dich su dung"]),
            "thoi_han": _extract_property_field_by_label(cleaned_lines, ["thoi han su dung", "thoi han"]),
            "hinh_thuc_su_dung": _extract_property_land_use_form(cleaned_lines),
            "nguon_goc": _extract_property_field_by_label(cleaned_lines, ["nguon goc su dung", "nguon goc"]),
            "land_rows": land_rows,
        }
    )
    _fill_property_from_land_rows(data)
    non_empty = sum(1 for v in data.values() if _property_has_value(v))
    strong_fields = ["so_serial", "so_vao_so", "so_thua_dat", "so_to_ban_do", "dien_tich", "dia_chi", "loai_dat", "chu_su_dung"]
    strong_hits = sum(1 for key in strong_fields if _property_has_value(data.get(key)))
    if not looks_like_property and strong_hits < 2:
        return {"doc_type": "unknown", "side": normalized_side, "data": {}, "filename": filename, "text_lines": cleaned_lines}
    missing_fields = _property_missing_fields(data)
    warnings = list(missing_fields)
    return {
        "doc_type": "property" if non_empty > 0 else "unknown",
        "side": normalized_side,
        "data": data if non_empty > 0 else {},
        "filename": filename,
        "text_lines": cleaned_lines,
        "warnings": warnings,
        "missing_fields": missing_fields,
    }


def _property_doc_score(doc: dict[str, Any]) -> int:
    if doc.get("doc_type") != "property":
        return 0
    data = doc.get("data") if isinstance(doc.get("data"), dict) else {}
    score = 0
    for key in ("so_serial", "so_vao_so", "dia_chi", "ngay_cap"):
        if _property_has_value(data.get(key)):
            score += 2
    for key in ("so_thua_dat", "so_to_ban_do", "dien_tich", "co_quan_cap", "loai_so", "land_rows"):
        if _property_has_value(data.get(key)):
            score += 1
    return score


def _should_retry_property_rotate(doc: dict[str, Any]) -> bool:
    if doc.get("doc_type") != "property":
        return False
    data = doc.get("data") if isinstance(doc.get("data"), dict) else {}
    critical = ["so_serial", "so_vao_so", "dia_chi", "ngay_cap"]
    filled = sum(1 for key in critical if _property_has_value(data.get(key)))
    return filled < 3


def _count_alpha_num(text: str) -> int:
    return sum(1 for ch in text if ch.isalnum())


def _property_serial_value_score(value: str) -> int:
    compact = re.sub(r"\s+", "", _clean_property_code(value).upper())
    if not compact:
        return 0
    if re.fullmatch(r"[A-Z]{2}\d{6,8}", compact):
        return 10
    if re.fullmatch(r"[A-Z]\d{6,8}", compact):
        return 7
    if re.fullmatch(r"[A-Z]{1,4}\d{4,12}(?:/\d{1,8})?", compact):
        return 4
    return 1


def _property_registry_value_score(value: str) -> int:
    compact = re.sub(r"\s+", "", _clean_property_code(value).upper())
    if not compact:
        return 0
    if re.fullmatch(r"[A-Z]{1,4}\d{3,12}(?:/\d{1,8})?", compact):
        return 8 + (1 if "/" in compact else 0)
    if re.fullmatch(r"[A-Z]{1,4}\d{3,12}", compact):
        return 7
    return 1


def _property_area_value_score(value: str) -> int:
    text = _normalize_property_area_number(value)
    if not text:
        return 0
    try:
        area = float(text)
    except Exception:
        return 0
    if area <= 0 or area > 1000000:
        return 1
    return 7 + (1 if "." in text else 0)


def _merge_property_land_rows(front_rows: list[dict[str, str]], back_rows: list[dict[str, str]]) -> tuple[list[dict[str, str]], str]:
    merged_rows: dict[str, dict[str, str]] = {}
    sources: set[str] = set()
    for source, rows in (("front", front_rows), ("back", back_rows)):
        for raw_row in rows:
            if not isinstance(raw_row, dict):
                continue
            row = _normalize_property_data({"land_rows": [raw_row]}).get("land_rows", [])
            if not row:
                continue
            item = row[0]
            code = _clean_text(item.get("loai_dat")) or f"__{len(merged_rows)}"
            current = merged_rows.get(code)
            if current is None:
                merged_rows[code] = item
                sources.add(source)
                continue
            if _property_area_value_score(item.get("dien_tich", "")) > _property_area_value_score(current.get("dien_tich", "")):
                current["dien_tich"] = item.get("dien_tich", "")
            if _clean_text(item.get("thoi_han")) and not _clean_text(current.get("thoi_han")):
                current["thoi_han"] = item.get("thoi_han", "")
            sources.add(source)
    if not merged_rows:
        return [], "none"
    source_tag = "merged" if len(sources) > 1 else next(iter(sources))
    return list(merged_rows.values()), source_tag


def _property_value_clean_score(field: str, value: Any) -> tuple[int, int, int, str]:
    if isinstance(value, list):
        return (1 if len(value) > 0 else 0, len(value), 0, json.dumps(value, ensure_ascii=False, default=str))
    text = _clean_text(value)
    if not text:
        return (0, 0, 0, "")
    quality = 1
    if field == "so_serial":
        quality = _property_serial_value_score(text)
    elif field == "so_vao_so":
        quality = _property_registry_value_score(text)
    elif field == "dia_chi":
        quality = _property_address_score(text)
    elif field == "chu_su_dung":
        quality = _property_owner_score(text)
    elif field == "dien_tich":
        quality = _property_area_value_score(text)
    elif field == "co_quan_cap":
        quality = _property_authority_score(_clean_property_authority_value(text))
    elif field in {"so_thua_dat", "so_to_ban_do", "dien_tich"}:
        quality += 1 if re.search(r"\d", text) else 0
    elif field in {"loai_dat"}:
        quality = 6 if _normalize_property_land_type_value(text) else 1
    stable_text = _clean_text(text)
    return (quality, len(text), _count_alpha_num(text), stable_text)


def _parse_property_issue_date_candidate(value: Any) -> tuple[bool, bool, int, str]:
    text = _clean_text(value)
    normalized = _normalize_date(text)
    if not normalized:
        return (False, False, 0, "")
    try:
        parsed = datetime.strptime(normalized, "%d/%m/%Y")
    except ValueError:
        return (True, False, 0, normalized)
    today = datetime.now()
    in_range = datetime(1900, 1, 1) <= parsed <= today
    return (True, in_range, parsed.toordinal() if in_range else 0, normalized)


def _property_authority_marker_score(value: Any) -> int:
    key = _fold_text(_clean_property_authority_value(_clean_text(value)))
    if not key:
        return 0
    score = 0
    if "chi nhanh van phong dang ky" in key:
        score += 4
    if "van phong dang ky" in key:
        score += 3
    if "so tai nguyen" in key:
        score += 3
    if "ubnd" in key or "uy ban nhan dan" in key:
        score += 3
    return score


def _pick_property_issue_date_value(front_value: Any, back_value: Any) -> tuple[Any, str] | None:
    front_meta = _parse_property_issue_date_candidate(front_value)
    back_meta = _parse_property_issue_date_candidate(back_value)
    if back_meta[:3] > front_meta[:3]:
        return back_meta[3], "back"
    if front_meta[:3] > back_meta[:3]:
        return front_meta[3], "front"
    return None


def _pick_property_authority_value(front_value: Any, back_value: Any) -> tuple[Any, str] | None:
    front_clean = _clean_property_authority_value(_clean_text(front_value))
    back_clean = _clean_property_authority_value(_clean_text(back_value))
    if front_clean and back_clean and front_clean == back_clean:
        if len(_clean_text(back_value)) < len(_clean_text(front_value)):
            return back_clean, "back"
        return front_clean, "front"
    front_key = (
        _property_authority_marker_score(front_clean),
        _property_authority_score(front_clean),
        -len(front_clean),
        front_clean,
    )
    back_key = (
        _property_authority_marker_score(back_clean),
        _property_authority_score(back_clean),
        -len(back_clean),
        back_clean,
    )
    if back_key > front_key:
        return back_clean, "back"
    if front_key > back_key:
        return front_clean, "front"
    return None


def _pick_property_field_value(field: str, front_value: Any, back_value: Any) -> tuple[Any, str]:
    front_has = _property_has_value(front_value)
    back_has = _property_has_value(back_value)
    if front_has and not back_has:
        return front_value, "front"
    if back_has and not front_has:
        return back_value, "back"
    if not front_has and not back_has:
        return "", "none"
    if field == "ngay_cap":
        chosen = _pick_property_issue_date_value(front_value, back_value)
        if chosen is not None:
            return chosen
    if field == "co_quan_cap":
        chosen = _pick_property_authority_value(front_value, back_value)
        if chosen is not None:
            return chosen
    if isinstance(front_value, list) and isinstance(back_value, list):
        if _property_value_clean_score(field, back_value) > _property_value_clean_score(field, front_value):
            return back_value, "back"
        return front_value, "front"
    if _property_value_clean_score(field, back_value) > _property_value_clean_score(field, front_value):
        return back_value, "back"
    if _property_value_clean_score(field, front_value) > _property_value_clean_score(field, back_value):
        return front_value, "front"
    if _clean_text(str(back_value)) < _clean_text(str(front_value)):
        return back_value, "back"
    return front_value, "front"


def _merge_property_pair(front_doc: dict[str, Any], back_doc: dict[str, Any]) -> dict[str, Any]:
    front_data = front_doc.get("data") if isinstance(front_doc.get("data"), dict) else {}
    back_data = back_doc.get("data") if isinstance(back_doc.get("data"), dict) else {}
    merged_seed: dict[str, Any] = {}
    field_sources: dict[str, str] = {}

    for field in _PROPERTY_FORM_FIELDS:
        chosen, source = _pick_property_field_value(field, front_data.get(field), back_data.get(field))
        merged_seed[field] = chosen
        if source in {"front", "back"}:
            field_sources[field] = source

    front_rows = front_data.get("land_rows") if isinstance(front_data.get("land_rows"), list) else []
    back_rows = back_data.get("land_rows") if isinstance(back_data.get("land_rows"), list) else []
    merged_rows, rows_source = _merge_property_land_rows(front_rows, back_rows)
    merged_seed["land_rows"] = merged_rows
    if rows_source in {"front", "back", "merged"}:
        field_sources["land_rows"] = rows_source

    merged = _normalize_property_data(merged_seed)
    _fill_property_from_land_rows(merged)

    missing_fields = _property_missing_fields(merged)
    warnings: list[str] = []
    if front_doc.get("doc_type") != "property":
        warnings.append("front_not_property")
    if back_doc.get("doc_type") != "property":
        warnings.append("back_not_property")
    warnings.extend(f"missing_{field}" for field in missing_fields)

    return {
        **merged,
        "field_sources": field_sources,
        "missing_fields": missing_fields,
        "warnings": warnings,
    }


def _normalize_native_ocr_doc(lines: list[str], filename: str) -> dict[str, Any]:
    cleaned_lines = [_clean_text(ln) for ln in lines if _clean_text(ln)]
    if not cleaned_lines:
        return {"doc_type": "unknown", "side": "unknown", "data": {}, "filename": filename, "text_lines": []}

    side = _detect_side(cleaned_lines)
    mrz_lines = _extract_mrz_lines(cleaned_lines)
    mrz_data = _parse_person_mrz(mrz_lines) if mrz_lines else _normalize_person_data({})

    ai_data = _normalize_person_data(
        {
            "ho_ten": _extract_name_candidate(cleaned_lines, side=side),
            "so_giay_to": _extract_id(cleaned_lines),
            "ngay_sinh": _extract_birth_date(cleaned_lines),
            "gioi_tinh": _extract_gender(cleaned_lines),
            "dia_chi": _extract_address(cleaned_lines),
            "ngay_cap": _extract_issue_date(cleaned_lines, side=side),
            "ngay_het_han": "",
        }
    )

    # Front-side CCCD does not carry the real issue date. When Qwen hallucinates a
    # date on a front image, keep it out of the deterministic payload and require
    # a matching back side instead.
    if side == "front":
        ai_data["ngay_cap"] = ""

    if side == "back":
        if mrz_data.get("so_giay_to"):
            ai_data["so_giay_to"] = mrz_data["so_giay_to"]
        if mrz_data.get("ho_ten"):
            ai_data["ho_ten"] = mrz_data["ho_ten"]
        if mrz_data.get("ngay_sinh"):
            ai_data["ngay_sinh"] = mrz_data["ngay_sinh"]
        if mrz_data.get("gioi_tinh"):
            ai_data["gioi_tinh"] = mrz_data["gioi_tinh"]

    non_empty = sum(1 for v in ai_data.values() if _clean_text(v))
    doc_type = "person" if non_empty > 0 else "unknown"
    return {
        "doc_type": doc_type,
        "side": side,
        "data": ai_data if doc_type == "person" else {},
        "filename": filename,
        "text_lines": cleaned_lines,
    }


def _append_qr_person(
    *,
    persons: list[dict[str, Any]],
    raw_results: list[dict[str, Any]],
    filename: str,
    qr_text: str,
    qr_data: dict[str, Any],
) -> None:
    normalized = _normalize_person_data(qr_data)
    person = {
        **normalized,
        "_source": "QR",
        "source_type": "QR",
        "side": "front",
        "_files": [filename],
        "_qr": True,
        "field_sources": _field_sources(normalized, "qr"),
        "warnings": ["missing_back"],
        "_qr_text": qr_text,
    }
    persons.append(person)
    raw_results.append({"doc_type": "person", "side": "front", "data": normalized, "filename": filename, "source_type": "QR"})


def _append_ai_doc(
    *,
    doc: dict[str, Any],
    persons: list[dict[str, Any]],
    raw_results: list[dict[str, Any]],
) -> None:
    raw_results.append({**doc, "source_type": "AI"})
    if doc.get("doc_type") != "person":
        return
    data = doc.get("data") if isinstance(doc.get("data"), dict) else {}
    persons.append(
        {
            **data,
            "_source": "AI",
            "source_type": "AI",
            "side": doc.get("side", "unknown"),
            "_files": [doc.get("filename") or "unknown"],
            "_qr": False,
            "field_sources": _field_sources(data, "ai"),
            "warnings": list(doc.get("warnings") or []),
            "_raw_text": "\n".join(doc.get("text_lines") or []),
        }
    )


def _has_diacritics(text: str) -> bool:
    value = _clean_text(text)
    if not value:
        return False
    if "đ" in value.lower():
        return True
    normalized = unicodedata.normalize("NFD", value)
    return any(unicodedata.combining(ch) for ch in normalized)


def _normalize_name_ascii(value: str) -> str:
    folded = _fold_text(_clean_text(value))
    folded = re.sub(r"[^a-z\s]", " ", folded)
    return re.sub(r"\s+", " ", folded).strip()


def _id_hamming_distance(left: str, right: str) -> int | None:
    if len(left) != 12 or len(right) != 12:
        return None
    return sum(1 for a, b in zip(left, right) if a != b)


def _name_match_strong(left: str, right: str) -> bool:
    a = _normalize_name_ascii(left)
    b = _normalize_name_ascii(right)
    if not a or not b:
        return False
    if a == b:
        return True
    if SequenceMatcher(None, a, b).ratio() >= PAIR_FUZZY_NAME_THRESHOLD:
        return True
    tokens_a = {tok for tok in a.split() if len(tok) >= 2}
    tokens_b = {tok for tok in b.split() if len(tok) >= 2}
    if len(tokens_a) >= 2 and len(tokens_b) >= 2 and tokens_a == tokens_b:
        return True
    return False


def _sides_can_pair(side_a: str, side_b: str) -> bool:
    a = _clean_text(side_a).lower() or "unknown"
    b = _clean_text(side_b).lower() or "unknown"
    if a == "front_back" or b == "front_back":
        return False
    sides = {a, b}
    if "front" in sides and "back" in sides:
        return True
    if "unknown" in sides and ("front" in sides or "back" in sides):
        return True
    return False


def _is_optional_field_compatible(left: dict[str, Any], right: dict[str, Any], key: str) -> bool:
    a = _clean_text(left.get(key))
    b = _clean_text(right.get(key))
    if not a or not b:
        return True
    if key in {"gioi_tinh"}:
        return _fold_text(a) == _fold_text(b)
    return a == b


def _should_fuzzy_pair(left: dict[str, Any], right: dict[str, Any]) -> bool:
    id_left = re.sub(r"\D", "", str(left.get("so_giay_to") or ""))
    id_right = re.sub(r"\D", "", str(right.get("so_giay_to") or ""))
    if len(id_left) != 12 or len(id_right) != 12 or id_left == id_right:
        return False

    mismatch = _id_hamming_distance(id_left, id_right)
    if mismatch is None or mismatch > PAIR_FUZZY_MAX_ID_MISMATCH:
        return False

    if not _name_match_strong(str(left.get("ho_ten") or ""), str(right.get("ho_ten") or "")):
        return False
    if not _sides_can_pair(str(left.get("side") or "unknown"), str(right.get("side") or "unknown")):
        return False
    if not _is_optional_field_compatible(left, right, "ngay_sinh"):
        return False
    if not _is_optional_field_compatible(left, right, "gioi_tinh"):
        return False
    return True


def _merge_person_group(group: list[dict[str, Any]]) -> dict[str, Any]:
    merged = {
        "ho_ten": "",
        "so_giay_to": "",
        "ngay_sinh": "",
        "gioi_tinh": "",
        "dia_chi": "",
        "ngay_cap": "",
        "ngay_het_han": "",
        "_source": "AI",
        "source_type": "AI",
        "side": "unknown",
        "_files": [],
        "_qr": False,
        "field_sources": {},
        "warnings": [],
        "paired": False,
    }
    source_priority = {"QR": 2, "AI": 1}
    side_seen = set()
    seen_files = set()
    qr_found = False

    for item in group:
        src = str(item.get("source_type") or "AI").upper()
        if src == "QR":
            qr_found = True
        side = str(item.get("side") or "unknown").lower()
        if side in {"front", "back"}:
            side_seen.add(side)
        for f in (item.get("_files") or []):
            if f and f not in seen_files:
                seen_files.add(f)
                merged["_files"].append(f)

        for warning in item.get("warnings") or []:
            clean_warning = _clean_text(warning)
            if clean_warning and clean_warning not in merged["warnings"]:
                merged["warnings"].append(clean_warning)

        for key in ("ho_ten", "so_giay_to", "ngay_sinh", "gioi_tinh", "dia_chi", "ngay_cap", "ngay_het_han"):
            current = _clean_text(merged.get(key))
            incoming = _clean_text(item.get(key))
            if not incoming:
                continue
            if not current:
                merged[key] = incoming
                merged["field_sources"][key] = src.lower()
                continue
            cur_src = merged["field_sources"].get(key, "ai")
            if source_priority.get(src, 1) > source_priority.get(cur_src.upper(), 1):
                merged[key] = incoming
                merged["field_sources"][key] = src.lower()
            elif len(incoming) > len(current):
                merged[key] = incoming

    # Name priority: QR > front > unknown > back; prefer Vietnamese diacritics over MRZ-style ASCII.
    best_name = ""
    best_name_source = ""
    best_name_score = (-1, -1, -1, -1)
    for item in group:
        name = _clean_text(item.get("ho_ten"))
        if not name:
            continue
        src = str(item.get("source_type") or "AI").upper()
        side = str(item.get("side") or "unknown").lower()
        score = (
            source_priority.get(src, 1),
            2 if side == "front" else 1 if side == "unknown" else 0,
            1 if _has_diacritics(name) else 0,
            len(name),
        )
        if score > best_name_score:
            best_name_score = score
            best_name = name
            best_name_source = src.lower()
    if best_name:
        merged["ho_ten"] = best_name
        merged["field_sources"]["ho_ten"] = best_name_source

    merged["_qr"] = qr_found
    if qr_found:
        merged["_source"] = "QR"
        merged["source_type"] = "QR"
    merged["paired"] = len(group) > 1 or ("front" in side_seen and "back" in side_seen)
    if "front" in side_seen and "back" in side_seen:
        merged["side"] = "front_back"
    elif "front" in side_seen:
        merged["side"] = "front"
    elif "back" in side_seen:
        merged["side"] = "back"
    if merged["warnings"]:
        merged["warnings"] = [
            warning
            for warning in merged["warnings"]
            if not ((warning == "missing_front" and "front" in side_seen) or (warning == "missing_back" and "back" in side_seen))
        ]
    if not qr_found:
        if merged["side"] == "back" and "missing_front" not in merged["warnings"]:
            merged["warnings"].append("missing_front")
        elif merged["side"] == "front" and not _clean_text(merged.get("ngay_cap")) and "missing_back" not in merged["warnings"]:
            merged["warnings"].append("missing_back")
    return merged


def _pair_persons(persons: list[dict[str, Any]]) -> list[dict[str, Any]]:
    groups: dict[str, list[dict[str, Any]]] = {}
    passthrough: list[dict[str, Any]] = []
    for p in persons:
        id_no = re.sub(r"\D", "", str(p.get("so_giay_to") or ""))
        if len(id_no) == 12:
            groups.setdefault(id_no, []).append(p)
        else:
            one = dict(p)
            one["paired"] = False
            if not isinstance(one.get("_files"), list):
                one["_files"] = []
            passthrough.append(one)
    merged_exact = [_merge_person_group(g) for g in groups.values()]
    if len(merged_exact) < 2:
        return merged_exact + passthrough

    # Fuzzy stage for OCR slips: allow pairing when ID differs by <=1 digit,
    # names strongly match (accent/no-accent tolerant), and sides complement.
    parent = list(range(len(merged_exact)))

    def find(x: int) -> int:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a: int, b: int) -> None:
        ra = find(a)
        rb = find(b)
        if ra != rb:
            parent[rb] = ra

    for i in range(len(merged_exact)):
        for j in range(i + 1, len(merged_exact)):
            if _should_fuzzy_pair(merged_exact[i], merged_exact[j]):
                union(i, j)

    fuzzy_groups: dict[int, list[dict[str, Any]]] = {}
    for idx, person in enumerate(merged_exact):
        root = find(idx)
        fuzzy_groups.setdefault(root, []).append(person)

    merged_final: list[dict[str, Any]] = []
    for group in fuzzy_groups.values():
        if len(group) == 1:
            one = dict(group[0])
            if not isinstance(one.get("_files"), list):
                one["_files"] = []
            merged_final.append(one)
        else:
            merged_final.append(_merge_person_group(group))
    return merged_final + passthrough


async def _process_single_image(
    upload: UploadFile,
    *,
    model: str,
    api_key: str,
    ai_semaphore: asyncio.Semaphore,
    client: httpx.AsyncClient,
) -> dict[str, Any]:
    filename = upload.filename or "unknown"
    file_bytes = await upload.read()

    async def run_qr() -> tuple[str, dict[str, Any] | None]:
        qr_text = try_decode_qr(file_bytes) or ""
        qr_data = parse_cccd_qr(qr_text) if qr_text else None
        if not (qr_data and qr_data.get("so_giay_to")):
            return "", None
        return qr_text, qr_data

    async def run_ai() -> dict[str, Any]:
        if not api_key:
            raise HTTPException(status_code=500, detail="Missing API key for OCR AI model")
        image_jpeg = _prepare_ai_image_bytes(file_bytes)
        image_b64 = base64.b64encode(image_jpeg).decode()
        async with ai_semaphore:
            lines = await _call_qwen_native_ocr_single(
                client,
                api_key=api_key,
                model=model,
                image_b64=image_b64,
                filename=filename,
            )
        return _normalize_native_ocr_doc(lines, filename)

    qr_task = asyncio.create_task(run_qr())
    ai_task = asyncio.create_task(run_ai())
    qr_result, ai_result = await asyncio.gather(qr_task, ai_task, return_exceptions=True)

    out: dict[str, Any] = {
        "filename": filename,
        "qr_text": "",
        "qr_data": None,
        "ai_doc": None,
        "error": None,
        "ai_started": True,
        "ai_discarded_by_qr": False,
        "ai_selected": False,
    }

    if isinstance(qr_result, Exception):
        _log_ocr_ai("qr_decode_error", level="warning", filename=filename, error=str(qr_result)[:300])
    elif isinstance(qr_result, tuple):
        out["qr_text"], out["qr_data"] = qr_result

    if isinstance(ai_result, Exception):
        if out["qr_data"] is None:
            detail = ai_result.detail if isinstance(ai_result, HTTPException) else str(ai_result)
            out["error"] = str(detail)
    else:
        out["ai_doc"] = ai_result

    if out["qr_data"] is not None:
        out["ai_discarded_by_qr"] = out["ai_doc"] is not None
        return out

    if out["ai_doc"] is not None:
        out["ai_selected"] = True
    return out


async def _process_single_property_image(
    upload: UploadFile,
    *,
    model: str,
    api_key: str,
    ai_semaphore: asyncio.Semaphore,
    client: httpx.AsyncClient,
    side: str = "unknown",
    enable_footer_date_rescue: bool = True,
) -> dict[str, Any]:
    filename = upload.filename or "unknown"
    file_bytes = await upload.read()
    if not api_key:
        raise HTTPException(status_code=500, detail="Missing API key for OCR AI model")

    image_jpeg = _prepare_ai_image_bytes(file_bytes)
    image_b64 = base64.b64encode(image_jpeg).decode()
    used_rotate_retry = False

    async with ai_semaphore:
        lines = await _call_qwen_native_ocr_single(
            client,
            api_key=api_key,
            model=model,
            image_b64=image_b64,
            filename=filename,
            enable_rotate=False,
        )
    doc = _normalize_property_ocr_doc(lines, filename, side=side)

    if _should_retry_property_rotate(doc):
        try:
            async with ai_semaphore:
                lines_rotate = await _call_qwen_native_ocr_single(
                    client,
                    api_key=api_key,
                    model=model,
                    image_b64=image_b64,
                    filename=filename,
                    enable_rotate=True,
                )
            rotated_doc = _normalize_property_ocr_doc(lines_rotate, filename, side=side)
            if _property_doc_score(rotated_doc) >= _property_doc_score(doc):
                doc = rotated_doc
            used_rotate_retry = True
        except Exception as exc:
            _log_ocr_ai(
                "property_rotate_retry_error",
                level="warning",
                filename=filename,
                error=str(exc)[:240],
            )

    used_footer_date_rescue = False
    if enable_footer_date_rescue and _should_rescue_property_issue_date(doc):
        footer_bytes = _prepare_property_footer_image_bytes(file_bytes)
        if footer_bytes:
            try:
                footer_b64 = base64.b64encode(footer_bytes).decode()
                async with ai_semaphore:
                    footer_lines = await _call_qwen_native_ocr_single(
                        client,
                        api_key=api_key,
                        model=model,
                        image_b64=footer_b64,
                        filename=f"{filename}#footer",
                        enable_rotate=False,
                    )
                footer_date = _extract_property_issue_date(footer_lines)
                if footer_date:
                    footer_authority = _extract_property_authority(footer_lines, footer_date)
                    current_date = _clean_text((doc.get("data") if isinstance(doc.get("data"), dict) else {}).get("ngay_cap"))
                    current_year = _extract_year(current_date)
                    footer_year = _extract_year(footer_date)
                    footer_context_year = _extract_footer_context_year(
                        doc.get("text_lines") if isinstance(doc.get("text_lines"), list) else []
                    )
                    should_replace_date = (
                        not current_date
                        or (footer_context_year and footer_year == footer_context_year and footer_year > current_year)
                    )
                    if should_replace_date and isinstance(doc.get("data"), dict):
                        doc["data"]["ngay_cap"] = footer_date
                        current_authority = _clean_text(doc["data"].get("co_quan_cap"))
                        if footer_authority and _property_authority_score(footer_authority) > _property_authority_score(current_authority):
                            doc["data"]["co_quan_cap"] = footer_authority
                        doc["missing_fields"] = _property_missing_fields(doc["data"])
                        doc["warnings"] = list(doc["missing_fields"])
                        doc["text_lines"] = list(doc.get("text_lines") or []) + ["[footer_rescue]"] + footer_lines
                    used_footer_date_rescue = True
            except Exception as exc:
                _log_ocr_ai(
                    "property_footer_date_rescue_error",
                    level="warning",
                    filename=filename,
                    error=str(exc)[:240],
                )

    return {
        "filename": filename,
        "side": _normalize_property_side(side),
        "doc": doc,
        "used_rotate_retry": used_rotate_retry,
        "used_footer_date_rescue": used_footer_date_rescue,
    }


@router.post("/analyze")
async def analyze_images(files: list[UploadFile] = File(...)):
    if not files:
        raise HTTPException(status_code=400, detail="No images uploaded")

    t_total = perf_counter()
    t_qr_ai_start = perf_counter()

    persons: list[dict[str, Any]] = []
    properties: list[dict[str, Any]] = []
    marriages: list[dict[str, Any]] = []
    raw_results: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []

    model = _get_model()
    api_key = _get_api_key(model)
    ai_semaphore = asyncio.Semaphore(OCR_AI_CONCURRENCY)

    results: list[dict[str, Any]] = []
    async with httpx.AsyncClient(timeout=AI_TIMEOUT_SECONDS) as client:
        tasks = [
            _process_single_image(
                upload,
                model=model,
                api_key=api_key,
                ai_semaphore=ai_semaphore,
                client=client,
            )
            for upload in files
        ]
        for item in await asyncio.gather(*tasks, return_exceptions=True):
            if isinstance(item, Exception):
                errors.append({"filename": "unknown", "error": str(item)})
            else:
                results.append(item)

    qr_ai_ms = perf_counter() - t_qr_ai_start

    qr_hits = 0
    ai_started = 0
    ai_selected = 0
    ai_discarded = 0

    t_parse_start = perf_counter()
    for item in results:
        filename = item["filename"]
        ai_started += 1 if item.get("ai_started") else 0
        if item.get("error"):
            errors.append({"filename": filename, "error": str(item["error"])})
            continue

        qr_data = item.get("qr_data")
        if qr_data:
            qr_hits += 1
            if item.get("ai_discarded_by_qr"):
                ai_discarded += 1
            _append_qr_person(
                persons=persons,
                raw_results=raw_results,
                filename=filename,
                qr_text=item.get("qr_text") or "",
                qr_data=qr_data,
            )
            continue

        doc = item.get("ai_doc")
        if isinstance(doc, dict):
            if item.get("ai_selected"):
                ai_selected += 1
            _append_ai_doc(doc=doc, persons=persons, raw_results=raw_results)
        else:
            errors.append({"filename": filename, "error": "No OCR result"})

    backend_parse_ms = perf_counter() - t_parse_start

    t_pair_start = perf_counter()
    persons = _pair_persons(persons)
    pair_ms = perf_counter() - t_pair_start

    unknowns = sum(1 for item in raw_results if item.get("doc_type") == "unknown")
    paired_count = sum(1 for person in persons if person.get("paired"))
    total_ms = perf_counter() - t_total

    _log_ocr_ai(
        "ocr_ai_done",
        model=model,
        images=len(files),
        total_ms=_ms(total_ms),
        qr_ms=_ms(qr_ai_ms),
        ocr_native_ms=_ms(qr_ai_ms),
        backend_parse_ms=_ms(backend_parse_ms),
        pair_ms=_ms(pair_ms),
        qr_hits=qr_hits,
        ai_started=ai_started,
        ai_selected=ai_selected,
        ai_discarded_by_qr=ai_discarded,
        errors=len(errors),
    )

    return {
        "persons": persons,
        "properties": properties,
        "marriages": marriages,
        "raw_results": raw_results,
        "errors": errors,
        "summary": {
            "total_images": len(files),
            "model": model,
            "qr_hits": qr_hits,
            "ai_runs": ai_selected,
            "ocr_runs": ai_selected,
            "ai_started": ai_started,
            "ai_selected": ai_selected,
            "ai_discarded_by_qr": ai_discarded,
            "persons": len(persons),
            "paired_persons": paired_count,
            "properties": len(properties),
            "marriages": len(marriages),
            "unknowns": unknowns,
            "ocr_native_ms": _ms(qr_ai_ms),
            "backend_parse_ms": _ms(backend_parse_ms),
            "pair_ms": _ms(pair_ms),
            "total_ms": _ms(total_ms),
        },
    }


@router.post("/analyze-property")
async def analyze_property_images(files: list[UploadFile] = File(...)):
    if not files:
        raise HTTPException(status_code=400, detail="No images uploaded")

    t_total = perf_counter()
    properties: list[dict[str, Any]] = []
    raw_results: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []

    model = _get_model()
    api_key = _get_api_key(model)
    ai_semaphore = asyncio.Semaphore(OCR_AI_CONCURRENCY)

    results: list[dict[str, Any]] = []
    async with httpx.AsyncClient(timeout=AI_TIMEOUT_SECONDS) as client:
        tasks = [
            _process_single_property_image(
                upload,
                model=model,
                api_key=api_key,
                ai_semaphore=ai_semaphore,
                client=client,
                side="unknown",
            )
            for upload in files
        ]
        for item in await asyncio.gather(*tasks, return_exceptions=True):
            if isinstance(item, Exception):
                detail = item.detail if isinstance(item, HTTPException) else str(item)
                errors.append({"filename": "unknown", "error": str(detail)})
            else:
                results.append(item)

    used_rotate_retry = 0
    used_footer_date_rescue = 0
    unknowns = 0
    for item in results:
        filename = str(item.get("filename") or "unknown")
        doc = item.get("doc") if isinstance(item.get("doc"), dict) else {}
        used_rotate_retry += 1 if item.get("used_rotate_retry") else 0
        used_footer_date_rescue += 1 if item.get("used_footer_date_rescue") else 0
        if not doc:
            errors.append({"filename": filename, "error": "No OCR result"})
            continue

        doc_type = str(doc.get("doc_type") or "unknown")
        data = doc.get("data") if isinstance(doc.get("data"), dict) else {}
        warnings = doc.get("warnings") if isinstance(doc.get("warnings"), list) else []
        missing_fields = doc.get("missing_fields") if isinstance(doc.get("missing_fields"), list) else []
        raw_results.append(
            {
                "doc_type": doc_type,
                "filename": filename,
                "side": "unknown",
                "source_type": "AI",
                "data": data,
                "text_lines": doc.get("text_lines") if isinstance(doc.get("text_lines"), list) else [],
                "warnings": warnings,
                "missing_fields": missing_fields,
                "status": "ok" if doc_type == "property" else "skipped",
            }
        )
        if doc_type == "property":
            properties.append(
                {
                    **data,
                    "_file": filename,
                    "_source": "AI",
                    "source_type": "AI",
                    "warnings": warnings,
                    "missing_fields": missing_fields,
                }
            )
        else:
            unknowns += 1

    total_ms = perf_counter() - t_total
    _log_ocr_ai(
        "ocr_property_done",
        model=model,
        images=len(files),
        properties=len(properties),
        unknowns=unknowns,
        errors=len(errors),
        rotate_retry=used_rotate_retry,
        footer_date_rescue=used_footer_date_rescue,
        total_ms=_ms(total_ms),
    )
    return {
        "persons": [],
        "properties": properties,
        "marriages": [],
        "raw_results": raw_results,
        "errors": errors,
        "summary": {
            "total_images": len(files),
            "model": model,
            "persons": 0,
            "properties": len(properties),
            "marriages": 0,
            "unknowns": unknowns,
            "rotate_retry": used_rotate_retry,
            "footer_date_rescue": used_footer_date_rescue,
            "total_ms": _ms(total_ms),
        },
    }


@router.post("/analyze-property-pair")
async def analyze_property_pair(
    front_file: UploadFile = File(...),
    back_file: UploadFile = File(...),
):
    t_total = perf_counter()
    model = _get_model()
    api_key = _get_api_key(model)
    ai_semaphore = asyncio.Semaphore(OCR_AI_CONCURRENCY)

    errors: list[dict[str, Any]] = []
    front_result: dict[str, Any] | None = None
    back_result: dict[str, Any] | None = None

    async with httpx.AsyncClient(timeout=AI_TIMEOUT_SECONDS) as client:
        tasks = [
            _process_single_property_image(
                front_file,
                model=model,
                api_key=api_key,
                ai_semaphore=ai_semaphore,
                client=client,
                side="front",
                enable_footer_date_rescue=False,
            ),
            _process_single_property_image(
                back_file,
                model=model,
                api_key=api_key,
                ai_semaphore=ai_semaphore,
                client=client,
                side="back",
                enable_footer_date_rescue=False,
            ),
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        for idx, item in enumerate(results):
            side = "front" if idx == 0 else "back"
            filename = front_file.filename if side == "front" else back_file.filename
            safe_filename = str(filename or f"{side}.jpg")
            if isinstance(item, Exception):
                detail = item.detail if isinstance(item, HTTPException) else str(item)
                errors.append({"side": side, "filename": safe_filename, "error": str(detail)})
                continue
            if side == "front":
                front_result = item
            else:
                back_result = item

    front_doc = (
        (front_result or {}).get("doc")
        if isinstance((front_result or {}).get("doc"), dict)
        else {"doc_type": "unknown", "side": "front", "data": {}, "filename": str(front_file.filename or "front.jpg")}
    )
    back_doc = (
        (back_result or {}).get("doc")
        if isinstance((back_result or {}).get("doc"), dict)
        else {"doc_type": "unknown", "side": "back", "data": {}, "filename": str(back_file.filename or "back.jpg")}
    )

    merged = _merge_property_pair(front_doc, back_doc)
    property_data = {
        **{k: merged.get(k, "") for k in _PROPERTY_FORM_FIELDS},
        "land_rows": merged.get("land_rows") if isinstance(merged.get("land_rows"), list) else [],
        "field_sources": merged.get("field_sources") if isinstance(merged.get("field_sources"), dict) else {},
        "missing_fields": merged.get("missing_fields") if isinstance(merged.get("missing_fields"), list) else [],
        "warnings": merged.get("warnings") if isinstance(merged.get("warnings"), list) else [],
        "_source": "AI",
        "source_type": "AI",
        "_files": [
            str(front_doc.get("filename") or front_file.filename or "front.jpg"),
            str(back_doc.get("filename") or back_file.filename or "back.jpg"),
        ],
    }

    per_side = {
        "front": {
            "file": str(front_doc.get("filename") or front_file.filename or "front.jpg"),
            "doc_type": str(front_doc.get("doc_type") or "unknown"),
            "data": front_doc.get("data") if isinstance(front_doc.get("data"), dict) else {},
            "warnings": front_doc.get("warnings") if isinstance(front_doc.get("warnings"), list) else [],
            "missing_fields": front_doc.get("missing_fields") if isinstance(front_doc.get("missing_fields"), list) else [],
            "status": "ok" if str(front_doc.get("doc_type") or "") == "property" else "skipped",
            "text_lines": front_doc.get("text_lines") if isinstance(front_doc.get("text_lines"), list) else [],
        },
        "back": {
            "file": str(back_doc.get("filename") or back_file.filename or "back.jpg"),
            "doc_type": str(back_doc.get("doc_type") or "unknown"),
            "data": back_doc.get("data") if isinstance(back_doc.get("data"), dict) else {},
            "warnings": back_doc.get("warnings") if isinstance(back_doc.get("warnings"), list) else [],
            "missing_fields": back_doc.get("missing_fields") if isinstance(back_doc.get("missing_fields"), list) else [],
            "status": "ok" if str(back_doc.get("doc_type") or "") == "property" else "skipped",
            "text_lines": back_doc.get("text_lines") if isinstance(back_doc.get("text_lines"), list) else [],
        },
    }

    total_ms = perf_counter() - t_total
    _log_ocr_ai(
        "ocr_property_pair_done",
        model=model,
        front_file=per_side["front"]["file"],
        back_file=per_side["back"]["file"],
        front_doc_type=per_side["front"]["doc_type"],
        back_doc_type=per_side["back"]["doc_type"],
        missing_fields=len(property_data.get("missing_fields") or []),
        errors=len(errors),
        total_ms=_ms(total_ms),
    )

    return {
        "property": property_data,
        "per_side": per_side,
        "warnings": property_data.get("warnings") or [],
        "missing_fields": property_data.get("missing_fields") or [],
        "summary": {
            "model": model,
            "total_ms": _ms(total_ms),
            "errors": len(errors),
            "front_doc_type": per_side["front"]["doc_type"],
            "back_doc_type": per_side["back"]["doc_type"],
        },
        "errors": errors,
    }


@router.get("/config")
async def ocr_config():
    model = _get_model()
    configured = bool(_get_api_key(model))
    return {
        "configured": configured,
        "model": model,
        "provider": "qwen_native_ocr" if "qwen" in model.lower() else "other",
        "max_image_px": AI_MAX_IMAGE_PX,
        "ocr_ai_concurrency": OCR_AI_CONCURRENCY,
        "qwen_ocr": {
            "base_url": QWEN_OCR_BASE_URL,
            "min_pixels": QWEN_OCR_MIN_PIXELS,
            "max_pixels": QWEN_OCR_MAX_PIXELS,
            "enable_rotate": QWEN_OCR_ENABLE_ROTATE,
        },
        "pairing": {
            "fuzzy_max_id_mismatch": PAIR_FUZZY_MAX_ID_MISMATCH,
            "fuzzy_name_threshold": PAIR_FUZZY_NAME_THRESHOLD,
        },
    }
