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

DEFAULT_MODEL = "qwen-vl-ocr-latest"
QWEN_OCR_BASE_URL = os.getenv("QWEN_OCR_BASE_URL", "https://dashscope-intl.aliyuncs.com").rstrip("/")
QWEN_OCR_MIN_PIXELS = int(os.getenv("QWEN_OCR_MIN_PIXELS", "3072"))
QWEN_OCR_MAX_PIXELS = int(os.getenv("QWEN_OCR_MAX_PIXELS", "8388608"))
QWEN_OCR_ENABLE_ROTATE = os.getenv("QWEN_OCR_ENABLE_ROTATE", "0").strip().lower() in {"1", "true", "yes", "on"}
OCR_AI_CONCURRENCY = max(1, int(os.getenv("OCR_AI_CONCURRENCY", "6")))
AI_TIMEOUT_SECONDS = float(os.getenv("OCR_AI_TIMEOUT_SECONDS", "90"))
AI_MAX_IMAGE_PX = max(640, int(os.getenv("QWEN_MAX_IMAGE_PX", "1800")))
JPEG_QUALITY = 82


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
        return "Nu"
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
                gender = "Nu"

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
) -> list[str]:
    url = f"{QWEN_OCR_BASE_URL}/api/v1/services/aigc/multimodal-generation/generation"
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
                            "enable_rotate": QWEN_OCR_ENABLE_ROTATE,
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
                gioi_tinh = "Nu"
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


def _extract_address(lines: list[str]) -> str:
    for idx, line in enumerate(lines):
        if _looks_like_label(line, ["noi thuong tru", "noi cu tru", "place of residence"]):
            after = line.split(":", 1)[1].strip() if ":" in line else ""
            parts = [after] if after else []
            if idx + 1 < len(lines):
                next_line = _clean_text(lines[idx + 1])
                if next_line and not _looks_like_label(
                    next_line,
                    ["ho va ten", "ngay sinh", "gioi tinh", "so/no", "ngay cap", "date of issue", "que quan"],
                ):
                    parts.append(next_line)
            return _clean_text(", ".join([p for p in parts if p]))
    return ""


def _extract_issue_date(lines: list[str]) -> str:
    for line in lines:
        if _looks_like_label(line, ["ngay cap", "date of issue"]):
            dates = _extract_dates_from_line(line)
            if dates:
                return dates[0]
    return ""


def _extract_birth_date(lines: list[str]) -> str:
    for line in lines:
        if _looks_like_label(line, ["ngay sinh", "date of birth"]):
            dates = _extract_dates_from_line(line)
            if dates:
                return dates[0]
    return ""


def _extract_gender(lines: list[str]) -> str:
    for line in lines:
        if _looks_like_label(line, ["gioi tinh", "sex"]):
            g = _normalize_gender(line)
            if g:
                return g
    return ""


def _extract_id(lines: list[str]) -> str:
    for line in lines:
        id12 = _extract_id12(line)
        if id12:
            return id12
    return ""


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
            "ngay_cap": _extract_issue_date(cleaned_lines),
            "ngay_het_han": "",
        }
    )

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
        "side": "unknown",
        "_files": [filename],
        "_qr": True,
        "field_sources": _field_sources(normalized, "qr"),
        "warnings": [],
        "_qr_text": qr_text,
    }
    persons.append(person)
    raw_results.append({"doc_type": "person", "side": "unknown", "data": normalized, "filename": filename, "source_type": "QR"})


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
            "warnings": [],
        }
    )


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
    merged = [_merge_person_group(g) for g in groups.values()]
    return merged + passthrough


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
    }
