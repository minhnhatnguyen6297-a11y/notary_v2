import json
from pathlib import Path

from docx import Document

from services.fast_audit.cache_store import CacheStore
from services.fast_audit.compare_engine import CompareEngine
from services.fast_audit.doc_grouper import DocumentGrouper
from services.fast_audit.models import AuditRunMeta, OCRPage
from services.fast_audit.pdf_splitter import PDFSplitter
from services.fast_audit.report_writer import ReportWriter
from services.fast_audit.scan_loader import ScanLoader
from services.fast_audit.word_parser import WordParser


def test_full_pipeline_without_ocr_api(tmp_path: Path):
    # Build a fake cache so the OCR API is not called.
    folder = tmp_path / "ho_so"
    folder.mkdir()
    cache_dir = folder / "_audit_cache"
    output_dir = folder / "_audit_out"
    cache_dir.mkdir(parents=True, exist_ok=True)

    # Create a simple image "scan" by writing a tiny valid JPEG is hard; use cached OCR instead.
    cache = CacheStore(cache_dir)
    fake_image_bytes = b"fake_image_for_hash"
    page_hash = cache.page_hash_from_bytes(fake_image_bytes)
    cache.set_ocr(page_hash, {"text": "Tôi là: Nguyễn Văn Sơn\nCCCD: 001080000123", "provider": "mock"})

    # Write a Word doc.
    docx = Document()
    docx.add_paragraph("VĂN BẢN TỪ CHỐI NHẬN DI SẢN")
    docx.add_paragraph("Tôi là: Nguyễn Văn Sơn")
    docx.add_paragraph("CCCD: 001080000123")
    docx.save(str(folder / "VP_Từ chối_Sơn.docx"))

    # Write a fake image file.
    (folder / "scan.jpg").write_bytes(fake_image_bytes)

    loader = ScanLoader(folder)
    scans, words = loader.load()
    assert len(scans) == 1 and len(words) == 1

    # Skip PDF splitter for image by using the cached bytes path manually.
    splitter = PDFSplitter(image_dir=cache_dir / "page_images")
    pages = splitter.split(scans[0])
    assert len(pages) == 1
    assert pages[0].page_hash == page_hash

    ocr_page = OCRPage(
        page_id=pages[0].page_id,
        page_hash=pages[0].page_hash,
        sequence_no=1,
        source_file=str(folder / "scan.jpg"),
        page_no=1,
        text="Tôi là: Nguyễn Văn Sơn\nCCCD: 001080000123",
        provider="mock",
        from_cache=True,
    )

    grouper = DocumentGrouper()
    spans = grouper.group([ocr_page])
    assert len(spans) == 1

    parser = WordParser()
    word_doc = parser.parse(words[0].path)
    assert any(f.name == "declarant_name" and f.value == "Nguyễn Văn Sơn" for f in word_doc.fields)

    engine = CompareEngine([ocr_page], spans)
    issues = engine.compare(word_doc)
    # CCCD exact match should not produce an issue; name exact match should not either.
    assert not any(i.field == "id_number" for i in issues)
    assert not any(i.field == "declarant_name" for i in issues)

    meta = AuditRunMeta(
        started_at="now",
        folder=str(folder),
        output_dir=str(output_dir),
        cache_dir=str(cache_dir),
        ocr_provider="mock",
        ocr_calls=0,
        cache_hits=1,
    )
    writer = ReportWriter(output_dir)
    json_path, md_path = writer.write(meta, [ocr_page], spans, [word_doc], issues)
    assert json_path.exists() and md_path.exists()
    report = json.loads(json_path.read_text(encoding="utf-8"))
    assert report["meta"]["cache_hits"] == 1
    assert report["meta"]["total_word_files"] == 1
