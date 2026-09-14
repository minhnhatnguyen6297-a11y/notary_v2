"""Local MarkItDown conversion for the isolated document-conversion POC."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from typing import Callable, Protocol

from .models import (
    ContentRecord,
    ConversionEnvelope,
    ConversionSegment,
    ConverterRecord,
    OcrCall,
    PocError,
)
from .policy import classify_source, decide_ocr
from .qwen_compatible import QwenCompatibleOcrError


class OcrClient(Protocol):
    """Explicitly policy-gated OCR boundary for raster candidates."""

    def extract(self, image_bytes: bytes, mime_type: str) -> str:
        """Extract text without exposing provider transport to the router."""


def convert_path(
    path: Path,
    *,
    allow_cloud: bool,
    converter: Callable[[Path], str] | None = None,
    ocr: OcrClient | None = None,
) -> ConversionEnvelope:
    """Convert a source through a local route or an explicit OCR allow decision."""

    source_bytes = path.read_bytes()
    envelope = ConversionEnvelope.for_source(path, source_bytes)
    route = classify_source(path, source_bytes)
    if route == "ocr_candidate":
        return _convert_ocr_candidate(
            envelope,
            source_bytes=source_bytes,
            allow_cloud=allow_cloud,
            ocr=ocr,
        )
    if route != "local":
        return replace(
            envelope,
            errors=(
                PocError(
                    code="route_not_supported",
                    message=f"Route {route!r} is not handled by local conversion.",
                ),
            ),
        )

    active_converter = converter or _convert_with_markitdown
    try:
        text = active_converter(path)
    except Exception as exc:
        return replace(
            envelope,
            converter=ConverterRecord("markitdown"),
            errors=(
                PocError(
                    code="local_conversion_failed",
                    message=f"Local conversion failed: {type(exc).__name__}",
                ),
            ),
        )

    return replace(
        envelope,
        converter=ConverterRecord("markitdown"),
        content_record=ContentRecord(text),
        segments=(ConversionSegment(text=text, source_ref=None),),
        warnings=("provenance_unavailable",),
    )


def _convert_ocr_candidate(
    envelope: ConversionEnvelope,
    *,
    source_bytes: bytes,
    allow_cloud: bool,
    ocr: OcrClient | None,
) -> ConversionEnvelope:
    decision = decide_ocr(
        "ocr_candidate", policy_version="poc-1", allow_cloud=allow_cloud
    )
    if not decision.allow:
        return replace(
            envelope,
            errors=(
                PocError(code="ocr_not_permitted", message=decision.reason),
            ),
        )
    if ocr is None:
        return replace(
            envelope,
            errors=(
                PocError(
                    code="ocr_client_unavailable",
                    message="No OCR client was configured for an allowed request.",
                ),
            ),
        )

    mime_type = _raster_mime_type(source_bytes)
    if mime_type is None:
        # This adapter sends image_url data URLs.  A PDF (or any other
        # non-raster OCR candidate) must not be sent with an invalid MIME type.
        return replace(
            envelope,
            errors=(
                PocError(
                    code="ocr_input_not_supported",
                    message="OCR adapter accepts raster image inputs only.",
                ),
            ),
        )

    try:
        text = ocr.extract(source_bytes, mime_type)
    except QwenCompatibleOcrError as exc:
        return replace(
            envelope,
            converter=ConverterRecord("qwen_compatible"),
            ocr_calls=(exc.ocr_call,),
            errors=(exc.error,),
        )
    except Exception:
        # This fallback keeps alternate injected test adapters from leaking an
        # exception's potentially sensitive request/response text into a report.
        return replace(
            envelope,
            converter=ConverterRecord("qwen_compatible"),
            errors=(
                PocError(
                    code="ocr_request_failed",
                    message="OCR request failed.",
                    retryable=False,
                ),
            ),
        )

    ocr_call = getattr(ocr, "last_ocr_call", None)
    if not isinstance(ocr_call, OcrCall):
        ocr_call = OcrCall(
            provider="injected_ocr",
            status="completed",
            input_sha256=envelope.source.sha256,
        )
    return replace(
        envelope,
        converter=ConverterRecord("qwen_compatible"),
        content_record=ContentRecord(text),
        segments=(ConversionSegment(text=text, source_ref=None),),
        ocr_calls=(ocr_call,),
        warnings=("provenance_unavailable",),
    )


def _raster_mime_type(data: bytes) -> str | None:
    """Return an image MIME validated by content, never by filename suffix."""

    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if data.startswith((b"GIF87a", b"GIF89a")):
        return "image/gif"
    if data.startswith(b"BM"):
        return "image/bmp"
    if data.startswith((b"II*\x00", b"MM\x00*")):
        return "image/tiff"
    if len(data) >= 12 and data.startswith(b"RIFF") and data[8:12] == b"WEBP":
        return "image/webp"
    return None


def _convert_with_markitdown(path: Path) -> str:
    """Convert through MarkItDown without enabling unclassified plugins."""

    from markitdown import MarkItDown

    result = MarkItDown(enable_plugins=False).convert(path)
    return result.markdown
