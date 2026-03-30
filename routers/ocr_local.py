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
import shutil
import re
import traceback
import unicodedata
import logging
from datetime import datetime
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

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
_logger = logging.getLogger("ocr_local")

# ---------------------- Config (env) ----------------------
YOLO_WEIGHTS = os.getenv("LOCAL_OCR_YOLO_WEIGHTS", "").strip()
YOLO_CONF = float(os.getenv("LOCAL_OCR_YOLO_CONF", "0.25"))
YOLO_IMG_SIZE = int(os.getenv("LOCAL_OCR_YOLO_IMG_SIZE", "960"))
YOLO_REQUIRE = os.getenv("LOCAL_OCR_REQUIRE_YOLO", "").strip() == "1"

MIN_BOX_SCORE = float(os.getenv("LOCAL_OCR_MIN_BOX_SCORE", "0.3"))
TEXT_LLM_MODEL = os.getenv("OCR_TEXT_LLM_MODEL", "gpt-4o-mini")
LOCAL_OCR_REC_MODEL_PATH = os.getenv("LOCAL_OCR_REC_MODEL_PATH", "").strip()
LOCAL_OCR_REC_KEYS_PATH = os.getenv("LOCAL_OCR_REC_KEYS_PATH", "").strip()

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
_rapidocr_rec_mode = "default"


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
    global _rapidocr_engine, _rapidocr_rec_mode
    if _rapidocr_engine is not None:
        return _rapidocr_engine
    try:
        try:
            from rapidocr_onnxruntime import RapidOCR
        except ImportError:
            from rapidocr import RapidOCR

        rec_model_path = LOCAL_OCR_REC_MODEL_PATH
        rec_keys_path = LOCAL_OCR_REC_KEYS_PATH
        custom_kwargs = {}

        if rec_model_path:
            if os.path.exists(rec_model_path):
                custom_kwargs["rec_model_path"] = rec_model_path
            else:
                _logger.warning(
                    "LOCAL_OCR_REC_MODEL_PATH khong ton tai: %s. Fallback RapidOCR mac dinh.",
                    rec_model_path,
                )

        if rec_keys_path:
            if os.path.exists(rec_keys_path):
                custom_kwargs["rec_keys_path"] = rec_keys_path
            else:
                _logger.warning(
                    "LOCAL_OCR_REC_KEYS_PATH khong ton tai: %s. Bo qua rec_keys_path.",
                    rec_keys_path,
                )

        if custom_kwargs.get("rec_model_path"):
            try:
                _rapidocr_engine = RapidOCR(**custom_kwargs)
                _rapidocr_rec_mode = "vi_rec"
                _logger.info("RapidOCR khoi dong voi rec model tieng Viet: %s", custom_kwargs["rec_model_path"])
                print(f"[OCR_LOCAL] RapidOCR rec model mode: {_rapidocr_rec_mode}")
            except Exception as e:
                _logger.warning(
                    "Khoi dong RapidOCR voi rec model tieng Viet that bai (%s). Fallback model mac dinh.",
                    e,
                )
                _rapidocr_engine = RapidOCR()
                _rapidocr_rec_mode = "default_fallback"
                print(f"[OCR_LOCAL][WARNING] RapidOCR fallback mode: {_rapidocr_rec_mode} (khong dung duoc model tieng Viet)")
        else:
            _rapidocr_engine = RapidOCR()
            _rapidocr_rec_mode = "default"
            print(f"[OCR_LOCAL][WARNING] RapidOCR rec model mode: {_rapidocr_rec_mode} (chua cau hinh model tieng Viet)")
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
    total = 0
    for ch in text or "":
        if ch in {"đ", "Đ"}:
            total += 1
            continue
        if any(unicodedata.combining(c) for c in unicodedata.normalize("NFD", ch)):
            total += 1
    return total


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


DOC_PROFILE_FRONT_OLD = "cccd_front_old"
DOC_PROFILE_BACK_OLD = "cccd_back_old"
DOC_PROFILE_FRONT_NEW = "cccd_front_new"
DOC_PROFILE_BACK_NEW = "cccd_back_new"
DOC_PROFILE_UNKNOWN = "unknown"

_OCR_NORMALIZE_RULES: tuple[tuple[str, str], ...] = (
    (r"\bnarn\b", "nam"),
    (r"\bnamn\b", "nam"),
    (r"\bn[uü]\b", "nu"),
    (r"\bqu[o0]c\s*t[i1]ch\b", "quoc tich"),
    (r"\bngay\s*,\s*thang\s*,\s*nam\s*cap\b", "ngay thang nam cap"),
    (r"\bdate\s*of\s*issve\b", "date of issue"),
    (r"\bdate\s*of\s*expiny\b", "date of expiry"),
    (r"\bpersonal\s*identiflcation\b", "personal identification"),
)


