"""
Local OCR (YOLO + RapidOCR):
1) Tien xu ly anh (Python/OpenCV)
2) YOLO cat anh + nhan dien loai giay to (mat truoc/mat sau)
3) Quet QR neu ro (uu tien QR). Neu QR khong ro -> tiep tuc OCR
4) RapidOCR detect + nhan dang text
5) Regex loc truong thong tin can thiet
"""

from __future__ import annotations

import io
import asyncio
import json
import uuid
import os
import re
import traceback
import unicodedata
from datetime import datetime
from dataclasses import dataclass
from typing import List, Optional, Tuple

from fastapi import APIRouter, UploadFile, File, HTTPException, Form, Body

_LOCAL_OCR_IMPORT_ERROR = None
try:
    import cv2
    import numpy as np
    from PIL import Image
except ImportError as e:
    cv2 = None
    np = None
    Image = None
    _LOCAL_OCR_IMPORT_ERROR = str(e)

from .ocr import try_decode_qr, parse_cccd_qr
from database import SessionLocal
from models import OCRJob, ExtractedDocument
import httpx

router = APIRouter()

# ---------------------- Config (env) ----------------------
YOLO_WEIGHTS = os.getenv("LOCAL_OCR_YOLO_WEIGHTS", "").strip()
YOLO_CONF = float(os.getenv("LOCAL_OCR_YOLO_CONF", "0.25"))
YOLO_IMG_SIZE = int(os.getenv("LOCAL_OCR_YOLO_IMG_SIZE", "960"))
YOLO_REQUIRE = os.getenv("LOCAL_OCR_REQUIRE_YOLO", "").strip() == "1"

MIN_BOX_SCORE = float(os.getenv("LOCAL_OCR_MIN_BOX_SCORE", "0.3"))
TEXT_LLM_MODEL = os.getenv("OCR_TEXT_LLM_MODEL", "gpt-4o-mini")

_ENV_PATH = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".env"))


def _read_env() -> dict:
    from dotenv import dotenv_values
    return dotenv_values(_ENV_PATH)


def _get_openai_key() -> str:
    key = os.getenv("OPENAI_API_KEY", "")
    if not key:
        key = _read_env().get("OPENAI_API_KEY", "")
    return key


def _torch_disabled() -> bool:
    return os.getenv("LOCAL_OCR_DISABLE_TORCH", "").strip() == "1"


# ---------------------- Lazy-loaded models ----------------------
_yolo_model = None
_rapidocr_engine = None


def _ensure_local_ocr_dependencies() -> None:
    if _LOCAL_OCR_IMPORT_ERROR:
        raise HTTPException(
            status_code=503,
            detail=(
                "Local OCR chua duoc cai dat day du. "
                "Hay chay install_local_ocr.bat. "
                f"Chi tiet: {_LOCAL_OCR_IMPORT_ERROR}"
            ),
        )


def _get_yolo_model():
    _ensure_local_ocr_dependencies()
    global _yolo_model
    if _yolo_model is not None:
        return _yolo_model
    if _torch_disabled():
        return None
    if not YOLO_WEIGHTS:
        return None
    if not os.path.exists(YOLO_WEIGHTS):
        if YOLO_REQUIRE:
            raise HTTPException(status_code=500, detail=f"Khong tim thay YOLO weights: {YOLO_WEIGHTS}")
        return None
    try:
        from ultralytics import YOLO
        _yolo_model = YOLO(YOLO_WEIGHTS)
    except ImportError:
        if YOLO_REQUIRE:
            raise HTTPException(status_code=500, detail="Chua cai ultralytics. Hay chay: pip install ultralytics")
        _yolo_model = None
    except Exception as e:
        if YOLO_REQUIRE:
            raise HTTPException(status_code=500, detail=f"Khong the load YOLO: {e}")
        _yolo_model = None
    return _yolo_model


def _get_rapidocr_engine():
    _ensure_local_ocr_dependencies()
    global _rapidocr_engine
    if _rapidocr_engine is not None:
        return _rapidocr_engine
    try:
        try:
            from rapidocr_onnxruntime import RapidOCR
        except ImportError:
            from rapidocr import RapidOCR
        _rapidocr_engine = RapidOCR()
    except ImportError:
        raise HTTPException(
            status_code=500,
            detail="Chua cai RapidOCR. Hay chay install_local_ocr.bat",
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Khong the khoi dong RapidOCR: {e}")
    return _rapidocr_engine


def warmup_local_ocr():
    """Warmup for startup (optional)."""
    try:
        _ensure_local_ocr_dependencies()
        _get_rapidocr_engine()
    except Exception:
        pass
    try:
        _get_yolo_model()
    except Exception:
        pass


def _needs_llm_fallback(data: dict) -> bool:
    required = ["ho_ten", "so_giay_to", "ngay_sinh"]
    missing = [k for k in required if not (data.get(k) or "").strip()]
    return len(missing) >= 2


async def _llm_parse_text(raw_text: str, doc_type: str) -> dict | None:
    api_key = _get_openai_key()
    if not api_key:
        return None
    prompt = (
        "Trich xuat thong tin tu van ban OCR (tieng Viet). "
        "Tra ve JSON phu hop voi loai giay to. "
        f"Loai giay to: {doc_type}. "
        "Chi tra ve JSON, khong giai thich.\n\n"
        f"VAN BAN:\n{raw_text}"
    )
    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(
                "https://api.openai.com/v1/chat/completions",
                headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                json={
                    "model": TEXT_LLM_MODEL,
                    "temperature": 0,
                    "messages": [{"role": "user", "content": prompt}],
                    "max_tokens": 800,
                },
            )
        if not resp.is_success:
            return None
        content = resp.json().get("choices", [{}])[0].get("message", {}).get("content", "")
        content = re.sub(r"^```(?:json)?\s*|\s*```$", "", content.strip(), flags=re.MULTILINE)
        return json.loads(content)
    except Exception:
        return None


def _count_vietnamese_diacritics(text: str) -> int:
    return len(re.findall(r"[àáảãạăắằẳẵặâấầẩẫậèéẻẽẹêếềểễệìíỉĩịòóỏõọôốồổỗộơớờởỡợùúủũụưứừửữựỳýỷỹỵđ]", (text or "").lower()))


def _has_vietnamese_diacritics(text: str) -> bool:
    return _count_vietnamese_diacritics(text) > 0


async def _llm_restore_name_diacritics(name_text: str, raw_text: str = "") -> str | None:
    api_key = _get_openai_key()
    if not api_key or not (name_text or "").strip():
        return None
    prompt = (
        "Khoi phuc dau tieng Viet cho HO TEN duoi day. "
        "Chi tra ve duy nhat 1 dong ho ten da co dau, khong giai thich.\n\n"
        f"HO_TEN_KHONG_DAU: {name_text}\n"
        f"NGU_CANH_OCR:\n{raw_text[:1200]}"
    )
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                "https://api.openai.com/v1/chat/completions",
                headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                json={
                    "model": TEXT_LLM_MODEL,
                    "temperature": 0,
                    "messages": [{"role": "user", "content": prompt}],
                    "max_tokens": 120,
                },
            )
        if not resp.is_success:
            return None
        content = resp.json().get("choices", [{}])[0].get("message", {}).get("content", "")
        content = re.sub(r"^```(?:json)?\s*|\s*```$", "", content.strip(), flags=re.MULTILINE).strip()
        if ":" in content and re.search(r"ho\s*ten|full\s*name", _ascii_fold(content), re.IGNORECASE):
            content = re.sub(r"^[^:]{0,80}:\s*", "", content).strip()
        content = re.sub(r"\s+", " ", content).strip(" .,:;")
        if not content or re.search(r"\d", content):
            return None
        return content.upper()
    except Exception:
        return None


