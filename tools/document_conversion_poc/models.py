from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import hashlib
import mimetypes
from pathlib import Path
from typing import Any, Mapping


CONTRACT_VERSION = "v0.experimental"


@dataclass(frozen=True)
class Source:
    source_id: str
    sha256: str
    media_type: str | None
    size_bytes: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_id": self.source_id,
            "sha256": self.sha256,
            "media_type": self.media_type,
            "size_bytes": self.size_bytes,
        }


@dataclass(frozen=True)
class Segment:
    segment_id: str
    text: str
    source_ref: Mapping[str, Any] | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "segment_id": self.segment_id,
            "text": self.text,
            "source_ref": None if self.source_ref is None else dict(self.source_ref),
        }


@dataclass(frozen=True)
class OcrCall:
    provider: str
    model: str
    input_hash: str
    status: str
    duration_ms: int | None = None
    error: str | None = None
    policy_version: str = "unknown"
    allow_reason: str = "unknown"
    attempt: int = 1
    source_ref: Mapping[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "provider": self.provider,
            "model": self.model,
            "input_hash": self.input_hash,
            "status": self.status,
            "duration_ms": self.duration_ms,
            "error": self.error,
            "policy_version": self.policy_version,
            "allow_reason": self.allow_reason,
            "attempt": self.attempt,
            "source_ref": None if self.source_ref is None else dict(self.source_ref),
        }


@dataclass(frozen=True)
class PocError:
    code: str
    message: str
    retryable: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "message": self.message,
            "retryable": self.retryable,
        }


@dataclass(frozen=True)
class Converter:
    name: str = "unassigned"
    version: str = "unknown"
    config_fingerprint: str = "unconfigured"

    def to_dict(self) -> dict[str, str]:
        return {
            "name": self.name,
            "version": self.version,
            "config_fingerprint": self.config_fingerprint,
        }


@dataclass(frozen=True)
class Content:
    format: str = "markdown"
    value: str = ""

    def to_dict(self) -> dict[str, str]:
        return {"format": self.format, "value": self.value}


@dataclass
class ConversionEnvelope:
    source: Source
    created_at: str
    converter: Converter = field(default_factory=Converter)
    content: Content = field(default_factory=Content)
    segments: list[Segment] = field(default_factory=list)
    ocr_calls: list[OcrCall] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    errors: list[PocError] = field(default_factory=list)

    @classmethod
    def for_source(cls, source_path: Path, source_bytes: bytes) -> "ConversionEnvelope":
        media_type, _ = mimetypes.guess_type(str(source_path))
        digest = hashlib.sha256(source_bytes).hexdigest()
        return cls(
            source=Source(
                source_id=f"sha256:{digest}",
                sha256=digest,
                media_type=media_type,
                size_bytes=len(source_bytes),
            ),
            created_at=datetime.now(timezone.utc).isoformat(),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "contract_version": CONTRACT_VERSION,
            "source": self.source.to_dict(),
            "created_at": self.created_at,
            "converter": self.converter.to_dict(),
            "content": self.content.to_dict(),
            "segments": [segment.to_dict() for segment in self.segments],
            "ocr_calls": [call.to_dict() for call in self.ocr_calls],
            "warnings": list(self.warnings),
            "errors": [error.to_dict() for error in self.errors],
        }
