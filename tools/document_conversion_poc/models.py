"""JSON-safe, immutable records for the document-conversion POC."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from hashlib import sha256
import mimetypes
from pathlib import Path


CONTRACT_VERSION = "v0.experimental"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


@dataclass(frozen=True, slots=True)
class SourceRecord:
    path: str
    sha256: str
    size_bytes: int
    mime_hint: str
    captured_at: str

    def to_dict(self) -> dict[str, object]:
        return {
            "path": self.path,
            "sha256": self.sha256,
            "size_bytes": self.size_bytes,
            "mime_hint": self.mime_hint,
            "captured_at": self.captured_at,
        }


@dataclass(frozen=True, slots=True)
class ConverterRecord:
    name: str
    version: str | None = None

    def to_dict(self) -> dict[str, object]:
        return {"name": self.name, "version": self.version}


@dataclass(frozen=True, slots=True)
class ContentRecord:
    text: str
    mime_type: str = "text/markdown"

    def to_dict(self) -> dict[str, str]:
        return {"text": self.text, "mime_type": self.mime_type}


@dataclass(frozen=True, slots=True)
class ConversionSegment:
    text: str
    source_ref: str | None = None

    def to_dict(self) -> dict[str, str | None]:
        return {"text": self.text, "source_ref": self.source_ref}


@dataclass(frozen=True, slots=True)
class OcrCall:
    provider: str
    status: str
    input_sha256: str
    duration_ms: int | None = None

    def to_dict(self) -> dict[str, str | int | None]:
        return {
            "provider": self.provider,
            "status": self.status,
            "input_sha256": self.input_sha256,
            "duration_ms": self.duration_ms,
        }


@dataclass(frozen=True, slots=True)
class PocWarning:
    code: str
    detail: str | None = None

    def to_dict(self) -> dict[str, str | None]:
        return {"code": self.code, "detail": self.detail}


@dataclass(frozen=True, slots=True)
class PocError:
    code: str
    message: str
    retryable: bool = False

    def to_dict(self) -> dict[str, str | bool]:
        return {
            "code": self.code,
            "message": self.message,
            "retryable": self.retryable,
        }


@dataclass(frozen=True, slots=True)
class ConversionEnvelope:
    source: SourceRecord
    converter: ConverterRecord = field(default_factory=lambda: ConverterRecord("unassigned"))
    content_record: ContentRecord = field(default_factory=lambda: ContentRecord(""))
    segments: tuple[ConversionSegment, ...] = ()
    ocr_calls: tuple[OcrCall, ...] = ()
    warnings: tuple[str, ...] = ()
    errors: tuple[PocError, ...] = ()
    created_at: str = field(default_factory=_utc_now)
    contract_version: str = CONTRACT_VERSION

    @property
    def content(self) -> str:
        return self.content_record.text

    @classmethod
    def for_source(cls, source_path: Path, source_bytes: bytes) -> "ConversionEnvelope":
        mime_hint, _ = mimetypes.guess_type(source_path.name)
        return cls(
            source=SourceRecord(
                path=source_path.name,
                sha256=sha256(source_bytes).hexdigest(),
                size_bytes=len(source_bytes),
                mime_hint=mime_hint or "application/octet-stream",
                captured_at=_utc_now(),
            )
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "contract_version": self.contract_version,
            "created_at": self.created_at,
            "source": self.source.to_dict(),
            "converter": self.converter.to_dict(),
            "content": self.content_record.to_dict(),
            "segments": [segment.to_dict() for segment in self.segments],
            "ocr_calls": [call.to_dict() for call in self.ocr_calls],
            "warnings": list(self.warnings),
            "errors": [error.to_dict() for error in self.errors],
        }