# ---------------------- Helpers ----------------------
@dataclass
class DocCrop:
    img: np.ndarray
    bbox: Tuple[int, int, int, int]  # x1, y1, x2, y2
    doc_type: str
    confidence: float


def _preprocess(img_bgr: np.ndarray) -> np.ndarray:
    """Light preprocessing for OCR."""
    img = img_bgr.copy()
    # Denoise + enhance contrast gently
    img = cv2.bilateralFilter(img, 5, 40, 40)
    # Sharpen to improve tiny QR/MRZ edges.
    kernel = np.array([[0, -1, 0], [-1, 5, -1], [0, -1, 0]], dtype=np.float32)
    img = cv2.filter2D(img, -1, kernel)
    return img


def _detect_documents(img_bgr: np.ndarray) -> List[DocCrop]:
    model = _get_yolo_model()
    h, w = img_bgr.shape[:2]
    if model is None:
        return [DocCrop(img=img_bgr, bbox=(0, 0, w, h), doc_type="unknown", confidence=0.0)]

    try:
        results = model.predict(img_bgr, conf=YOLO_CONF, imgsz=YOLO_IMG_SIZE, verbose=False)
        if not results:
            return [DocCrop(img=img_bgr, bbox=(0, 0, w, h), doc_type="unknown", confidence=0.0)]
        r = results[0]
        crops: List[DocCrop] = []
        names = getattr(model, "names", {}) or {}
        for box in r.boxes:
            xyxy = box.xyxy[0].cpu().numpy().astype(int).tolist()
            x1, y1, x2, y2 = xyxy
            conf = float(box.conf[0].cpu().numpy()) if hasattr(box, "conf") else 0.0
            cls_id = int(box.cls[0].cpu().numpy()) if hasattr(box, "cls") else -1
            label = str(names.get(cls_id, cls_id))
            doc_type = _map_doc_type(label)
            x1, y1 = max(0, x1), max(0, y1)
            x2, y2 = min(w, x2), min(h, y2)
            if x2 - x1 < 10 or y2 - y1 < 10:
                continue
            crops.append(DocCrop(img=img_bgr[y1:y2, x1:x2], bbox=(x1, y1, x2, y2), doc_type=doc_type, confidence=conf))
        if not crops:
            crops = [DocCrop(img=img_bgr, bbox=(0, 0, w, h), doc_type="unknown", confidence=0.0)]
        return crops
    except Exception:
        return [DocCrop(img=img_bgr, bbox=(0, 0, w, h), doc_type="unknown", confidence=0.0)]


def _map_doc_type(label: str) -> str:
    lbl = (label or "").lower()
    if "front" in lbl:
        return "cccd_front"
    if "back" in lbl:
        return "cccd_back"
    if "cccd" in lbl or "can_cuoc" in lbl or "card" in lbl:
        return "cccd"
    return "unknown"


def _normalize_box_points(box) -> np.ndarray | None:
    if box is None:
        return None
    arr = np.array(box, dtype=np.float32)
    if arr.size == 4 and arr.ndim == 1:
        x1, y1, x2, y2 = arr.tolist()
        arr = np.array(
            [[x1, y1], [x2, y1], [x2, y2], [x1, y2]],
            dtype=np.float32,
        )
    if arr.ndim != 2 or arr.shape[1] != 2:
        return None
    if arr.shape[0] == 2:
        (x1, y1), (x2, y2) = arr.tolist()
        arr = np.array(
            [[x1, y1], [x2, y1], [x2, y2], [x1, y2]],
            dtype=np.float32,
        )
    return arr


def _looks_like_box_list(value) -> bool:
    if not isinstance(value, (list, tuple)) or not value:
        return False
    try:
        return _normalize_box_points(value[0]) is not None
    except Exception:
        return False


