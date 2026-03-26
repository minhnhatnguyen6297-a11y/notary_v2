"""
Local OCR (YOLO + EasyOCR + VietOCR):
1) Tien xu ly anh (Python/OpenCV)
2) YOLO cat anh + nhan dien loai giay to (mat truoc/mat sau)
3) Quet QR neu ro (uu tien QR). Neu QR khong ro -> tiep tuc OCR
4) EasyOCR detect text box
5) VietOCR nhan dang text
6) Regex loc truong thong tin can thiet
"""

from __future__ import annotations

import io
import asyncio
import json
import uuid
import os
import re
import traceback
from datetime import datetime
from dataclasses import dataclass
from typing import List, Optional, Tuple

import cv2
import numpy as np
from PIL import Image
from fastapi import APIRouter, UploadFile, File, HTTPException, Form, Body

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

VIETOCR_WEIGHTS = os.getenv("LOCAL_OCR_VIETOCR_WEIGHTS", "").strip()
VIETOCR_DEVICE = os.getenv("LOCAL_OCR_VIETOCR_DEVICE", "cpu").strip()

EASYOCR_LANGS = os.getenv("LOCAL_OCR_EASYOCR_LANGS", "vi,en")

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


# ---------------------- Lazy-loaded models ----------------------
_yolo_model = None
_easyocr_reader = None
_vietocr_predictor = None


def _get_yolo_model():
    global _yolo_model
    if _yolo_model is not None:
        return _yolo_model
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


