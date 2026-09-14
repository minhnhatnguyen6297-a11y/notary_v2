"""Offline-first manifest measurement harness for the isolated conversion POC."""

from __future__ import annotations

import argparse
from hashlib import sha256
from importlib.metadata import PackageNotFoundError, version
import json
from pathlib import Path
import re
import subprocess
import tempfile
from time import perf_counter
import tracemalloc
from typing import Any

from .converter import convert_path
from .models import ConversionEnvelope, PocError
from .policy import classify_source


POC_REVISION = "2026-09-11-markitdown-qwen-poc"
_POC_PACKAGES = ("markitdown", "markitdown-ocr", "openai")
_FIXTURE_FIELDS = frozenset(
    {
        "sample_id",
        "path",
        "sha256",
        "mime",
        "sensitivity",
        "expected_text",
        "expected_facts",
        "expected_route",
        "required_provenance",
    }
)
_DOCX_MIME = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
_XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def run_manifest(
    manifest_path: Path, output_path: Path, *, allow_cloud: bool
) -> dict[str, Any]:
    """Run a strict synthetic-fixture manifest and atomically write its report.

    Every fixture is manifest-relative and hash/MIME validated before conversion.
    ``allow_cloud`` is required and the CLI makes it opt-in. A bad fixture is a
    reportable item failure; a malformed manifest is rejected before any fixture
    or provider is touched.
    """

    manifest_path = Path(manifest_path)
    output_path = Path(output_path)
    manifest_directory = manifest_path.parent.resolve()
    fixtures = _read_manifest(manifest_path, manifest_directory)
    tracemalloc.start()
    started_at = perf_counter()
    items = [
        _run_fixture(manifest_directory, fixture, allow_cloud=allow_cloud)
        for fixture in fixtures
    ]
    _, peak_memory_bytes = tracemalloc.get_traced_memory()
    tracemalloc.stop()

    completed = sum(not item["partial_failure"] for item in items)
    passed = sum(item["pass"] for item in items)
    report: dict[str, Any] = {
        "poc_revision": POC_REVISION,
        "baseline_commit": _baseline_commit(Path(__file__).resolve().parents[2]),
        "allow_cloud": allow_cloud,
        "package_versions": _package_versions(),
        "memory_measurement": {
            "method": "tracemalloc_peak_bytes (Python allocations only)",
            "peak_bytes": peak_memory_bytes,
        },
        "duration_ms": _duration_ms(started_at),
        "cost_estimate": _cost_estimate(sum(item["cloud_call_count"] for item in items)),
        "summary": {
            "total": len(items),
            "completed": completed,
            "failed": len(items) - completed,
            "passed": passed,
            "not_passed": len(items) - passed,
        },
        "fixtures": items,
    }
    _write_json_atomically(output_path, report)
    return report


