"""Explicit, opt-in OpenAI-compatible Qwen OCR adapter for the isolated POC."""

from __future__ import annotations

import base64
from dataclasses import dataclass, field
import os
from hashlib import sha256
from time import perf_counter
from typing import Any

from .models import OcrCall, PocError


_REQUIRED_ENVIRONMENT = (
    "QWEN_COMPATIBLE_BASE_URL",
    "QWEN_COMPATIBLE_API_KEY",
    "QWEN_COMPATIBLE_MODEL",
)


class QwenCompatibleOcrError(RuntimeError):
    """A safe error boundary that retains structured, non-secret metadata."""

    def __init__(self, error: PocError, ocr_call: OcrCall) -> None:
        super().__init__(error.code)
        self.error = error
        self.ocr_call = ocr_call


@dataclass(slots=True)
class QwenCompatibleOcr:
    """Small adapter around an injected OpenAI-compatible chat client.

    The constructor deliberately accepts a client to keep unit tests offline.  The
    real OpenAI client is built only by :meth:`from_environment`.
    """

    client: Any
    model: str
    last_ocr_call: OcrCall | None = field(init=False, default=None)

    @classmethod
    def from_environment(cls) -> "QwenCompatibleOcr":
        """Create the opt-in production-shaped client from required environment.

        This POC never reads credential values except at this explicit boundary.
        """

        values = {name: os.environ.get(name) for name in _REQUIRED_ENVIRONMENT}
        missing = [name for name, value in values.items() if not value]
        if missing:
            raise ValueError(
                "Missing required Qwen-compatible environment variables: "
                + ", ".join(missing)
            )

        # Keep the optional SDK import and the only real-client construction here.
        from openai import OpenAI

        return cls(
            client=OpenAI(
                base_url=values["QWEN_COMPATIBLE_BASE_URL"],
                api_key=values["QWEN_COMPATIBLE_API_KEY"],
            ),
            model=values["QWEN_COMPATIBLE_MODEL"],
        )

    def extract(self, image_bytes: bytes, mime_type: str) -> str:
        """Request text extraction using exactly one base64 data URL.

        Request failures are raised as :class:`QwenCompatibleOcrError`, whose
        public fields deliberately exclude exception text, provider responses,
        URLs, image payloads, and credentials.
        """

        input_sha256 = sha256(image_bytes).hexdigest()
        started_at = perf_counter()
        data_url = "data:{};base64,{}".format(
            mime_type, base64.b64encode(image_bytes).decode("ascii")
        )
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "text",
                                "text": "Extract all visible text from this image.",
                            },
                            {"type": "image_url", "image_url": {"url": data_url}},
                        ],
                    }
                ],
            )
            content = response.choices[0].message.content
            if not isinstance(content, str):
                raise TypeError("OCR response content is not text")
        except Exception as exc:
            ocr_call = OcrCall(
                provider="qwen_compatible",
                status="failed",
                input_sha256=input_sha256,
                duration_ms=_duration_ms(started_at),
            )
            self.last_ocr_call = ocr_call
            error = PocError(
                code="ocr_request_failed",
                message="OCR request failed.",
                retryable=_is_retryable_request_failure(exc),
            )
            raise QwenCompatibleOcrError(error, ocr_call) from None

        ocr_call = OcrCall(
            provider="qwen_compatible",
            status="completed",
            input_sha256=input_sha256,
            duration_ms=_duration_ms(started_at),
        )
        self.last_ocr_call = ocr_call
        return content


def _duration_ms(started_at: float) -> int:
    return int((perf_counter() - started_at) * 1000)


def _is_retryable_request_failure(exc: Exception) -> bool:
    """Classify transport failures without serialising provider exception detail."""

    status_code = getattr(exc, "status_code", None)
    if isinstance(status_code, int):
        return status_code == 408 or status_code == 429 or status_code >= 500

    exception_name = type(exc).__name__.lower()
    return isinstance(exc, TimeoutError) or "timeout" in exception_name or "connection" in exception_name