def _ascii_fold(text: str) -> str:
    text = unicodedata.normalize("NFKD", text or "")
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return text.replace("đ", "d").replace("Đ", "D")


def _normalize_ocr_line(text: str) -> str:
    folded = _ascii_fold(text or "").lower()
    folded = folded.replace("nü", "nu")
    for pattern, replacement in _OCR_NORMALIZE_RULES:
        folded = re.sub(pattern, replacement, folded, flags=re.IGNORECASE)
    folded = re.sub(r"[^a-z0-9:/-]+", " ", folded)
    folded = re.sub(r"\s+", " ", folded).strip()
    return folded


def _normalize_ocr_lines(lines: List[str]) -> List[str]:
    return [_normalize_ocr_line(ln) for ln in lines]


def _norm_ocr_text(text: str) -> str:
    return _normalize_ocr_line(text or "")


def _coarse_doc_type_from_profile(profile: str, model_doc_type: str = "unknown") -> str:
    if profile.startswith("cccd_front_"):
        return "cccd_front"
    if profile.startswith("cccd_back_"):
        return "cccd_back"
    if model_doc_type in {"cccd_front", "cccd_back"}:
        return model_doc_type
    return "unknown"


def _infer_doc_profile(normalized_lines: List[str], model_doc_type: str = "unknown") -> str:
    full_norm = " ".join([ln for ln in normalized_lines if ln])
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


def _infer_doc_type(lines: List[str], model_doc_type: str = "unknown") -> str:
    profile = _infer_doc_profile(_normalize_ocr_lines(lines), model_doc_type=model_doc_type)
    return _coarse_doc_type_from_profile(profile, model_doc_type=model_doc_type)


def _normalize_date(s: str) -> str:
    raw = (s or "").replace("-", "/").replace(".", "/")
    m = re.search(r"(?<!\d)(\d{1,2})/(\d{1,2})/(\d{4})(?!\d)", raw)
    if not m:
        return ""
    dd = int(m.group(1))
    mm = int(m.group(2))
    yyyy = int(m.group(3))
    if not (1 <= dd <= 31 and 1 <= mm <= 12 and 1900 <= yyyy <= 2100):
        return ""
    return f"{dd:02d}/{mm:02d}/{yyyy:04d}"


def _find_date_after_label(raw_lines: List[str], normalized_lines: List[str], label_pattern: str) -> str:
    for i, norm_ln in enumerate(normalized_lines):
        if re.search(label_pattern, norm_ln, re.IGNORECASE):
            d = _normalize_date(raw_lines[i])
            if d:
                return d
            for j in range(i + 1, min(i + 3, len(raw_lines))):
                d = _normalize_date(raw_lines[j])
                if d:
                    return d
    return ""


def _clean_name_candidate(text: str) -> str:
    text = (text or "").replace("'", "")
    text = re.sub(r"(?i)\b(h[oọ]\s*(v[aà]\s*)?t[eê]n|ho\s*va\s*ten|ho\s*ten|full\s*name)\b", " ", text)
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


def _extract_name(raw_lines: List[str], normalized_lines: List[str]) -> str:
    label_pat = r"(ho\s*va\s*ten|ho\s*ten|full\s*name)"
    stop_pat = r"(\d{2}/\d{2}/\d{4}|ngay\s*sinh|date\s*of\s*birth|gioi\s*tinh|sex|quoc\s*tich|nationality|que\s*quan|place\s*of\s*origin|noi\s*thuong\s*tru|noi\s*cu\s*tru|place\s*of\s*residence|co\s*gia\s*tri|date\s*of\s*expiry)"
    for i, norm_ln in enumerate(normalized_lines):
        if re.search(label_pat, norm_ln, re.IGNORECASE):
            raw_ln = raw_lines[i]
            tail = raw_ln.split(":", 1)[1] if ":" in raw_ln else raw_ln
            tail = re.split(stop_pat, tail, maxsplit=1, flags=re.IGNORECASE)[0]
            candidate = _clean_name_candidate(tail)
            if _is_likely_name(candidate):
                return candidate
            for j in range(i + 1, min(i + 3, len(raw_lines))):
                candidate = _clean_name_candidate(re.split(stop_pat, raw_lines[j], maxsplit=1, flags=re.IGNORECASE)[0])
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
    for ln in raw_lines:
        if re.search(r"\d", ln):
            continue
        candidate = _clean_name_candidate(ln)
        if blacklist.search(_norm_ocr_text(candidate)):
            continue
        if _is_likely_name(candidate) and len(candidate) > len(best):
            best = candidate
    return best


