"""Fast text audit pipeline for comparing Word documents against scan OCR.

Independent from the web app's CCCD OCR flows; meant to be run as a CLI tool.
"""

from services.fast_audit.compare_engine import CompareEngine
from services.fast_audit.doc_grouper import DocumentGrouper
from services.fast_audit.models import (
    AuditIssue,
    AuditRunMeta,
    CacheEntry,
    DocumentSpan,
    OCRPage,
    PageInput,
    ScanSource,
    WordAuditDoc,
)
from services.fast_audit.ocr_runner import OCRRunner
from services.fast_audit.pdf_splitter import PDFSplitter
from services.fast_audit.report_writer import ReportWriter
from services.fast_audit.scan_loader import ScanLoader
from services.fast_audit.word_parser import WordParser

__all__ = [
    "AuditIssue",
    "AuditRunMeta",
    "CacheEntry",
    "CompareEngine",
    "DocumentGrouper",
    "DocumentSpan",
    "OCRPage",
    "OCRRunner",
    "PageInput",
    "PDFSplitter",
    "ReportWriter",
    "ScanLoader",
    "ScanSource",
    "WordAuditDoc",
    "WordParser",
]
