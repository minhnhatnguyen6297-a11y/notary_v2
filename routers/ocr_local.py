"""
Local OCR (RapidOCR-only):
1) Tien xu ly anh (Python/OpenCV)
2) Quet QR neu ro (uu tien QR). Neu QR khong ro -> tiep tuc OCR
3) RapidOCR detect + nhan dang text
4) Regex loc truong thong tin can thiet
"""

from __future__ import annotations

import asyncio
import json
import uuid
import os
import shutil
import re
import traceback
import unicodedata
import logging
from time import perf_counter
from datetime import datetime
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from fastapi import APIRouter, UploadFile, File, HTTPException, Form, Body

_LOCAL_OCR_IMPORT_ERROR = None
try:
    import cv2
    import numpy as np
except ImportError as e:
    cv2 = None
    np = None
    _LOCAL_OCR_IMPORT_ERROR = str(e)

from .ocr import try_decode_qr, parse_cccd_qr
from database import SessionLocal
from models import OCRJob, ExtractedDocument
import httpx

router = APIRouter()
_logger = logging.getLogger("ocr_local")

# ---------------------- Config (env) ----------------------
MIN_BOX_SCORE = float(os.getenv("LOCAL_OCR_MIN_BOX_SCORE", "0.3"))
TEXT_LLM_MODEL = os.getenv("OCR_TEXT_LLM_MODEL", "gpt-4o-mini")
LOCAL_OCR_REC_MODEL_PATH = os.getenv("LOCAL_OCR_REC_MODEL_PATH", "").strip()
LOCAL_OCR_REC_KEYS_PATH = os.getenv("LOCAL_OCR_REC_KEYS_PATH", "").strip()
LOCAL_OCR_SMART_CROP_MIN_CONF = float(os.getenv("LOCAL_OCR_SMART_CROP_MIN_CONF", "0.22"))
LOCAL_OCR_MAX_SIDE_LEN = int(os.getenv("LOCAL_OCR_MAX_SIDE_LEN", "1200"))
LOCAL_OCR_TIMING_LOG = os.getenv("LOCAL_OCR_TIMING_LOG", "1").strip().lower() not in {"0", "false", "no", "off"}
LOCAL_OCR_TIMING_SLOW_MS = float(os.getenv("LOCAL_OCR_TIMING_SLOW_MS", "1500"))
LOCAL_OCR_TRIAGE_V2 = os.getenv("LOCAL_OCR_TRIAGE_V2", "1").strip().lower() not in {"0", "false", "no", "off"}
LOCAL_OCR_TRIAGE_FALLBACK_LEGACY = os.getenv("LOCAL_OCR_TRIAGE_FALLBACK_LEGACY", "1").strip().lower() not in {"0", "false", "no", "off"}
LOCAL_OCR_TRIAGE_PROXY_MAX_SIDE = int(os.getenv("LOCAL_OCR_TRIAGE_PROXY_MAX_SIDE", "720"))
LOCAL_OCR_TRIAGE_MRZ_MIN_SCORE = float(os.getenv("LOCAL_OCR_TRIAGE_MRZ_MIN_SCORE", "0.20"))

_ENV_PATH = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".env"))
_REC_MODEL_DIR = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "models", "rapidocr"))
_VI_REC_MODEL_CANDIDATES = [
    os.path.join(_REC_MODEL_DIR, "vi_PP-OCRv4_rec_infer.onnx"),
    os.path.join(_REC_MODEL_DIR, "vi_PP-OCRv3_rec_infer.onnx"),
]
_LATIN_REC_MODEL_CANDIDATES = [
    os.path.join(_REC_MODEL_DIR, "latin_PP-OCRv5_mobile_rec.onnx"),
    os.path.join(_REC_MODEL_DIR, "latin_PP-OCRv4_mobile_rec.onnx"),
    os.path.join(_REC_MODEL_DIR, "latin_PP-OCRv3_rec_infer.onnx"),
    os.path.join(_REC_MODEL_DIR, "latin_PP-OCRv3_mobile_rec.onnx"),
]
_VI_REC_KEYS_CANDIDATES = [
    os.path.join(_REC_MODEL_DIR, "vi_dict.txt"),
]
_LATIN_REC_KEYS_CANDIDATES = [
    os.path.join(_REC_MODEL_DIR, "latin_dict.txt"),
    os.path.join(_REC_MODEL_DIR, "ppocr_keys_v1.txt"),
]


def _read_env() -> dict:
    from dotenv import dotenv_values
    return dotenv_values(_ENV_PATH)


def _get_openai_key() -> str:
    key = os.getenv("OPENAI_API_KEY", "")
    if not key:
        key = _read_env().get("OPENAI_API_KEY", "")
    return key


def _pick_existing_path(candidates: List[str]) -> str:
    for candidate in candidates:
        if candidate and os.path.exists(candidate):
            return candidate
    return ""


def _describe_rec_model_path(path: str) -> str:
    base = os.path.basename(path or "").lower()
    if base.startswith("vi_"):
        return "vi_rec"
    if "latin" in base:
        return "latin_rec"
    if path:
        return "custom_rec"
    return "default"


def _resolve_rec_assets() -> tuple[str, str]:
    env_model_path = LOCAL_OCR_REC_MODEL_PATH
    env_keys_path = LOCAL_OCR_REC_KEYS_PATH
    vi_model_path = _pick_existing_path(_VI_REC_MODEL_CANDIDATES)
    latin_model_path = _pick_existing_path(_LATIN_REC_MODEL_CANDIDATES)
    vi_keys_path = _pick_existing_path(_VI_REC_KEYS_CANDIDATES)
    latin_keys_path = _pick_existing_path(_LATIN_REC_KEYS_CANDIDATES)

    selected_model_path = env_model_path if env_model_path and os.path.exists(env_model_path) else ""
    selected_keys_path = env_keys_path if env_keys_path and os.path.exists(env_keys_path) else ""

    if selected_model_path:
        current_mode = _describe_rec_model_path(selected_model_path)
        if current_mode == "latin_rec" and vi_model_path:
            _logger.info(
                "Phat hien model tieng Viet, uu tien dung thay cho model Latin tu env: %s -> %s",
                selected_model_path,
                vi_model_path,
            )
            selected_model_path = vi_model_path
            if not selected_keys_path or "latin" in os.path.basename(selected_keys_path).lower():
                selected_keys_path = vi_keys_path or selected_keys_path
    else:
        selected_model_path = vi_model_path or latin_model_path

    if not selected_keys_path:
        if _describe_rec_model_path(selected_model_path) == "vi_rec":
            selected_keys_path = vi_keys_path or latin_keys_path
        else:
            selected_keys_path = latin_keys_path or vi_keys_path

    return selected_model_path, selected_keys_path


# ---------------------- Lazy-loaded models ----------------------
_rapidocr_engine = None
_rapidocr_rec_mode = "default"
_rapidocr_runtime_label = "RapidOCR (CPU)"
_face_cascade = None
_qr_detector = None


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


def _ensure_local_ocr_dependencies() -> None:
    if _LOCAL_OCR_IMPORT_ERROR:
        _logger.error("Local OCR dependencies missing: %s", _LOCAL_OCR_IMPORT_ERROR)
        raise HTTPException(
            status_code=503,
            detail=(
                "Local OCR chua duoc cai dat day du. "
                "Hay cai dependency Local OCR (VPS: bash install_vps.sh). "
                f"Chi tiet: {_LOCAL_OCR_IMPORT_ERROR}"
            ),
        )