def _extract_gender(normalized_lines: List[str]) -> str:
    for norm_ln in normalized_lines:
        if re.search(r"\bgioi\s*tinh\b|\bsex\b", norm_ln, re.IGNORECASE):
            if re.search(r"\bnu\b|\bfemale\b", norm_ln):
                return "Nữ"
            if re.search(r"\bnam\b|\bmale\b", norm_ln):
                return "Nam"
    return ""


def _extract_address_block(
    raw_lines: List[str],
    normalized_lines: List[str],
    label_pattern: str,
    from_bottom: bool = False,
) -> str:
    stop_pat = re.compile(
        r"("
        r"noi\s*dang\s*ky\s*khai\s*sinh|place\s*of\s*birth|"
        r"ngay\s*cap|ngay\s*thang\s*nam\s*cap|date\s*of\s*issue|"
        r"ngay\s*het\s*han|co\s*gia\s*tri|date\s*of\s*expiry|expiry|"
        r"quoc\s*tich|nationality|"
        r"gioi\s*tinh|sex|"
        r"ngay\s*sinh|date\s*of\s*birth|"
        r"que\s*quan|place\s*of\s*origin|"
        r"idvnm|mrz"
        r")",
        re.IGNORECASE,
    )
    indexes = list(range(len(raw_lines)))
    if from_bottom:
        indexes.reverse()
    for i in indexes:
        norm_ln = normalized_lines[i]
        if re.search(label_pattern, norm_ln, re.IGNORECASE):
            parts = []
            raw_ln = raw_lines[i].strip(" .,:;")
            if ":" in raw_ln:
                inline_tail = raw_ln.split(":", 1)[1].strip(" .,:;")
                if inline_tail:
                    parts.append(inline_tail)
            for j in range(i + 1, len(raw_lines)):
                next_norm = normalized_lines[j]
                if stop_pat.search(next_norm):
                    break
                val = raw_lines[j].strip(" .,:;")
                if val:
                    parts.append(val)
            cleaned = []
            for p in parts:
                if not p:
                    continue
                pn = _norm_ocr_text(p)
                if re.fullmatch(r"(noi\s*(thuong\s*tru|cu\s*tru)|place\s*of\s*residence)", pn, re.IGNORECASE):
                    continue
                cleaned.append(p)
            if cleaned:
                return re.sub(r"\s+", " ", ", ".join(cleaned)).strip(" ,")
    return ""


def _extract_address_by_profile(raw_lines: List[str], normalized_lines: List[str], profile: str) -> str:
    if profile == DOC_PROFILE_FRONT_OLD:
        return _extract_address_block(
            raw_lines,
            normalized_lines,
            r"(noi\s*thuong\s*tru|place\s*of\s*residence)",
            from_bottom=True,
        )
    if profile == DOC_PROFILE_BACK_NEW:
        return _extract_address_block(
            raw_lines,
            normalized_lines,
            r"(noi\s*cu\s*tru|place\s*of\s*residence)",
            from_bottom=False,
        )
    # front_new + back_old: address is not expected on this side
    return ""


def _extract_mrz(raw_lines: List[str]) -> dict:
    compact_lines = [re.sub(r"\s+", "", _ascii_fold(ln or "").upper()) for ln in raw_lines if ln]
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


def _extract_cccd(raw_lines: List[str], normalized_lines: List[str]) -> str:
    mrz = _extract_mrz(raw_lines)
    if mrz.get("so_giay_to"):
        return mrz["so_giay_to"]

    for idx, norm_ln in enumerate(normalized_lines):
        if re.search(r"personal\s+identification|s[o0]\s*/?\s*no|so\s+dinh\s+danh", norm_ln, re.IGNORECASE):
            if m := re.search(r"\b(\d{12})\b", raw_lines[idx]):
                return m.group(1)

    full = " ".join(raw_lines)
    if m := re.search(r"\b(\d{12})\b", full):
        return m.group(1)
    digits = re.sub(r"\D", "", full)
    if len(digits) >= 12:
        return digits[:12]
    return ""


def _is_back_profile(profile: str) -> bool:
    return profile in {DOC_PROFILE_BACK_NEW, DOC_PROFILE_BACK_OLD}


