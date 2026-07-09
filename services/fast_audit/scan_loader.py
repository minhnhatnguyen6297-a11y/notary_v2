from __future__ import annotations

import hashlib
import os
from pathlib import Path

from services.fast_audit.models import ScanSource, SourceKind


class ScanLoader:
    """Collect supported scan/image/word files from a folder, ignoring temps and cache."""

    SUPPORTED_SCAN = {".pdf", ".jpg", ".jpeg", ".png", ".tiff", ".tif", ".bmp"}
    SUPPORTED_WORD = {".docx"}
    IGNORED_NAME_PREFIXES = ("~$", ".~")
    IGNORED_EXTENSIONS = {".tmp", ".xls", ".xlsx", ".xlsb", ".json", ".md"}
    IGNORED_DIRS = {"_audit_out", "_audit_cache"}

    def __init__(self, root: str | Path):
        self.root = Path(root).resolve()

    def load(self) -> tuple[list[ScanSource], list[ScanSource]]:
        scans: list[ScanSource] = []
        words: list[ScanSource] = []

        for dir_path, dir_names, file_names in os.walk(self.root):
            dir_names[:] = [d for d in dir_names if d not in self.IGNORED_DIRS]
            current = Path(dir_path)
            rel_dir = current.relative_to(self.root)

            for file_name in sorted(file_names):
                if file_name.startswith(self.IGNORED_NAME_PREFIXES):
                    continue
                path = current / file_name
                ext = path.suffix.lower()
                if ext in self.IGNORED_EXTENSIONS:
                    continue
                if ext in self.SUPPORTED_SCAN:
                    kind = SourceKind.PDF if ext == ".pdf" else SourceKind.IMAGE
                    scans.append(self._to_source(path, kind, rel_dir))
                elif ext in self.SUPPORTED_WORD:
                    words.append(self._to_source(path, SourceKind.WORD, rel_dir))

        scans.sort(key=self._sort_key)
        words.sort(key=self._sort_key)
        return scans, words

    def _to_source(self, path: Path, kind: SourceKind, rel_dir: Path) -> ScanSource:
        stat = path.stat()
        digest = self._file_hash(path)
        rel = rel_dir / path.name
        if str(rel_dir) == ".":
            rel = Path(path.name)
        return ScanSource(
            source_id=digest[:16],
            path=str(path),
            kind=kind,
            rel_path=rel.as_posix(),
            size=stat.st_size,
            mtime=stat.st_mtime,
            sha256=digest,
        )

    @staticmethod
    def _file_hash(path: Path) -> str:
        h = hashlib.sha256()
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                h.update(chunk)
        return h.hexdigest()

    def _sort_key(self, source: ScanSource) -> tuple:
        rel = Path(source.rel_path)
        kind_order = {"pdf": 0, "image": 1, "word": 2}
        ext = Path(source.path).suffix.lower().lstrip(".")
        ext_kind = "pdf" if ext == "pdf" else "image" if ext in {"jpg", "jpeg", "png", "tiff", "tif", "bmp"} else "word"
        return (str(rel.parent), kind_order.get(ext_kind, 3), rel.name, source.mtime)
