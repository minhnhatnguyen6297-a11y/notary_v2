from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class SourceKind(str, Enum):
    PDF = "pdf"
    IMAGE = "image"
    WORD = "word"


class DocType(str, Enum):
    TRICH_LUC_KHAI_TU = "trich_luc_khai_tu"
    CAN_CUOC = "can_cuoc"
    GIAY_CHUNG_NHAN = "giay_chung_nhan"
    VAN_BAN_TU_CHOI = "van_ban_tu_choi"
    BIEN_BAN_HOP_GIA_DINH = "bien_ban_hop_gia_dinh"
    SO_DO_THUA_KE = "so_do_thua_ke"
    DON_XAC_NHAN = "don_xac_nhan"
    UNKNOWN = "unknown"


class MatchType(str, Enum):
    EXACT = "exact"
    NORMALIZED = "normalized"
    FUZZY = "fuzzy"
    MISSING = "missing"
    TEMPLATE_RESIDUE = "template_residue"


class Severity(str, Enum):
    CERTAIN = "certain"
    LIKELY = "likely"
    COPY_TEMPLATE = "copy_template"
    MANUAL_CHECK = "manual_check"


@dataclass
class ScanSource:
    source_id: str
    path: str
    kind: SourceKind
    rel_path: str
    size: int
    mtime: float
    sha256: str


@dataclass
class PageInput:
    page_id: str
    sequence_no: int
    source_file: str
    source_kind: SourceKind
    page_no: int
    page_hash: str
    image_path: str
    bytes: bytes


@dataclass
class OCRPage:
    page_id: str
    page_hash: str
    sequence_no: int
    source_file: str
    page_no: int
    text: str
    confidence: float | None = None
    provider: str = ""
    latency_ms: int = 0
    from_cache: bool = False


@dataclass
class DocumentSpan:
    doc_span_id: str
    doc_type: DocType
    page_ids: list[str]
    start_sequence: int
    end_sequence: int
    source_files: list[str]
    header_snippet: str = ""
    excluded_from_compare: bool = False


@dataclass
class WordField:
    name: str
    value: str
    context: str = ""


@dataclass
class WordAuditDoc:
    word_file: str
    template_type: str
    raw_text: str
    paragraphs: list[str]
    fields: list[WordField]
    anchors_found: list[str] = field(default_factory=list)
    mode: str = "filled_document"


@dataclass
class AuditIssue:
    word_file: str
    template_type: str
    field: str
    word_value: str
    ocr_value: str
    ocr_page_refs: list[str]
    match_type: MatchType
    score: float
    severity: Severity
    reason: str
    suggested_fix: str
    manual_check: bool = False


@dataclass
class CacheEntry:
    key: str
    path: str
    kind: str


@dataclass
class AuditRunMeta:
    started_at: str
    folder: str
    output_dir: str
    cache_dir: str
    ocr_provider: str
    ocr_calls: int = 0
    cache_hits: int = 0
    total_pages: int = 0
    total_word_files: int = 0
    issues_found: int = 0
    total_ms: int = 0
