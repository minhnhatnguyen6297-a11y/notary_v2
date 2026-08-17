from __future__ import annotations

from services.fast_audit.models import DocType, DocumentSpan, OCRPage
from services.fast_audit.rules import classify_doc_type, cut_at_notary_anchor


class DocumentGrouper:
    """Group sequential OCR pages into document spans using lightweight rules."""

    def group(self, pages: list[OCRPage]) -> list[DocumentSpan]:
        if not pages:
            return []
        pages = sorted(pages, key=lambda p: p.sequence_no)
        spans: list[DocumentSpan] = []
        current_type: DocType = DocType.UNKNOWN
        current_page_ids: list[str] = []
        current_sources: set[str] = set()
        current_start = pages[0].sequence_no
        current_header = ""

        for page in pages:
            text = page.text or ""
            comparison_text, has_notary = cut_at_notary_anchor(text)
            notary_only = has_notary and not comparison_text.strip()
            detected = classify_doc_type(comparison_text)
            page_type = DocType(detected) if detected else DocType.UNKNOWN

            if notary_only:
                # Close current span if any.
                if current_page_ids:
                    spans.append(self._make_span(
                        current_type, current_page_ids, current_sources,
                        current_start, page.sequence_no - 1, current_header,
                    ))
                    current_page_ids = []
                    current_sources = set()
                # Emit notary-only span excluded from compare.
                spans.append(DocumentSpan(
                    doc_span_id=f"span_{page.page_id}",
                    doc_type=DocType.UNKNOWN,
                    page_ids=[page.page_id],
                    start_sequence=page.sequence_no,
                    end_sequence=page.sequence_no,
                    source_files=[page.source_file],
                    header_snippet=text[:200],
                    excluded_from_compare=True,
                ))
                current_type = DocType.UNKNOWN
                current_start = page.sequence_no + 1
                current_header = ""
                continue

            if page_type == DocType.UNKNOWN:
                # Attach to previous span if previous exists.
                if current_page_ids:
                    current_page_ids.append(page.page_id)
                    current_sources.add(page.source_file)
                    continue
                # Start unknown span.
                current_type = DocType.UNKNOWN
                current_page_ids = [page.page_id]
                current_sources.add(page.source_file)
                current_header = comparison_text[:200]
                current_start = page.sequence_no
            elif page_type == current_type:
                current_page_ids.append(page.page_id)
                current_sources.add(page.source_file)
            else:
                if current_page_ids:
                    spans.append(self._make_span(
                        current_type, current_page_ids, current_sources,
                        current_start, page.sequence_no - 1, current_header,
                    ))
                current_type = page_type
                current_page_ids = [page.page_id]
                current_sources = {page.source_file}
                current_start = page.sequence_no
                current_header = comparison_text[:200]

        if current_page_ids:
            spans.append(self._make_span(
                current_type, current_page_ids, current_sources,
                current_start, pages[-1].sequence_no, current_header,
            ))

        return spans

    @staticmethod
    def _make_span(
        doc_type: DocType,
        page_ids: list[str],
        sources: set[str],
        start_sequence: int,
        end_sequence: int,
        header_snippet: str,
    ) -> DocumentSpan:
        return DocumentSpan(
            doc_span_id=f"span_{page_ids[0]}",
            doc_type=doc_type,
            page_ids=page_ids,
            start_sequence=start_sequence,
            end_sequence=end_sequence,
            source_files=sorted(sources),
            header_snippet=header_snippet,
            excluded_from_compare=False,
        )
