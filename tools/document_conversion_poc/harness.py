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


def _working_tree_state() -> dict[str, Any]:
    try:
        result = subprocess.run(
            ["git", "status", "--porcelain", "--untracked-files=all"],
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.SubprocessError):
        return {"dirty": None, "paths": []}
    paths = [line[3:] for line in result.stdout.splitlines() if len(line) >= 4]
    return {"dirty": bool(paths), "paths": paths}


def _package_versions() -> dict[str, str]:
    versions: dict[str, str] = {}
    for name in _PACKAGE_NAMES:
        try:
            versions[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            versions[name] = "not-installed"
    return versions


def _load_manifest(manifest_path: Path) -> list[dict[str, Any]]:
    # Accept manifests authored by Windows PowerShell (which may prepend a
    # UTF-8 BOM) while always emitting BOM-free report JSON.
    payload = json.loads(manifest_path.read_text(encoding="utf-8-sig"))
    entries = payload.get("sources", payload) if isinstance(payload, dict) else payload
    if not isinstance(entries, list):
        raise ValueError("manifest must contain a JSON list or a sources list")
    entries_out: list[dict[str, Any]] = []
    for entry in entries:
        raw_path = entry.get("path") if isinstance(entry, dict) else entry
        if not isinstance(raw_path, str) or not raw_path:
            raise ValueError("each manifest source must provide a non-empty path")
        normalized = dict(entry) if isinstance(entry, dict) else {"path": raw_path}
        normalized["path"] = Path(raw_path)
        entries_out.append(normalized)
    return entries_out


def _expected_mismatches(expected: dict[str, Any], actual: dict[str, Any]) -> list[str]:
    """Compare only declared golden fields; absence of expectations is not a pass."""
    mismatches: list[str] = []
    not_asserted = set(expected.get("not_asserted", []))
    aliases = {"route": "expected_route", "status": "expected_status", "sha256": "expected_sha256"}
    for key, expected_key in aliases.items():
        if key not in not_asserted and expected_key in expected and expected[expected_key] is not None and expected[expected_key] != actual.get(key):
            mismatches.append(f"{key}: expected {expected[expected_key]!r}, got {actual.get(key)!r}")
    for key in ("text", "facts", "provenance"):
        expected_key = f"expected_{key}"
        if key not in not_asserted and expected_key in expected and expected[expected_key] is not None:
            actual_value = actual.get(key)
            if actual_value != expected[expected_key]:
                mismatches.append(f"{key}: expected value does not match actual")
    return mismatches


def _error_dict(error: Any) -> dict[str, Any]:
    return error.to_dict() if hasattr(error, "to_dict") else {"message": str(error)}


def _canonical_digest(results: list[dict[str, Any]]) -> str:
    stable = []
    for result in results:
        stable.append({
            key: result.get(key)
            for key in ("sample_id", "sha256", "route", "status", "text", "facts", "provenance", "errors", "cloud_call_count")
        })
    payload = json.dumps(stable, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def run_manifest(manifest_path: Path, output_path: Path, *, allow_cloud: bool) -> dict[str, Any]:
    """Run synthetic fixtures and write a reproducible, atomic JSON report.

    The harness deliberately does not configure an OCR client. Cloud use is
    therefore opt-in at the router boundary and still requires an injected
    client supplied by a caller; this CLI remains offline by default.
    """

    manifest_entries = _load_manifest(manifest_path)
    results: list[dict[str, Any]] = []
    total_started = perf_counter()
    tracemalloc.start()
    try:
        for entry in manifest_entries:
            path = entry["path"]
            started = perf_counter()
            source_hash = None
            route = "unreadable"
            try:
                source_bytes = path.read_bytes()
                source_hash = hashlib.sha256(source_bytes).hexdigest()
                route = classify_source(path, source_bytes)
                envelope = convert_path(path, allow_cloud=allow_cloud)
                # A fixture is partial when at least one page/segment survived;
                # a fixture with no usable output is failed.
                if envelope.errors:
                    status = "partial" if envelope.segments else "failed"
                elif route == "unsupported":
                    status = "unsupported"
                elif route in {"ocr_candidate", "legacy_doc_external"} and not envelope.content.value.strip():
                    status = "denied" if not allow_cloud else "partial"
                elif not envelope.content.value.strip():
                    status = "failed"
                else:
                    status = "completed"
                actual = {
                        "sample_id": entry.get("sample_id"),
                        "path": str(path),
                        "sha256": source_hash,
                        "route": route,
                        "status": status,
                        "duration_ms": round((perf_counter() - started) * 1000),
                        "warnings": list(envelope.warnings),
                        "errors": [_error_dict(error) for error in envelope.errors],
                        "cloud_call_count": len(envelope.ocr_calls),
                        "text": envelope.content.value,
                        "facts": [],
                        "provenance": [segment.source_ref for segment in envelope.segments],
                        "expected": {
                            key: entry[key]
                            for key in entry
                            if key.startswith("expected_")
                        },
                    }
                actual["expected_mismatches"] = _expected_mismatches(entry, actual)
                if actual["expected_mismatches"]:
                    actual["status"] = "failed"
                results.append(actual)
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
                        "expected_mismatches": [f"exception: {exc}"],
                    }
                )
    finally:
        _, peak_bytes = tracemalloc.get_traced_memory()
        tracemalloc.stop()

    completed = sum(item["status"] == "completed" for item in results)
    failed = sum(item["status"] == "failed" for item in results)
    non_completed = len(results) - completed
    working_tree = _working_tree_state()
    report: dict[str, Any] = {
        "poc_revision": _revision(),
        "working_tree_dirty": working_tree["dirty"],
        "working_tree_paths": working_tree["paths"],
        "manifest": str(manifest_path),
        "allow_cloud": allow_cloud,
        "summary": {
            "total": len(manifest_entries),
            "completed": completed,
            "failed": failed,
            "non_completed": non_completed,
        },
        "duration_ms": round((perf_counter() - total_started) * 1000),
        "measurements": {
            "latency": "duration_ms measured with time.perf_counter per fixture",
            "memory": "peak Python allocations measured with tracemalloc",
            "peak_memory_bytes": peak_bytes,
        },
        "packages": _package_versions(),
        "cloud_call_count": sum(item["cloud_call_count"] for item in results),
        "estimated_cloud_cost_usd": None,
        "results": results,
        "canonical_result_sha256": _canonical_digest(results),
        "decision": "review_required",
        "decision_basis": "technical measurement only; human approval is required",
        "manifest_complete": bool(manifest_entries) and all(
            {
                "sample_id",
                "mime",
                "sensitivity",
                "expected_route",
                "expected_status",
                "expected_text",
                "expected_facts",
                "expected_provenance",
            }.issubset(entry)
            for entry in manifest_entries
        ),
        "partial_failure": any(item["status"] == "partial" for item in results)
        or (completed > 0 and failed > 0),
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
    parser.add_argument(
        "--materialize-golden", action="store_true",
        help="create synthetic GD-01..07 files beside the manifest before running",
    )
    args = parser.parse_args()
    if args.manifest is None or args.output is None:
        parser.print_help()
        return 0
    if args.materialize_golden:
        from .golden_fixtures import materialize_golden_fixtures

        repo_root = args.manifest.parents[2] if len(args.manifest.parents) > 2 else args.manifest.parent
        materialize_golden_fixtures(repo_root / "tests" / "fixtures" / "document_conversion_poc")
    report = run_manifest(args.manifest, args.output, allow_cloud=args.allow_cloud)
    print(json.dumps(report["summary"], ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