def _rapidocr_entries(raw_result) -> List[Tuple[np.ndarray, str, float]]:
    if raw_result is None:
        return []

    if hasattr(raw_result, "boxes") and hasattr(raw_result, "txts"):
        boxes = getattr(raw_result, "boxes", []) or []
        txts = getattr(raw_result, "txts", []) or []
        scores = getattr(raw_result, "scores", []) or []
        entries = []
        for idx, box in enumerate(boxes):
            text = txts[idx] if idx < len(txts) else ""
            score = scores[idx] if idx < len(scores) else 1.0
            entries.append((box, text, score))
        return [
            (_normalize_box_points(box), str(text).strip(), float(score or 0.0))
            for box, text, score in entries
            if _normalize_box_points(box) is not None
        ]

    if isinstance(raw_result, tuple) and raw_result:
        if hasattr(raw_result[0], "boxes") and hasattr(raw_result[0], "txts"):
            return _rapidocr_entries(raw_result[0])

        if isinstance(raw_result[0], list):
            return _rapidocr_entries(raw_result[0])

        if len(raw_result) >= 3 and _looks_like_box_list(raw_result[0]):
            boxes, txts, scores = raw_result[:3]
            entries = []
            for idx, box in enumerate(boxes):
                text = txts[idx] if idx < len(txts) else ""
                score = scores[idx] if idx < len(scores) else 1.0
                norm_box = _normalize_box_points(box)
                if norm_box is not None:
                    entries.append((norm_box, str(text).strip(), float(score or 0.0)))
            return entries

        if len(raw_result) >= 2 and _looks_like_box_list(raw_result[0]):
            boxes, rec_res = raw_result[:2]
            entries = []
            for idx, box in enumerate(boxes):
                rec_item = rec_res[idx] if idx < len(rec_res) else None
                text = ""
                score = 1.0
                if isinstance(rec_item, (list, tuple)):
                    text = rec_item[0] if rec_item else ""
                    score = rec_item[1] if len(rec_item) > 1 else 1.0
                elif isinstance(rec_item, dict):
                    text = rec_item.get("text") or rec_item.get("txt") or ""
                    score = rec_item.get("score") or 1.0
                elif rec_item is not None:
                    text = str(rec_item)
                norm_box = _normalize_box_points(box)
                if norm_box is not None:
                    entries.append((norm_box, str(text).strip(), float(score or 0.0)))
            return entries

    if isinstance(raw_result, list):
        entries = []
        for item in raw_result:
            if isinstance(item, dict):
                box = item.get("box") or item.get("bbox") or item.get("points")
                text = item.get("text") or item.get("txt") or ""
                score = item.get("score") or item.get("confidence") or 1.0
            elif isinstance(item, (list, tuple)) and len(item) >= 3:
                box, text, score = item[:3]
            else:
                continue
            norm_box = _normalize_box_points(box)
            if norm_box is not None:
                entries.append((norm_box, str(text).strip(), float(score or 0.0)))
        return entries

    return []


def _rapidocr_recognize(img_bgr: np.ndarray) -> List[dict]:
    engine = _get_rapidocr_engine()
    raw_result = engine(img_bgr)
    results = []
    for box, text, score in _rapidocr_entries(raw_result):
        if text and score >= MIN_BOX_SCORE:
            results.append({"text": text, "box": box, "score": score})
    return results