def _parse_cccd(
    raw_lines: List[str],
    normalized_lines: List[str],
    qr_data: Optional[dict],
    profile: str,
) -> dict:
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

    mrz = _extract_mrz(raw_lines)
    is_back = _is_back_profile(profile)

    if not data["so_giay_to"]:
        data["so_giay_to"] = _extract_cccd(raw_lines, normalized_lines)
    if not data["ho_ten"]:
        data["ho_ten"] = _extract_name(raw_lines, normalized_lines)
    if not data["ngay_sinh"]:
        data["ngay_sinh"] = _find_date_after_label(raw_lines, normalized_lines, r"ngay\s*sinh|date\s*of\s*birth")
    if not data["gioi_tinh"]:
        data["gioi_tinh"] = _extract_gender(normalized_lines)
    if not data["dia_chi"]:
        data["dia_chi"] = _extract_address_by_profile(raw_lines, normalized_lines, profile)

    if mrz.get("so_giay_to") and (is_back or not data["so_giay_to"]):
        data["so_giay_to"] = mrz["so_giay_to"]
    # Ten uu tien QR/mat truoc; MRZ chi fallback khi thieu hoan toan.
    if mrz.get("ho_ten") and not data["ho_ten"]:
        data["ho_ten"] = mrz["ho_ten"]
    if mrz.get("ngay_sinh") and (is_back or not data["ngay_sinh"]):
        data["ngay_sinh"] = mrz["ngay_sinh"]
    if mrz.get("gioi_tinh") and (is_back or not data["gioi_tinh"]):
        data["gioi_tinh"] = mrz["gioi_tinh"]

    data["ngay_cap"] = _find_date_after_label(
        raw_lines,
        normalized_lines,
        r"ngay\s*cap|ngay\s*thang\s*nam\s*cap|date\s*of\s*issue",
    ) or data["ngay_cap"]
    data["ngay_het_han"] = _find_date_after_label(
        raw_lines,
        normalized_lines,
        r"co\s*gia\s*tri|ngay\s*het\s*han|date\s*of\s*expiry|expiry",
    ) or data["ngay_het_han"]

    if mrz.get("ngay_het_han") and not data["ngay_het_han"]:
        data["ngay_het_han"] = mrz["ngay_het_han"]

    if is_back:
        dates = re.findall(r"\d{1,2}/\d{1,2}/\d{4}", " ".join(raw_lines).replace("-", "/").replace(".", "/"))
        dates = [_normalize_date(d) for d in dates]
        dates = [d for d in dates if d]
        if not data["ngay_cap"] and len(dates) >= 1:
            data["ngay_cap"] = dates[0]
        if not data["ngay_het_han"] and len(dates) >= 2:
            data["ngay_het_han"] = dates[1]

    return data


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
def _build_raw_text(lines: List[str]) -> str:
    return "\n".join([ln for ln in lines if ln])


def _print_rapidocr_raw_text(raw_text: str, context: str = "") -> None:
    text = (raw_text or "").strip()
    if not text:
        return
    header = " RAW TEXT TU RAPIDOCR "
    if context:
        header = f" RAW TEXT TU RAPIDOCR ({context}) "
    print(f"\n{'='*20}{header}{'='*20}\n{text}\n{'='*80}\n")


def _clean_doc_number(value: str) -> str:
    return re.sub(r"\D", "", str(value or ""))


def _safe_filename(filename: str, index: int) -> str:
    base = os.path.basename(filename or f"image_{index + 1}.jpg")
    base = re.sub(r"[^A-Za-z0-9._-]+", "_", base).strip("._")
    if not base:
        base = f"image_{index + 1}.jpg"
    return base


def _pick_primary_crop(crops: List[DocCrop]) -> DocCrop:
    if not crops:
        raise ValueError("Khong phat hien crop hop le")
    return max(
        crops,
        key=lambda c: (
            float(c.confidence or 0.0),
            max(1, (c.bbox[2] - c.bbox[0])) * max(1, (c.bbox[3] - c.bbox[1])),
        ),
    )


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


_PROFILE_PRIORITY = {
    DOC_PROFILE_FRONT_OLD: 4,
    DOC_PROFILE_FRONT_NEW: 3,
    DOC_PROFILE_BACK_NEW: 2,
    DOC_PROFILE_BACK_OLD: 1,
    DOC_PROFILE_UNKNOWN: 0,
}


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

        if source_tag == "qr":
            base_data[key] = incoming_val
            field_sources[key] = "qr"
            continue

        if not current_val:
            base_data[key] = incoming_val
            field_sources[key] = source_tag
            continue

        if fill_missing_only:
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


def _append_person_raw_text(record: dict, raw_text: str, filename: str = "") -> None:
    text = (raw_text or "").strip()
    if not text:
        return
    if filename:
        text = f"[{filename}]\n{text}"
    if "raw_texts" not in record:
        record["raw_texts"] = []
    if text not in record["raw_texts"]:
        record["raw_texts"].append(text)


