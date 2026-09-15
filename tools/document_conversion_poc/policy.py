from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import fitz

Route = Literal["local", "ocr_candidate", "legacy_doc_external", "unsupported"]


@dataclass(frozen=True)
class OcrDecision:
    allow: bool
    reason: str
    policy_version: str


def classify_source(path: Path, data: bytes) -> Route:
    """Classify only the formats the POC is allowed to handle.

    This intentionally makes no conversion decision from a filename alone: ZIP
    signatures are required for Office files, PDF magic is required for PDF and
    raster magic is required for image OCR candidates.
    """

    suffix = path.suffix.lower()
    if suffix in {".docx", ".xlsx"} and data.startswith(b"PK\x03\x04"):
        return "local"
    if suffix == ".pdf" and data.startswith(b"%PDF-"):
        try:
            document = fitz.open(stream=data, filetype="pdf")
            try:
                has_text = any(page.get_text("text").strip() for page in document)
            finally:
                document.close()
        # PyMuPDF exposes version-specific parser exceptions (for example
        # FzErrorFormat). This boundary handles only untrusted PDF parsing;
        # malformed input must not abort a batch.
        except Exception:
            return "unsupported"
        return "local" if has_text else "ocr_candidate"
    if suffix == ".png" and data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "ocr_candidate"
    if suffix in {".jpg", ".jpeg"} and data.startswith(b"\xff\xd8\xff"):
        return "ocr_candidate"
    if suffix == ".doc" and data.startswith(b"\xd0\xcf\x11\xe0"):
        return "legacy_doc_external"
    return "unsupported"


def decide_ocr(
    route: Route,
    *,
    policy_version: str,
    allow_cloud: bool,
) -> OcrDecision:
    if route != "ocr_candidate":
        return OcrDecision(
            allow=False,
            reason="route_not_ocr_candidate",
            policy_version=policy_version,
        )
    if not allow_cloud:
        return OcrDecision(
            allow=False,
            reason="cloud_not_authorized",
            policy_version=policy_version,
        )
    return OcrDecision(
        allow=True,
        reason="explicit_cloud_authorization",
        policy_version=policy_version,
    )
