from __future__ import annotations

from collections.abc import Callable
import hashlib
from pathlib import Path
from time import perf_counter
from typing import Protocol

import fitz

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


def _ocr_inputs(path: Path, source_bytes: bytes) -> list[tuple[bytes, str, dict[str, int] | None]]:
    """Render scanned PDF pages; never send PDF bytes as an image data URL."""
    if path.suffix.lower() != ".pdf":
        return [(source_bytes, "image/png" if path.suffix.lower() == ".png" else "image/jpeg", None)]
    document = fitz.open(stream=source_bytes, filetype="pdf")
    try:
        inputs = []
        for page_number, page in enumerate(document, start=1):
            pixmap = page.get_pixmap(matrix=fitz.Matrix(2, 2), alpha=False)
            inputs.append((pixmap.tobytes("png"), "image/png", {"page": page_number}))
        return inputs
    finally:
        document.close()


def _markitdown_convert(path: Path) -> str:
    if MarkItDown is None:
        raise RuntimeError(
            "markitdown is not installed; install requirements-poc-markitdown.txt"
        )
    result = MarkItDown(enable_plugins=False).convert(str(path))
    return result.markdown


def _local_pdf_page_segments(source_bytes: bytes) -> list[Segment]:
    """Return page-addressable plain-text segments without changing Markdown content."""
    document = fitz.open(stream=source_bytes, filetype="pdf")
    try:
        return [
            Segment(
                segment_id=f"page-{page_number}",
                text=page.get_text("text"),
                source_ref={"page": page_number},
            )
            for page_number, page in enumerate(document, start=1)
        ]
    finally:
        document.close()


def convert_path(
    path: Path,
    *,
    allow_cloud: bool,
    converter: Callable[[Path], str] = _markitdown_convert,
    ocr: OcrClient | None = None,
    max_retries: int = 1,
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
        if path.suffix.lower() == ".pdf":
            try:
                segments = _local_pdf_page_segments(source_bytes)
            except Exception:
                segments = []
            if segments:
                envelope.segments.extend(segments)
                return envelope
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

    try:
        ocr_inputs = _ocr_inputs(path, source_bytes)
    except Exception as exc:
        envelope.errors.append(PocError(code="pdf_render_failed", message=str(exc), retryable=False))
        return envelope

    texts: list[str] = []
    policy_version = decision.policy_version
    for index, (image_bytes, mime_type, source_ref) in enumerate(ocr_inputs, start=1):
        input_hash = hashlib.sha256(image_bytes).hexdigest()
        for attempt in range(1, max(0, max_retries) + 2):
            started_at = perf_counter()
            try:
                text = ocr.extract(image_bytes, mime_type)
            except OcrRequestError as exc:
                duration_ms = round((perf_counter() - started_at) * 1000)
                envelope.ocr_calls.append(OcrCall(
                    provider=getattr(ocr, "provider", "injected-ocr"), model=getattr(ocr, "model", "unknown"),
                    input_hash=input_hash, status="failed", duration_ms=duration_ms, error=str(exc),
                    policy_version=policy_version, allow_reason=decision.reason, attempt=attempt,
                    source_ref=source_ref,
                ))
                if exc.retryable and attempt <= max_retries:
                    continue
                envelope.errors.append(PocError(code="ocr_request_failed", message=str(exc), retryable=exc.retryable))
                break
            else:
                duration_ms = round((perf_counter() - started_at) * 1000)
                texts.append(text)
                envelope.segments.append(Segment(segment_id=f"ocr-{index}", text=text, source_ref=source_ref))
                envelope.ocr_calls.append(OcrCall(
                    provider=getattr(ocr, "provider", "injected-ocr"), model=getattr(ocr, "model", "unknown"),
                    input_hash=input_hash, status="completed", duration_ms=duration_ms,
                    policy_version=policy_version, allow_reason=decision.reason, attempt=attempt,
                    source_ref=source_ref,
                ))
                break

    envelope.content = Content(format="text", value="\n".join(texts))
    if any(segment.source_ref is not None for segment in envelope.segments):
        envelope.warnings.append("provenance_partial")
    else:
        envelope.warnings.append("provenance_unavailable")
    return envelope
