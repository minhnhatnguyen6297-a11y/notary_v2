from __future__ import annotations

import hashlib
from pathlib import Path

import fitz

from services.fast_audit.models import PageInput, ScanSource, SourceKind


class PDFSplitter:
    """Render PDF pages to images for OCR."""

    def __init__(
        self,
        dpi: int = 160,
        fmt: str = "jpeg",
        quality: int = 82,
        image_dir: str | Path | None = None,
    ):
        self.dpi = dpi
        self.fmt = fmt
        self.quality = quality
        self.image_dir = Path(image_dir) if image_dir else None

    def split(self, source: ScanSource, start_sequence: int = 1) -> list[PageInput]:
        pages: list[PageInput] = []
        if source.kind == SourceKind.IMAGE:
            source_path = Path(source.path)
            data = source_path.read_bytes()
            if source_path.suffix.lower() not in {".jpg", ".jpeg"}:
                data = self._pixmap_bytes(fitz.Pixmap(str(source_path)))
            page_hash = hashlib.sha256(data).hexdigest()
            image_path = self._image_path(page_hash)
            if not image_path.exists():
                image_path.write_bytes(data)
            pages.append(
                PageInput(
                    page_id=f"{source.source_id}_p1",
                    sequence_no=start_sequence,
                    source_file=source.path,
                    source_kind=SourceKind.IMAGE,
                    page_no=1,
                    page_hash=page_hash,
                    image_path=str(image_path),
                    bytes=data,
                )
            )
            return pages

        doc = fitz.open(source.path)
        try:
            for page_no in range(len(doc)):
                pix = doc[page_no].get_pixmap(dpi=self.dpi)
                data = self._pixmap_bytes(pix)
                page_hash = hashlib.sha256(data).hexdigest()
                image_path = self._image_path(page_hash)
                if not image_path.exists():
                    image_path.write_bytes(data)
                pages.append(
                    PageInput(
                        page_id=f"{source.source_id}_p{page_no + 1}",
                        sequence_no=start_sequence + page_no,
                        source_file=source.path,
                        source_kind=SourceKind.PDF,
                        page_no=page_no + 1,
                        page_hash=page_hash,
                        image_path=str(image_path),
                        bytes=data,
                    )
                )
        finally:
            doc.close()
        return pages

    def _pixmap_bytes(self, pix: fitz.Pixmap) -> bytes:
        if self.fmt == "jpeg":
            if pix.alpha:
                pix = fitz.Pixmap(pix, 0)
            return pix.tobytes(output="jpeg", jpg_quality=self.quality)
        return pix.tobytes(output=self.fmt)

    def _image_path(self, page_hash: str) -> Path:
        if self.image_dir is None:
            raise RuntimeError("image_dir is required")
        self.image_dir.mkdir(parents=True, exist_ok=True)
        ext = "jpg" if self.fmt == "jpeg" else self.fmt
        return self.image_dir / f"{page_hash}.{ext}"
