from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Protocol

from markitdown import MarkItDown

from .models import Content, Converter, ConversionEnvelope, PocError, Segment
from .policy import classify_source, decide_ocr


class OcrClient(Protocol):
    def extract(self, image_bytes: bytes, mime_type: str) -> str:
        """Return OCR text for an already-approved image input."""


def _markitdown_convert(path: Path) -> str:
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

    envelope.errors.append(
        PocError(code="ocr_not_implemented", message="OCR adapter is Task 4", retryable=False)
    )
    return envelope