def _resolve_runtime_label(engine, available_providers: Optional[List[str]] = None, prefer_cuda: bool = False) -> str:
    """Best-effort runtime label from active ONNX providers."""
    try:
        for attr in ("text_det", "text_cls", "text_rec"):
            module = getattr(engine, attr, None)
            ort_wrapper = getattr(module, "session", None)
            ort_session = getattr(ort_wrapper, "session", None)
            if ort_session is None or not hasattr(ort_session, "get_providers"):
                continue
            providers = ort_session.get_providers() or []
            if providers and providers[0] == "CUDAExecutionProvider":
                return "RapidOCR (GPU)"
    except Exception:
        pass

    if prefer_cuda and available_providers and "CUDAExecutionProvider" in available_providers:
        return "RapidOCR (GPU)"
    return "RapidOCR (CPU)"


def _get_rapidocr_engine():
    _ensure_local_ocr_dependencies()
    global _rapidocr_engine, _rapidocr_rec_mode, _rapidocr_runtime_label
    if _rapidocr_engine is not None:
        return _rapidocr_engine
    t_engine_start = perf_counter()
    try:
        try:
            from rapidocr_onnxruntime import RapidOCR
        except ImportError:
            from rapidocr import RapidOCR

        available_providers: List[str] = []
        prefer_cuda = False
        try:
            import onnxruntime as ort
            available_providers = ort.get_available_providers() or []
            prefer_cuda = "CUDAExecutionProvider" in available_providers
        except Exception:
            available_providers = []
            prefer_cuda = False

        rec_model_path, rec_keys_path = _resolve_rec_assets()
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

        if prefer_cuda:
            custom_kwargs["det_use_cuda"] = True
            custom_kwargs["cls_use_cuda"] = True
            custom_kwargs["rec_use_cuda"] = True

        if custom_kwargs.get("rec_model_path"):
            try:
                _rapidocr_engine = RapidOCR(**custom_kwargs)
                _rapidocr_rec_mode = _describe_rec_model_path(custom_kwargs["rec_model_path"])
                _logger.info(
                    "RapidOCR khoi dong voi rec model: %s (%s)",
                    custom_kwargs["rec_model_path"],
                    _rapidocr_rec_mode,
                )
                print(f"[OCR_LOCAL] RapidOCR rec model mode: {_rapidocr_rec_mode}")
            except Exception as e:
                _logger.warning(
                    "Khoi dong RapidOCR voi rec model custom that bai (%s). Fallback model mac dinh.",
                    e,
                )
                fallback_kwargs = {}
                if prefer_cuda:
                    fallback_kwargs["det_use_cuda"] = True
                    fallback_kwargs["cls_use_cuda"] = True
                    fallback_kwargs["rec_use_cuda"] = True
                _rapidocr_engine = RapidOCR(**fallback_kwargs)
                _rapidocr_rec_mode = "default_fallback"
                print(f"[OCR_LOCAL][WARNING] RapidOCR fallback mode: {_rapidocr_rec_mode} (khong dung duoc model custom)")
        else:
            _rapidocr_engine = RapidOCR(**custom_kwargs)
            _rapidocr_rec_mode = "default"
            print(f"[OCR_LOCAL][WARNING] RapidOCR rec model mode: {_rapidocr_rec_mode} (chua cau hinh model tieng Viet)")
        _rapidocr_runtime_label = _resolve_runtime_label(
            _rapidocr_engine,
            available_providers=available_providers,
            prefer_cuda=prefer_cuda,
        )
        _log_timing(
            "engine_init",
            ms=_ms(perf_counter() - t_engine_start),
            runtime=_rapidocr_runtime_label,
            rec_model_mode=_rapidocr_rec_mode,
            prefer_cuda=prefer_cuda,
            providers=available_providers,
        )
    except ImportError:
        raise HTTPException(
            status_code=500,
            detail="Chua cai RapidOCR. Hay chay install_local_ocr.bat",
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Khong the khoi dong RapidOCR: {e}")
    return _rapidocr_engine


def warmup_local_ocr() -> tuple[bool, str]:
    """Warmup for startup (optional)."""
    try:
        _ensure_local_ocr_dependencies()
        _get_rapidocr_engine()
        return True, ""
    except Exception as e:
        _logger.exception("Local OCR warmup failed: %s", e)
        return False, str(e)


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


def _resize_long_side(img_bgr: np.ndarray, max_side: int = LOCAL_OCR_MAX_SIDE_LEN) -> np.ndarray:
    if img_bgr is None:
        return img_bgr
    h, w = img_bgr.shape[:2]
    longest = max(h, w)
    if longest <= max_side or max_side <= 0:
        return img_bgr
    scale = max_side / float(longest)
    nw = max(1, int(round(w * scale)))
    nh = max(1, int(round(h * scale)))
    return cv2.resize(img_bgr, (nw, nh), interpolation=cv2.INTER_AREA)


def _preprocess(img_bgr: np.ndarray) -> np.ndarray:
    """Light preprocessing for OCR."""
    img = img_bgr.copy()
    # Keep a light sharpen pass for small text.
    kernel = np.array([[0, -1, 0], [-1, 5, -1], [0, -1, 0]], dtype=np.float32)
    img = cv2.filter2D(img, -1, kernel)
    return img


def _opencv_smart_crop(img_bgr: np.ndarray) -> tuple[np.ndarray, Tuple[int, int, int, int], float] | None:
    """Fast contour-based crop for card-like rectangle; returns (crop, bbox, confidence)."""
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

    best_bbox: Tuple[int, int, int, int] | None = None
    best_score = 0.0
    for c in contours:
        area = float(cv2.contourArea(c))
        if area < img_area * 0.06:
            continue

        x, y, bw, bh = cv2.boundingRect(c)
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


def _detect_documents(img_bgr: np.ndarray) -> List[DocCrop]:
    h, w = img_bgr.shape[:2]
    full = DocCrop(
        img=_resize_long_side(img_bgr, LOCAL_OCR_MAX_SIDE_LEN),
        bbox=(0, 0, w, h),
        doc_type="unknown",
        confidence=0.0,
    )

    try:
        smart = _opencv_smart_crop(img_bgr)
        if smart is None:
            return [full]
        crop_img, bbox, conf = smart
        if conf < LOCAL_OCR_SMART_CROP_MIN_CONF:
            return [full]
        return [
            DocCrop(
                img=_resize_long_side(crop_img, LOCAL_OCR_MAX_SIDE_LEN),
                bbox=bbox,
                doc_type="unknown",
                confidence=conf,
            )
        ]
    except Exception:
        return [full]


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


def _rapidocr_recognize(img_bgr: np.ndarray, use_cls: bool = False) -> List[dict]:
    engine = _get_rapidocr_engine()
    try:
        raw_result = engine(img_bgr, use_cls=use_cls)
    except TypeError:
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
    t_probe = perf_counter()
    doc_type_from_model = crop.doc_type if crop.doc_type != "unknown" else "unknown"
    # Always allow backend QR rescue.
    # client_qr_failed is kept for telemetry/backward compatibility only.
    qr_timing: dict = {}
    qr_data, qr_text = _try_qr_data_from_crop(crop, seeded_qr_text, timing=qr_timing)

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
            "_timing": {
                "probe_ms": _ms(perf_counter() - t_probe),
                "qr_ms": qr_timing.get("total_ms", 0.0),
                "rapidocr_ms": 0.0,
                "group_lines_ms": 0.0,
                "normalize_ms": 0.0,
                "profile_infer_ms": 0.0,
                "qr_detail": qr_timing,
                "ocr_box_count": 0,
                "line_count": 0,
            },
        }

    t_ocr = perf_counter()
    ocr_boxes = _rapidocr_recognize(crop.img)
    rapidocr_ms = _ms(perf_counter() - t_ocr)
    t_group = perf_counter()
    lines = _group_lines(ocr_boxes)
    group_lines_ms = _ms(perf_counter() - t_group)
    t_norm = perf_counter()
    normalized_lines = _normalize_ocr_lines(lines)
    normalize_ms = _ms(perf_counter() - t_norm)
    raw_text = _build_raw_text(lines)
    _print_rapidocr_raw_text(raw_text, context="batch_probe")
    t_profile = perf_counter()
    inferred_profile = _infer_doc_profile(normalized_lines, model_doc_type=doc_type_from_model)
    inferred_doc_type = _coarse_doc_type_from_profile(inferred_profile, model_doc_type=doc_type_from_model)
    profile_infer_ms = _ms(perf_counter() - t_profile)
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
        "_timing": {
            "probe_ms": _ms(perf_counter() - t_probe),
            "qr_ms": qr_timing.get("total_ms", 0.0),
            "rapidocr_ms": rapidocr_ms,
            "group_lines_ms": group_lines_ms,
            "normalize_ms": normalize_ms,
            "profile_infer_ms": profile_infer_ms,
            "qr_detail": qr_timing,
            "ocr_box_count": len(ocr_boxes),
            "line_count": len(lines),
        },
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
                "rec_model_mode": _rapidocr_rec_mode,
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

    image_results: List[dict] = []
    errors: List[dict] = []
    records: List[dict] = []
    for idx, item in enumerate(file_items):
        image_results.append(
            {
                "index": idx,
                "filename": item.get("filename") or f"image_{idx + 1}.jpg",
                "source_type": "unknown",
                "side": "unknown",
                "profile": DOC_PROFILE_UNKNOWN,
                "doc_type": "unknown",
                "raw_text": "",
                "warnings": [],
                "triage_state": TRIAGE_STATE_UNKNOWN,
                "orientation_angle": 0,
                "face_detected": False,
                "qr_detected": False,
                "mrz_score": 0.0,
                "id_12": "",
                "id_source": "none",
                "paired": False,
                "pair_key": None,
                "fallback_legacy_used": False,
                "timing_ms": {},
            }
        )

    _log_timing(
        "batch_v2_start",
        trace_id=trace_id,
        total_images=total,
        qr_texts_count=len(qr_texts or []),
        qr_failed_flags_count=len(client_qr_failed or []),
    )

    for idx, item in enumerate(file_items):
        filename = item.get("filename") or f"image_{idx + 1}.jpg"
        raw_bytes = item.get("bytes") or b""
        t_img = perf_counter()
        try:
            t_decode = perf_counter()
            img_np = np.frombuffer(raw_bytes, np.uint8)
            img_bgr = cv2.imdecode(img_np, cv2.IMREAD_COLOR)
            decode_ms = _ms(perf_counter() - t_decode)
            if img_bgr is None:
                raise ValueError("Khong doc duoc anh")

            h, w = img_bgr.shape[:2]
            t_pre = perf_counter()
            img_bgr = _preprocess(img_bgr)
            preprocess_ms = _ms(perf_counter() - t_pre)
            t_detect = perf_counter()
            crops = _detect_documents(img_bgr)
            detect_ms = _ms(perf_counter() - t_detect)
            crop = _pick_primary_crop(crops)
            crop_h, crop_w = crop.img.shape[:2]

            analyzed = _analyze_crop_triage_v2(
                crop,
                seeded_qr_text=qr_text_values[idx],
                client_qr_failed=qr_failed_flags[idx],
            )

            triage_state = analyzed.get("triage_state", TRIAGE_STATE_UNKNOWN)
            state_counts[triage_state] = state_counts.get(triage_state, 0) + 1
            timing = analyzed.get("_timing", {}) or {}
            total_img_ms = _ms(perf_counter() - t_img)
            timing_ms = {
                "decode_ms": decode_ms,
                "preprocess_ms": preprocess_ms,
                "detect_ms": detect_ms,
                "triage_ms": timing.get("triage_ms", 0.0),
                "qr_detect_ms": timing.get("qr_detect_ms", 0.0),
                "qr_decode_ms": timing.get("qr_decode_ms", 0.0),
                "targeted_ocr_ms": timing.get("targeted_ocr_ms", 0.0),
                "id_extract_ms": timing.get("id_extract_ms", 0.0),
                "group_lines_ms": timing.get("group_lines_ms", 0.0),
                "normalize_ms": timing.get("normalize_ms", 0.0),
                "fallback_phase_ms": timing.get("fallback_phase_ms", 0.0),
                "merge_ms": 0.0,
                "total_ms": total_img_ms,
            }

            row = {
                "index": idx,
                "filename": filename,
                "source_type": analyzed.get("source_type", "OCR"),
                "side": analyzed.get("side", "unknown"),
                "profile": analyzed.get("profile", DOC_PROFILE_UNKNOWN),
                "doc_type": analyzed.get("doc_type", "unknown"),
                "raw_text": analyzed.get("raw_text", ""),
                "warnings": analyzed.get("warnings", []),
                "triage_state": triage_state,
                "orientation_angle": analyzed.get("orientation_angle", 0),
                "face_detected": analyzed.get("face_detected", False),
                "qr_detected": analyzed.get("qr_detected", False),
                "mrz_score": analyzed.get("mrz_score", 0.0),
                "id_12": _clean_doc_number(analyzed.get("id_12", analyzed.get("data", {}).get("so_giay_to", ""))),
                "id_source": analyzed.get("id_source", "none"),
                "paired": False,
                "pair_key": None,
                "fallback_legacy_used": bool(analyzed.get("fallback_legacy_used", False)),
                "timing_ms": timing_ms,
            }
            image_results[idx] = row
            records.append(
                {
                    "index": idx,
                    "filename": filename,
                    "analysis": analyzed,
                    "timing_ms": timing_ms,
                    "image_shape": f"{w}x{h}",
                    "crop_shape": f"{crop_w}x{crop_h}",
                }
            )
            _log_timing(
                "batch_v2_image",
                trace_id=trace_id,
                index=idx,
                filename=filename,
                source_type=row["source_type"],
                triage_state=row["triage_state"],
                orientation_angle=row["orientation_angle"],
                id_12=row["id_12"],
                id_source=row["id_source"],
                fallback_legacy_used=row["fallback_legacy_used"],
                timing_ms=timing_ms,
                img_shape=f"{w}x{h}",
                crop_shape=f"{crop_w}x{crop_h}",
                qr_seeded=bool((qr_text_values[idx] or "").strip()),
                client_qr_failed=bool(qr_failed_flags[idx]),
            )
        except Exception as e:
            errors.append({"index": idx, "filename": filename, "error": str(e)})
            image_results[idx].update(
                {
                    "source_type": "error",
                    "warnings": ["ho_ten", "so_giay_to", "ngay_sinh", "gioi_tinh", "dia_chi", "ngay_cap"],
                    "error": str(e),
                    "timing_ms": {"total_ms": _ms(perf_counter() - t_img)},
                }
            )
            _log_timing(
                "batch_v2_image_error",
                level="warning",
                trace_id=trace_id,
                index=idx,
                filename=filename,
                total_ms=_ms(perf_counter() - t_img),
                error=str(e),
            )

    t_merge_phase = perf_counter()
    groups: Dict[str, List[dict]] = {}
    unpaired_records: List[dict] = []
    for rec in records:
        analysis = rec.get("analysis", {})
        id_12 = _clean_doc_number(analysis.get("id_12", analysis.get("data", {}).get("so_giay_to", "")))
        if id_12:
            groups.setdefault(id_12, []).append(rec)
        else:
            unpaired_records.append(rec)

    persons: List[dict] = []
    paired_count = 0
    for pair_key, recs in sorted(groups.items(), key=lambda kv: min(r.get("index", 0) for r in kv[1])):
        t_merge_one = perf_counter()
        merged_data = {
            "so_giay_to": pair_key,
            "ho_ten": "",
            "ngay_sinh": "",
            "gioi_tinh": "",
            "dia_chi": "",
            "ngay_cap": "",
        }
        field_sources: Dict[str, str] = {}
        side = "unknown"
        profile = DOC_PROFILE_UNKNOWN
        has_qr = False
        raw_texts: List[str] = []
        files: List[str] = []

        ordered = sorted(
            recs,
            key=lambda r: (
                1 if str(r.get("analysis", {}).get("source_type", "OCR")).upper() == "QR" else 0,
                1 if r.get("analysis", {}).get("side") == "front" else 0,
                -int(r.get("index", 0)),
            ),
            reverse=True,
        )
        for rec in ordered:
            analysis = rec.get("analysis", {})
            data = analysis.get("data", {}) or {}
            src = str(analysis.get("source_type", "OCR")).upper()
            has_qr = has_qr or src == "QR"
            _merge_person_data(merged_data, data, field_sources, src, fill_missing_only=False)
            side = _merge_side(side, analysis.get("side", "unknown"))
            profile = _merge_profile(profile, analysis.get("profile", DOC_PROFILE_UNKNOWN))
            raw = analysis.get("raw_text", "")
            if raw:
                raw_texts.append(raw)
            if rec.get("filename") and rec["filename"] not in files:
                files.append(rec["filename"])

        _apply_delta_merge(merged_data, [r.get("analysis", {}) for r in ordered])
        merged_data["so_giay_to"] = pair_key
        warnings = _collect_warnings(merged_data, profile)
        person_source = "QR" if has_qr else "OCR"
        combined_raw_text = "\n\n".join([txt for txt in raw_texts if txt])
        person_payload = {
            "type": "person",
            "data": {**merged_data, "profile": profile},
            "_source": f"{person_source} ({side})",
            "source_type": person_source,
            "side": side,
            "profile": profile,
            "field_sources": field_sources,
            "warnings": warnings,
            "_files": files,
            "raw_text": combined_raw_text,
        }
        persons.append(person_payload)
        if len(recs) >= 2:
            paired_count += 1

        merge_one_ms = _ms(perf_counter() - t_merge_one)
        for rec in recs:
            idx = rec.get("index", -1)
            if 0 <= idx < len(image_results):
                image_results[idx]["paired"] = True
                image_results[idx]["pair_key"] = pair_key
                image_results[idx]["timing_ms"]["merge_ms"] = merge_one_ms
                warn_data = (
                    merged_data
                    if image_results[idx].get("source_type") == "QR"
                    else rec.get("analysis", {}).get("data", {})
                )
                image_results[idx]["warnings"] = _collect_warnings(
                    warn_data,
                    rec.get("analysis", {}).get("profile", DOC_PROFILE_UNKNOWN),
                )

    for rec in unpaired_records:
        idx = rec.get("index", -1)
        if 0 <= idx < len(image_results):
            image_results[idx]["paired"] = False
            image_results[idx]["pair_key"] = None
            if "so_giay_to" not in image_results[idx]["warnings"]:
                image_results[idx]["warnings"] = list(dict.fromkeys(image_results[idx]["warnings"] + ["so_giay_to"]))

    merge_phase_ms = _ms(perf_counter() - t_merge_phase)
    total_ms = _ms(perf_counter() - t_total)

    qr_hits = sum(1 for r in records if str(r.get("analysis", {}).get("source_type", "OCR")).upper() == "QR")
    ocr_runs = sum(1 for r in records if str(r.get("analysis", {}).get("source_type", "OCR")).upper() == "OCR")
    skipped_by_qr = qr_hits

    def _sum_phase(phase_key: str) -> float:
        return round(
            sum(float((row.get("timing_ms") or {}).get(phase_key, 0.0) or 0.0) for row in image_results if isinstance(row, dict)),
            2,
        )

    timing_summary = {
        "total_ms": total_ms,
        "engine_init_ms": engine_ms,
        "decode_total_ms": _sum_phase("decode_ms"),
        "preprocess_total_ms": _sum_phase("preprocess_ms"),
        "detect_total_ms": _sum_phase("detect_ms"),
        "triage_phase_ms": _sum_phase("triage_ms"),
        "qr_detect_phase_ms": _sum_phase("qr_detect_ms"),
        "qr_decode_phase_ms": _sum_phase("qr_decode_ms"),
        "targeted_extract_phase_ms": _sum_phase("targeted_ocr_ms"),
        "id_extract_phase_ms": _sum_phase("id_extract_ms"),
        "merge_phase_ms": merge_phase_ms,
        "fallback_phase_ms": _sum_phase("fallback_phase_ms"),
    }
    slowest_images = sorted(
        [row for row in image_results if isinstance(row, dict)],
        key=lambda row: float((row.get("timing_ms") or {}).get("total_ms", 0.0) or 0.0),
        reverse=True,
    )[:5]

    _log_timing(
        "batch_v2_done",
        level="warning" if total_ms >= LOCAL_OCR_TIMING_SLOW_MS * max(1, total) else "info",
        trace_id=trace_id,
        total_images=total,
        persons=len(persons),
        errors=len(errors),
        qr_hits=qr_hits,
        ocr_runs=ocr_runs,
        paired_count=paired_count,
        unpaired_count=len(unpaired_records),
        state_counts=state_counts,
        timing_ms=timing_summary,
        slowest_images=slowest_images,
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
            "state_counts": state_counts,
            "pairing": {
                "paired_count": paired_count,
                "unpaired_count": len(unpaired_records),
            },
            "local_engine": _local_engine_name(),
            "rec_model_mode": _rapidocr_rec_mode,
            "timing_ms": timing_summary,
            "slowest_images": slowest_images,
        },
    }


