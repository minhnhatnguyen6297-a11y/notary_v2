from __future__ import annotations

from collections.abc import Callable
import hashlib
from pathlib import Path
from time import perf_counter
from typing import Protocol

try:
    from markitdown import MarkItDown
except ImportError:  # Optional POC dependency; production imports stay usable.
    MarkItDown = None  # type: ignore[assignment,misc]

from .models import Content, Converter, ConversionEnvelope, OcrCall, PocError, Segment
from .policy import classify_source, decide_ocr
from .qwen_compatible import OcrRequestError


class OcrClient(Protocol):
    def extract(self, image_bytes: bytes, mime_type: str) -> str:
        """Return OCR text for an already-approved image input."""


def _markitdown_convert(path: Path) -> str:
    if MarkItDown is None:
        raise RuntimeError(
            "markitdown is not installed; install requirements-poc-markitdown.txt"
        )
    result = MarkItDown(enable_plugins=False).convert(str(path))
    return result.markdown


def convert_path(
    path: Path,
    *,
    allow_cloud: bool,
    converter: Callable[[Path], str] = _markitdown_convert,
    ocr: OcrClient | None = None,
) -> ConversionEnvelope:
    source_bytes = path.read_bytes()
    envelope = ConversionEnvelope.for_source(path, source_bytes)
    route = classify_source(path, source_bytes)
    envelope.converter = Converter(
        name="markitdown" if converter is _markitdown_convert else "injected-test-converter",
        version="0.1.7" if converter is _markitdown_convert else "test",
        config_fingerprint="plugins-disabled",
    )

    if route == "local":
        try:
            text = converter(path)
        except Exception as exc:
            envelope.errors.append(
                PocError(code="local_conversion_failed", message=str(exc), retryable=False)
            )
            return envelope
        envelope.content = Content(format="markdown", value=text)
        envelope.segments.append(Segment(segment_id="segment-1", text=text, source_ref=None))
        envelope.warnings.append("provenance_unavailable")
        return envelope

    if route == "legacy_doc_external":
        envelope.warnings.append("legacy_doc_requires_upload_lab_ifilter")
        return envelope

    decision = decide_ocr(route, policy_version="poc-1", allow_cloud=allow_cloud)
    if not decision.allow:
        envelope.warnings.append(decision.reason)
        return envelope

    if ocr is None:
        envelope.warnings.append("approved_ocr_client_not_configured")
        return envelope

    started_at = perf_counter()
    input_hash = hashlib.sha256(source_bytes).hexdigest()
    try:
        text = ocr.extract(source_bytes, envelope.source.media_type or "application/octet-stream")
    except OcrRequestError as exc:
        duration_ms = round((perf_counter() - started_at) * 1000)
        envelope.ocr_calls.append(
            OcrCall(
                provider=getattr(ocr, "provider", "injected-ocr"),
                model=getattr(ocr, "model", "unknown"),
                input_hash=input_hash,
                status="failed",
                duration_ms=duration_ms,
                error=str(exc),
            )
        )
        envelope.errors.append(
            PocError(code="ocr_request_failed", message=str(exc), retryable=exc.retryable)
        )
        return envelope

    duration_ms = round((perf_counter() - started_at) * 1000)
    envelope.content = Content(format="text", value=text)
    envelope.segments.append(Segment(segment_id="ocr-1", text=text, source_ref=None))
    envelope.ocr_calls.append(
        OcrCall(
            provider=getattr(ocr, "provider", "injected-ocr"),
            model=getattr(ocr, "model", "unknown"),
            input_hash=input_hash,
            status="completed",
            duration_ms=duration_ms,
        )
    )
    envelope.warnings.append("provenance_unavailable")
    return envelope
