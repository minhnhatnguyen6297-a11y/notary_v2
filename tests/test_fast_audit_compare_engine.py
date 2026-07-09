from services.fast_audit.compare_engine import CompareEngine
from services.fast_audit.models import DocType, DocumentSpan, OCRPage, WordAuditDoc, WordField


def _ocr_page(page_id: str, text: str, seq: int = 1) -> OCRPage:
    return OCRPage(
        page_id=page_id,
        page_hash=page_id,
        sequence_no=seq,
        source_file="scan.pdf",
        page_no=1,
        text=text,
    )


def _word_doc(fields: list[WordField]) -> WordAuditDoc:
    return WordAuditDoc(
        word_file="test.docx",
        template_type="van_ban_tu_choi",
        raw_text="",
        paragraphs=[],
        fields=fields,
    )


def _span(page_ids: list[str], doc_type: DocType = DocType.UNKNOWN) -> DocumentSpan:
    return DocumentSpan(
        doc_span_id=f"span_{page_ids[0]}",
        doc_type=doc_type,
        page_ids=page_ids,
        start_sequence=1,
        end_sequence=1,
        source_files=["scan.pdf"],
    )


def test_exact_match_for_id_card():
    ocr = _ocr_page("p1", "Căn cước công dân số 001080000123 do Bộ Công an cấp")
    span = _span(["p1"], DocType.CAN_CUOC)
    word = _word_doc([WordField(name="id_number", value="001080000123", context="regex")])
    engine = CompareEngine([ocr], [span])
    issues = engine.compare(word)
    assert not issues


def test_fuzzy_match_for_name_typo():
    ocr = _ocr_page("p1", "Tôi là: Diềng Văn Sơn")
    span = _span(["p1"])
    word = _word_doc([WordField(name="declarant_name", value="Riềng Văn Sơn", context="anchor")])
    engine = CompareEngine([ocr], [span])
    issues = engine.compare(word)
    # Diềng vs Riềng should be flagged as likely/manual_check but not certain error.
    assert issues
    assert issues[0].field == "declarant_name"
    assert issues[0].severity.value in {"likely", "manual_check"}


def test_notary_page_excluded_from_compare():
    ocr = _ocr_page("p1", "LỜI CHỨNG CỦA CÔNG CHỨNG VIÊN\nTôi là: Nguyễn Văn Giả")
    span = DocumentSpan(
        doc_span_id="span_p1",
        doc_type=DocType.UNKNOWN,
        page_ids=["p1"],
        start_sequence=1,
        end_sequence=1,
        source_files=["scan.pdf"],
        excluded_from_compare=True,
    )
    word = _word_doc([WordField(name="declarant_name", value="Nguyễn Văn Giả", context="anchor")])
    engine = CompareEngine([ocr], [span])
    issues = engine.compare(word)
    assert all(i.manual_check for i in issues)


def test_case_insensitive_and_punctuation_normalized():
    ocr = _ocr_page("p1", "địa chỉ: thôn 1, xã minh tân, huyện ý yên")
    span = _span(["p1"])
    word = _word_doc([WordField(name="address", value="Thôn 1, xã Minh Tân, huyện Ý Yên", context="regex")])
    engine = CompareEngine([ocr], [span])
    issues = engine.compare(word)
    assert not issues


def test_template_residue_placeholder_detected():
    ocr = _ocr_page("p1", "Tôi là: Nguyễn Văn Sơn")
    span = _span(["p1"])
    word = WordAuditDoc(
        word_file="test.docx",
        template_type="van_ban_tu_choi",
        raw_text="[Họ tên ngườ từ chối]",
        paragraphs=["[Họ tên ngườ từ chối]"],
        fields=[WordField(name="Họ tên ngườ từ chối", value="Nguyễn Văn Sơn", context="placeholder")],
    )
    engine = CompareEngine([ocr], [span])
    issues = engine.compare(word)
    residue = [i for i in issues if i.field == "template_residue"]
    assert residue
    assert residue[0].severity.value == "copy_template"