def local_ocr_batch_from_inputs(
    file_items: List[dict],
    qr_texts: Optional[List[str]] = None,
    client_qr_failed: Optional[List[Any]] = None,
    trace_id: str | None = None,
) -> dict:
    if LOCAL_OCR_TRIAGE_V2:
        try:
            return _local_ocr_batch_from_inputs_triage_v2(
                file_items=file_items,
                qr_texts=qr_texts,
                client_qr_failed=client_qr_failed,
                trace_id=trace_id,
            )
        except Exception as e:
            if not LOCAL_OCR_TRIAGE_FALLBACK_LEGACY:
                raise
            _log_timing(
                "batch_v2_failed_fallback_legacy",
                level="warning",
                trace_id=trace_id,
                error=str(e),
            )

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
                "timing_ms": {},
            },
        }

    t_total = perf_counter()
    _log_timing(
        "batch_start",
        trace_id=trace_id,
        total_images=len(file_items),
        qr_texts_count=len(qr_texts or []),
        qr_failed_flags_count=len(client_qr_failed or []),
    )

    _ensure_local_ocr_dependencies()
    t_engine = perf_counter()
    _get_rapidocr_engine()
    engine_ms = _ms(perf_counter() - t_engine)

    total = len(file_items)
    qr_text_values = _normalize_qr_texts(qr_texts, total)
    qr_failed_flags = _normalize_qr_failed_flags(client_qr_failed, total)

    prepared: List[dict] = []
    errors: List[dict] = []
    image_timing_rows: List[dict] = []
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
        t_img_total = perf_counter()
        filename = item.get("filename") or f"image_{idx + 1}.jpg"
        raw_bytes = item.get("bytes") or b""
        try:
            t_decode = perf_counter()
            img_np = np.frombuffer(raw_bytes, np.uint8)
            img_bgr = cv2.imdecode(img_np, cv2.IMREAD_COLOR)
            decode_ms = _ms(perf_counter() - t_decode)
            if img_bgr is None:
                raise ValueError("Khong doc duoc anh")
            h, w = img_bgr.shape[:2]
            t_pre = perf_counter()
            img_bgr = _preprocess(img_bgr)
            preprocess_ms = _ms(perf_counter() - t_pre)
            t_detect = perf_counter()
            crops = _detect_documents(img_bgr)
            detect_ms = _ms(perf_counter() - t_detect)
            crop = _pick_primary_crop(crops)
            crop_h, crop_w = crop.img.shape[:2]
            t_probe = perf_counter()
            probe = _probe_crop_for_batch(
                crop,
                seeded_qr_text=qr_text_values[idx],
                client_qr_failed=qr_failed_flags[idx],
            )
            probe_ms = _ms(perf_counter() - t_probe)
            if probe.get("qr_valid"):
                qr_hits += 1
            probe_timing = probe.get("_timing", {})
            image_total_ms = _ms(perf_counter() - t_img_total)
            image_row = {
                "index": idx,
                "filename": filename,
                "probe_source_type": "QR" if probe.get("qr_valid") else "OCR",
                "decode_ms": decode_ms,
                "preprocess_ms": preprocess_ms,
                "detect_ms": detect_ms,
                "probe_ms": probe_ms,
                "qr_ms": probe_timing.get("qr_ms", 0.0),
                "rapidocr_ms": probe_timing.get("rapidocr_ms", 0.0),
                "profile_infer_ms": probe_timing.get("profile_infer_ms", 0.0),
                "ocr_box_count": probe_timing.get("ocr_box_count", 0),
                "line_count": probe_timing.get("line_count", 0),
                "image_total_ms": image_total_ms,
                "img_shape": f"{w}x{h}",
                "crop_shape": f"{crop_w}x{crop_h}",
                "qr_seeded": bool((qr_text_values[idx] or "").strip()),
                "client_qr_failed": bool(qr_failed_flags[idx]),
            }
            image_timing_rows.append(image_row)
            _log_timing(
                "batch_probe_image",
                trace_id=trace_id,
                **image_row,
            )
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
            _log_timing(
                "batch_probe_image_error",
                level="warning",
                trace_id=trace_id,
                index=idx,
                filename=filename,
                image_total_ms=_ms(perf_counter() - t_img_total),
                error=str(e),
            )

    timing_row_by_index = {row.get("index"): row for row in image_timing_rows}

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
        t_merge_image = perf_counter()
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
            merge_ms = _ms(perf_counter() - t_merge_image)
            row = timing_row_by_index.get(idx)
            if isinstance(row, dict):
                row["merge_ms"] = merge_ms
                row["final_source_type"] = "QR"
            _log_timing(
                "batch_merge_image",
                trace_id=trace_id,
                index=idx,
                filename=filename,
                final_source_type="QR",
                merge_reason="direct_qr",
                merge_ms=merge_ms,
                warnings=warnings,
            )
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
            merge_ms = _ms(perf_counter() - t_merge_image)
            row = timing_row_by_index.get(idx)
            if isinstance(row, dict):
                row["merge_ms"] = merge_ms
                row["final_source_type"] = source_type
            _log_timing(
                "batch_merge_image",
                trace_id=trace_id,
                index=idx,
                filename=filename,
                final_source_type=source_type,
                merge_reason="matched_qr_with_ocr" if source_type == "OCR" else "matched_qr_skip_ocr",
                merge_ms=merge_ms,
                warnings=warnings,
            )
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
        merge_ms = _ms(perf_counter() - t_merge_image)
        row = timing_row_by_index.get(idx)
        if isinstance(row, dict):
            row["merge_ms"] = merge_ms
            row["final_source_type"] = "OCR"
        _log_timing(
            "batch_merge_image",
            trace_id=trace_id,
            index=idx,
            filename=filename,
            final_source_type="OCR",
            merge_reason="ocr_only",
            merge_ms=merge_ms,
            warnings=warnings,
        )

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

    total_ms = _ms(perf_counter() - t_total)
    probe_total_ms = round(sum(float(row.get("probe_ms", 0.0) or 0.0) for row in image_timing_rows), 2)
    merge_total_ms = round(sum(float(row.get("merge_ms", 0.0) or 0.0) for row in image_timing_rows), 2)
    decode_total_ms = round(sum(float(row.get("decode_ms", 0.0) or 0.0) for row in image_timing_rows), 2)
    preprocess_total_ms = round(sum(float(row.get("preprocess_ms", 0.0) or 0.0) for row in image_timing_rows), 2)
    detect_total_ms = round(sum(float(row.get("detect_ms", 0.0) or 0.0) for row in image_timing_rows), 2)
    qr_stage_total_ms = round(sum(float(row.get("qr_ms", 0.0) or 0.0) for row in image_timing_rows), 2)
    rapidocr_stage_total_ms = round(sum(float(row.get("rapidocr_ms", 0.0) or 0.0) for row in image_timing_rows), 2)
    top_slow_images = sorted(
        image_timing_rows,
        key=lambda x: float(x.get("image_total_ms", 0.0) or 0.0),
        reverse=True,
    )[:3]

    _log_timing(
        "batch_done",
        level="warning" if total_ms >= LOCAL_OCR_TIMING_SLOW_MS * max(1, total) else "info",
        trace_id=trace_id,
        total_images=total,
        persons=len(persons),
        errors=len(errors),
        total_ms=total_ms,
        engine_init_ms=engine_ms,
        decode_total_ms=decode_total_ms,
        preprocess_total_ms=preprocess_total_ms,
        detect_total_ms=detect_total_ms,
        probe_total_ms=probe_total_ms,
        merge_total_ms=merge_total_ms,
        qr_stage_total_ms=qr_stage_total_ms,
        rapidocr_stage_total_ms=rapidocr_stage_total_ms,
        qr_hits=qr_hits,
        ocr_runs=ocr_runs,
        skipped_by_qr=skipped_by_qr,
        slowest_images=top_slow_images,
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
            "timing_ms": {
                "total_ms": total_ms,
                "engine_init_ms": engine_ms,
                "decode_total_ms": decode_total_ms,
                "preprocess_total_ms": preprocess_total_ms,
                "detect_total_ms": detect_total_ms,
                "probe_total_ms": probe_total_ms,
                "merge_total_ms": merge_total_ms,
                "qr_stage_total_ms": qr_stage_total_ms,
                "rapidocr_stage_total_ms": rapidocr_stage_total_ms,
            },
            "slowest_images": top_slow_images,
        },
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
        success, encoded_img = cv2.imencode(".jpg", crop.img)
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


