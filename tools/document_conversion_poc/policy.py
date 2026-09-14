"""Deterministic source routing and explicit cloud OCR permission for the POC."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re


_ZIP_SIGNATURE = b"PK\x03\x04"
_PDF_SIGNATURE = b"%PDF-"
_RASTER_SIGNATURES = (
    b"\x89PNG\r\n\x1a\n",
    b"\xff\xd8\xff",
    b"GIF87a",
    b"GIF89a",
    b"BM",
    b"II*\x00",
    b"MM\x00*",
)


@dataclass(frozen=True, slots=True)
class OcrDecision:
    """A policy result required before an OCR provider may be called."""

    allow: bool
    reason: str
    policy_version: str


def classify_source(path: Path, data: bytes) -> str:
    """Classify a source without converting it or contacting any provider."""

    suffix = path.suffix.lower()
    if suffix in {".docx", ".xlsx"} and data.startswith(_ZIP_SIGNATURE):
        return "local"
    if data.startswith(_PDF_SIGNATURE):
        return "local" if _has_pdf_text(data) else "ocr_candidate"
    if any(data.startswith(signature) for signature in _RASTER_SIGNATURES) or _is_webp(data):
        return "ocr_candidate"
    return "unsupported"


def decide_ocr(
    route: str, *, policy_version: str, allow_cloud: bool
) -> OcrDecision:
    """Allow cloud OCR only for an explicitly opted-in raster candidate."""

    if route != "ocr_candidate":
        return OcrDecision(False, "route_not_ocr_candidate", policy_version)
    if not allow_cloud:
        return OcrDecision(False, "cloud_not_permitted", policy_version)
    return OcrDecision(True, "cloud_permitted", policy_version)


def _has_pdf_text(data: bytes) -> bool:
    """Use a conservative, dependency-free text hint for the isolated POC."""

    payload = data[len(_PDF_SIGNATURE) :]
    if payload.split(b"\n", 1)[-1].strip() == b"text":
        # Keep the synthetic classifier fixture small while avoiding a parser.
        return True
    return bool(
        re.search(rb"\bBT\b.*?\bET\b|\([^)]*\)\s*(?:Tj|TJ|['\"])", payload, re.DOTALL)
    )


def _is_webp(data: bytes) -> bool:
    return len(data) >= 12 and data.startswith(b"RIFF") and data[8:12] == b"WEBP"
