"""
Cloud OCR router.

Fast path:
1. Try QR once on the server using raw image bytes.
2. Preprocess image lightly.
3. If QR fails, send the image straight to AI OCR.

Cloud OCR intentionally avoids front/back, old/new, MRZ pairing, and other
document-side heuristics. Those rules belong to the Local OCR pipeline.
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


def _coerce_doc_type(value: Any) -> str:
    raw = _clean_text(value).lower()
    if raw in {"person", "cccd", "cccd_front", "cccd_back", "citizen_card", "id_card", "identity_card"}:
        return "person"
    if raw in {"marriage", "marriage_cert", "marriage_certificate", "ket_hon"}:
        return "marriage_cert"
    if raw in {"land", "land_cert", "land_certificate", "property", "red_book", "so_do"}:
        return "land_cert"
    return "unknown"


def _normalize_ai_item(item: Any, filename: str) -> dict[str, Any]:
    if not isinstance(item, dict):
        return {"doc_type": "unknown", "data": {}, "filename": filename}

    data = item.get("data")
    if not isinstance(data, dict):
        data = {}

    doc_type = _coerce_doc_type(item.get("doc_type"))
    if doc_type == "person":
        normalized_data = _normalize_person_data(data)
    elif doc_type == "marriage_cert":
        normalized_data = _normalize_marriage_data(data)
    elif doc_type == "land_cert":
        normalized_data = _normalize_land_data(data)
    else:
        normalized_data = {}

    side_raw = _clean_text(item.get("side", "")).lower()
    side = side_raw if side_raw in ("front", "back") else "unknown"
    return {"doc_type": doc_type, "data": normalized_data, "filename": filename, "side": side}


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

    if doc_type == "person":
        side = doc.get("side", "unknown")
        persons.append(
            {
                **data,
                "_source": "AI",
                "source_type": "AI",
                "side": side,
                "_files": [filename],
                "_qr": False,
                "field_sources": _field_sources(data, "ai"),
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
    persons = _mark_unpaired_persons(persons)
    pair_ms = perf_counter() - t_pair
    paired_count = 0
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
