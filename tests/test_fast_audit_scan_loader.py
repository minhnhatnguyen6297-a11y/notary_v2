from pathlib import Path

import pytest

from services.fast_audit.scan_loader import ScanLoader


@pytest.fixture
def sample_folder(tmp_path: Path) -> Path:
    (tmp_path / "scan1.pdf").write_bytes(b"pdf1")
    (tmp_path / "photo.jpg").write_bytes(b"jpg1")
    (tmp_path / "doc.docx").write_bytes(b"docx1")
    (tmp_path / "~$temp.docx").write_bytes(b"temp")
    (tmp_path / "sheet.xlsx").write_bytes(b"xlsx")
    (tmp_path / "_audit_out").mkdir()
    (tmp_path / "_audit_out" / "old_report.md").write_text("old")
    sub = tmp_path / "sub"
    sub.mkdir()
    (sub / "scan2.pdf").write_bytes(b"pdf2")
    (sub / "VP_Từ chối_Sơn.docx").write_bytes(b"docx2")
    return tmp_path


def test_scan_loader_ignores_temp_excel_and_cache(sample_folder: Path):
    loader = ScanLoader(sample_folder)
    scans, words = loader.load()
    scan_rels = {s.rel_path for s in scans}
    word_rels = {w.rel_path for w in words}

    assert "scan1.pdf" in scan_rels
    assert "photo.jpg" in scan_rels
    assert "sub/scan2.pdf" in scan_rels
    assert "doc.docx" in word_rels
    assert "sub/VP_Từ chối_Sơn.docx" in word_rels
    assert "~$temp.docx" not in word_rels
    assert "sheet.xlsx" not in scan_rels and "sheet.xlsx" not in word_rels
    assert "_audit_out/old_report.md" not in scan_rels


def test_scan_loader_sorts_pdf_before_image_before_word(sample_folder: Path):
    loader = ScanLoader(sample_folder)
    scans, words = loader.load()
    # Files are grouped by relative directory first, then kind (pdf < image < word), then name.
    assert scans[0].rel_path == "scan1.pdf"
    assert scans[1].rel_path == "photo.jpg"
    assert scans[2].rel_path == "sub/scan2.pdf"
    assert words[0].rel_path == "doc.docx"
    assert words[1].rel_path == "sub/VP_Từ chối_Sơn.docx"


def test_scan_loader_hashes_are_stable(sample_folder: Path):
    loader = ScanLoader(sample_folder)
    scans1, _ = loader.load()
    scans2, _ = loader.load()
    assert [s.sha256 for s in scans1] == [s.sha256 for s in scans2]


def test_identical_files_keep_distinct_source_identity(tmp_path: Path):
    (tmp_path / "first.jpg").write_bytes(b"same")
    (tmp_path / "second.jpg").write_bytes(b"same")

    scans, _ = ScanLoader(tmp_path).load()

    assert scans[0].sha256 == scans[1].sha256
    assert scans[0].source_id != scans[1].source_id
