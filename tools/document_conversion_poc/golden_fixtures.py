"""Create deterministic synthetic files for the GD-01..07 manifest."""

from __future__ import annotations

from datetime import datetime, timezone
import io
from pathlib import Path
import re
import zipfile

import fitz
from docx import Document
from PIL import Image


def _pdf(path: Path, *, text: str | None) -> None:
    document = fitz.open()
    document.set_metadata({"format": "PDF 1.7", "title": "Synthetic", "author": "POC", "creationDate": "D:20200101000000Z"})
    page = document.new_page()
    if text:
        page.insert_text((72, 72), text)
    data = document.tobytes()
    data = re.sub(
        rb"/ID\s*\[<[^>]+><[^>]+>\]",
        b"/ID [<00000000000000000000000000000000><11111111111111111111111111111111>]",
        data,
    )
    path.write_bytes(data)
    document.close()


def _normalize_docx(path: Path) -> None:
    """Normalize ZIP metadata so identical synthetic inputs have identical bytes."""
    source = zipfile.ZipFile(path)
    try:
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as target:
            for info in sorted(source.infolist(), key=lambda item: item.filename):
                normalized = zipfile.ZipInfo(info.filename, date_time=(1980, 1, 1, 0, 0, 0))
                normalized.compress_type = zipfile.ZIP_DEFLATED
                normalized.external_attr = info.external_attr
                target.writestr(normalized, source.read(info.filename))
        path.write_bytes(buffer.getvalue())
    finally:
        source.close()


def materialize_golden_fixtures(directory: Path) -> list[Path]:
    """Write only synthetic fixtures; return paths in GD-01..07 order."""
    directory.mkdir(parents=True, exist_ok=True)
    _pdf(directory / "gd-01-text.pdf", text="Synthetic PDF text")
    _pdf(directory / "gd-02-scanned.pdf", text=None)
    Image.new("RGB", (2, 2), "white").save(directory / "gd-03-id.png", format="PNG")
    document = Document()
    document.add_paragraph("Synthetic DOCX text")
    fixed = datetime(2020, 1, 1, tzinfo=timezone.utc)
    document.core_properties.created = fixed
    document.core_properties.modified = fixed
    document.core_properties.last_printed = fixed
    document.save(directory / "gd-04-contract.docx")
    _normalize_docx(directory / "gd-04-contract.docx")
    (directory / "gd-05-legacy.doc").write_bytes(b"\xd0\xcf\x11\xe0" + b"synthetic")
    (directory / "gd-06-unsupported.bin").write_bytes(b"synthetic unsupported")
    Image.new("RGB", (2, 2), "black").save(directory / "gd-07-partial.png", format="PNG")
    return [directory / f"gd-0{index}-{name}" for index, name in (
        (1, "text.pdf"), (2, "scanned.pdf"), (3, "id.png"),
        (4, "contract.docx"), (5, "legacy.doc"), (6, "unsupported.bin"),
        (7, "partial.png"),
    )]