def _should_run_ocr_for_matched_qr(person_data: dict, profile: str) -> bool:
    # With QR matched card, run OCR only when side likely contributes missing data.
    if any(not (person_data.get(k) or "").strip() for k in ("so_giay_to", "ho_ten", "ngay_sinh", "gioi_tinh")):
        return True
    if profile in {DOC_PROFILE_BACK_NEW, DOC_PROFILE_BACK_OLD} and not (person_data.get("ngay_cap") or "").strip():
        return True
    if profile == DOC_PROFILE_FRONT_OLD and not (person_data.get("dia_chi") or "").strip():
        return True
    if profile == DOC_PROFILE_UNKNOWN:
        return True
    return False


def _normalize_qr_texts(qr_texts: Optional[List[str]], total: int) -> List[str]:
    out = ["" for _ in range(total)]
    if not isinstance(qr_texts, list):
        return out
    for i in range(min(total, len(qr_texts))):
        out[i] = str(qr_texts[i] or "").strip()
    return out


def _normalize_qr_failed_flags(flags: Optional[List[Any]], total: int) -> List[bool]:
    out = [False for _ in range(total)]
    if not isinstance(flags, list):
        return out
    for i in range(min(total, len(flags))):
        v = flags[i]
        if isinstance(v, bool):
            out[i] = v
        elif isinstance(v, str):
            out[i] = v.strip().lower() in {"1", "true", "yes", "y"}
        else:
            out[i] = bool(v)
    return out


def _probe_crop_for_batch(
    crop: DocCrop,
    seeded_qr_text: str = "",
    client_qr_failed: bool = False,
) -> dict:
    doc_type_from_model = crop.doc_type if crop.doc_type != "unknown" else "unknown"
    qr_data, qr_text = _try_qr_data_from_crop(crop, seeded_qr_text)

    qr_valid = _is_valid_qr_data(qr_data)
    if qr_valid:
        fallback_doc_type = "unknown" if doc_type_from_model == "cccd" else doc_type_from_model
        side = _infer_side(DOC_PROFILE_UNKNOWN, fallback_doc_type)
        return {
            "qr_valid": True,
            "qr_data": qr_data or {},
            "qr_text": qr_text,
            "lines": [],
            "normalized_lines": [],
            "raw_text": "",
            "profile": DOC_PROFILE_UNKNOWN,
            "doc_type": fallback_doc_type,
            "side": side,
            "so_giay_to": _clean_doc_number((qr_data or {}).get("so_giay_to", "")),
        }

    ocr_boxes = _rapidocr_recognize(crop.img)
    lines = _group_lines(ocr_boxes)
    normalized_lines = _normalize_ocr_lines(lines)
    raw_text = _build_raw_text(lines)
    _print_rapidocr_raw_text(raw_text, context="batch_probe")
    inferred_profile = _infer_doc_profile(normalized_lines, model_doc_type=doc_type_from_model)
    inferred_doc_type = _coarse_doc_type_from_profile(inferred_profile, model_doc_type=doc_type_from_model)
    fallback_doc_type = "unknown" if doc_type_from_model == "cccd" else doc_type_from_model
    final_doc_type = inferred_doc_type if inferred_doc_type != "unknown" else fallback_doc_type

    return {
        "qr_valid": False,
        "qr_data": None,
        "qr_text": "",
        "lines": lines,
        "normalized_lines": normalized_lines,
        "raw_text": raw_text,
        "profile": inferred_profile,
        "doc_type": final_doc_type,
        "side": _infer_side(inferred_profile, final_doc_type),
        "so_giay_to": _extract_cccd(lines, normalized_lines),
    }


