from __future__ import annotations

import hashlib
import json
from pathlib import Path

from services.fast_audit.models import CacheEntry


class CacheStore:
    """Filesystem cache for page images and OCR text."""

    def __init__(self, cache_dir: str | Path):
        self.cache_dir = Path(cache_dir)
        self.page_images_dir = self.cache_dir / "page_images"
        self.ocr_text_dir = self.cache_dir / "ocr_text"
        self.file_hashes_path = self.cache_dir / "file_hashes.json"
        self.page_images_dir.mkdir(parents=True, exist_ok=True)
        self.ocr_text_dir.mkdir(parents=True, exist_ok=True)

    def get_file_hash_entry(self, source_id: str) -> dict | None:
        data = self._load_file_hashes()
        return data.get(source_id)

    def set_file_hash_entry(self, source_id: str, entry: dict) -> None:
        data = self._load_file_hashes()
        data[source_id] = entry
        self.file_hashes_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    def get_ocr(self, page_hash: str) -> dict | None:
        path = self.ocr_text_path(page_hash)
        if not path.exists():
            return None
        return json.loads(path.read_text(encoding="utf-8"))

    def set_ocr(self, page_hash: str, payload: dict) -> CacheEntry:
        path = self.ocr_text_path(page_hash)
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        return CacheEntry(key=page_hash, path=str(path), kind="ocr_text")

    def ocr_text_path(self, page_hash: str) -> Path:
        return self.ocr_text_dir / f"{page_hash}.json"

    def _load_file_hashes(self) -> dict:
        if not self.file_hashes_path.exists():
            return {}
        return json.loads(self.file_hashes_path.read_text(encoding="utf-8"))

    @staticmethod
    def page_hash_from_bytes(data: bytes) -> str:
        return hashlib.sha256(data).hexdigest()
