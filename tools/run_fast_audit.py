# ruff: noqa: E402
"""CLI entry point for fast_text_audit pipeline.

Example:
    python tools/run_fast_audit.py --folder "D:\\Hồ sơ\\06.25 Cù Tất Bích"
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
import time
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv

# Ensure repo root is on path when running from tools/.
repo_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(repo_root))

from services.fast_audit.cache_store import CacheStore
from services.fast_audit.compare_engine import CompareEngine
from services.fast_audit.doc_grouper import DocumentGrouper
from services.fast_audit.models import AuditRunMeta
from services.fast_audit.ocr_runner import OCRRunner
from services.fast_audit.pdf_splitter import PDFSplitter
from services.fast_audit.report_writer import ReportWriter
from services.fast_audit.scan_loader import ScanLoader
from services.fast_audit.word_parser import WordParser


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Soát chính tả Word theo scan OCR nhanh.")
    parser.add_argument("--folder", required=True, help="Thư mục hồ sơ cần audit.")
    parser.add_argument("--output", default=None, help="Thư mục output (mặc định: <folder>\\_audit_out).")
    parser.add_argument("--cache", default=None, help="Thư mục cache (mặc định: <folder>\\_audit_cache).")
    parser.add_argument("--force-ocr", action="store_true", help="Bỏ qua cache OCR, gọi lại API.")
    parser.add_argument("--only-word-glob", default=None, help="Chỉ audit file Word khớp glob (ví dụ: VP_Từ chối*.docx).")
    parser.add_argument("--provider", default=os.getenv("FAST_AUDIT_OCR_PROVIDER", "qwen"), help="OCR provider.")
    parser.add_argument("--base-url", default=os.getenv("FAST_AUDIT_OCR_BASE_URL", ""), help="Base URL OCR API.")
    parser.add_argument("--api-key", default=os.getenv("FAST_AUDIT_OCR_API_KEY", ""), help="API key OCR.")
    parser.add_argument("--model", default=os.getenv("FAST_AUDIT_OCR_MODEL", ""), help="Model OCR.")
    parser.add_argument("--concurrency", type=int, default=int(os.getenv("FAST_AUDIT_OCR_CONCURRENCY", "6")), help="Số request OCR song song.")
    parser.add_argument("--timeout", type=int, default=int(os.getenv("FAST_AUDIT_OCR_TIMEOUT", "60")), help="Timeout OCR (giây).")
    return parser.parse_args(argv)


async def main(argv: list[str] | None = None) -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass
    load_dotenv()
    args = parse_args(argv)

    folder = Path(args.folder).resolve()
    if not folder.exists():
        print(f"ERROR: folder không tồn tại: {folder}", file=sys.stderr)
        return 1

    output_dir = Path(args.output) if args.output else folder / "_audit_out"
    cache_dir = Path(args.cache) if args.cache else folder / "_audit_cache"
    output_dir.mkdir(parents=True, exist_ok=True)
    cache_dir.mkdir(parents=True, exist_ok=True)

    if not args.base_url or not args.api_key:
        print(
            "ERROR: Thiếu FAST_AUDIT_OCR_BASE_URL hoặc FAST_AUDIT_OCR_API_KEY. "
            "Vui lòng thiết lập .env hoặc truyền --base-url / --api-key.",
            file=sys.stderr,
        )
        return 1

    started = datetime.now().isoformat()
    overall_start = time.perf_counter()

    meta = AuditRunMeta(
        started_at=started,
        folder=str(folder),
        output_dir=str(output_dir),
        cache_dir=str(cache_dir),
        ocr_provider=args.provider,
    )

    print(f"[fast_audit] Quét thư mục: {folder}")
    loader = ScanLoader(folder)
    scans, words = loader.load()
    print(f"[fast_audit] {len(scans)} file scan, {len(words)} file Word")

    if args.only_word_glob:
        import fnmatch
        words = [w for w in words if fnmatch.fnmatch(Path(w.path).name, args.only_word_glob)]
        print(f"[fast_audit] Lọc còn {len(words)} file Word theo glob")

    cache = CacheStore(cache_dir)
    if args.force_ocr:
        # Remove cached OCR text files so _run_one will miss cache.
        for child in cache.ocr_text_dir.iterdir():
            child.unlink()

    # Split PDFs / pass images.
    splitter = PDFSplitter(dpi=160, fmt="jpeg", quality=82, image_dir=cache_dir / "page_images")
    pages: list = []
    seq = 1
    for source in scans:
        source_pages = splitter.split(source, start_sequence=seq)
        pages.extend(source_pages)
        seq += len(source_pages)

    # OCR.
    runner = OCRRunner(
        provider=args.provider,
        base_url=args.base_url,
        api_key=args.api_key,
        model=args.model,
        concurrency=args.concurrency,
        timeout=args.timeout,
        cache=cache,
    )
    print(f"[fast_audit] OCR {len(pages)} page với provider={args.provider} ...")
    ocr_pages = await runner.run_batch(pages)
    meta.ocr_calls = runner.calls
    meta.cache_hits = runner.cache_hits

    # Group pages.
    grouper = DocumentGrouper()
    spans = grouper.group(ocr_pages)
    print(f"[fast_audit] {len(spans)} document span")

    # Parse Word.
    word_parser = WordParser()
    word_docs = []
    for source in words:
        try:
            word_docs.append(word_parser.parse(source.path))
        except Exception as exc:
            print(f"WARNING: Không parse được {source.path}: {exc}", file=sys.stderr)

    # Compare.
    engine = CompareEngine(ocr_pages, spans)
    all_issues = []
    for doc in word_docs:
        all_issues.extend(engine.compare(doc))

    # Write reports.
    writer = ReportWriter(output_dir)
    meta.total_ms = int((time.perf_counter() - overall_start) * 1000)
    json_path, md_path = writer.write(meta, ocr_pages, spans, word_docs, all_issues)

    print(f"[fast_audit] Xong. OCR calls={runner.calls}, cache hits={runner.cache_hits}, thờ gian={meta.total_ms}ms")
    print(f"[fast_audit] Report: {md_path}")
    print(f"[fast_audit] JSON:   {json_path}")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(asyncio.run(main()))
    except KeyboardInterrupt:
        print("\n[fast_audit] Đã dừng bởi user.", file=sys.stderr)
        sys.exit(130)