def local_ocr_batch_from_inputs(
    file_items: List[dict],
    qr_texts: Optional[List[str]] = None,
    client_qr_failed: Optional[List[Any]] = None,
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
                "local_engine": _local_engine_name(),
                "rec_model_mode": _rapidocr_rec_mode,
            },
        }

    _ensure_local_ocr_dependencies()
    _get_rapidocr_engine()

    total = len(file_items)
    qr_text_values = _normalize_qr_texts(qr_texts, total)
    qr_failed_flags = _normalize_qr_failed_flags(client_qr_failed, total)

    prepared: List[dict] = []
    errors: List[dict] = []
    image_results: List[dict] = []
    for idx, item in enumerate(file_items):
        filename = item.get("filename") or f"image_{idx + 1}.jpg"
        image_results.append(
            {
                "index": idx,
                "filename": filename,
                "source_type": "unknown",
                "side": "unknown",
                "profile": DOC_PROFILE_UNKNOWN,
                "doc_type": "unknown",
                "raw_text": "",
                "warnings": [],
            }
        )

    qr_hits = 0
    for idx, item in enumerate(file_items):
        filename = item.get("filename") or f"image_{idx + 1}.jpg"
        raw_bytes = item.get("bytes") or b""
        try:
            img_np = np.frombuffer(raw_bytes, np.uint8)
            img_bgr = cv2.imdecode(img_np, cv2.IMREAD_COLOR)
            if img_bgr is None:
                raise ValueError("Khong doc duoc anh")
            img_bgr = _preprocess(img_bgr)
            crops = _detect_documents(img_bgr)
            crop = _pick_primary_crop(crops)
            probe = _probe_crop_for_batch(
                crop,
                seeded_qr_text=qr_text_values[idx],
                client_qr_failed=qr_failed_flags[idx],
            )
            if probe.get("qr_valid"):
                qr_hits += 1
            prepared.append(
                {
                    "index": idx,
                    "filename": filename,
                    "probe": probe,
                }
            )
        except Exception as e:
            errors.append({"index": idx, "filename": filename, "error": str(e)})
            image_results[idx] = {
                "index": idx,
                "filename": filename,
                "source_type": "error",
                "side": "unknown",
                "profile": DOC_PROFILE_UNKNOWN,
                "doc_type": "unknown",
                "raw_text": "",
                "warnings": ["ho_ten", "so_giay_to", "ngay_sinh", "gioi_tinh", "dia_chi", "ngay_cap"],
                "error": str(e),
            }

    persons_map: Dict[str, dict] = {}
    person_order: List[str] = []
    qr_by_cccd: Dict[str, dict] = {}

    for it in prepared:
        probe = it["probe"]
        if not probe.get("qr_valid"):
            continue
        cccd = _clean_doc_number(probe.get("so_giay_to", ""))
        if not cccd:
            continue
        existing = qr_by_cccd.get(cccd)
        current = probe.get("qr_data") or {}
        if not existing:
            qr_by_cccd[cccd] = current
            continue
        cur_score = _score_person(_build_qr_person_data(current))
        old_score = _score_person(_build_qr_person_data(existing))
        if cur_score > old_score:
            qr_by_cccd[cccd] = current

    ocr_runs = 0
    skipped_by_qr = 0

    def _ensure_person(key: str, base_data: dict, source_type: str, side: str, profile: str, filename: str, index: int) -> dict:
        if key not in persons_map:
            normalized = {k: (base_data.get(k) or "") for k in ("so_giay_to", "ho_ten", "ngay_sinh", "gioi_tinh", "dia_chi", "ngay_cap", "ngay_het_han")}
            persons_map[key] = {
                "data": normalized,
                "source_type": source_type,
                "side": side or "unknown",
                "profile": profile or DOC_PROFILE_UNKNOWN,
                "field_sources": _build_field_sources(source_type, normalized),
                "files": [filename] if filename else [],
                "indexes": [index],
                "raw_texts": [],
            }
            person_order.append(key)
            return persons_map[key]
        rec = persons_map[key]
        if filename and filename not in rec["files"]:
            rec["files"].append(filename)
        if index not in rec["indexes"]:
            rec["indexes"].append(index)
        rec["side"] = _merge_side(rec.get("side", "unknown"), side)
        rec["profile"] = _merge_profile(rec.get("profile", DOC_PROFILE_UNKNOWN), profile)
        if str(source_type or "").upper() == "QR":
            rec["source_type"] = "QR"
        return rec

    for item in sorted(prepared, key=lambda x: x["index"]):
        idx = item["index"]
        filename = item["filename"]
        probe = item["probe"]
        profile = probe.get("profile", DOC_PROFILE_UNKNOWN)
        side = probe.get("side", "unknown")
        doc_type = probe.get("doc_type", "unknown")
        cccd = _clean_doc_number(probe.get("so_giay_to", ""))

        if probe.get("qr_valid") and cccd:
            qr_data = _build_qr_person_data(probe.get("qr_data") or {})
            rec = _ensure_person(cccd, qr_data, "QR", side, profile, filename, idx)
            _merge_person_data(rec["data"], qr_data, rec["field_sources"], "QR")
            rec["data"]["so_giay_to"] = cccd
            warnings = _collect_warnings(rec["data"], rec.get("profile", DOC_PROFILE_UNKNOWN))
            image_results[idx] = {
                "index": idx,
                "filename": filename,
                "source_type": "QR",
                "side": side,
                "profile": rec.get("profile", profile),
                "doc_type": doc_type,
                "raw_text": "",
                "warnings": warnings,
            }
            continue

        matched_qr = bool(cccd and cccd in qr_by_cccd)
        if matched_qr:
            rec = _ensure_person(
                cccd,
                _build_qr_person_data(qr_by_cccd.get(cccd, {})),
                "QR",
                side,
                profile,
                filename,
                idx,
            )
            run_ocr = _should_run_ocr_for_matched_qr(rec["data"], profile)
            if run_ocr and probe.get("lines"):
                parsed = _parse_cccd(
                    probe.get("lines", []),
                    probe.get("normalized_lines", []),
                    None,
                    profile,
                )
                _merge_person_data(rec["data"], parsed, rec["field_sources"], "OCR", fill_missing_only=True)
                _append_person_raw_text(rec, probe.get("raw_text", ""), filename)
                ocr_runs += 1
                source_type = "OCR"
            else:
                skipped_by_qr += 1
                source_type = "QR"

            warnings = _collect_warnings(rec["data"], rec.get("profile", DOC_PROFILE_UNKNOWN))
            image_results[idx] = {
                "index": idx,
                "filename": filename,
                "source_type": source_type,
                "side": side,
                "profile": rec.get("profile", profile),
                "doc_type": doc_type,
                "raw_text": probe.get("raw_text", "") if source_type == "OCR" else "",
                "warnings": warnings,
            }
            continue

        parsed = {
            "so_giay_to": "",
            "ho_ten": "",
            "ngay_sinh": "",
            "gioi_tinh": "",
            "dia_chi": "",
            "ngay_cap": "",
            "ngay_het_han": "",
        }
        if probe.get("lines"):
            parsed = _parse_cccd(
                probe.get("lines", []),
                probe.get("normalized_lines", []),
                None,
                profile,
            )
        key_doc = _clean_doc_number(parsed.get("so_giay_to", "")) or cccd
        key = key_doc if key_doc else f"img:{idx}"
        if key_doc:
            parsed["so_giay_to"] = key_doc

        rec = _ensure_person(key, parsed, "OCR", side, profile, filename, idx)
        _merge_person_data(rec["data"], parsed, rec["field_sources"], "OCR", fill_missing_only=False)
        _append_person_raw_text(rec, probe.get("raw_text", ""), filename)
        ocr_runs += 1

        warnings = _collect_warnings(rec["data"], rec.get("profile", DOC_PROFILE_UNKNOWN))
        image_results[idx] = {
            "index": idx,
            "filename": filename,
            "source_type": "OCR",
            "side": side,
            "profile": rec.get("profile", profile),
            "doc_type": doc_type,
            "raw_text": probe.get("raw_text", ""),
            "warnings": warnings,
        }

    persons = []
    for key in person_order:
        rec = persons_map[key]
        data = {**rec["data"]}
        profile = rec.get("profile", DOC_PROFILE_UNKNOWN)
        warnings = _collect_warnings(data, profile)
        person_source = rec.get("source_type", "OCR")
        side = rec.get("side", "unknown")
        combined_raw_text = "\n\n".join(rec.get("raw_texts", []))
        if combined_raw_text:
            data["_raw_text"] = combined_raw_text
        persons.append(
            {
                "type": "person",
                "data": {**data, "profile": profile},
                "_source": f"{person_source} ({side})",
                "source_type": person_source,
                "side": side,
                "profile": profile,
                "field_sources": rec.get("field_sources", {}),
                "warnings": warnings,
                "_files": rec.get("files", []),
                "raw_text": combined_raw_text,
            }
        )

    return {
        "persons": persons,
        "properties": [],
        "marriages": [],
        "errors": errors,
        "image_results": image_results,
        "summary": {
            "total_images": total,
            "qr_hits": qr_hits,
            "ocr_runs": ocr_runs,
            "skipped_by_qr": skipped_by_qr,
            "local_engine": _local_engine_name(),
            "rec_model_mode": _rapidocr_rec_mode,
        },
    }


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


