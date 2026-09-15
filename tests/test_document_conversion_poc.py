import base64
import json
import hashlib
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import fitz
from docx import Document
from PIL import Image

from tools.document_conversion_poc import converter as converter_module
from tools.document_conversion_poc import harness as harness_module
from tools.document_conversion_poc.converter import convert_path
from tools.document_conversion_poc.harness import run_manifest
from tools.document_conversion_poc.golden_fixtures import materialize_golden_fixtures
from tools.document_conversion_poc.models import Content, ConversionEnvelope, Segment
from tools.document_conversion_poc.policy import classify_source, decide_ocr
from tools.document_conversion_poc.qwen_compatible import OcrRequestError, QwenCompatibleOcr


def test_envelope_is_json_safe_and_has_experimental_version() -> None:
    envelope = ConversionEnvelope.for_source(Path("sample.docx"), b"synthetic")

    payload = envelope.to_dict()

    assert payload["contract_version"] == "v0.experimental"
    digest = hashlib.sha256(b"synthetic").hexdigest()
    assert payload["source"] == {
        "source_id": f"sha256:{digest}",
        "sha256": digest,
        "media_type": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "size_bytes": 9,
    }
    assert payload["converter"] == {
        "name": "unassigned",
        "version": "unknown",
        "config_fingerprint": "unconfigured",
    }
    assert payload["content"] == {"format": "markdown", "value": ""}
    assert payload["segments"] == []
    assert payload["ocr_calls"] == []
    assert json.loads(json.dumps(payload)) == payload


def _pdf_bytes(*, with_text: bool) -> bytes:
    document = fitz.open()
    page = document.new_page()
    if with_text:
        page.insert_text((72, 72), "Synthetic PDF text")
    data = document.tobytes()
    document.close()
    return data


def _text_pdf_bytes(*texts: str) -> bytes:
    document = fitz.open()
    for text in texts:
        page = document.new_page()
        page.insert_text((72, 72), text)
    data = document.tobytes()
    document.close()
    return data


def _scanned_pdf_bytes(page_count: int = 2) -> bytes:
    document = fitz.open()
    for _ in range(page_count):
        document.new_page()
    data = document.tobytes()
    document.close()
    return data


def test_classify_source() -> None:
    cases = [
        (".docx", b"PK\x03\x04", "local"),
        (".xlsx", b"PK\x03\x04", "local"),
        (".pdf", _pdf_bytes(with_text=True), "local"),
        (".pdf", _pdf_bytes(with_text=False), "ocr_candidate"),
        (".png", b"\x89PNG\r\n\x1a\n", "ocr_candidate"),
        (".doc", b"\xd0\xcf\x11\xe0", "legacy_doc_external"),
        (".exe", b"MZ", "unsupported"),
    ]

    for suffix, data, expected in cases:
        assert classify_source(Path("sample" + suffix), data) == expected


def test_ocr_gate_denies_without_explicit_permission() -> None:
    decision = decide_ocr(
        "ocr_candidate",
        policy_version="poc-1",
        allow_cloud=False,
    )

    assert decision.allow is False
    assert decision.reason == "cloud_not_authorized"


def test_malformed_pdf_is_unsupported_without_raising() -> None:
    assert classify_source(Path("broken.pdf"), b"%PDF-not-valid") == "unsupported"


def test_ocr_gate_allows_only_explicit_ocr_candidates() -> None:
    allowed = decide_ocr(
        "ocr_candidate",
        policy_version="poc-1",
        allow_cloud=True,
    )
    local = decide_ocr("local", policy_version="poc-1", allow_cloud=True)
    unsupported = decide_ocr(
        "unsupported",
        policy_version="poc-1",
        allow_cloud=True,
    )
    legacy_doc = decide_ocr(
        "legacy_doc_external",
        policy_version="poc-1",
        allow_cloud=True,
    )

    assert allowed.allow is True
    assert local.allow is False
    assert unsupported.allow is False
    assert legacy_doc.allow is False