TRIAGE_STATE_FRONT_OLD = "front_old"
TRIAGE_STATE_FRONT_NEW = "front_new"
TRIAGE_STATE_BACK_NEW = "back_new"
TRIAGE_STATE_BACK_OLD = "back_old"
TRIAGE_STATE_UNKNOWN = "unknown"


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
    a = int(angle) % 360
    if a == 90:
        return cv2.rotate(img_bgr, cv2.ROTATE_90_CLOCKWISE)
    if a == 180:
        return cv2.rotate(img_bgr, cv2.ROTATE_180)
    if a == 270:
        return cv2.rotate(img_bgr, cv2.ROTATE_90_COUNTERCLOCKWISE)
    return img_bgr


def _make_proxy_image(img_bgr: np.ndarray, max_side: int) -> np.ndarray:
    if img_bgr is None:
        return img_bgr
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
        faces = cascade.detectMultiScale(
            gray,
            scaleFactor=1.1,
            minNeighbors=4,
            minSize=(24, 24),
        )
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
        for c in contours:
            x, y, bw, bh = cv2.boundingRect(c)
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
            key=lambda r: (
                float(r.get("confidence", 0.0)),
                1 if r.get("qr_detected") else 0,
                1 if r.get("face_detected") else 0,
                float(r.get("mrz_score", 0.0)),
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


def _front_roi(img_bgr: np.ndarray) -> np.ndarray:
    h, _ = img_bgr.shape[:2]
    y2 = max(1, int(round(h * 0.55)))
    return img_bgr[:y2, :]


def _back_mrz_roi(img_bgr: np.ndarray) -> np.ndarray:
    h, _ = img_bgr.shape[:2]
    y1 = min(h - 1, max(0, int(round(h * 0.70))))
    return img_bgr[y1:, :]


def _extract_id_12_from_text(text: str) -> str:
    if not text:
        return ""
    if m := re.search(r"(?<!\d)(\d{12})(?!\d)", text):
        return m.group(1)
    digits = re.sub(r"\D", "", text)
    if len(digits) >= 12:
        return digits[:12]
    return ""


def _extract_id_12_from_mrz_text(text: str) -> str:
    normalized = re.sub(r"\s+", "", _ascii_fold(text or "").upper())
    if not normalized:
        return ""
    if m := re.search(r"IDVNM\d{10}(\d{12})", normalized):
        return m.group(1)
    if m := re.search(r"IDVNM(?:\d|<){0,18}(\d{12})", normalized):
        return m.group(1)
    if m := re.search(r"(\d{12})<<\d", normalized):
        return m.group(1)
    return ""


def _ocr_lines_from_image(img_bgr: np.ndarray, use_cls: bool = False) -> tuple[List[str], List[str], str, dict]:
    t_ocr = perf_counter()
    ocr_boxes = _rapidocr_recognize(img_bgr, use_cls=use_cls)
    targeted_ocr_ms = _ms(perf_counter() - t_ocr)
    t_group = perf_counter()
    lines = _group_lines(ocr_boxes)
    group_lines_ms = _ms(perf_counter() - t_group)
    t_norm = perf_counter()
    normalized_lines = _normalize_ocr_lines(lines)
    normalize_ms = _ms(perf_counter() - t_norm)
    raw_text = _build_raw_text(lines)
    return lines, normalized_lines, raw_text, {
        "targeted_ocr_ms": targeted_ocr_ms,
        "group_lines_ms": group_lines_ms,
        "normalize_ms": normalize_ms,
        "ocr_box_count": len(ocr_boxes),
        "line_count": len(lines),
    }


def _analyze_crop_triage_v2(
    crop: DocCrop,
    seeded_qr_text: str | None = None,
    client_qr_failed: bool = False,
) -> dict:
    t_total = perf_counter()
    triage = _triage_crop_orientation(crop.img)
    oriented_img = triage.get("oriented_img", crop.img)
    triage_state = str(triage.get("triage_state", TRIAGE_STATE_UNKNOWN))
    profile = _triage_profile_from_state(triage_state)
    side = _triage_side_from_state(triage_state)

    oriented_crop = DocCrop(
        img=_resize_long_side(oriented_img, LOCAL_OCR_MAX_SIDE_LEN),
        bbox=crop.bbox,
        doc_type=crop.doc_type,
        confidence=crop.confidence,
    )

    data = {
        "so_giay_to": "",
        "ho_ten": "",
        "ngay_sinh": "",
        "gioi_tinh": "",
        "dia_chi": "",
        "ngay_cap": "",
    }
    raw_text = ""
    source_type = "OCR"
    id_12 = ""
    id_source = "none"
    qr_text = ""
    qr_timing: dict = {}
    qr_decode_ms = 0.0
    targeted_ocr_ms = 0.0
    group_lines_ms = 0.0
    normalize_ms = 0.0
    id_extract_ms = 0.0
    ocr_box_count = 0
    line_count = 0
    fallback_legacy_used = False
    fallback_ms = 0.0

    state_has_qr = _triage_state_has_qr(triage_state)
    if state_has_qr or (seeded_qr_text or "").strip():
        t_qr = perf_counter()
        qr_data, qr_text = _try_qr_data_from_crop(
            oriented_crop,
            seeded_qr_text=seeded_qr_text,
            timing=qr_timing,
        )
        qr_decode_ms = _ms(perf_counter() - t_qr)
        if _is_valid_qr_data(qr_data):
            parsed_qr = _build_qr_person_data(qr_data or {})
            parsed_qr.pop("ngay_het_han", None)
            data.update(parsed_qr)
            source_type = "QR"
            id_12 = _clean_doc_number(parsed_qr.get("so_giay_to", ""))
            id_source = "qr" if id_12 else "none"

    if source_type != "QR":
        if triage_state in {TRIAGE_STATE_FRONT_OLD, TRIAGE_STATE_FRONT_NEW}:
            roi = _front_roi(oriented_crop.img)
        elif triage_state in {TRIAGE_STATE_BACK_NEW, TRIAGE_STATE_BACK_OLD}:
            roi = _back_mrz_roi(oriented_crop.img)
        else:
            roi = oriented_crop.img

        lines, normalized_lines, raw_text, ocr_timing = _ocr_lines_from_image(roi, use_cls=False)
        _print_rapidocr_raw_text(raw_text, context=f"targeted_{triage_state}")
        targeted_ocr_ms = ocr_timing.get("targeted_ocr_ms", 0.0)
        group_lines_ms = ocr_timing.get("group_lines_ms", 0.0)
        normalize_ms = ocr_timing.get("normalize_ms", 0.0)
        ocr_box_count = ocr_timing.get("ocr_box_count", 0)
        line_count = ocr_timing.get("line_count", 0)

        t_id = perf_counter()
        if triage_state in {TRIAGE_STATE_BACK_NEW, TRIAGE_STATE_BACK_OLD}:
            id_12 = _extract_id_12_from_mrz_text(raw_text) or _extract_id_12_from_text(raw_text)
            id_source = "mrz" if id_12 else "none"
            parsed = _parse_cccd(lines, normalized_lines, None, profile or DOC_PROFILE_BACK_OLD)
        else:
            id_12 = _extract_id_12_from_text(raw_text)
            id_source = "front_roi" if id_12 else "none"
            parsed = _parse_cccd(lines, normalized_lines, None, profile or DOC_PROFILE_FRONT_NEW)
        id_extract_ms = _ms(perf_counter() - t_id)

        parsed.pop("ngay_het_han", None)
        data.update({k: v for k, v in parsed.items() if k in data and (v or "").strip()})
        if id_12:
            data["so_giay_to"] = id_12

    need_legacy_fallback = (
        LOCAL_OCR_TRIAGE_FALLBACK_LEGACY
        and (
            triage_state == TRIAGE_STATE_UNKNOWN
            or not _clean_doc_number(data.get("so_giay_to", ""))
            or _score_person(data, profile) < 2
        )
    )
    if need_legacy_fallback:
        t_fb = perf_counter()
        legacy = _analyze_crop(
            oriented_crop,
            seeded_qr_text=seeded_qr_text,
            allow_llm=False,
            client_qr_failed=client_qr_failed,
        )
        fallback_ms = _ms(perf_counter() - t_fb)
        fallback_legacy_used = True
        legacy_data = legacy.get("data", {})
        legacy_source = legacy.get("source_type", "OCR")
        merged_field_sources = _build_field_sources(source_type, data)
        _merge_person_data(
            data,
            legacy_data,
            merged_field_sources,
            legacy_source,
            fill_missing_only=False,
        )
        if legacy_source == "QR":
            source_type = "QR"
            qr_text = legacy.get("qr_text", qr_text)
            id_source = "qr"
        if not id_12:
            id_12 = _clean_doc_number(data.get("so_giay_to", ""))
            if id_12 and id_source == "none":
                id_source = "mrz" if triage_state in {TRIAGE_STATE_BACK_NEW, TRIAGE_STATE_BACK_OLD} else "front_roi"
        raw_text = raw_text or legacy.get("raw_text", "")
        side = _merge_side(side, legacy.get("side", "unknown"))
        profile = _merge_profile(profile, legacy.get("profile", DOC_PROFILE_UNKNOWN))

    if id_12 and not (data.get("so_giay_to") or "").strip():
        data["so_giay_to"] = id_12
    if not id_12:
        id_12 = _clean_doc_number(data.get("so_giay_to", ""))
        if id_12 and id_source == "none":
            id_source = "front_roi" if side == "front" else "mrz"

    warnings = _collect_warnings(data, profile)
    field_sources = _build_field_sources(source_type, data)
    total_ms = _ms(perf_counter() - t_total)
    return {
        "data": data,
        "doc_type": crop.doc_type if crop.doc_type != "cccd" else "unknown",
        "profile": profile,
        "confidence": crop.confidence,
        "raw_text": raw_text,
        "_lines": [],
        "_qr": source_type == "QR",
        "qr_text": qr_text,
        "source_type": source_type,
        "side": side,
        "field_sources": field_sources,
        "warnings": warnings,
        "triage_state": triage_state,
        "orientation_angle": int(triage.get("orientation_angle", 0)),
        "face_detected": bool(triage.get("face_detected", False)),
        "qr_detected": bool(triage.get("qr_detected", False)),
        "mrz_score": float(triage.get("mrz_score", 0.0)),
        "id_12": id_12,
        "id_source": id_source,
        "fallback_legacy_used": fallback_legacy_used,
        "_timing": {
            "total_ms": total_ms,
            "triage_ms": triage.get("triage_ms", 0.0),
            "qr_detect_ms": triage.get("qr_detect_ms", 0.0),
            "qr_decode_ms": qr_decode_ms,
            "targeted_ocr_ms": targeted_ocr_ms,
            "group_lines_ms": group_lines_ms,
            "normalize_ms": normalize_ms,
            "id_extract_ms": id_extract_ms,
            "fallback_phase_ms": fallback_ms,
            "ocr_box_count": ocr_box_count,
            "line_count": line_count,
            "qr_detail": qr_timing,
            "angle_candidates": triage.get("angle_candidates", []),
        },
    }


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
            name_candidates.append((source_rank, front_rank, len(data["ho_ten"]), data["ho_ten"]))
        if (data.get("dia_chi") or "").strip() and profile in {DOC_PROFILE_FRONT_OLD, DOC_PROFILE_BACK_NEW}:
            addr_candidates.append((source_rank, len(data["dia_chi"]), data["dia_chi"]))
        if (data.get("ngay_cap") or "").strip():
            issue_candidates.append((2 if side == "back" else 1, source_rank, data["ngay_cap"]))

    if name_candidates:
        name_candidates.sort(reverse=True)
        merged_data["ho_ten"] = name_candidates[0][3]
    if addr_candidates:
        addr_candidates.sort(reverse=True)
        merged_data["dia_chi"] = addr_candidates[0][2]
    if issue_candidates:
        issue_candidates.sort(reverse=True)
        merged_data["ngay_cap"] = issue_candidates[0][2]

def _analyze_crop(
    crop: DocCrop,
    seeded_qr_text: str | None = None,
    allow_llm: bool = False,
    client_qr_failed: bool = False,
) -> dict:
    t_analyze = perf_counter()
    doc_type_from_model = crop.doc_type if crop.doc_type != "unknown" else "unknown"
    # Always allow backend QR rescue.
    # client_qr_failed is kept for telemetry/backward compatibility only.
    qr_timing: dict = {}
    qr_data, qr_text = _try_qr_data_from_crop(crop, seeded_qr_text, timing=qr_timing)

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
            "_timing": {
                "analyze_ms": _ms(perf_counter() - t_analyze),
                "qr_ms": qr_timing.get("total_ms", 0.0),
                "rapidocr_ms": 0.0,
                "group_lines_ms": 0.0,
                "normalize_ms": 0.0,
                "parse_cccd_ms": 0.0,
                "llm_parse_ms": 0.0,
                "llm_restore_ms": 0.0,
                "qr_detail": qr_timing,
                "ocr_box_count": 0,
                "line_count": 0,
            },
        }

    t_ocr = perf_counter()
    ocr_boxes = _rapidocr_recognize(crop.img)
    rapidocr_ms = _ms(perf_counter() - t_ocr)
    t_group = perf_counter()
    lines = _group_lines(ocr_boxes)
    group_lines_ms = _ms(perf_counter() - t_group)
    t_norm = perf_counter()
    normalized_lines = _normalize_ocr_lines(lines)
    normalize_ms = _ms(perf_counter() - t_norm)
    raw_text = _build_raw_text(lines)
    _print_rapidocr_raw_text(raw_text, context="single_crop")
    inferred_profile = _infer_doc_profile(normalized_lines, model_doc_type=doc_type_from_model)
    inferred_doc_type = _coarse_doc_type_from_profile(inferred_profile, model_doc_type=doc_type_from_model)
    fallback_doc_type = "unknown" if doc_type_from_model == "cccd" else doc_type_from_model
    final_doc_type = inferred_doc_type if inferred_doc_type != "unknown" else fallback_doc_type

    t_parse = perf_counter()
    data = _parse_cccd(lines, normalized_lines, None, inferred_profile)
    parse_cccd_ms = _ms(perf_counter() - t_parse)
    data.pop("ngay_het_han", None)

    llm_parse_ms = 0.0
    llm_restore_ms = 0.0
    if allow_llm and _needs_llm_fallback(data) and raw_text:
        loop_data = None
        t_llm_parse = perf_counter()
        try:
            loop_data = asyncio.run(_llm_parse_text(raw_text, inferred_profile))
        except Exception:
            loop_data = None
        llm_parse_ms = _ms(perf_counter() - t_llm_parse)
        if isinstance(loop_data, dict):
            data.update({k: v for k, v in loop_data.items() if v and k in data})

    if allow_llm and (data.get("ho_ten") or "").strip() and _count_vietnamese_diacritics(data.get("ho_ten", "")) < 2:
        restored = None
        t_llm_restore = perf_counter()
        try:
            restored = asyncio.run(_llm_restore_name_diacritics(data.get("ho_ten", ""), raw_text))
        except Exception:
            restored = None
        llm_restore_ms = _ms(perf_counter() - t_llm_restore)
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
        "_timing": {
            "analyze_ms": _ms(perf_counter() - t_analyze),
            "qr_ms": qr_timing.get("total_ms", 0.0),
            "rapidocr_ms": rapidocr_ms,
            "group_lines_ms": group_lines_ms,
            "normalize_ms": normalize_ms,
            "parse_cccd_ms": parse_cccd_ms,
            "llm_parse_ms": llm_parse_ms,
            "llm_restore_ms": llm_restore_ms,
            "qr_detail": qr_timing,
            "ocr_box_count": len(ocr_boxes),
            "line_count": len(lines),
        },
    }