def _group_lines(boxes: List[dict]) -> List[str]:
    if not boxes:
        return []
    items = []
    for b in boxes:
        xs = b["box"][:, 0]
        ys = b["box"][:, 1]
        x1, x2 = float(xs.min()), float(xs.max())
        y1, y2 = float(ys.min()), float(ys.max())
        items.append({
            "text": b["text"],
            "x": x1,
            "y": y1,
            "h": max(1.0, y2 - y1),
        })
    items.sort(key=lambda x: (x["y"], x["x"]))
    median_h = sorted([i["h"] for i in items])[len(items) // 2]
    line_gap = max(10.0, median_h * 0.6)

    lines = []
    current = []
    cur_y = None
    for it in items:
        if cur_y is None or abs(it["y"] - cur_y) <= line_gap:
            current.append(it)
            cur_y = it["y"] if cur_y is None else (cur_y + it["y"]) / 2
        else:
            current.sort(key=lambda x: x["x"])
            lines.append(" ".join([c["text"] for c in current]).strip())
            current = [it]
            cur_y = it["y"]
    if current:
        current.sort(key=lambda x: x["x"])
        lines.append(" ".join([c["text"] for c in current]).strip())
    return [ln for ln in lines if ln]


def _ascii_fold(text: str) -> str:
    text = unicodedata.normalize("NFKD", text or "")
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return text.replace("đ", "d").replace("Đ", "D")


def _norm_ocr_text(text: str) -> str:
    text = _ascii_fold(text).lower()
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _infer_doc_type(lines: List[str]) -> str:
    full = " ".join(lines)
    compact = re.sub(r"\s", "", full).upper()
    full_lower = full.lower()
    if "IDVNM" in compact or re.search(r"\bngon\s+tro\b|\bdau\s+ngon\b|date\s+of\s+issue|date\s+of\s+expiry|ngay,\s*thang,\s*nam\s*cap", full_lower):
        return "cccd_back"
    if re.search(r"c[aă]n\s*c[uư][oơ]c|citizen\s*identity\s*card|identity\s*card|h[oọ]\s*v[aà]\s*t[eê]n|full\s*name", full_lower):
        return "cccd_front"
    return "unknown"


def _normalize_date(s: str) -> str:
    s = s.strip()
    s = s.replace("-", "/")
    m = re.search(r"\b(\d{2})/(\d{2})/(\d{4})\b", s)
    if not m:
        return ""
    return f"{m.group(1)}/{m.group(2)}/{m.group(3)}"


def _find_date_after_label(lines: List[str], label_pattern: str) -> str:
    for i, ln in enumerate(lines):
        if re.search(label_pattern, ln, re.IGNORECASE):
            d = _normalize_date(ln)
            if d:
                return d
            for j in range(i + 1, min(i + 3, len(lines))):
                d = _normalize_date(lines[j])
                if d:
                    return d
    return ""


def _extract_cccd(lines: List[str]) -> str:
    mrz = _extract_mrz(lines)
    if mrz.get("so_giay_to"):
        return mrz["so_giay_to"]
    for ln in lines:
        if re.search(r"personal\s+identification|s[oố]\s*/?\s*no|s[oố]\s+định\s+danh", ln, re.IGNORECASE):
            if m := re.search(r"\b(\d{12})\b", ln):
                return m.group(1)
    full = " ".join(lines)
    if m := re.search(r"\b(\d{12})\b", full):
        return m.group(1)
    # Fallback: remove non-digits and scan
    digits = re.sub(r"\D", "", full)
    if len(digits) >= 12:
        return digits[:12]
    return ""


def _clean_name_candidate(text: str) -> str:
    text = re.sub(r"[<|]", " ", text or "")
    text = re.sub(r"\s+", " ", text).strip(" .:-")
    return text.upper()


def _extract_name(lines: List[str]) -> str:
    label_pat = r"(h[oọ]\s*(v[aà]\s*)?t[eê]n|full\s*name)"
    for i, ln in enumerate(lines):
        m = re.search(label_pat, ln, re.IGNORECASE)
        if m:
            tail = ln[m.end():]
            tail = re.split(r"ng[aà]y\s*sinh|date\s*of\s*birth|gioi\s*tinh|sex|qu[oố]c\s*t[ịi]ch|nationality|qu[eê]\s*qu[aá]n|place\s*of\s*origin|n[oơ]i\s*th", tail, maxsplit=1, flags=re.IGNORECASE)[0]
            candidate = _clean_name_candidate(tail)
            if candidate and len(candidate.split()) >= 2 and not re.search(r"\d", candidate):
                return candidate
            if i + 1 < len(lines):
                candidate = _clean_name_candidate(lines[i + 1])
                if candidate and len(candidate.split()) >= 2 and not re.search(r"\d", candidate):
                    return candidate
    # Heuristic: longest line without digits
    best = ""
    blacklist = re.compile(
        r"cong\s*hoa|socialist|independence|freedom|hanh\s*phuc|can\s*c[uư][oơ]c|citizen|identity|"
        r"bo\s*cong\s*an|ministry|noi\s*(thuong\s*tru|cu\s*tru)|place\s*of\s*(residence|origin)|"
        r"ngon\s*tro|dac\s*diem|personal\s*identification|date\s*of\s*(issue|expiry|birth)|"
        r"quoc\s*tich|nationality|que\s*quan",
        re.IGNORECASE,
    )
    for ln in lines:
        if re.search(r"\d", ln):
            continue
        candidate = _clean_name_candidate(ln)
        if blacklist.search(candidate):
            continue
        word_count = len(candidate.split())
        if 2 <= word_count <= 5 and len(candidate) > len(best):
            best = candidate
    return best


def _extract_gender(lines: List[str]) -> str:
    for ln in lines:
        if re.search(r"gi[oớ]i\s*t[ií]nh|sex", ln, re.IGNORECASE):
            lower = ln.lower()
            if re.search(r"\bnu\w*\b|\bn[uữ]\b|female", lower):
                return "Nữ"
            if re.search(r"\bnam\b|male", lower):
                return "Nam"
    return ""


def _extract_address(lines: List[str]) -> str:
    stop_pat = re.compile(r"(quoc\s*tich|quốc\s*tịch|gioi\s*tinh|giới\s*tính|ngay\s*sinh|ngày\s*sinh|ngay\s*cap|ngày\s*cấp|co\s*gia\s*tri|có\s*giá\s*trị|date\s*of\s*expiry|expiry)", re.IGNORECASE)
    for i, ln in enumerate(lines):
        if re.search(r"n[oơ]i\s*(th[uư]ờ?ng\s*trú|c[uư]\s*trú)|place\s*of\s*residence", ln, re.IGNORECASE):
            parts = []
            m = re.search(r"(n[oơ]i\s*(th[uư]ờ?ng\s*trú|c[uư]\s*trú)|place\s*of\s*residence)\s*:?\s*(.+)$", ln, re.IGNORECASE)
            if m:
                parts.append(m.group(3).strip(" .,:;"))
            for j in range(i + 1, len(lines)):
                if stop_pat.search(lines[j]):
                    break
                parts.append(lines[j])
            return ", ".join([p.strip(" .,:;") for p in parts if p and p.strip(" .,:;")])
    return ""


def _extract_mrz(lines: List[str]) -> dict:
    compact_lines = [re.sub(r"\s+", "", (ln or "").upper()) for ln in lines if ln]
    joined = " ".join(compact_lines)
    line1 = next((ln for ln in compact_lines if "IDVNM" in ln and "<<" in ln), "")
    line2 = next((ln for ln in compact_lines if re.search(r"\d{6}\d[MF<]\d{6}\dVNM", ln)), "")
    name_line = next((ln for ln in compact_lines if "<<" in ln and "IDVNM" not in ln and re.search(r"[A-Z]{2,}", ln)), "")

    def _fmt_yyMMdd(raw: str, prefer_future: bool = False) -> str:
        if not re.fullmatch(r"\d{6}", raw or ""):
            return ""
        yy = int(raw[:2])
        mm = raw[2:4]
        dd = raw[4:6]
        if prefer_future:
            year = 2000 + yy if yy < 70 else 1900 + yy
        else:
            current_yy = datetime.now().year % 100
            year = 1900 + yy if yy > current_yy else 2000 + yy
        return f"{dd}/{mm}/{year:04d}"

    cccd = ""
    if line1:
        m = re.search(r"(\d{12})<<\d", line1)
        if m:
            cccd = m.group(1)
        else:
            matches = re.findall(r"\d{12}", line1)
            if matches:
                cccd = matches[-1]

    name = ""
    if name_line:
        name = _clean_name_candidate(name_line.replace("<<", " ").replace("<", " "))

    dob = ""
    expiry = ""
    gender = ""
    if line2 and len(line2) >= 15:
        dob = _fmt_yyMMdd(line2[0:6], prefer_future=False)
        gender = "Nam" if line2[7] == "M" else ("Nữ" if line2[7] == "F" else "")
        expiry = _fmt_yyMMdd(line2[8:14], prefer_future=True)

    return {
        "mrz_line1": line1 or joined,
        "so_giay_to": cccd,
        "ho_ten": name,
        "ngay_sinh": dob,
        "gioi_tinh": gender,
        "ngay_het_han": expiry,
    }


def _parse_cccd(lines: List[str], qr_data: Optional[dict], doc_type: str) -> dict:
    data = {
        "so_giay_to": "",
        "ho_ten": "",
        "ngay_sinh": "",
        "gioi_tinh": "",
        "dia_chi": "",
        "ngay_cap": "",
        "ngay_het_han": "",
    }

    if qr_data:
        data["so_giay_to"] = qr_data.get("so_giay_to", "")
        data["ho_ten"] = qr_data.get("ho_ten", "")
        data["ngay_sinh"] = qr_data.get("ngay_sinh", "")
        data["gioi_tinh"] = qr_data.get("gioi_tinh", "")
        data["dia_chi"] = qr_data.get("dia_chi", "")
        data["ngay_het_han"] = qr_data.get("ngay_het_han", "")

    mrz = _extract_mrz(lines)

    if not data["so_giay_to"]:
        data["so_giay_to"] = _extract_cccd(lines)
    if not data["ho_ten"]:
        data["ho_ten"] = _extract_name(lines)
    if not data["ngay_sinh"]:
        data["ngay_sinh"] = _find_date_after_label(lines, r"ngay\s*sinh|ngày\s*sinh")
    if not data["gioi_tinh"]:
        data["gioi_tinh"] = _extract_gender(lines)
    if not data["dia_chi"]:
        data["dia_chi"] = _extract_address(lines)

    if mrz.get("so_giay_to") and (doc_type == "cccd_back" or not data["so_giay_to"]):
        data["so_giay_to"] = mrz["so_giay_to"]
    if mrz.get("ho_ten") and (doc_type == "cccd_back" or not data["ho_ten"]):
        data["ho_ten"] = mrz["ho_ten"]
    if mrz.get("ngay_sinh") and (doc_type == "cccd_back" or not data["ngay_sinh"]):
        data["ngay_sinh"] = mrz["ngay_sinh"]
    if mrz.get("gioi_tinh") and (doc_type == "cccd_back" or not data["gioi_tinh"]):
        data["gioi_tinh"] = mrz["gioi_tinh"]

    data["ngay_cap"] = _find_date_after_label(lines, r"ngay\s*cap|ngày\s*cấp") or data["ngay_cap"]
    data["ngay_het_han"] = _find_date_after_label(lines, r"(co\s*gia\s*tri\s*den|có\s*giá\s*trị\s*đến|ngay\s*het\s*han|ngày\s*hết\s*hạn)") or data["ngay_het_han"]

    if mrz.get("ngay_het_han") and not data["ngay_het_han"]:
        data["ngay_het_han"] = mrz["ngay_het_han"]

    # Fallback cho mặt sau: ảnh thường có 2 ngày issue/expiry
    if doc_type == "cccd_back":
        dates = re.findall(r"\d{2}/\d{2}/\d{4}", " ".join(lines).replace("-", "/"))
        if not data["ngay_cap"] and len(dates) >= 1:
            data["ngay_cap"] = dates[0]
        if not data["ngay_het_han"] and len(dates) >= 2:
            data["ngay_het_han"] = dates[1]

    return data


# Override parser helpers with ASCII-folded variants to handle OCR noise on Windows.
def _ascii_fold(text: str) -> str:
    text = unicodedata.normalize("NFKD", text or "")
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return text.replace("đ", "d").replace("Đ", "D")


def _norm_ocr_text(text: str) -> str:
    text = _ascii_fold(text).lower()
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _infer_doc_type(lines: List[str]) -> str:
    full = " ".join(lines)
    compact = re.sub(r"\s", "", _ascii_fold(full)).upper()
    full_norm = _norm_ocr_text(full)
    if "IDVNM" in compact:
        return "cccd_back"
    if any(token in full_norm for token in [
        "ngon tro",
        "dau ngon",
        "date of issue",
        "date of expiry",
        "ngay thang nam cap",
    ]):
        return "cccd_back"
    if any(token in full_norm for token in [
        "can cuoc",
        "citizen identity card",
        "identity card",
        "ho va ten",
        "full name",
    ]):
        return "cccd_front"
    return "unknown"


def _find_date_after_label(lines: List[str], label_pattern: str) -> str:
    for i, ln in enumerate(lines):
        if re.search(label_pattern, _ascii_fold(ln), re.IGNORECASE):
            d = _normalize_date(ln)
            if d:
                return d
            for j in range(i + 1, min(i + 3, len(lines))):
                d = _normalize_date(lines[j])
                if d:
                    return d
    return ""


def _clean_name_candidate(text: str) -> str:
    text = (text or "").replace("'", "")
    text = re.sub(r"(?i)\b(họ\s*(và\s*)?tên|ho\s*va\s*ten|ho\s*ten|full\s*name)\b", " ", text)
    text = re.sub(r"[<|/]", " ", text)
    text = re.sub(r"\s+", " ", text).strip(" .:-")
    return text.upper()


def _is_likely_name(candidate: str) -> bool:
    if not candidate or re.search(r"\d", candidate):
        return False
    words = candidate.split()
    if not (2 <= len(words) <= 6):
        return False
    folded = _ascii_fold(candidate)
    if re.search(
        r"\b(CONG HOA|SOCIALIST|MINISTRY|PUBLIC SECURITY|CAN CUOC|CITIZEN|IDENTITY|"
        r"FULL NAME|HO VA TEN|PLACE OF|DATE OF|NGON TRO|DAC DIEM|QUOC TICH|QUE QUAN)\b",
        folded,
        re.IGNORECASE,
    ):
        return False
    return True


def _extract_name(lines: List[str]) -> str:
    label_pat = r"(ho\s*va\s*ten|ho\s*ten|full\s*name)"
    stop_pat = r"(\d{2}/\d{2}/\d{4}|ngay\s*sinh|date\s*of\s*birth|dateofbirth|gioi\s*tinh|sex|quoc\s*tich|nationality|que\s*quan|place\s*of\s*origin|noi\s*thuong\s*tru|noi\s*cu\s*tru|place\s*of\s*residence|co\s*gia\s*tri|date\s*of\s*expiry)"
    for i, ln in enumerate(lines):
        folded = _ascii_fold(ln)
        m = re.search(label_pat, folded, re.IGNORECASE)
        if m:
            tail = re.split(r":", ln, maxsplit=1)
            tail = tail[1] if len(tail) == 2 else ln[m.end():]
            tail = re.split(stop_pat, tail, maxsplit=1, flags=re.IGNORECASE)[0]
            candidate = _clean_name_candidate(tail)
            if _is_likely_name(candidate):
                return candidate
            for j in range(i + 1, min(i + 3, len(lines))):
                candidate = _clean_name_candidate(re.split(stop_pat, lines[j], maxsplit=1, flags=re.IGNORECASE)[0])
                if _is_likely_name(candidate):
                    return candidate

    best = ""
    blacklist = re.compile(
        r"cong\s*hoa|socialist|independence|freedom|hanh\s*phuc|can\s*cuoc|citizen|identity|"
        r"bo\s*cong\s*an|ministry|noi\s*(thuong\s*tru|cu\s*tru)|place\s*of\s*(residence|origin)|"
        r"ngon\s*tro|dac\s*diem|personal\s*identification|date\s*of\s*(issue|expiry|birth)|"
        r"quoc\s*tich|nationality|que\s*quan|full\s*name|ho\s*va\s*ten",
        re.IGNORECASE,
    )
    for ln in lines:
        if re.search(r"\d", ln):
            continue
        candidate = _clean_name_candidate(ln)
        if blacklist.search(_ascii_fold(candidate)):
            continue
        if _is_likely_name(candidate) and len(candidate) > len(best):
            best = candidate
    return best


def _extract_gender(lines: List[str]) -> str:
    for ln in lines:
        folded = _ascii_fold(ln).lower()
        if re.search(r"gioi\s*tinh|sex", folded, re.IGNORECASE):
            if re.search(r"\bnu\w*\b|female", folded):
                return "Nữ"
            if re.search(r"\bnam\b|male", folded):
                return "Nam"
    return ""


def _extract_address_block(lines: List[str], label_pattern: str, from_bottom: bool = False) -> str:
    stop_pat = re.compile(
        r"(quoc\s*tich|gioi\s*tinh|ngay\s*sinh|ngay\s*cap|co\s*gia|date\s*of|expiry|que\s*quan|place\s*of\s*origin|^\d{4}/\d{2}/\d{2})",
        re.IGNORECASE,
    )
    indexes = list(range(len(lines)))
    if from_bottom:
        indexes.reverse()
    for i in indexes:
        ln = lines[i]
        folded = _ascii_fold(ln)
        if re.search(label_pattern, folded, re.IGNORECASE):
            parts = []
            m = re.search(label_pattern + r"\s*:?\s*(.+)$", folded, re.IGNORECASE)
            if m:
                inline_tail = m.group(1).strip(" .,:;")
                if inline_tail and not re.search(label_pattern, inline_tail, re.IGNORECASE):
                    parts.append(inline_tail)
            for j in range(i + 1, len(lines)):
                next_folded = _ascii_fold(lines[j])
                if stop_pat.search(next_folded):
                    break
                parts.append(lines[j].strip(" .,:;"))
            cleaned = []
            for p in parts:
                v = p.strip(" .,:;")
                if not v:
                    continue
                if re.fullmatch(r"(noi\s*(thuong\s*tru|cu\s*tru)|place\s*of\s*residence)", _ascii_fold(v), re.IGNORECASE):
                    continue
                cleaned.append(v)
            if cleaned:
                return ", ".join(cleaned)
    return ""


def _extract_address(lines: List[str], doc_type: str) -> str:
    """
    Luat co dinh:
    - CCCD cu: dia chi o duoi cung mat truoc => "Noi thuong tru".
    - CCCD moi: dia chi o tren cung mat sau => "Noi cu tru".
    Khong xac dinh duoc block thi de trong.
    """
    if doc_type == "cccd_front":
        return _extract_address_block(lines, r"(noi\s*thuong\s*tru|place\s*of\s*residence)", from_bottom=True)
    if doc_type == "cccd_back":
        return _extract_address_block(lines, r"(noi\s*cu\s*tru|place\s*of\s*residence)", from_bottom=False)
    # unknown: chi nhan neu tim thay duy nhat 1 block ro rang
    front_addr = _extract_address_block(lines, r"(noi\s*thuong\s*tru|place\s*of\s*residence)", from_bottom=True)
    back_addr = _extract_address_block(lines, r"(noi\s*cu\s*tru|place\s*of\s*residence)", from_bottom=False)
    if front_addr and not back_addr:
        return front_addr
    if back_addr and not front_addr:
        return back_addr
    return ""


def _extract_mrz(lines: List[str]) -> dict:
    compact_lines = [re.sub(r"\s+", "", _ascii_fold(ln or "").upper()) for ln in lines if ln]
    joined = " ".join(compact_lines)
    mrz_start = next((idx for idx, ln in enumerate(compact_lines) if "IDVNM" in ln and "<<" in ln), -1)
    line1 = compact_lines[mrz_start] if mrz_start >= 0 else next((ln for ln in compact_lines if "IDVNM" in ln and "<<" in ln), "")

    def _fmt_yyMMdd(raw: str, prefer_future: bool = False) -> str:
        if not re.fullmatch(r"\d{6}", raw or ""):
            return ""
        yy = int(raw[:2])
        mm = raw[2:4]
        dd = raw[4:6]
        if prefer_future:
            year = 2000 + yy if yy < 70 else 1900 + yy
        else:
            current_yy = datetime.now().year % 100
            year = 1900 + yy if yy > current_yy else 2000 + yy
        return f"{dd}/{mm}/{year:04d}"

    line2_match = re.search(r"(\d{6})\d([MF<])(\d{6})\dVNM", joined)
    name_line = next(
        (ln for ln in compact_lines if "<<" in ln and "IDVNM" not in ln and ln.count("<") >= 4 and re.search(r"[A-Z]{2,}", ln)),
        "",
    )

    cccd = ""
    if line1:
        m = re.search(r"(\d{12})<<\d", line1)
        if m:
            cccd = m.group(1)
        else:
            matches = re.findall(r"\d{12}", line1)
            if matches:
                cccd = matches[-1]

    dob = _fmt_yyMMdd(line2_match.group(1), prefer_future=False) if line2_match else ""
    gender = "Nam" if line2_match and line2_match.group(2) == "M" else ("Nữ" if line2_match and line2_match.group(2) == "F" else "")
    expiry = _fmt_yyMMdd(line2_match.group(3), prefer_future=True) if line2_match else ""
    name = _clean_name_candidate(name_line.replace("<<", " ").replace("<", " ")) if name_line else ""
    if name and not _is_likely_name(name):
        name = ""

    return {
        "mrz_line1": line1 or joined,
        "so_giay_to": cccd,
        "ho_ten": name,
        "ngay_sinh": dob,
        "gioi_tinh": gender,
        "ngay_het_han": expiry,
    }


def _extract_cccd(lines: List[str]) -> str:
    mrz = _extract_mrz(lines)
    if mrz.get("so_giay_to"):
        return mrz["so_giay_to"]
    for ln in lines:
        if re.search(r"personal\s+identification|s[o0]\s*/?\s*no|so\s+dinh\s+danh", _ascii_fold(ln), re.IGNORECASE):
            if m := re.search(r"\b(\d{12})\b", ln):
                return m.group(1)
    full = " ".join(lines)
    if m := re.search(r"\b(\d{12})\b", full):
        return m.group(1)
    digits = re.sub(r"\D", "", full)
    if len(digits) >= 12:
        return digits[:12]
    return ""


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


def _infer_side(doc_type: str) -> str:
    if doc_type == "cccd_front":
        return "front"
    if doc_type == "cccd_back":
        return "back"
    return "unknown"


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


def _parse_cccd(lines: List[str], qr_data: Optional[dict], doc_type: str) -> dict:
    data = {
        "so_giay_to": "",
        "ho_ten": "",
        "ngay_sinh": "",
        "gioi_tinh": "",
        "dia_chi": "",
        "ngay_cap": "",
        "ngay_het_han": "",
    }

    if qr_data:
        data["so_giay_to"] = qr_data.get("so_giay_to", "")
        data["ho_ten"] = qr_data.get("ho_ten", "")
        data["ngay_sinh"] = qr_data.get("ngay_sinh", "")
        data["gioi_tinh"] = qr_data.get("gioi_tinh", "")
        data["dia_chi"] = qr_data.get("dia_chi", "")
        data["ngay_het_han"] = qr_data.get("ngay_het_han", "")

    mrz = _extract_mrz(lines)

    if not data["so_giay_to"]:
        data["so_giay_to"] = _extract_cccd(lines)
    if not data["ho_ten"]:
        data["ho_ten"] = _extract_name(lines)
    if not data["ngay_sinh"]:
        data["ngay_sinh"] = _find_date_after_label(lines, r"ngay\s*sinh|date\s*of\s*birth")
    if not data["gioi_tinh"]:
        data["gioi_tinh"] = _extract_gender(lines)
    if not data["dia_chi"]:
        data["dia_chi"] = _extract_address(lines, doc_type)

    if mrz.get("so_giay_to") and (doc_type == "cccd_back" or not data["so_giay_to"]):
        data["so_giay_to"] = mrz["so_giay_to"]
    # Ten uu tien QR/mat truoc; MRZ chi fallback khi thieu hoan toan.
    if mrz.get("ho_ten") and not data["ho_ten"]:
        data["ho_ten"] = mrz["ho_ten"]
    if mrz.get("ngay_sinh") and (doc_type == "cccd_back" or not data["ngay_sinh"]):
        data["ngay_sinh"] = mrz["ngay_sinh"]
    if mrz.get("gioi_tinh") and (doc_type == "cccd_back" or not data["gioi_tinh"]):
        data["gioi_tinh"] = mrz["gioi_tinh"]

    data["ngay_cap"] = _find_date_after_label(lines, r"ngay\s*cap|ngay\s*thang.*cap|date\s*of\s*issue") or data["ngay_cap"]
    data["ngay_het_han"] = _find_date_after_label(lines, r"co\s*gia\s*tri|ngay\s*het\s*han|date\s*of\s*expiry|expiry") or data["ngay_het_han"]

    if mrz.get("ngay_het_han") and not data["ngay_het_han"]:
        data["ngay_het_han"] = mrz["ngay_het_han"]

    if doc_type == "cccd_back":
        dates = re.findall(r"\d{2}/\d{2}/\d{4}", " ".join(lines).replace("-", "/"))
        if not data["ngay_cap"] and len(dates) >= 1:
            data["ngay_cap"] = dates[0]
        if not data["ngay_het_han"] and len(dates) >= 2:
            data["ngay_het_han"] = dates[1]

    return data


def _build_raw_text(lines: List[str]) -> str:
    return "\n".join([ln for ln in lines if ln])


def _try_qr_data_from_crop(crop: DocCrop, seeded_qr_text: str | None = None) -> tuple[dict | None, str]:
    qr_text = (seeded_qr_text or "").strip()
    qr_data = parse_cccd_qr(qr_text) if qr_text else None
    if _is_valid_qr_data(qr_data):
        return qr_data, qr_text

    try:
        pil_img = Image.fromarray(cv2.cvtColor(crop.img, cv2.COLOR_BGR2RGB))
        buf = io.BytesIO()
        pil_img.save(buf, format="PNG")
        detected = try_decode_qr(buf.getvalue()) or ""
        parsed = parse_cccd_qr(detected) if detected else None
        if _is_valid_qr_data(parsed):
            return parsed, detected
    except Exception:
        pass
    return None, ""


def _build_field_sources(source_type: str, data: dict) -> dict:
    tag = "qr" if source_type == "QR" else "ocr"
    out = {}
    for key in ("ho_ten", "so_giay_to", "ngay_sinh", "gioi_tinh", "dia_chi", "ngay_cap"):
        if (data.get(key) or "").strip():
            out[key] = tag
    return out


_CRITICAL_WARNING_FIELDS = ("ho_ten", "so_giay_to", "ngay_sinh", "gioi_tinh", "dia_chi", "ngay_cap")


def _collect_warnings(data: dict) -> List[str]:
    warnings: List[str] = []
    for key in _CRITICAL_WARNING_FIELDS:
        if not (data.get(key) or "").strip():
            warnings.append(key)

    ho_ten = (data.get("ho_ten") or "").strip()
    if ho_ten and _count_vietnamese_diacritics(ho_ten) < 2 and "ho_ten" not in warnings:
        warnings.append("ho_ten")

    return warnings


def _analyze_crop(
    crop: DocCrop,
    seeded_qr_text: str | None = None,
    allow_llm: bool = False,
    client_qr_failed: bool = False,
) -> dict:
    qr_data = None
    qr_text = ""
    if not client_qr_failed:
        qr_data, qr_text = _try_qr_data_from_crop(crop, seeded_qr_text)
    doc_type_from_model = crop.doc_type if crop.doc_type != "unknown" else "unknown"

    # QR gate: neu QR hop le thi dung OCR text cho anh nay.
    if _is_valid_qr_data(qr_data):
        data = _build_qr_person_data(qr_data or {})
        data.pop("ngay_het_han", None)
        warnings = _collect_warnings(data)
        return {
            "data": data,
            "doc_type": doc_type_from_model,
            "confidence": crop.confidence,
            "raw_text": "",
            "_lines": [],
            "_qr": True,
            "qr_text": qr_text,
            "source_type": "QR",
            "side": _infer_side(doc_type_from_model),
            "field_sources": _build_field_sources("QR", data),
            "warnings": warnings,
        }

    ocr_boxes = _rapidocr_recognize(crop.img)
    lines = _group_lines(ocr_boxes)
    raw_text = _build_raw_text(lines)
    inferred_doc_type = crop.doc_type if crop.doc_type != "unknown" else _infer_doc_type(lines)
    data = _parse_cccd(lines, None, inferred_doc_type)
    data.pop("ngay_het_han", None)

    if allow_llm and _needs_llm_fallback(data) and raw_text:
        loop_data = None
        try:
            loop_data = asyncio.run(_llm_parse_text(raw_text, inferred_doc_type))
        except Exception:
            loop_data = None
        if isinstance(loop_data, dict):
            data.update({k: v for k, v in loop_data.items() if v and k in data})

    if allow_llm and (data.get("ho_ten") or "").strip() and _count_vietnamese_diacritics(data.get("ho_ten", "")) < 2:
        restored = None
        try:
            restored = asyncio.run(_llm_restore_name_diacritics(data.get("ho_ten", ""), raw_text))
        except Exception:
            restored = None
        if restored:
            data["ho_ten"] = restored

    warnings = _collect_warnings(data)
    return {
        "data": data,
        "doc_type": inferred_doc_type,
        "confidence": crop.confidence,
        "raw_text": raw_text,
        "_lines": lines,
        "_qr": False,
        "qr_text": "",
        "source_type": "OCR",
        "side": _infer_side(inferred_doc_type),
        "field_sources": _build_field_sources("OCR", data),
        "warnings": warnings,
    }


def local_ocr_from_bytes(
    file_bytes: bytes,
    qr_text: str | None = None,
    client_qr_failed: bool = False,
) -> dict:
    _ensure_local_ocr_dependencies()
    img_np = np.frombuffer(file_bytes, np.uint8)
    img_bgr = cv2.imdecode(img_np, cv2.IMREAD_COLOR)
    if img_bgr is None:
        raise ValueError("Khong doc duoc anh")

    img_bgr = _preprocess(img_bgr)
    crops = _detect_documents(img_bgr)

    candidates = []
    seeded_qr = qr_text
    for crop in crops:
        analyzed = _analyze_crop(
            crop,
            seeded_qr_text=seeded_qr,
            allow_llm=False,
            client_qr_failed=client_qr_failed,
        )
        candidates.append(analyzed)
        seeded_qr = None

    best = None
    for c in candidates:
        score = _score_person(c["data"]) + (5 if c.get("source_type") == "QR" else 0)
        if best is None or score > best["score"]:
            best = {**c, "score": score}

    if not best:
        raise ValueError("Khong nhan dien duoc noi dung")

    data = best["data"]
    raw_text = best["raw_text"]
    warnings = best.get("warnings") or _collect_warnings(data)

    return {
        "persons": [{
            "type": "person",
            "data": {**data, "_raw_text": raw_text},
            "_source": f"{best.get('source_type', 'OCR')} ({best.get('side', 'unknown')})",
            "source_type": best.get("source_type", "OCR"),
            "side": best.get("side", "unknown"),
            "field_sources": best.get("field_sources", {}),
            "warnings": warnings,
        }],
        "properties": [],
        "marriages": [],
        "raw_text": raw_text,
        "doc_type": best["doc_type"],
    }


def _score_person(data: dict) -> int:
    keys = ["so_giay_to", "ho_ten", "ngay_sinh", "gioi_tinh", "dia_chi", "ngay_cap"]
    return sum(1 for k in keys if (data.get(k) or "").strip())


def _local_engine_name() -> str:
    if _torch_disabled() or not YOLO_WEIGHTS:
        return "RapidOCR"
    return "YOLO + RapidOCR"


# ---------------------- Endpoint ----------------------
@router.post("/analyze-local")
async def analyze_images_local(files: List[UploadFile] = File(...)):
    """
    OCR offline with pipeline: preprocess -> YOLO -> QR -> RapidOCR -> regex.
    Return same format as /api/ocr/analyze for frontend compatibility.
    """
    if not files:
        raise HTTPException(status_code=400, detail="Chua co anh nao duoc gui len")
    _ensure_local_ocr_dependencies()

    persons = []
    errors = []

    # Ensure required models
    _get_rapidocr_engine()

    for f in files:
        try:
            raw = await f.read()
            img_np = np.frombuffer(raw, np.uint8)
            img_bgr = cv2.imdecode(img_np, cv2.IMREAD_COLOR)
            if img_bgr is None:
                errors.append({"filename": f.filename, "error": "Khong doc duoc anh"})
                continue

            img_bgr = _preprocess(img_bgr)
            crops = _detect_documents(img_bgr)

            candidates = []
            for crop in crops:
                candidates.append(_analyze_crop(crop, allow_llm=False))

            # pick best candidate
            best = None
            for c in candidates:
                score = _score_person(c["data"]) + (5 if c.get("source_type") == "QR" else 0)
                if best is None or score > best["score"]:
                    best = {**c, "score": score}
            if best:
                data = best["data"]
                warnings = best.get("warnings") or _collect_warnings(data)
                persons.append({
                    "type": "person",
                    "data": data,
                    "_source": f"{best.get('source_type', 'OCR')} ({best.get('side', 'unknown')})",
                    "filename": f.filename,
                    "_qr": best.get("_qr", False),
                    "source_type": best.get("source_type", "OCR"),
                    "side": best.get("side", "unknown"),
                    "field_sources": best.get("field_sources", {}),
                    "warnings": warnings,
                    "_debug_lines": best["_lines"],
                })
            else:
                errors.append({"filename": f.filename, "error": "Khong nhan dien duoc noi dung"})

        except Exception as e:
            errors.append({"filename": f.filename, "error": str(e)})
            traceback.print_exc()

    return {
        "persons": persons,
        "properties": [],
        "marriages": [],
        "errors": errors,
        "summary": {
            "total_images": len(files),
            "local_engine": _local_engine_name(),
        },
    }


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
    with open(temp_path, "wb") as f:
        f.write(raw)

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
    """
    Payload requires:
      - parsed_data: dict
      - raw_text: str
      - document_type: str (optional)
    Or:
      - items: [{parsed_data, raw_text, document_type}]
    """
    items = payload.get("items")
    if not items:
        items = [{
            "parsed_data": payload.get("parsed_data") or {},
            "raw_text": payload.get("raw_text") or "",
            "document_type": payload.get("document_type") or "UNKNOWN",
        }]

    db = SessionLocal()
    try:
        ids = []
        for it in items:
            doc = ExtractedDocument(
                user_id=None,
                document_type=it.get("document_type") or "UNKNOWN",
                raw_text=it.get("raw_text") or "",
                parsed_data=it.get("parsed_data") or {},
            )
            db.add(doc)
            db.flush()
            ids.append(doc.id)
        db.commit()
        return {"ok": True, "ids": ids}
    finally:
        db.close()
