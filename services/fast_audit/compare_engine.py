from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

from rapidfuzz import fuzz

from services.fast_audit.models import AuditIssue, DocumentSpan, MatchType, OCRPage, Severity, WordAuditDoc, WordField
from services.fast_audit.rules import (
    AREA_RE,
    DATE_RE,
    DOC_NO_RE,
    ID_CARD_RE,
    MAP_SHEET_RE,
    PLOT_RE,
    cut_at_notary_anchor,
)


def _normalize_token(value: str) -> str:
    value = (value or "").strip().lower().replace("đ", "d")
    value = unicodedata.normalize("NFKD", value)
    value = "".join(char for char in value if not unicodedata.combining(char))
    return re.sub(r"\s+", " ", value)


def _normalized_exact_parts(field_name: str, value: str) -> tuple[str, ...]:
    parts = re.findall(r"[^\W_]+", _normalize_token(value))
    if field_name == "date":
        return tuple(str(int(part)) if part.isdigit() else part for part in parts)
    return tuple(parts)


@dataclass
class _Hit:
    value: str
    page_refs: list[str]
    score: float


class CompareEngine:
    """Compare Word fields against OCR text corpus and emit audit issues."""

    EXACT_FIELDS = {"cccd_or_doc_no", "id_number", "document_no", "date", "plot_no", "map_sheet_no", "area"}
    FUZZY_FIELDS = {
        "declarant_name", "mother_name", "father_name", "spouse_name", "deceased_name",
        "file_declarant_hint", "name",
    }
    FUZZY_NAME_THRESHOLD = 88
    FUZZY_PLACE_THRESHOLD = 90
    MIN_FUZZY_LEN = 6

    def __init__(self, ocr_pages: list[OCRPage], spans: list[DocumentSpan]):
        self.ocr_pages = {p.page_id: p for p in ocr_pages}
        self.spans = spans
        self.corpus = self._build_corpus()

    def _build_corpus(self) -> list[tuple[str, str, str]]:
        """Return list of (page_id, text, span_doc_type)."""
        items = []
        for span in self.spans:
            if span.excluded_from_compare:
                continue
            for page_id in span.page_ids:
                page = self.ocr_pages.get(page_id)
                if not page:
                    continue
                text, anchor_found = cut_at_notary_anchor(page.text)
                if anchor_found and not text.strip():
                    continue
                items.append((page_id, text, span.doc_type.value))
        return items

    def compare(self, doc: WordAuditDoc) -> list[AuditIssue]:
        issues: list[AuditIssue] = []
        if not self.corpus:
            issues.append(
                AuditIssue(
                    word_file=doc.word_file,
                    template_type=doc.template_type,
                    field="*",
                    word_value="",
                    ocr_value="",
                    ocr_page_refs=[],
                    match_type=MatchType.MISSING,
                    score=0.0,
                    severity=Severity.MANUAL_CHECK,
                    reason="Không có nguồn OCR nào để đối chiếu.",
                    suggested_fix="Kiểm tra lại ảnh scan hoặc bổ sung ảnh.",
                    manual_check=True,
                )
            )
            return issues

        for field in doc.fields:
            if not field.value or len(field.value.strip()) < 2:
                continue
            issue = self._compare_field(doc, field)
            if issue:
                issues.append(issue)

        # Template residue checks.
        issues.extend(self._check_residue(doc))
        return issues

    def _compare_field(self, doc: WordAuditDoc, field: WordField) -> AuditIssue | None:
        word_value = field.value.strip()
        hit = self._find_best_hit(word_value, field.name)
        if hit is None:
            return AuditIssue(
                word_file=doc.word_file,
                template_type=doc.template_type,
                field=field.name,
                word_value=word_value,
                ocr_value="",
                ocr_page_refs=[],
                match_type=MatchType.MISSING,
                score=0.0,
                severity=Severity.MANUAL_CHECK,
                reason="Không tìm thấy nguồn OCR phù hợp.",
                suggested_fix="Đối chiếu tay với scan hoặc bổ sung ảnh.",
                manual_check=True,
            )

        match_type, score, severity, reason, suggested_fix = self._evaluate(
            field.name, word_value, hit.value
        )

        # No issue for confident exact/normalized matches.
        if match_type in (MatchType.EXACT, MatchType.NORMALIZED) and score == 100.0:
            return None
        # Fuzzy matches must be perfect to avoid false negatives on name typos.
        if match_type == MatchType.FUZZY and score >= 100.0:
            return None

        return AuditIssue(
            word_file=doc.word_file,
            template_type=doc.template_type,
            field=field.name,
            word_value=word_value,
            ocr_value=hit.value,
            ocr_page_refs=hit.page_refs,
            match_type=match_type,
            score=score,
            severity=severity,
            reason=reason,
            suggested_fix=suggested_fix,
            manual_check=severity == Severity.MANUAL_CHECK,
        )

    def _find_best_hit(self, word_value: str, field_name: str) -> _Hit | None:
        word_norm = _normalize_token(word_value)
        best: _Hit | None = None
        best_score = 0.0

        for page_id, text, span_type in self.corpus:
            text_norm = _normalize_token(text)
            # Direct substring exact match for normalized tokens.
            direct_match = field_name not in self.EXACT_FIELDS and word_norm in text_norm
            if direct_match:
                score = 100.0
                hit_value = word_value if field_name in self.EXACT_FIELDS else self._extract_context(text, word_value)
                if best is None or score > best_score:
                    best_score = score
                    best = _Hit(value=hit_value, page_refs=[page_id], score=score)
                elif score == best_score:
                    best.page_refs.append(page_id)
                continue

            # Normalize punctuation only within field-specific candidates.
            if field_name in self.EXACT_FIELDS:
                word_parts = _normalized_exact_parts(field_name, word_value)
                for candidate in self._exact_candidates(field_name, text):
                    if word_parts and word_parts == _normalized_exact_parts(field_name, candidate):
                        score = 100.0
                        if best is None or score > best_score:
                            best_score = score
                            best = _Hit(value=candidate, page_refs=[page_id], score=score)
                        elif score == best_score:
                            best.page_refs.append(page_id)
                        break
                if best_score == 100.0:
                    continue

            # Fuzzy fallback for names/places.
            if field_name in self.FUZZY_FIELDS or len(word_value) >= self.MIN_FUZZY_LEN:
                threshold = self.FUZZY_PLACE_THRESHOLD if field_name == "address" else self.FUZZY_NAME_THRESHOLD
                score = fuzz.partial_ratio(word_norm, text_norm)
                if score >= threshold and (best is None or score > best_score):
                    best_score = score
                    best = _Hit(value=self._extract_context(text, word_value), page_refs=[page_id], score=score)

        return best

    @staticmethod
    def _exact_candidates(field_name: str, text: str) -> list[str]:
        if field_name == "id_number":
            return ID_CARD_RE.findall(text)
        if field_name == "cccd_or_doc_no":
            return [
                *ID_CARD_RE.findall(text),
                *(match.group(1).strip() for match in DOC_NO_RE.finditer(text)),
            ]
        if field_name == "date":
            return DATE_RE.findall(text)
        pattern = {
            "plot_no": PLOT_RE,
            "map_sheet_no": MAP_SHEET_RE,
            "area": AREA_RE,
            "document_no": DOC_NO_RE,
        }.get(field_name)
        return [match.group(1).strip() for match in pattern.finditer(text)] if pattern else []

    @staticmethod
    def _extract_context(text: str, needle: str, window: int = 80) -> str:
        norm_text = _normalize_token(text)
        norm_needle = _normalize_token(needle)
        idx = norm_text.find(norm_needle)
        if idx == -1:
            return text[:160]
        # Map normalized index back to original roughly.
        words = text.split()
        word_idx = len(norm_text[:idx].split())
        start = max(0, word_idx - 4)
        end = min(len(words), word_idx + 8)
        return " ".join(words[start:end])

    def _evaluate(
        self, field_name: str, word_value: str, ocr_value: str
    ) -> tuple[MatchType, float, Severity, str, str]:
        word_norm = _normalize_token(word_value)
        ocr_norm = _normalize_token(ocr_value)

        if field_name in self.EXACT_FIELDS:
            if word_norm == ocr_norm:
                return MatchType.EXACT, 100.0, Severity.CERTAIN, "Khớp chính xác.", ""
            if (
                field_name in self.EXACT_FIELDS
                and _normalized_exact_parts(field_name, word_value)
                == _normalized_exact_parts(field_name, ocr_value)
            ):
                return MatchType.NORMALIZED, 100.0, Severity.LIKELY, "Khớp sau khi chuẩn hóa dấu câu.", ""
            return (
                MatchType.EXACT,
                0.0,
                Severity.CERTAIN,
                "Không khớp chính xác.",
                f"Sửa thành: {ocr_value}" if ocr_value else "Kiểm tra lại nguồn scan.",
            )

        if field_name in self.FUZZY_FIELDS or len(word_value) >= self.MIN_FUZZY_LEN:
            score = fuzz.partial_ratio(word_norm, ocr_norm)
            if score >= self.FUZZY_NAME_THRESHOLD:
                return MatchType.FUZZY, score, Severity.LIKELY, f"Tương đồng {score:.0f}%.", ""
            return (
                MatchType.FUZZY,
                score,
                Severity.MANUAL_CHECK,
                f"Tương đồng thấp {score:.0f}%, cần kiểm tra tay.",
                f"Kiểm tra OCR: {ocr_value}",
            )

        # Short generic strings: normalized exact.
        if word_norm == ocr_norm:
            return MatchType.NORMALIZED, 100.0, Severity.LIKELY, "Khớp chuẩn hóa.", ""
        return (
            MatchType.NORMALIZED,
            0.0,
            Severity.MANUAL_CHECK,
            "Không khớp sau chuẩn hóa.",
            f"Kiểm tra OCR: {ocr_value}",
        )

    def _check_residue(self, doc: WordAuditDoc) -> list[AuditIssue]:
        issues = []
        text, _ = cut_at_notary_anchor(doc.raw_text)
        # Placeholder residue.
        for match in re.finditer(r"\[([^\[\]]+)\]", text):
            placeholder = match.group(0)
            issues.append(
                AuditIssue(
                    word_file=doc.word_file,
                    template_type=doc.template_type,
                    field="template_residue",
                    word_value=placeholder,
                    ocr_value="",
                    ocr_page_refs=[],
                    match_type=MatchType.TEMPLATE_RESIDUE,
                    score=0.0,
                    severity=Severity.COPY_TEMPLATE,
                    reason="Placeholder chưa được thay thế.",
                    suggested_fix=f"Điền giá trị thật vào {placeholder}.",
                    manual_check=False,
                )
            )

        # File name vs declarant mismatch.
        declarant_names = [f.value for f in doc.fields if f.name == "declarant_name"]
        file_hint = next((f.value for f in doc.fields if f.name == "file_declarant_hint"), "")
        if file_hint and declarant_names:
            for name in declarant_names:
                score = fuzz.partial_ratio(_normalize_token(file_hint), _normalize_token(name))
                if score < self.FUZZY_NAME_THRESHOLD:
                    issues.append(
                        AuditIssue(
                            word_file=doc.word_file,
                            template_type=doc.template_type,
                            field="file_declarant_hint",
                            word_value=file_hint,
                            ocr_value=name,
                            ocr_page_refs=[],
                            match_type=MatchType.TEMPLATE_RESIDUE,
                            score=score,
                            severity=Severity.COPY_TEMPLATE,
                            reason="Tên file không khớp với ngườ từ chối trong nội dung.",
                            suggested_fix=f"Kiểm tra file này có phải của {name} không.",
                            manual_check=False,
                        )
                    )

        return issues