def _local_ocr_from_bytes_triage_v2(
    file_bytes: bytes,
    qr_text: str | None = None,
    client_qr_failed: bool = False,
    trace_id: str | None = None,
) -> dict:
    batch_result = _local_ocr_batch_from_inputs_triage_v2(
        file_items=[{"index": 0, "filename": "single_upload.jpg", "bytes": file_bytes}],
        qr_texts=[qr_text or ""],
        client_qr_failed=[client_qr_failed],
        trace_id=trace_id,
    )
    persons = batch_result.get("persons") or []
    image_results = batch_result.get("image_results") or []
    if not persons:
        err = (batch_result.get("errors") or [{}])[0].get("error", "Khong nhan dien duoc noi dung")
        raise ValueError(err)

    best = persons[0]
    img0 = image_results[0] if image_results else {}
    profile = best.get("profile", DOC_PROFILE_UNKNOWN)
    raw_text = best.get("raw_text", "")
    data = dict(best.get("data", {}) or {})
    data.pop("profile", None)

    return {
        "persons": [{
            "type": "person",
            "data": {**data, "_raw_text": raw_text, "profile": profile},
            "_source": best.get("_source", "OCR (unknown)"),
            "source_type": best.get("source_type", "OCR"),
            "side": best.get("side", "unknown"),
            "profile": profile,
            "field_sources": best.get("field_sources", {}),
            "warnings": best.get("warnings", []),
            "triage_state": img0.get("triage_state", TRIAGE_STATE_UNKNOWN),
            "orientation_angle": img0.get("orientation_angle", 0),
            "face_detected": img0.get("face_detected", False),
            "qr_detected": img0.get("qr_detected", False),
            "mrz_score": img0.get("mrz_score", 0.0),
            "id_12": img0.get("id_12", ""),
            "id_source": img0.get("id_source", "none"),
            "fallback_legacy_used": img0.get("fallback_legacy_used", False),
        }],
        "properties": [],
        "marriages": [],
        "raw_text": raw_text,
        "doc_type": img0.get("doc_type", "unknown"),
        "timing_ms": (batch_result.get("summary") or {}).get("timing_ms", {}),
    }