def _write_synthetic_docx(path: Path, text: str) -> Path:
    document = Document()
    document.add_paragraph(text)
    document.save(path)
    return path


def _write_manifest(directory: Path, filenames: list[str]) -> Path:
    paths = []
    for filename in filenames:
        path = directory / filename
        if path.suffix == ".docx":
            _write_synthetic_docx(path, "Synthetic manifest document")
        else:
            path.write_bytes(b"not a supported document")
        paths.append({"path": str(path)})

    manifest_path = directory / "manifest.json"
    manifest_path.write_text(json.dumps({"sources": paths}), encoding="utf-8")
    return manifest_path


def test_docx_local_route_never_calls_ocr(tmp_path: Path) -> None:
    path = _write_synthetic_docx(tmp_path / "contract.docx", "Nguyễn Văn A")
    ocr = Mock()

    envelope = convert_path(
        path,
        allow_cloud=True,
        converter=lambda _: "Nguyễn Văn A",
        ocr=ocr,
    )

    assert envelope.content.value == "Nguyễn Văn A"
    ocr.extract.assert_not_called()
    assert envelope.segments[0].source_ref is None
    assert "provenance_unavailable" in envelope.warnings


def test_text_pdf_local_route_records_page_provenance(tmp_path: Path) -> None:
    path = tmp_path / "contract.pdf"
    path.write_bytes(_text_pdf_bytes("Trang mot", "Trang hai"))
    ocr = Mock()

    envelope = convert_path(
        path,
        allow_cloud=True,
        converter=lambda _: "# Markdown from local converter",
        ocr=ocr,
    )

    assert envelope.content == Content(format="markdown", value="# Markdown from local converter")
    assert [(segment.text, segment.source_ref) for segment in envelope.segments] == [
        ("Trang mot\n", {"page": 1}),
        ("Trang hai\n", {"page": 2}),
    ]
    assert envelope.warnings == []
    ocr.extract.assert_not_called()


def test_concrete_markitdown_adapter_disables_plugins(
    tmp_path: Path,
    monkeypatch,
) -> None:
    path = _write_synthetic_docx(tmp_path / "contract.docx", "Nguyễn Văn A")
    calls: list[bool] = []

    class FakeMarkItDown:
        def __init__(self, *, enable_plugins: bool) -> None:
            calls.append(enable_plugins)

        def convert(self, source_path: str) -> SimpleNamespace:
            assert source_path == str(path)
            return SimpleNamespace(markdown="local markdown")

    monkeypatch.setattr(converter_module, "MarkItDown", FakeMarkItDown)

    assert converter_module._markitdown_convert(path) == "local markdown"
    assert calls == [False]


def _write_png(path: Path) -> Path:
    Image.new("RGB", (2, 2), "white").save(path, format="PNG")
    return path


def test_allowed_image_sends_one_data_url_to_fake_client(tmp_path: Path) -> None:
    requests: list[dict] = []

    class FakeCompletions:
        def create(self, **kwargs):
            requests.append(kwargs)
            return SimpleNamespace(
                choices=[SimpleNamespace(message=SimpleNamespace(content="CCCD 012345678901"))]
            )

    fake_client = SimpleNamespace(chat=SimpleNamespace(completions=FakeCompletions()))
    ocr = QwenCompatibleOcr(client=fake_client, model="test-qwen")

    envelope = convert_path(
        _write_png(tmp_path / "id.png"),
        allow_cloud=True,
        converter=lambda _: "unused",
        ocr=ocr,
    )

    assert envelope.content.value == "CCCD 012345678901"
    assert envelope.ocr_calls[0].status == "completed"
    assert envelope.ocr_calls[0].input_hash
    request = requests[0]
    assert request["model"] == "test-qwen"
    data_url = request["messages"][0]["content"][1]["image_url"]["url"]
    prefix, encoded = data_url.split(",", maxsplit=1)
    assert prefix == "data:image/png;base64"
    assert base64.b64decode(encoded) == (tmp_path / "id.png").read_bytes()


