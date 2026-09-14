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
    PocError,
)
from .policy import classify_source


class OcrClient(Protocol):
    """Reserved boundary for the explicitly policy-gated OCR task."""


def convert_path(
    path: Path,
    *,
    allow_cloud: bool,
    converter: Callable[[Path], str] | None = None,
    ocr: OcrClient | None = None,
) -> ConversionEnvelope:
    """Convert a local-route source into a provenance-aware POC envelope.

    ``ocr`` and ``allow_cloud`` are deliberately unused on the local route: local
    documents must never contact a cloud provider.  OCR candidates remain for
    the later, separately policy-gated adapter task.
    """

    source_bytes = path.read_bytes()
    envelope = ConversionEnvelope.for_source(path, source_bytes)
    route = classify_source(path, source_bytes)
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


def _convert_with_markitdown(path: Path) -> str:
    """Convert through MarkItDown without enabling unclassified plugins."""

    from markitdown import MarkItDown

    result = MarkItDown(enable_plugins=False).convert(path)
    return result.markdown
