import subprocess
import sys

from services.fast_audit.compare_engine import CompareEngine
from services.fast_audit.doc_grouper import DocumentGrouper
from services.fast_audit.models import DocType, DocumentSpan, MatchType, OCRPage, WordAuditDoc, WordField
from services.fast_audit.rules import cut_at_notary_anchor


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


def test_id_card_mismatch_is_not_suppressed():
    ocr = _ocr_page("p1", "Căn cước công dân số 001080000124")
    word = _word_doc(
        [WordField(name="id_number", value="001080000123", context="regex")]
    )

    issues = CompareEngine([ocr], [_span(["p1"], DocType.CAN_CUOC)]).compare(word)

    assert issues and issues[0].field == "id_number"
    assert issues[0].score == 0.0


def test_exact_id_match_ignores_surrounding_context():
    ocr = _ocr_page(
        "p1",
        "CCCD: 001080000123, sinh ngày 01/01/1980",
    )
    word = _word_doc(
        [WordField(name="id_number", value="001080000123", context="regex")]
    )

    assert not CompareEngine([ocr], [_span(["p1"], DocType.CAN_CUOC)]).compare(word)


def test_id_card_does_not_match_longer_number():
    ocr = _ocr_page("p1", "CCCD: 0010800001234")
    word = _word_doc(
        [WordField(name="id_number", value="001080000123", context="regex")]
    )

    assert CompareEngine([ocr], [_span(["p1"], DocType.CAN_CUOC)]).compare(word)


def test_id_card_does_not_join_unrelated_digit_fields():
    ocr = _ocr_page("p1", "Số hồ sơ: 001080\nMã lưu trữ: 000123")
    word = _word_doc(
        [WordField(name="id_number", value="001080000123", context="regex")]
    )

    assert CompareEngine([ocr], [_span(["p1"], DocType.CAN_CUOC)]).compare(word)


def test_address_does_not_match_only_by_shared_digit():
    ocr = _ocr_page("p1", "Địa chỉ: Thôn 1, xã Minh Tân")
    word = _word_doc(
        [WordField(name="address", value="Thôn 1, xã Đại Thắng", context="regex")]
    )

    assert CompareEngine([ocr], [_span(["p1"])]).compare(word)


def test_date_matches_after_punctuation_normalization():
    ocr = _ocr_page("p1", "Ngày sinh: 01-01-1980")
    word = _word_doc(
        [WordField(name="date", value="01/01/1980", context="regex")]
    )

    assert not CompareEngine([ocr], [_span(["p1"])]).compare(word)


def test_distinct_dates_do_not_collapse_when_separators_are_removed():
    ocr = _ocr_page("p1", "Ngày sinh: 11/1/1980")
    word = _word_doc(
        [WordField(name="date", value="1/11/1980", context="regex")]
    )

    assert CompareEngine([ocr], [_span(["p1"])]).compare(word)


def test_document_number_matches_with_equivalent_separator():
    ocr = _ocr_page("p1", "Số văn bản: 99-ABC")
    word = _word_doc(
        [WordField(name="document_no", value="99/ABC", context="regex")]
    )

    assert not CompareEngine([ocr], [_span(["p1"])]).compare(word)


def test_document_number_does_not_match_longer_identifier():
    ocr = _ocr_page("p1", "Số văn bản: 99/ABC-1")
    word = _word_doc(
        [WordField(name="document_no", value="99/ABC", context="regex")]
    )

    assert CompareEngine([ocr], [_span(["p1"])]).compare(word)


def test_plot_number_does_not_match_longer_identifier():
    ocr = _ocr_page("p1", "Thửa đất số: 12/3-4")
    word = _word_doc(
        [WordField(name="plot_no", value="12/3", context="regex")]
    )

    assert CompareEngine([ocr], [_span(["p1"])]).compare(word)


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


def test_exact_loi_chung_excluded_from_compare_and_residue():
    pages = [
        _ocr_page("p1", "LỜI CHỨNG\nNguyễn Văn Giả", seq=1),
        _ocr_page("p2", "Tôi là: Nguyễn Văn Sơn", seq=2),
    ]
    spans = DocumentGrouper().group(pages)
    word = WordAuditDoc(
        word_file="test.docx",
        template_type="generic",
        raw_text="Tôi là: Nguyễn Văn Sơn\nLỜI CHỨNG\n[not-a-residue]",
        paragraphs=["Tôi là: Nguyễn Văn Sơn"],
        fields=[WordField(name="declarant_name", value="Nguyễn Văn Giả", context="anchor")],
    )

    issues = CompareEngine(pages, spans).compare(word)

    missing = [issue for issue in issues if issue.field == "declarant_name"]
    assert missing and missing[0].match_type == MatchType.MISSING
    assert not any(issue.field == "template_residue" for issue in issues)


def test_content_before_loi_chung_remains_comparable():
    page = _ocr_page(
        "p1",
        "Tôi là: Nguyễn Văn Sơn\nLỜI CHỨNG CỦA CÔNG CHỨNG VIÊN\nNội dung công chứng",
    )
    spans = DocumentGrouper().group([page])
    word = _word_doc(
        [WordField(name="declarant_name", value="Nguyễn Văn Sơn", context="anchor")]
    )

    assert not spans[0].excluded_from_compare
    assert not CompareEngine([page], spans).compare(word)


def test_giay_chung_nhan_heading_is_not_a_notary_anchor():
    text = "GIẤY CHỨNG NHẬN:\nQuyền sử dụng đất số 123"

    assert cut_at_notary_anchor(text) == (text, False)


def test_notary_cut_preserves_original_text_with_repeated_whitespace():
    before = "Tôi là: Nguyễn   Văn   Sơn"
    text = f"{before}\nLỜI    CHỨNG CỦA CÔNG CHỨNG VIÊN\nNội dung công chứng"

    assert cut_at_notary_anchor(text) == (before, True)


def test_import_does_not_load_word_engine():
    subprocess.run(
        [
            sys.executable,
            "-c",
            "import sys; import services.fast_audit; assert 'services.word_engine' not in sys.modules",
        ],
        check=True,
        cwd=".",
    )


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