def _get_easyocr_reader():
    global _easyocr_reader
    if _easyocr_reader is not None:
        return _easyocr_reader
    try:
        import easyocr
        langs = [s.strip() for s in EASYOCR_LANGS.split(",") if s.strip()]
        _easyocr_reader = easyocr.Reader(langs or ["vi", "en"], gpu=False, verbose=False)
    except ImportError:
        raise HTTPException(
            status_code=500,
            detail="Chua cai EasyOCR. Hay chay: pip install easyocr",
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Khong the khoi dong EasyOCR: {e}")
    return _easyocr_reader


def _get_vietocr_predictor():
    global _vietocr_predictor
    if _vietocr_predictor is not None:
        return _vietocr_predictor
    try:
        from vietocr.tool.predictor import Predictor
        from vietocr.tool.config import Cfg
        cfg = Cfg.load_config_from_name("vgg_transformer")
        cfg["device"] = VIETOCR_DEVICE or "cpu"
        if VIETOCR_WEIGHTS:
            cfg["weights"] = VIETOCR_WEIGHTS
        _vietocr_predictor = Predictor(cfg)
    except ImportError:
        raise HTTPException(
            status_code=500,
            detail="Chua cai VietOCR. Hay chay: pip install vietocr",
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Khong the khoi dong VietOCR: {e}")
    return _vietocr_predictor


def warmup_local_ocr():
    """Warmup for startup (optional)."""
    try:
        _get_easyocr_reader()
    except Exception:
        pass
    try:
        _get_vietocr_predictor()
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


def _easyocr_detect_boxes(img_bgr: np.ndarray) -> List[Tuple[np.ndarray, float]]:
    """Return list of (box, score). box: 4 points."""
    reader = _get_easyocr_reader()
    boxes = []
    try:
        results = reader.readtext(img_bgr, detail=1)
        for (box, _text, score) in results:
            if score >= MIN_BOX_SCORE:
                boxes.append((np.array(box, dtype=np.float32), float(score)))
    except Exception:
        pass
    return boxes


def _crop_from_box(img_bgr: np.ndarray, box: np.ndarray) -> Image.Image:
    xs = box[:, 0]
    ys = box[:, 1]
    x1, x2 = int(max(xs.min(), 0)), int(min(xs.max(), img_bgr.shape[1] - 1))
    y1, y2 = int(max(ys.min(), 0)), int(min(ys.max(), img_bgr.shape[0] - 1))
    crop = img_bgr[y1:y2, x1:x2]
    if crop.size == 0:
        return None
    crop_rgb = cv2.cvtColor(crop, cv2.COLOR_BGR2RGB)
    return Image.fromarray(crop_rgb)


def _vietocr_recognize(img_bgr: np.ndarray) -> List[dict]:
    predictor = _get_vietocr_predictor()
    boxes = _easyocr_detect_boxes(img_bgr)
    results = []
    for box, score in boxes:
        crop_img = _crop_from_box(img_bgr, box)
        if crop_img is None:
            continue
        try:
            text = predictor.predict(crop_img)
        except Exception:
            text = ""
        if text:
            results.append({"text": text.strip(), "box": box, "score": score})
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
    full = " ".join(lines)
    if m := re.search(r"\b(\d{12})\b", full):
        return m.group(1)
    # Fallback: remove non-digits and scan
    digits = re.sub(r"\D", "", full)
    if len(digits) >= 12:
        return digits[:12]
    return ""


def _extract_name(lines: List[str]) -> str:
    for i, ln in enumerate(lines):
        if re.search(r"h[oọ]\s*v[aà]\s*t[eê]n", ln, re.IGNORECASE):
            if i + 1 < len(lines):
                return lines[i + 1].strip().upper()
    # Heuristic: longest line without digits
    best = ""
    for ln in lines:
        if re.search(r"\d", ln):
            continue
        if len(ln) > len(best) and len(ln.split()) >= 2:
            best = ln
    return best.upper()


def _extract_gender(lines: List[str]) -> str:
    full = " ".join(lines).lower()
    if "nữ" in full or "nu" in full:
        return "Nữ"
    if "nam" in full:
        return "Nam"
    return ""


def _extract_address(lines: List[str]) -> str:
    stop_pat = re.compile(r"(quoc\s*tich|quốc\s*tịch|gioi\s*tinh|giới\s*tính|ngay\s*sinh|ngày\s*sinh|ngay\s*cap|ngày\s*cấp|co\s*gia\s*tri|có\s*giá\s*trị)", re.IGNORECASE)
    for i, ln in enumerate(lines):
        if re.search(r"n[oơ]i\s*(th[uư]ờ?ng\s*trú|c[uư]\s*trú)", ln, re.IGNORECASE):
            parts = []
            if ":" in ln:
                parts.append(ln.split(":", 1)[1].strip())
            for j in range(i + 1, len(lines)):
                if stop_pat.search(lines[j]):
                    break
                parts.append(lines[j])
            return ", ".join([p for p in parts if p])
    return ""


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

    data["ngay_cap"] = _find_date_after_label(lines, r"ngay\s*cap|ngày\s*cấp") or data["ngay_cap"]
    data["ngay_het_han"] = _find_date_after_label(lines, r"(co\s*gia\s*tri\s*den|có\s*giá\s*trị\s*đến|ngay\s*het\s*han|ngày\s*hết\s*hạn)") or data["ngay_het_han"]

    # Fallback: if doc_type = back and no ngay_cap, use 2nd date
    if doc_type == "cccd_back" and not data["ngay_cap"]:
        dates = re.findall(r"\d{2}/\d{2}/\d{4}", " ".join(lines).replace("-", "/"))
        if len(dates) >= 2:
            data["ngay_cap"] = dates[1]
    return data


def _build_raw_text(lines: List[str]) -> str:
    return "\n".join([ln for ln in lines if ln])


def local_ocr_from_bytes(file_bytes: bytes, qr_text: str | None = None) -> dict:
    img_np = np.frombuffer(file_bytes, np.uint8)
    img_bgr = cv2.imdecode(img_np, cv2.IMREAD_COLOR)
    if img_bgr is None:
        raise ValueError("Khong doc duoc anh")

    img_bgr = _preprocess(img_bgr)
    crops = _detect_documents(img_bgr)

    candidates = []
    for crop in crops:
        qr_data = parse_cccd_qr(qr_text) if qr_text else None
        if not qr_data:
            try:
                pil_img = Image.fromarray(cv2.cvtColor(crop.img, cv2.COLOR_BGR2RGB))
                buf = io.BytesIO()
                pil_img.save(buf, format="PNG")
                qr_detected = try_decode_qr(buf.getvalue())
                qr_data = parse_cccd_qr(qr_detected) if qr_detected else None
            except Exception:
                qr_data = None

        ocr_boxes = _vietocr_recognize(crop.img)
        lines = _group_lines(ocr_boxes)
        raw_text = _build_raw_text(lines)
        data = _parse_cccd(lines, qr_data, crop.doc_type)

        candidates.append({
            "data": data,
            "doc_type": crop.doc_type,
            "confidence": crop.confidence,
            "raw_text": raw_text,
            "_qr": bool(qr_data),
        })

    best = None
    for c in candidates:
        score = _score_person(c["data"]) + (3 if c["_qr"] else 0)
        if best is None or score > best["score"]:
            best = {**c, "score": score}

    if not best:
        raise ValueError("Khong nhan dien duoc noi dung")

    data = best["data"]
    raw_text = best["raw_text"]

    # Text-only LLM fallback nếu thiếu dữ liệu quan trọng
    if _needs_llm_fallback(data) and raw_text:
        loop_data = None
        try:
            loop_data = asyncio.run(_llm_parse_text(raw_text, best["doc_type"]))
        except Exception:
            loop_data = None
        if isinstance(loop_data, dict):
            data.update({k: v for k, v in loop_data.items() if v and k in data})

    return {
        "persons": [{
            "type": "person",
            "data": {**data, "_raw_text": raw_text},
            "_source": f"Local OCR ({best['doc_type']})",
        }],
        "properties": [],
        "marriages": [],
        "raw_text": raw_text,
        "doc_type": best["doc_type"],
    }


def _score_person(data: dict) -> int:
    keys = ["so_giay_to", "ho_ten", "ngay_sinh", "gioi_tinh", "dia_chi", "ngay_cap"]
    return sum(1 for k in keys if (data.get(k) or "").strip())


# ---------------------- Endpoint ----------------------
@router.post("/analyze-local")
async def analyze_images_local(files: List[UploadFile] = File(...)):
    """
    OCR offline with pipeline: preprocess -> YOLO -> QR -> EasyOCR -> VietOCR -> regex.
    Return same format as /api/ocr/analyze for frontend compatibility.
    """
    if not files:
        raise HTTPException(status_code=400, detail="Chua co anh nao duoc gui len")

    persons = []
    errors = []

    # Ensure required models
    _get_easyocr_reader()
    _get_vietocr_predictor()

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
                # QR scan
                qr_text = None
                try:
                    pil_img = Image.fromarray(cv2.cvtColor(crop.img, cv2.COLOR_BGR2RGB))
                    buf = io.BytesIO()
                    pil_img.save(buf, format="PNG")
                    qr_text = try_decode_qr(buf.getvalue())
                except Exception:
                    qr_text = None
                qr_data = parse_cccd_qr(qr_text) if qr_text else None

                # OCR lines
                ocr_boxes = _vietocr_recognize(crop.img)
                lines = _group_lines(ocr_boxes)
                data = _parse_cccd(lines, qr_data, crop.doc_type)

                candidates.append({
                    "data": data,
                    "doc_type": crop.doc_type,
                    "confidence": crop.confidence,
                    "_lines": lines,
                    "_qr": bool(qr_data),
                })

            # pick best candidate
            best = None
            for c in candidates:
                score = _score_person(c["data"]) + (3 if c["_qr"] else 0)
                if best is None or score > best["score"]:
                    best = {**c, "score": score}
            if best:
                data = best["data"]
                persons.append({
                    "type": "person",
                    "data": data,
                    "_source": f"Local OCR ({best['doc_type']})",
                    "filename": f.filename,
                    "_qr": best["_qr"],
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
            "local_engine": "YOLO + EasyOCR + VietOCR",
        },
    }


@router.post("/local/submit")
async def submit_local_job(file: UploadFile = File(...), qr_text: str | None = Form(None)):
    if not file:
        raise HTTPException(status_code=400, detail="Chua co file")

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
    process_ocr_job.delay(job_id, qr_text)
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
