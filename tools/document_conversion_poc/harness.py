from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import subprocess
import tempfile
from time import perf_counter
import tracemalloc
from typing import Any

from .converter import convert_path
from .policy import classify_source


_PACKAGE_NAMES = ("markitdown", "markitdown-ocr", "openai", "PyMuPDF", "Pillow")


def _revision() -> str:
    try:
        return subprocess.run(
            ["git", "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return "unknown"


def _package_versions() -> dict[str, str]:
    versions: dict[str, str] = {}
    for name in _PACKAGE_NAMES:
        try:
            versions[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            versions[name] = "not-installed"
    return versions


def _load_manifest(manifest_path: Path) -> list[Path]:
    # Accept manifests authored by Windows PowerShell (which may prepend a
    # UTF-8 BOM) while always emitting BOM-free report JSON.
    payload = json.loads(manifest_path.read_text(encoding="utf-8-sig"))
    entries = payload.get("sources", payload) if isinstance(payload, dict) else payload
    if not isinstance(entries, list):
        raise ValueError("manifest must contain a JSON list or a sources list")
    paths: list[Path] = []
    for entry in entries:
        raw_path = entry.get("path") if isinstance(entry, dict) else entry
        if not isinstance(raw_path, str) or not raw_path:
            raise ValueError("each manifest source must provide a non-empty path")
        paths.append(Path(raw_path))
    return paths


def _error_dict(error: Any) -> dict[str, Any]:
    return error.to_dict() if hasattr(error, "to_dict") else {"message": str(error)}


def run_manifest(manifest_path: Path, output_path: Path, *, allow_cloud: bool) -> dict[str, Any]:
    """Run synthetic fixtures and write a reproducible, atomic JSON report.

    The harness deliberately does not configure an OCR client. Cloud use is
    therefore opt-in at the router boundary and still requires an injected
    client supplied by a caller; this CLI remains offline by default.
    """

    paths = _load_manifest(manifest_path)
    results: list[dict[str, Any]] = []
    total_started = perf_counter()
    tracemalloc.start()
    try:
        for path in paths:
            started = perf_counter()
            source_hash = None
            route = "unreadable"
            try:
                source_bytes = path.read_bytes()
                source_hash = hashlib.sha256(source_bytes).hexdigest()
                route = classify_source(path, source_bytes)
                envelope = convert_path(path, allow_cloud=allow_cloud)
                failed = bool(envelope.errors) or not envelope.content.value.strip()
                results.append(
                    {
                        "path": str(path),
                        "sha256": source_hash,
                        "route": route,
                        "status": "failed" if failed else "completed",
                        "duration_ms": round((perf_counter() - started) * 1000),
                        "warnings": list(envelope.warnings),
                        "errors": [_error_dict(error) for error in envelope.errors],
                        "cloud_call_count": len(envelope.ocr_calls),
                    }
                )
            except Exception as exc:
                results.append(
                    {
                        "path": str(path),
                        "sha256": source_hash,
                        "route": route,
                        "status": "failed",
                        "duration_ms": round((perf_counter() - started) * 1000),
                        "warnings": [],
                        "errors": [{"code": "harness_item_failed", "message": str(exc)}],
                        "cloud_call_count": 0,
                    }
                )
    finally:
        _, peak_bytes = tracemalloc.get_traced_memory()
        tracemalloc.stop()

    completed = sum(item["status"] == "completed" for item in results)
    failed = len(results) - completed
    report: dict[str, Any] = {
        "poc_revision": _revision(),
        "manifest": str(manifest_path),
        "allow_cloud": allow_cloud,
        "summary": {"total": len(paths), "completed": completed, "failed": failed},
        "duration_ms": round((perf_counter() - total_started) * 1000),
        "measurements": {
            "latency": "duration_ms measured with time.perf_counter per fixture",
            "memory": "peak Python allocations measured with tracemalloc",
            "peak_memory_bytes": peak_bytes,
        },
        "packages": _package_versions(),
        "cloud_call_count": sum(item["cloud_call_count"] for item in results),
        "estimated_cloud_cost_usd": 0.0,
        "results": results,
        "decision": "adopt" if failed == 0 else "iterate",
        "partial_failure": 0 < completed < len(paths),
    }

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        mode="w", encoding="utf-8", dir=output_path.parent, delete=False, suffix=".tmp"
    ) as temporary:
        temporary_path = Path(temporary.name)
        json.dump(report, temporary, ensure_ascii=False, indent=2)
        temporary.write("\n")
        temporary.flush()
        os.fsync(temporary.fileno())
    os.replace(temporary_path, output_path)
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the offline document-conversion POC harness")
    parser.add_argument("manifest", type=Path, nargs="?", help="JSON manifest with a sources list")
    parser.add_argument("output", type=Path, nargs="?", help="Atomic JSON report path")
    parser.add_argument("--allow-cloud", action="store_true", help="allow OCR candidates (requires injected client)")
    args = parser.parse_args()
    if args.manifest is None or args.output is None:
        parser.print_help()
        return 0
    report = run_manifest(args.manifest, args.output, allow_cloud=args.allow_cloud)
    print(json.dumps(report["summary"], ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
