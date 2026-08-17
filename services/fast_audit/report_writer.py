from __future__ import annotations

import json
from pathlib import Path

from services.fast_audit.models import AuditIssue, AuditRunMeta, DocumentSpan, OCRPage, Severity, WordAuditDoc


class ReportWriter:
    """Write JSON and Markdown reports for the audit run."""

    def __init__(self, output_dir: str | Path):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def write(
        self,
        meta: AuditRunMeta,
        ocr_pages: list[OCRPage],
        spans: list[DocumentSpan],
        word_docs: list[WordAuditDoc],
        issues: list[AuditIssue],
    ) -> tuple[Path, Path]:
        meta.issues_found = len(issues)
        meta.total_pages = len(ocr_pages)
        meta.total_word_files = len(word_docs)

        json_path = self.output_dir / "report.json"
        md_path = self.output_dir / "report.md"

        payload = {
            "meta": meta.__dict__,
            "ocr_pages": [self._ocr_to_dict(p) for p in ocr_pages],
            "documents": [self._span_to_dict(s) for s in spans],
            "word_extract": [self._word_to_dict(w) for w in word_docs],
            "issues": [self._issue_to_dict(i) for i in issues],
        }
        for name, value in {
            "run_meta.json": payload["meta"],
            "ocr_pages.json": payload["ocr_pages"],
            "documents.json": payload["documents"],
            "word_extract.json": payload["word_extract"],
        }.items():
            (self.output_dir / name).write_text(
                json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8"
            )
        json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

        md = self._build_markdown(meta, issues)
        md_path.write_text(md, encoding="utf-8")

        return json_path, md_path

    @staticmethod
    def _ocr_to_dict(p: OCRPage) -> dict:
        return {
            "page_id": p.page_id,
            "page_hash": p.page_hash,
            "sequence_no": p.sequence_no,
            "source_file": p.source_file,
            "page_no": p.page_no,
            "text": p.text,
            "confidence": p.confidence,
            "provider": p.provider,
            "latency_ms": p.latency_ms,
            "from_cache": p.from_cache,
        }

    @staticmethod
    def _span_to_dict(s: DocumentSpan) -> dict:
        return {
            "doc_span_id": s.doc_span_id,
            "doc_type": s.doc_type.value,
            "page_ids": s.page_ids,
            "start_sequence": s.start_sequence,
            "end_sequence": s.end_sequence,
            "source_files": s.source_files,
            "header_snippet": s.header_snippet,
            "excluded_from_compare": s.excluded_from_compare,
        }

    @staticmethod
    def _word_to_dict(w: WordAuditDoc) -> dict:
        return {
            "word_file": w.word_file,
            "template_type": w.template_type,
            "mode": w.mode,
            "paragraphs": w.paragraphs,
            "fields": [{"name": f.name, "value": f.value, "context": f.context} for f in w.fields],
            "anchors_found": w.anchors_found,
        }

    @staticmethod
    def _issue_to_dict(i: AuditIssue) -> dict:
        return {
            "word_file": i.word_file,
            "template_type": i.template_type,
            "field": i.field,
            "word_value": i.word_value,
            "ocr_value": i.ocr_value,
            "ocr_page_refs": i.ocr_page_refs,
            "match_type": i.match_type.value,
            "score": i.score,
            "severity": i.severity.value,
            "reason": i.reason,
            "suggested_fix": i.suggested_fix,
            "manual_check": i.manual_check,
        }

    def _build_markdown(self, meta: AuditRunMeta, issues: list[AuditIssue]) -> str:
        lines: list[str] = []
        lines.append("# Báo cáo soát chính tả fast_text_audit")
        lines.append("")
        lines.append(f"- Thư mục hồ sơ: `{meta.folder}`")
        lines.append(f"- Thờ điểm chạy: {meta.started_at}")
        lines.append(f"- OCR provider: {meta.ocr_provider}")
        lines.append(f"- Tổng số page: {meta.total_pages}")
        lines.append(f"- Tổng số file Word: {meta.total_word_files}")
        lines.append(f"- Số lỗi phát hiện: {meta.issues_found}")
        lines.append(f"- Số lần gọi OCR: {meta.ocr_calls}")
        lines.append(f"- Cache hits: {meta.cache_hits}")
        lines.append(f"- Tổng thờ gian (ms): {meta.total_ms}")
        lines.append("")

        grouped: dict[str, list[AuditIssue]] = {}
        for issue in issues:
            grouped.setdefault(issue.word_file, []).append(issue)

        if not grouped:
            lines.append("Không phát hiện vấn đề nào cần kiểm tra.")
            return "\n".join(lines)

        for word_file, file_issues in grouped.items():
            lines.append(f"## {word_file}")
            lines.append("")
            for issue in file_issues:
                lines.append(self._issue_markdown(issue))
                lines.append("")

        return "\n".join(lines)

    def _issue_markdown(self, issue: AuditIssue) -> str:
        severity_label = {
            Severity.CERTAIN: "❌ Lỗi chắc chắn",
            Severity.LIKELY: "⚠️ Lỗi nghi chính tả",
            Severity.COPY_TEMPLATE: "📝 Lỗi copy mẫu",
            Severity.MANUAL_CHECK: "🔍 Cần đối chiếu tay",
        }.get(issue.severity, issue.severity.value)

        parts = [
            f"**{severity_label}** | field `{issue.field}`",
            f"- Word: `{issue.word_value}`",
        ]
        if issue.ocr_value:
            parts.append(f"- OCR: `{issue.ocr_value}`")
        if issue.ocr_page_refs:
            refs = ", ".join(issue.ocr_page_refs)
            parts.append(f"- Page: `{refs}`")
        parts.append(f"- Score: {issue.score:.1f}")
        parts.append(f"- Lý do: {issue.reason}")
        if issue.suggested_fix:
            parts.append(f"- Gợi ý: {issue.suggested_fix}")
        return "\n".join(parts)