def test_scanned_pdf_renders_each_page_and_records_provenance(tmp_path: Path) -> None:
    calls: list[tuple[bytes, str]] = []

    class FakeOcr:
        provider = "fake"
        model = "synthetic"

        def extract(self, image_bytes: bytes, mime_type: str) -> str:
            calls.append((image_bytes, mime_type))
            return f"page-{len(calls)}"

    path = tmp_path / "scan.pdf"
    path.write_bytes(_scanned_pdf_bytes())
    envelope = convert_path(
        path, allow_cloud=True, converter=lambda _: "unused", ocr=FakeOcr(), max_retries=0,
    )

    assert len(calls) == 2
    assert all(mime == "image/png" and data.startswith(b"\x89PNG") for data, mime in calls)
    assert [segment.source_ref for segment in envelope.segments] == [{"page": 1}, {"page": 2}]
    assert all(call.policy_version == "poc-1" and call.allow_reason == "explicit_cloud_authorization" for call in envelope.ocr_calls)


def test_retry_is_bounded_and_reuses_same_page_hash(tmp_path: Path) -> None:
    attempts = 0
    hashes: list[str] = []

    class RetryOnce:
        provider = "fake"
        model = "synthetic"

        def extract(self, image_bytes: bytes, mime_type: str) -> str:
            nonlocal attempts
            attempts += 1
            hashes.append(hashlib.sha256(image_bytes).hexdigest())
            if attempts == 1:
                error = OcrRequestError("temporary", retryable=True)
                raise error
            return "ok"

    path = tmp_path / "scan.png"
    _write_png(path)
    envelope = convert_path(path, allow_cloud=True, converter=lambda _: "unused", ocr=RetryOnce(), max_retries=1)

    assert attempts == 2
    assert hashes[0] == hashes[1]
    assert envelope.content.value == "ok"
    assert [call.attempt for call in envelope.ocr_calls] == [1, 2]


def test_scanned_pdf_partial_failure_keeps_successful_page(tmp_path: Path, monkeypatch) -> None:
    calls = 0

    class FailSecondPage:
        provider = "fake"
        model = "synthetic"

        def extract(self, image_bytes: bytes, mime_type: str) -> str:
            nonlocal calls
            calls += 1
            if calls == 2:
                raise OcrRequestError("second page unavailable", retryable=False)
            return "page-1 text"

    path = tmp_path / "partial.pdf"
    path.write_bytes(_scanned_pdf_bytes(page_count=2))
    envelope = convert_path(path, allow_cloud=True, converter=lambda _: "unused", ocr=FailSecondPage(), max_retries=0)

    assert envelope.content.value == "page-1 text"
    assert [segment.source_ref for segment in envelope.segments] == [{"page": 1}]
    assert envelope.errors[0].code == "ocr_request_failed"
    assert envelope.ocr_calls[-1].source_ref == {"page": 2}

    manifest = tmp_path / "partial-manifest.json"
    manifest.write_text(json.dumps({"sources": [{"sample_id": "GD-partial", "path": str(path)}]}), encoding="utf-8")
    monkeypatch.setattr(harness_module, "convert_path", lambda path, *, allow_cloud: envelope)
    report = run_manifest(manifest, tmp_path / "partial-report.json", allow_cloud=True)
    assert report["results"][0]["status"] == "partial"
    assert report["partial_failure"] is True


def test_denied_image_never_calls_client(tmp_path: Path) -> None:
    ocr = Mock()

    envelope = convert_path(
        _write_png(tmp_path / "id.png"),
        allow_cloud=False,
        converter=lambda _: "unused",
        ocr=ocr,
    )

    ocr.extract.assert_not_called()
    assert envelope.ocr_calls == []