def local_ocr_from_bytes(
    file_bytes: bytes,
    qr_text: str | None = None,
    client_qr_failed: bool = False,
    trace_id: str | None = None,
) -> dict:
    if LOCAL_OCR_TRIAGE_V2:
        try:
            return _local_ocr_from_bytes_triage_v2(
                file_bytes=file_bytes,
                qr_text=qr_text,
                client_qr_failed=client_qr_failed,
                trace_id=trace_id,
            )
        except Exception as e:
            if not LOCAL_OCR_TRIAGE_FALLBACK_LEGACY:
                raise
            _log_timing(
                "single_v2_failed_fallback_legacy",
                level="warning",
                trace_id=trace_id,
                error=str(e),
            )

    t_total = perf_counter()
    _log_timing(
        "single_start",
        trace_id=trace_id,
        bytes=len(file_bytes or b""),
        qr_seeded=bool((qr_text or "").strip()),
        client_qr_failed=bool(client_qr_failed),
    )
    _ensure_local_ocr_dependencies()
    t_decode = perf_counter()
    img_np = np.frombuffer(file_bytes, np.uint8)
    img_bgr = cv2.imdecode(img_np, cv2.IMREAD_COLOR)
    decode_ms = _ms(perf_counter() - t_decode)
    if img_bgr is None:
        raise ValueError("Khong doc duoc anh")

    h, w = img_bgr.shape[:2]
    t_pre = perf_counter()
    img_bgr = _preprocess(img_bgr)
    preprocess_ms = _ms(perf_counter() - t_pre)
    t_detect = perf_counter()
    crops = _detect_documents(img_bgr)
    detect_ms = _ms(perf_counter() - t_detect)

    candidates = []
    seeded_qr = qr_text
    for crop_idx, crop in enumerate(crops):
        t_crop = perf_counter()
        analyzed = _analyze_crop(
            crop,
            seeded_qr_text=seeded_qr,
            allow_llm=False,
            client_qr_failed=client_qr_failed,
        )
        candidates.append(analyzed)
        stage_timing = analyzed.get("_timing", {})
        crop_total_ms = _ms(perf_counter() - t_crop)
        _log_timing(
            "single_crop",
            trace_id=trace_id,
            crop_index=crop_idx,
            source_type=analyzed.get("source_type"),
            profile=analyzed.get("profile"),
            side=analyzed.get("side"),
            qr_ms=stage_timing.get("qr_ms", 0.0),
            rapidocr_ms=stage_timing.get("rapidocr_ms", 0.0),
            parse_cccd_ms=stage_timing.get("parse_cccd_ms", 0.0),
            analyze_ms=stage_timing.get("analyze_ms", 0.0),
            crop_total_ms=crop_total_ms,
            ocr_box_count=stage_timing.get("ocr_box_count", 0),
            line_count=stage_timing.get("line_count", 0),
        )
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
    best_timing = best.get("_timing", {})
    total_ms = _ms(perf_counter() - t_total)
    level = "warning" if total_ms >= LOCAL_OCR_TIMING_SLOW_MS else "info"
    _log_timing(
        "single_done",
        level=level,
        trace_id=trace_id,
        total_ms=total_ms,
        decode_ms=decode_ms,
        preprocess_ms=preprocess_ms,
        detect_ms=detect_ms,
        crop_count=len(crops),
        winner_source=best.get("source_type"),
        winner_profile=profile,
        winner_side=best.get("side"),
        winner_qr_ms=best_timing.get("qr_ms", 0.0),
        winner_rapidocr_ms=best_timing.get("rapidocr_ms", 0.0),
        winner_parse_cccd_ms=best_timing.get("parse_cccd_ms", 0.0),
        warnings=warnings,
    )

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
        "timing_ms": {
            "total_ms": total_ms,
            "decode_ms": decode_ms,
            "preprocess_ms": preprocess_ms,
            "detect_ms": detect_ms,
            "winner_qr_ms": best_timing.get("qr_ms", 0.0),
            "winner_rapidocr_ms": best_timing.get("rapidocr_ms", 0.0),
            "winner_parse_cccd_ms": best_timing.get("parse_cccd_ms", 0.0),
        },
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
    return _rapidocr_runtime_label or "RapidOCR (CPU)"


# ---------------------- Endpoint ----------------------
@router.post("/analyze-local")
async def analyze_images_local(files: List[UploadFile] = File(...)):
    """
    OCR offline with pipeline: preprocess -> QR -> RapidOCR -> regex.
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
