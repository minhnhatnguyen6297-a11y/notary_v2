from __future__ import annotations

import asyncio
import base64
import time
from typing import Any

import httpx

from services.fast_audit.cache_store import CacheStore
from services.fast_audit.models import OCRPage, PageInput


class OCRRunner:
    """Call an OCR API with caching and bounded concurrency."""

    def __init__(
        self,
        provider: str,
        base_url: str,
        api_key: str,
        model: str = "",
        concurrency: int = 6,
        timeout: float = 60,
        cache: CacheStore | None = None,
    ):
        self.provider = provider
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.concurrency = concurrency
        self.timeout = timeout
        self.cache = cache
        self._semaphore = asyncio.Semaphore(concurrency)
        self.calls = 0
        self.cache_hits = 0

    async def run_batch(self, pages: list[PageInput]) -> list[OCRPage]:
        tasks = [self._run_one(page) for page in pages]
        return await asyncio.gather(*tasks)

    async def _run_one(self, page: PageInput) -> OCRPage:
        if self.cache:
            cached = self.cache.get_ocr(page.page_hash)
            if cached is not None:
                self.cache_hits += 1
                return OCRPage(
                    page_id=page.page_id,
                    page_hash=page.page_hash,
                    sequence_no=page.sequence_no,
                    source_file=page.source_file,
                    page_no=page.page_no,
                    text=cached.get("text", ""),
                    confidence=cached.get("confidence"),
                    provider=cached.get("provider", self.provider),
                    latency_ms=cached.get("latency_ms", 0),
                    from_cache=True,
                )

        async with self._semaphore:
            start = time.perf_counter()
            try:
                result = await self._call_api(page)
            except Exception:
                # One retry for transient network errors.
                await asyncio.sleep(0.5)
                try:
                    result = await self._call_api(page)
                except Exception as exc:
                    elapsed = int((time.perf_counter() - start) * 1000)
                    return OCRPage(
                        page_id=page.page_id,
                        page_hash=page.page_hash,
                        sequence_no=page.sequence_no,
                        source_file=page.source_file,
                        page_no=page.page_no,
                        text=f"[OCR ERROR: {exc}]",
                        confidence=None,
                        provider=self.provider,
                        latency_ms=elapsed,
                        from_cache=False,
                    )
            elapsed = int((time.perf_counter() - start) * 1000)

        self.calls += 1
        ocr_page = OCRPage(
            page_id=page.page_id,
            page_hash=page.page_hash,
            sequence_no=page.sequence_no,
            source_file=page.source_file,
            page_no=page.page_no,
            text=result.get("text", ""),
            confidence=result.get("confidence"),
            provider=self.provider,
            latency_ms=elapsed,
            from_cache=False,
        )
        if self.cache:
            self.cache.set_ocr(
                page.page_hash,
                {
                    "text": ocr_page.text,
                    "confidence": ocr_page.confidence,
                    "provider": ocr_page.provider,
                    "latency_ms": ocr_page.latency_ms,
                },
            )
        return ocr_page

    async def _call_api(self, page: PageInput) -> dict[str, Any]:
        if self.provider == "qwen":
            return await self._call_qwen(page)
        if self.provider == "openai":
            return await self._call_openai(page)
        raise ValueError(f"Unsupported OCR provider: {self.provider}")

    async def _call_qwen(self, page: PageInput) -> dict[str, Any]:
        url = f"{self.base_url}/compatible-mode/v1/chat/completions"
        image_b64 = base64.b64encode(page.bytes).decode("utf-8")
        payload = {
            "model": self.model or "qwen-vl-ocr-2025-11-20",
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "Trích xuất toàn bộ văn bản trong ảnh. Chỉ trả về text thuần."},
                        {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{image_b64}"}},
                    ],
                }
            ],
        }
        headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            resp = await client.post(url, json=payload, headers=headers)
            resp.raise_for_status()
            data = resp.json()
        text = data["choices"][0]["message"]["content"]
        return {"text": text, "confidence": None}

    async def _call_openai(self, page: PageInput) -> dict[str, Any]:
        url = f"{self.base_url}/v1/chat/completions"
        image_b64 = base64.b64encode(page.bytes).decode("utf-8")
        payload = {
            "model": self.model or "gpt-4o",
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "Trích xuất toàn bộ văn bản trong ảnh. Chỉ trả về text thuần."},
                        {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{image_b64}"}},
                    ],
                }
            ],
        }
        headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            resp = await client.post(url, json=payload, headers=headers)
            resp.raise_for_status()
            data = resp.json()
        text = data["choices"][0]["message"]["content"]
        return {"text": text, "confidence": None}