def test_malformed_compatible_response_becomes_structured_error(tmp_path: Path) -> None:
    class FakeCompletions:
        def create(self, **kwargs):
            return SimpleNamespace(choices=[])

    client = SimpleNamespace(chat=SimpleNamespace(completions=FakeCompletions()))
    envelope = convert_path(
        _write_png(tmp_path / "id.png"),
        allow_cloud=True,
        converter=lambda _: "unused",
        ocr=QwenCompatibleOcr(client=client, model="test-qwen"),
    )

    assert envelope.ocr_calls[0].status == "failed"
    assert envelope.errors[0].code == "ocr_request_failed"
    assert envelope.errors[0].retryable is False


def test_compatible_ocr_classifies_retryability(tmp_path: Path) -> None:
    class RequestFailure(Exception):
        def __init__(self, status_code: int) -> None:
            self.status_code = status_code

    class FakeCompletions:
        def __init__(self, error: Exception) -> None:
            self.error = error

        def create(self, **kwargs):
            raise self.error

    def run_with(error: Exception):
        client = SimpleNamespace(chat=SimpleNamespace(completions=FakeCompletions(error)))
        return convert_path(
            _write_png(tmp_path / f"id-{id(error)}.png"),
            allow_cloud=True,
            converter=lambda _: "unused",
            ocr=QwenCompatibleOcr(client=client, model="test-qwen"),
        )

    assert run_with(RequestFailure(401)).errors[0].retryable is False
    assert run_with(RequestFailure(503)).errors[0].retryable is True
    assert run_with(TimeoutError("network timeout")).errors[0].retryable is True


def test_harness_reports_partial_failure_without_aborting_batch(
    tmp_path: Path, monkeypatch
) -> None:
    output_path = tmp_path / "report.json"

    def fake_convert(path: Path, *, allow_cloud: bool):
        source_bytes = path.read_bytes()
        envelope = ConversionEnvelope.for_source(path, source_bytes)
        if path.suffix == ".docx":
            envelope.content = Content(value="synthetic markdown")
        return envelope

    monkeypatch.setattr(harness_module, "convert_path", fake_convert)

    report = run_manifest(
        _write_manifest(tmp_path, ["ok.docx", "bad.bin"]),
        output_path,
        allow_cloud=False,
    )

    assert report["summary"] == {
        "total": 2,
        "completed": 1,
        "failed": 0,
        "non_completed": 1,
    }
    assert output_path.exists()
    assert json.loads(output_path.read_text(encoding="utf-8"))["summary"] == report["summary"]


def test_empty_manifest_cannot_be_adopted(tmp_path: Path) -> None:
    manifest = tmp_path / "empty.json"
    manifest.write_text(json.dumps({"sources": []}), encoding="utf-8")

    report = run_manifest(manifest, tmp_path / "report.json", allow_cloud=False)

    assert report["summary"] == {"total": 0, "completed": 0, "failed": 0, "non_completed": 0}
    assert report["manifest_complete"] is False
    assert report["decision"] == "review_required"


def test_golden_manifest_declares_gd_01_to_gd_07_without_customer_data() -> None:
    manifest = json.loads(
        (Path(__file__).parents[1] / "tools/document_conversion_poc/golden_manifest.json").read_text(
            encoding="utf-8"
        )
    )
    entries = manifest["sources"]
    assert [entry["sample_id"] for entry in entries] == [f"GD-{index:02d}" for index in range(1, 8)]
    required = {
        "sample_id", "path", "mime", "sensitivity", "expected_route", "expected_status",
        "expected_sha256", "expected_text", "expected_facts", "expected_provenance", "not_asserted",
    }
    assert all(required.issubset(entry) and entry["sensitivity"] == "synthetic" for entry in entries)


