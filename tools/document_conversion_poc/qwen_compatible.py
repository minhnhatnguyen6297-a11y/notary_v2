from __future__ import annotations

import base64
import os
from typing import Any

try:
    from openai import APIConnectionError, APITimeoutError, OpenAI, RateLimitError
except ImportError:  # Optional POC dependency; only environment construction needs it.
    class APIConnectionError(Exception):
        pass

    class APITimeoutError(Exception):
        pass

    class RateLimitError(Exception):
        pass

    OpenAI = None  # type: ignore[assignment,misc]


class OcrRequestError(RuntimeError):
    def __init__(self, message: str, *, retryable: bool) -> None:
        super().__init__(message)
        self.retryable = retryable


class QwenCompatibleOcr:
    provider = "qwen-compatible"

    def __init__(self, *, client: Any, model: str) -> None:
        self.client = client
        self.model = model

    @classmethod
    def from_environment(cls) -> "QwenCompatibleOcr":
        base_url = os.environ.get("QWEN_COMPATIBLE_BASE_URL")
        api_key = os.environ.get("QWEN_COMPATIBLE_API_KEY")
        model = os.environ.get("QWEN_COMPATIBLE_MODEL")
        if not base_url or not api_key or not model:
            raise ValueError(
                "QWEN_COMPATIBLE_BASE_URL, QWEN_COMPATIBLE_API_KEY, and "
                "QWEN_COMPATIBLE_MODEL are required"
            )
        if OpenAI is None:
            raise RuntimeError(
                "openai is not installed; install requirements-poc-markitdown.txt"
            )
        return cls(
            client=OpenAI(
                base_url=base_url,
                api_key=api_key,
                timeout=20.0,
                max_retries=0,
            ),
            model=model,
        )

    @staticmethod
    def _is_retryable(exc: Exception) -> bool:
        if isinstance(exc, (APITimeoutError, APIConnectionError, RateLimitError, TimeoutError)):
            return True
        status_code = getattr(exc, "status_code", None)
        return isinstance(status_code, int) and status_code >= 500

    def extract(self, image_bytes: bytes, mime_type: str) -> str:
        data_url = f"data:{mime_type};base64,{base64.b64encode(image_bytes).decode('ascii')}"
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "text",
                                "text": "Extract all visible text. Preserve line breaks when possible.",
                            },
                            {"type": "image_url", "image_url": {"url": data_url}},
                        ],
                    }
                ],
            )
            choices = response.choices
            if not choices:
                raise OcrRequestError("compatible OCR response had no choices", retryable=False)
            content = choices[0].message.content
            if not isinstance(content, str) or not content.strip():
                raise OcrRequestError("compatible OCR response had no text", retryable=False)
            return content
        except OcrRequestError:
            raise
        except Exception as exc:
            raise OcrRequestError(
                "compatible OCR request failed",
                retryable=self._is_retryable(exc),
            ) from exc