def _read_manifest(manifest_path: Path, manifest_directory: Path) -> list[dict[str, Any]]:
    """Validate the JSON manifest before any source file is read or converted."""

    raw = json.loads(manifest_path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError("Manifest must be a JSON object with a non-empty fixtures list.")
    entries = raw.get("fixtures")
    if not isinstance(entries, list) or not entries:
        raise ValueError("Manifest fixtures must be a non-empty list.")

    fixtures: list[dict[str, Any]] = []
    sample_ids: set[str] = set()
    for index, entry in enumerate(entries):
        if not isinstance(entry, dict):
            raise ValueError(f"Fixture {index} must be an object.")
        missing = _FIXTURE_FIELDS.difference(entry)
        if missing:
            missing_names = ", ".join(sorted(missing))
            raise ValueError(f"Fixture {index} is missing required fields: {missing_names}.")
        fixture = dict(entry)
        _validate_fixture(fixture, index, manifest_directory)
        sample_id = fixture["sample_id"]
        if sample_id in sample_ids:
            raise ValueError(f"Fixture {index} repeats sample_id {sample_id!r}.")
        sample_ids.add(sample_id)
        fixture["sha256"] = fixture["sha256"].lower()
        fixtures.append(fixture)
    return fixtures


def _validate_fixture(fixture: dict[str, Any], index: int, manifest_directory: Path) -> None:
    for field in ("sample_id", "path", "mime", "sensitivity", "expected_route"):
        if not isinstance(fixture[field], str) or not fixture[field].strip():
            raise ValueError(f"Fixture {index} field {field!r} must be a non-empty string.")
    if not isinstance(fixture["expected_text"], str):
        raise ValueError(f"Fixture {index} field 'expected_text' must be a string.")
    if not isinstance(fixture["expected_facts"], (list, dict)):
        raise ValueError(f"Fixture {index} field 'expected_facts' must be a list or object.")
    if not isinstance(fixture["required_provenance"], bool):
        raise ValueError(f"Fixture {index} field 'required_provenance' must be boolean.")
    if not re.fullmatch(r"[0-9a-fA-F]{64}", fixture["sha256"]):
        raise ValueError(f"Fixture {index} field 'sha256' must be a SHA-256 hex digest.")

    relative_path = Path(fixture["path"])
    if relative_path.is_absolute() or ".." in relative_path.parts:
        raise ValueError(f"Fixture {index} path must be relative and stay under the manifest directory.")
    candidate = (manifest_directory / relative_path).resolve()
    if not candidate.is_relative_to(manifest_directory):
        raise ValueError(f"Fixture {index} path must stay under the manifest directory.")


def _run_fixture(
    manifest_directory: Path, fixture: dict[str, Any], *, allow_cloud: bool
) -> dict[str, Any]:
    path = (manifest_directory / fixture["path"]).resolve()
    started_at = perf_counter()
    if tracemalloc.is_tracing():
        tracemalloc.reset_peak()
    envelope: ConversionEnvelope | None = None
    actual_sha256: str | None = None
    actual_mime: str | None = None
    actual_route: str | None = None
    errors: list[dict[str, Any]] = []
    warnings: list[str] = []
    cloud_call_count = 0
    try:
        source_bytes = path.read_bytes()
        actual_sha256 = sha256(source_bytes).hexdigest()
        actual_mime = _actual_mime(path, source_bytes)
        actual_route = classify_source(path, source_bytes)
        if actual_sha256 != fixture["sha256"]:
            errors.append(
                _error("manifest_sha256_mismatch", "Fixture SHA-256 does not match the manifest.")
            )
        if actual_mime != fixture["mime"]:
            errors.append(_error("manifest_mime_mismatch", "Fixture MIME does not match the manifest."))
        if not errors:
            envelope = convert_path(path, allow_cloud=allow_cloud)
            errors.extend(error.to_dict() for error in envelope.errors)
            warnings = list(envelope.warnings)
            cloud_call_count = len(envelope.ocr_calls)
    except Exception as exc:
        errors.append(
            _error("harness_fixture_failed", f"Fixture processing failed: {type(exc).__name__}.")
        )

    actual_text = envelope.content if envelope is not None else None
    actual_provenance = _has_provenance(envelope)
    checks = _checks(fixture, actual_sha256, actual_mime, actual_route, actual_text, actual_provenance)
    reasons = [check["reason"] for check in checks.values() if check["status"] == "failed"]
    reasons.extend(error["code"] for error in errors)
    peak_memory_bytes = tracemalloc.get_traced_memory()[1] if tracemalloc.is_tracing() else None
    partial_failure = bool(errors)
    passed = not partial_failure and all(
        check["status"] in {"passed", "not_applicable"} for check in checks.values()
    )
    return {
        "sample_id": fixture["sample_id"],
        "declared": _safe_declared(fixture),
        "actual": {
            "sha256": actual_sha256,
            "mime": actual_mime,
            "route": actual_route,
            "text": _text_metadata(actual_text),
            "facts": _facts_metadata(None),
            "provenance_present": actual_provenance,
        },
        "checks": checks,
        "duration_ms": _duration_ms(started_at),
        "peak_memory_bytes": peak_memory_bytes,
        "cloud_call_count": cloud_call_count,
        "token_count": {"value": None, "status": "unavailable"},
        "cost_estimate": _cost_estimate(cloud_call_count),
        "warnings": warnings,
        "errors": errors,
        "partial_failure": partial_failure,
        "pass": passed,
        "reasons": reasons,
    }


def _checks(
    fixture: dict[str, Any],
    actual_sha256: str | None,
    actual_mime: str | None,
    actual_route: str | None,
    actual_text: str | None,
    actual_provenance: bool,
) -> dict[str, dict[str, Any]]:
    facts_requested = bool(fixture["expected_facts"])
    return {
        "sha256": _comparison(fixture["sha256"], actual_sha256, "Fixture SHA-256 differs from manifest."),
        "mime": _comparison(fixture["mime"], actual_mime, "Fixture MIME differs from manifest."),
        "route": _comparison(fixture["expected_route"], actual_route, "Actual route differs from expected route."),
        "text": _text_comparison(fixture["expected_text"], actual_text),
        "facts": {
            "expected": _facts_metadata(fixture["expected_facts"]),
            "actual": _facts_metadata(None),
            "status": "not_evaluable" if facts_requested else "not_applicable",
            "passed": not facts_requested,
            "reason": "Fact extraction is not implemented in this POC."
            if facts_requested
            else "No expected facts were declared.",
        },
        "provenance": _comparison(
            fixture["required_provenance"],
            actual_provenance,
            "Actual provenance availability differs from the requirement.",
        ),
    }


def _safe_declared(fixture: dict[str, Any]) -> dict[str, Any]:
    """Return report-safe manifest metadata without expected contents."""

    return {
        "sample_id": fixture["sample_id"],
        "path": fixture["path"],
        "sha256": fixture["sha256"],
        "mime": fixture["mime"],
        "sensitivity": fixture["sensitivity"],
        "expected_text": _text_metadata(fixture["expected_text"]),
        "expected_facts": _facts_metadata(fixture["expected_facts"]),
        "expected_route": fixture["expected_route"],
        "required_provenance": fixture["required_provenance"],
    }


def _text_metadata(text: str | None) -> dict[str, Any]:
    return {
        "present": text is not None,
        "type": "string" if text is not None else None,
        "length": len(text) if text is not None else None,
        "sha256": sha256(text.encode("utf-8")).hexdigest() if text is not None else None,
    }


def _facts_metadata(facts: list[Any] | dict[str, Any] | None) -> dict[str, Any]:
    if facts is None:
        return {"present": False, "type": None, "count": 0, "sha256": None}
    encoded = json.dumps(facts, ensure_ascii=True, separators=(",", ":"), sort_keys=True)
    return {
        "present": True,
        "type": "list" if isinstance(facts, list) else "object",
        "count": len(facts),
        "sha256": sha256(encoded.encode("utf-8")).hexdigest(),
    }


def _text_comparison(expected: str, actual: str | None) -> dict[str, Any]:
    expected_metadata = _text_metadata(expected)
    actual_metadata = _text_metadata(actual)
    if actual is None:
        return {
            "expected": expected_metadata,
            "actual": actual_metadata,
            "status": "not_evaluable",
            "passed": False,
            "reason": "Converted text is unavailable.",
        }
    passed = expected == actual
    return {
        "expected": expected_metadata,
        "actual": actual_metadata,
        "status": "passed" if passed else "failed",
        "passed": passed,
        "reason": "Matched expected text." if passed else "Actual text differs from expected text.",
    }


def _comparison(expected: Any, actual: Any, failure_reason: str) -> dict[str, Any]:
    if actual is None:
        return {
            "expected": expected,
            "actual": actual,
            "status": "not_evaluable",
            "passed": False,
            "reason": failure_reason,
        }
    passed = expected == actual
    return {
        "expected": expected,
        "actual": actual,
        "status": "passed" if passed else "failed",
        "passed": passed,
        "reason": "Matched expected value." if passed else failure_reason,
    }


def _has_provenance(envelope: ConversionEnvelope | None) -> bool:
    return bool(envelope and envelope.segments and all(segment.source_ref for segment in envelope.segments))


def _actual_mime(path: Path, data: bytes) -> str:
    suffix = path.suffix.lower()
    if data.startswith(b"PK\x03\x04"):
        if suffix == ".docx":
            return _DOCX_MIME
        if suffix == ".xlsx":
            return _XLSX_MIME
        return "application/zip"
    if data.startswith(b"%PDF-"):
        return "application/pdf"
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if data.startswith((b"GIF87a", b"GIF89a")):
        return "image/gif"
    if data.startswith(b"BM"):
        return "image/bmp"
    if data.startswith((b"II*\x00", b"MM\x00*")):
        return "image/tiff"
    if len(data) >= 12 and data.startswith(b"RIFF") and data[8:12] == b"WEBP":
        return "image/webp"
    return "application/octet-stream"


def _cost_estimate(cloud_call_count: int) -> dict[str, Any]:
    if cloud_call_count == 0:
        return {"currency": "USD", "amount": 0.0, "status": "no_cloud_calls"}
    return {
        "currency": "USD",
        "amount": None,
        "status": "unavailable_no_provider_price_schedule",
    }


def _error(code: str, message: str) -> dict[str, Any]:
    return PocError(code=code, message=message).to_dict()


def _package_versions() -> dict[str, str | None]:
    versions: dict[str, str | None] = {}
    for package in _POC_PACKAGES:
        try:
            versions[package] = version(package)
        except PackageNotFoundError:
            versions[package] = None
    return versions


def _baseline_commit(cwd: Path) -> str | None:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=cwd,
            capture_output=True,
            check=True,
            text=True,
            timeout=2,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return result.stdout.strip() or None


def _duration_ms(started_at: float) -> int:
    return int((perf_counter() - started_at) * 1000)


def _write_json_atomically(output_path: Path, report: dict[str, Any]) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        dir=output_path.parent,
        prefix=f".{output_path.name}.",
        suffix=".tmp",
        delete=False,
    ) as temporary:
        temporary_path = Path(temporary.name)
        json.dump(report, temporary, ensure_ascii=False, indent=2, sort_keys=True)
        temporary.write("\n")
    try:
        temporary_path.replace(output_path)
    except Exception:
        temporary_path.unlink(missing_ok=True)
        raise


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run the offline-first document conversion POC manifest."
    )
    parser.add_argument("manifest", type=Path, help="Strict JSON manifest of synthetic fixtures")
    parser.add_argument("output", type=Path, help="Destination JSON measurement report")
    parser.add_argument(
        "--allow-cloud",
        action="store_true",
        help="Explicitly permit policy-approved cloud OCR candidates (default: disabled)",
    )
    args = parser.parse_args()
    report = run_manifest(args.manifest, args.output, allow_cloud=args.allow_cloud)
    print(json.dumps(report["summary"], sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