def test_golden_fixture_materialization_is_byte_repeatable(tmp_path: Path) -> None:
    first_dir = tmp_path / "first"
    second_dir = tmp_path / "second"
    first = materialize_golden_fixtures(first_dir)
    second = materialize_golden_fixtures(second_dir)

    assert [hashlib.sha256(path.read_bytes()).hexdigest() for path in first] == [
        hashlib.sha256(path.read_bytes()).hexdigest() for path in second
    ]


def test_canonical_golden_manifest_hashes_and_routes(tmp_path: Path, monkeypatch) -> None:
    manifest_path = Path(__file__).parents[1] / "tools/document_conversion_poc/golden_manifest.json"
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    fixture_dir = tmp_path / "document_conversion_poc"
    materialized = materialize_golden_fixtures(fixture_dir)
    entries = payload["sources"]

    assert [entry["sample_id"] for entry in entries] == [f"GD-{index:02d}" for index in range(1, 8)]
    assert entries[0]["not_asserted"] == ["text"]
    assert entries[0]["expected_provenance"] == [{"page": 1}]
    assert [hashlib.sha256(path.read_bytes()).hexdigest() for path in materialized] == [
        entry["expected_sha256"] for entry in entries
    ]

    def fake_convert(path: Path, *, allow_cloud: bool):
        return convert_path(
            path,
            allow_cloud=allow_cloud,
            converter=lambda _: "synthetic local conversion",
        )

    monkeypatch.setattr(harness_module, "convert_path", fake_convert)
    for entry in entries:
        entry["path"] = str(fixture_dir / Path(entry["path"]).name)
    isolated_manifest = tmp_path / "golden.json"
    isolated_manifest.write_text(json.dumps(payload), encoding="utf-8")
    report = run_manifest(isolated_manifest, tmp_path / "report.json", allow_cloud=False)

    assert report["manifest_complete"] is True
    assert report["summary"] == {"total": 7, "completed": 3, "failed": 0, "non_completed": 4}
    assert report["cloud_call_count"] == 0
    assert all(not result["expected_mismatches"] for result in report["results"])


def test_manifest_expectations_are_checked_and_sample_id_is_reported(
    tmp_path: Path, monkeypatch
) -> None:
    source = _write_synthetic_docx(tmp_path / "sample.docx", "Synthetic manifest document")
    manifest = tmp_path / "golden.json"
    manifest.write_text(
        json.dumps(
            {
                "sources": [
                    {
                        "sample_id": "GD-test",
                        "path": str(source),
                        "expected_route": "local",
                        "expected_status": "completed",
                        "expected_text": "expected text",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(harness_module, "convert_path", lambda path, *, allow_cloud: ConversionEnvelope.for_source(path, path.read_bytes()))

    report = run_manifest(manifest, tmp_path / "report.json", allow_cloud=False)

    result = report["results"][0]
    assert result["sample_id"] == "GD-test"
    assert result["expected_mismatches"]
    assert result["status"] == "failed"
    assert report["decision"] == "review_required"


def test_harness_canonical_digest_is_repeatable(tmp_path: Path, monkeypatch) -> None:
    source = _write_synthetic_docx(tmp_path / "repeat.docx", "repeatable")
    manifest = tmp_path / "repeat.json"
    manifest.write_text(json.dumps({"sources": [{"sample_id": "GD-repeat", "path": str(source)}]}), encoding="utf-8")
    monkeypatch.setattr(
        harness_module,
        "convert_path",
        lambda path, *, allow_cloud: ConversionEnvelope(
            source=ConversionEnvelope.for_source(path, path.read_bytes()).source,
            created_at="fixed",
            content=Content(value="stable"),
        ),
    )

    first = run_manifest(manifest, tmp_path / "first.json", allow_cloud=False)
    second = run_manifest(manifest, tmp_path / "second.json", allow_cloud=False)

    assert first["canonical_result_sha256"] == second["canonical_result_sha256"]
    assert "working_tree_dirty" in first