def _analyze_crop(
    crop: DocCrop,
    seeded_qr_text: str | None = None,
    allow_llm: bool = False,
    client_qr_failed: bool = False,
) -> dict:
    doc_type_from_model = crop.doc_type if crop.doc_type != "unknown" else "unknown"
    qr_data, qr_text = _try_qr_data_from_crop(crop, seeded_qr_text)

    # QR gate tuyệt đối: nếu đã có QR hợp lệ thì KHÔNG OCR ảnh này nữa.
    if _is_valid_qr_data(qr_data):
        data = _build_qr_person_data(qr_data or {})
        data.pop("ngay_het_han", None)
        fallback_doc_type = "unknown" if doc_type_from_model == "cccd" else doc_type_from_model
        profile = DOC_PROFILE_UNKNOWN
        warnings = _collect_warnings(data, profile)
        return {
            "data": data,
            "doc_type": fallback_doc_type,
            "profile": profile,
            "confidence": crop.confidence,
            "raw_text": "",
            "_lines": [],
            "_qr": True,
            "qr_text": qr_text,
            "source_type": "QR",
            "side": _infer_side(profile, fallback_doc_type),
            "field_sources": _build_field_sources("QR", data),
            "warnings": warnings,
        }

    ocr_boxes = _rapidocr_recognize(crop.img)
    lines = _group_lines(ocr_boxes)
    normalized_lines = _normalize_ocr_lines(lines)
    raw_text = _build_raw_text(lines)
    _print_rapidocr_raw_text(raw_text, context="single_crop")
    inferred_profile = _infer_doc_profile(normalized_lines, model_doc_type=doc_type_from_model)
    inferred_doc_type = _coarse_doc_type_from_profile(inferred_profile, model_doc_type=doc_type_from_model)
    fallback_doc_type = "unknown" if doc_type_from_model == "cccd" else doc_type_from_model
    final_doc_type = inferred_doc_type if inferred_doc_type != "unknown" else fallback_doc_type

    data = _parse_cccd(lines, normalized_lines, None, inferred_profile)
    data.pop("ngay_het_han", None)

    if allow_llm and _needs_llm_fallback(data) and raw_text:
        loop_data = None
        try:
            loop_data = asyncio.run(_llm_parse_text(raw_text, inferred_profile))
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

    warnings = _collect_warnings(data, inferred_profile)
    return {
        "data": data,
        "doc_type": final_doc_type,
        "profile": inferred_profile,
        "confidence": crop.confidence,
        "raw_text": raw_text,
        "_lines": lines,
        "_qr": False,
        "qr_text": "",
        "source_type": "OCR",
        "side": _infer_side(inferred_profile, final_doc_type),
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
        score = _score_person(c["data"], c.get("profile", DOC_PROFILE_UNKNOWN)) + (5 if c.get("source_type") == "QR" else 0)
        if best is None or score > best["score"]:
            best = {**c, "score": score}

    if not best:
        raise ValueError("Khong nhan dien duoc noi dung")

    data = best["data"]
    profile = best.get("profile", DOC_PROFILE_UNKNOWN)
    raw_text = best["raw_text"]
    warnings = best.get("warnings") or _collect_warnings(data, profile)

    return {
        "persons": [{
            "type": "person",
            "data": {**data, "_raw_text": raw_text, "profile": profile},
            "_source": f"{best.get('source_type', 'OCR')} ({best.get('side', 'unknown')})",
            "source_type": best.get("source_type", "OCR"),
            "side": best.get("side", "unknown"),
            "profile": profile,
            "field_sources": best.get("field_sources", {}),
            "warnings": warnings,
        }],
        "properties": [],
        "marriages": [],
        "raw_text": raw_text,
        "doc_type": best["doc_type"],
    }


def _score_person(data: dict, profile: str = DOC_PROFILE_UNKNOWN) -> int:
    core_keys = ["so_giay_to", "ho_ten", "ngay_sinh", "gioi_tinh", "ngay_cap"]
    score = sum(1 for k in core_keys if (data.get(k) or "").strip())
    if (data.get("dia_chi") or "").strip():
        score += 1
    elif not _address_expected(profile):
        # Neutral score when this profile should not contain address on current side.
        score += 1
    return score


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
                score = _score_person(c["data"], c.get("profile", DOC_PROFILE_UNKNOWN)) + (5 if c.get("source_type") == "QR" else 0)
                if best is None or score > best["score"]:
                    best = {**c, "score": score}
            if best:
                data = best["data"]
                profile = best.get("profile", DOC_PROFILE_UNKNOWN)
                warnings = best.get("warnings") or _collect_warnings(data, profile)
                persons.append({
                    "type": "person",
                    "data": {**data, "profile": profile},
                    "_source": f"{best.get('source_type', 'OCR')} ({best.get('side', 'unknown')})",
                    "filename": f.filename,
                    "_qr": best.get("_qr", False),
                    "source_type": best.get("source_type", "OCR"),
                    "side": best.get("side", "unknown"),
                    "profile": profile,
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
            "rec_model_mode": _rapidocr_rec_mode,
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
        for idx, upload in enumerate(files):
            safe_name = _safe_filename(upload.filename or "", idx)
            ext = os.path.splitext(safe_name)[1].lower() or ".jpg"
            stored_name = f"{idx:04d}{ext}"
            file_path = os.path.join(batch_dir, stored_name)
            raw = await upload.read()
            with open(file_path, "wb") as fw:
                fw.write(raw)
            manifest_items.append(
                {
                    "index": idx,
                    "filename": upload.filename or safe_name,
                    "stored_name": stored_name,
                }
            )

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
