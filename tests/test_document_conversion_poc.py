from pathlib import Path
from dataclasses import replace
from hashlib import sha256
import json
from unittest.mock import Mock

import pytest

from tools.document_conversion_poc.converter import convert_path
from tools.document_conversion_poc.harness import _write_json_atomically, run_manifest
from tools.document_conversion_poc.models import ContentRecord, ConversionEnvelope, PocError
from tools.document_conversion_poc.policy import classify_source, decide_ocr
from tools.document_conversion_poc.qwen_compatible import QwenCompatibleOcr


def write_synthetic_docx(path: Path, text: str) -> Path:
    """Create a minimal synthetic ZIP-signature DOCX fixture for routing tests."""

    path.write_bytes(b"PK\x03\x04synthetic-docx")
    path.with_suffix(path.suffix + ".expected.txt").write_text(text, encoding="utf-8")
    return path


def fake_converter(path: Path) -> str:
    return path.with_suffix(path.suffix + ".expected.txt").read_text(encoding="utf-8")


def write_png(path: Path) -> Path:
    """Create a synthetic raster fixture; its content is never sent to cloud."""

    path.write_bytes(b"\x89PNG\r\n\x1a\nsynthetic-image")
    return path


def write_manifest(directory: Path, fixture_names: list[str]) -> Path:
    """Create a strict, synthetic manifest whose paths are manifest-relative."""

    fixtures = []
    for name in fixture_names:
        path = directory / name
        if name.endswith(".docx"):
            write_synthetic_docx(path, "synthetic fixture")
            mime = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
            route = "local"
        else:
            path.write_bytes(b"unsupported synthetic fixture")
            mime = "application/octet-stream"
            route = "unsupported"
        fixtures.append(
            {
                "sample_id": f"synthetic-{name}",
                "path": name,
                "sha256": sha256(path.read_bytes()).hexdigest(),
                "mime": mime,
                "sensitivity": "synthetic",
                "expected_text": "",
                "expected_facts": [],
                "expected_route": route,
                "required_provenance": False,
            }
        )
    manifest = directory / "manifest.json"
    manifest.write_text(
        json.dumps({"fixtures": fixtures}),
        encoding="utf-8",
    )
    return manifest


class FakeCompletions:
    def __init__(self, text: str | Exception):
        self.text = text
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        if isinstance(self.text, Exception):
            raise self.text
        message = type("Message", (), {"content": self.text})()
        choice = type("Choice", (), {"message": message})()
        return type("Response", (), {"choices": [choice]})()


class FakeClient:
    def __init__(self, text: str | Exception):
        self.completions = FakeCompletions(text)
        self.chat = type("Chat", (), {"completions": self.completions})()


def test_envelope_is_json_safe_and_has_experimental_version():
    envelope = ConversionEnvelope.for_source(Path("sample.docx"), b"synthetic")

    assert envelope.to_dict()["contract_version"] == "v0.experimental"
    assert envelope.to_dict()["source"]["sha256"]
    json.dumps(envelope.to_dict())


@pytest.mark.parametrize(
    ("suffix", "data", "route"),
    [
        (".docx", b"PK\x03\x04", "local"),
        (".xlsx", b"PK\x03\x04", "local"),
        (".pdf", b"%PDF-1.7\ntext", "local"),
        (
            ".pdf",
            b"%PDF-1.7\n1 0 obj\n<< /Type /XObject /Subtype /Image >>",
            "ocr_candidate",
        ),
        (".png", b"\x89PNG\r\n\x1a\n", "ocr_candidate"),
        (".exe", b"MZ", "unsupported"),
    ],
)
def test_classify_source(suffix, data, route):
    assert classify_source(Path("sample" + suffix), data) == route


def test_ocr_gate_denies_without_explicit_permission():
    assert not decide_ocr(
        "ocr_candidate", policy_version="poc-1", allow_cloud=False
    ).allow


def test_docx_local_route_never_calls_ocr(tmp_path):
    path = write_synthetic_docx(tmp_path / "contract.docx", "Nguy\u1ec5n V\u0103n A")
    ocr = Mock()

    envelope = convert_path(path, allow_cloud=True, converter=fake_converter, ocr=ocr)

    assert envelope.content == "Nguy\u1ec5n V\u0103n A"
    assert ocr.call_count == 0
    assert envelope.segments[0].source_ref is None
    assert "provenance_unavailable" in envelope.warnings


def test_wave_riff_is_unsupported_and_cannot_be_allowed_for_ocr():
    route = classify_source(Path("sample.wav"), b"RIFF\x00\x00\x00\x00WAVE")

    assert route == "unsupported"
    assert not decide_ocr(route, policy_version="poc-1", allow_cloud=True).allow


def test_allowed_image_sends_one_data_url_to_fake_client(tmp_path):
    client = FakeClient("CCCD 012345678901")
    ocr = QwenCompatibleOcr(client=client, model="test")

    envelope = convert_path(
        write_png(tmp_path / "id.png"),
        allow_cloud=True,
        converter=fake_converter,
        ocr=ocr,
    )

    assert envelope.content == "CCCD 012345678901"
    assert envelope.ocr_calls[0].status == "completed"
    assert len(client.completions.calls) == 1
    image_url = client.completions.calls[0]["messages"][0]["content"][1]["image_url"]["url"]
    assert image_url.startswith("data:image/png;base64,")


def test_png_magic_with_executable_suffix_uses_validated_png_mime(tmp_path):
    client = FakeClient("CCCD 012345678901")
    ocr = QwenCompatibleOcr(client=client, model="test")

    envelope = convert_path(
        write_png(tmp_path / "id.exe"),
        allow_cloud=True,
        converter=fake_converter,
        ocr=ocr,
    )

    assert envelope.ocr_calls[0].status == "completed"
    image_url = client.completions.calls[0]["messages"][0]["content"][1]["image_url"]["url"]
    assert image_url.startswith("data:image/png;base64,")


def test_non_raster_ocr_candidate_never_reaches_image_provider(tmp_path):
    path = tmp_path / "scanned.pdf"
    path.write_bytes(b"%PDF-1.7\n1 0 obj\n<< /Type /XObject /Subtype /Image >>")
    client = FakeClient("must not be returned")
    ocr = QwenCompatibleOcr(client=client, model="test")

    envelope = convert_path(
        path, allow_cloud=True, converter=fake_converter, ocr=ocr
    )

    assert client.completions.calls == []
    assert envelope.errors[0].code == "ocr_input_not_supported"


def test_denied_image_never_calls_client(tmp_path):
    client = FakeClient("must not be returned")
    ocr = QwenCompatibleOcr(client=client, model="test")

    envelope = convert_path(
        write_png(tmp_path / "id.png"),
        allow_cloud=False,
        converter=fake_converter,
        ocr=ocr,
    )

    assert client.completions.calls == []
    assert envelope.ocr_calls == ()
    assert envelope.errors[0].code == "ocr_not_permitted"


def test_ocr_request_failure_is_structured_and_does_not_leak_exception(tmp_path):
    secret = "https://provider.example/v1?api_key=not-for-output"
    client = FakeClient(TimeoutError(secret))
    ocr = QwenCompatibleOcr(client=client, model="test")

    envelope = convert_path(
        write_png(tmp_path / "id.png"),
        allow_cloud=True,
        converter=fake_converter,
        ocr=ocr,
    )

    error = envelope.errors[0]
    assert error.code == "ocr_request_failed"
    assert error.retryable
    assert secret not in error.message
    assert envelope.ocr_calls[0].status == "failed"


def test_qwen_adapter_requires_all_environment_values(monkeypatch):
    for name in (
        "QWEN_COMPATIBLE_BASE_URL",
        "QWEN_COMPATIBLE_API_KEY",
        "QWEN_COMPATIBLE_MODEL",
    ):
        monkeypatch.delenv(name, raising=False)

    with pytest.raises(ValueError, match="QWEN_COMPATIBLE_BASE_URL") as exc_info:
        QwenCompatibleOcr.from_environment()

    assert "QWEN_COMPATIBLE_API_KEY" in str(exc_info.value)
    assert "QWEN_COMPATIBLE_MODEL" in str(exc_info.value)


def test_harness_reports_partial_failure_without_aborting_batch(tmp_path, monkeypatch):
    from tools.document_conversion_poc import harness

    def fake_convert(path, *, allow_cloud):
        envelope = ConversionEnvelope.for_source(path, path.read_bytes())
        if path.name == "bad.bin":
            return replace(
                envelope,
                errors=(PocError(code="synthetic_failure", message="expected"),),
            )
        return envelope

    monkeypatch.setattr(harness, "convert_path", fake_convert)
    report = run_manifest(
        write_manifest(tmp_path, ["ok.docx", "bad.bin"]),
        tmp_path / "report.json",
        allow_cloud=False,
    )

    assert report["summary"] == {
        "total": 2,
        "completed": 1,
        "failed": 1,
        "passed": 1,
        "not_passed": 1,
    }
    assert json.loads((tmp_path / "report.json").read_text(encoding="utf-8")) == report
    assert report["fixtures"][0]["declared"]["sha256"]
    assert report["fixtures"][0]["actual"]["route"] == "local"
    assert report["fixtures"][0]["checks"]["facts"]["status"] == "not_applicable"
    assert report["fixtures"][1]["partial_failure"]


def test_harness_rejects_manifest_path_escape_and_top_level_list(tmp_path):
    manifest = write_manifest(tmp_path, ["ok.docx"])
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    payload["fixtures"][0]["path"] = "../outside.docx"
    manifest.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ValueError, match="relative"):
        run_manifest(manifest, tmp_path / "report.json", allow_cloud=False)

    manifest.write_text("[]", encoding="utf-8")
    with pytest.raises(ValueError, match="object"):
        run_manifest(manifest, tmp_path / "report.json", allow_cloud=False)


def test_harness_rejects_hash_mismatch_without_converting(tmp_path, monkeypatch):
    from tools.document_conversion_poc import harness

    manifest = write_manifest(tmp_path, ["ok.docx"])
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    payload["fixtures"][0]["sha256"] = "0" * 64
    manifest.write_text(json.dumps(payload), encoding="utf-8")
    monkeypatch.setattr(
        harness,
        "convert_path",
        lambda *args, **kwargs: pytest.fail("hash-mismatched fixture was converted"),
    )

    report = run_manifest(manifest, tmp_path / "report.json", allow_cloud=False)

    assert report["summary"] == {
        "total": 1,
        "completed": 0,
        "failed": 1,
        "passed": 0,
        "not_passed": 1,
    }
    assert report["fixtures"][0]["errors"][0]["code"] == "manifest_sha256_mismatch"


def test_harness_rejects_mime_mismatch_and_marks_requested_facts_not_evaluable(
    tmp_path, monkeypatch
):
    from tools.document_conversion_poc import harness

    manifest = write_manifest(tmp_path, ["ok.docx"])
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    payload["fixtures"][0]["mime"] = "application/pdf"
    manifest.write_text(json.dumps(payload), encoding="utf-8")
    monkeypatch.setattr(
        harness,
        "convert_path",
        lambda *args, **kwargs: pytest.fail("MIME-mismatched fixture was converted"),
    )

    report = run_manifest(manifest, tmp_path / "report.json", allow_cloud=False)

    assert report["fixtures"][0]["errors"][0]["code"] == "manifest_mime_mismatch"

    payload["fixtures"][0]["mime"] = (
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    )
    payload["fixtures"][0]["expected_facts"] = [{"field": "cccd", "value": "synthetic"}]
    manifest.write_text(json.dumps(payload), encoding="utf-8")
    monkeypatch.setattr(
        harness,
        "convert_path",
        lambda path, *, allow_cloud: ConversionEnvelope.for_source(path, path.read_bytes()),
    )

    report = run_manifest(manifest, tmp_path / "report.json", allow_cloud=False)

    assert not report["fixtures"][0]["partial_failure"]
    assert not report["fixtures"][0]["pass"]
    assert report["fixtures"][0]["checks"]["facts"]["status"] == "not_evaluable"


def test_atomic_report_write_preserves_existing_file_on_replace_failure(tmp_path, monkeypatch):
    output_path = tmp_path / "report.json"
    output_path.write_text('{"previous": true}\n', encoding="utf-8")

    def fail_replace(self, target):
        raise OSError("synthetic replacement failure")

    monkeypatch.setattr(Path, "replace", fail_replace)
    with pytest.raises(OSError, match="synthetic replacement failure"):
        _write_json_atomically(output_path, {"new": True})

    assert json.loads(output_path.read_text(encoding="utf-8")) == {"previous": True}
    assert not list(tmp_path.glob(".report.json.*.tmp"))


def test_harness_report_never_serializes_fixture_derived_or_expected_text_and_facts(
    tmp_path, monkeypatch
):
    from tools.document_conversion_poc import harness

    actual_secret = "runtime-text-cccd-987654321012"
    expected_secret = "expected-text-cccd-012345678901"
    expected_fact_secret = "expected-fact-serial-ABC-123"
    manifest = write_manifest(tmp_path, ["ok.docx"])
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    payload["fixtures"][0]["expected_text"] = expected_secret
    payload["fixtures"][0]["expected_facts"] = [{"serial": expected_fact_secret}]
    manifest.write_text(json.dumps(payload), encoding="utf-8")

    def fake_convert(path, *, allow_cloud):
        return replace(
            ConversionEnvelope.for_source(path, path.read_bytes()),
            content_record=ContentRecord(actual_secret),
        )

    monkeypatch.setattr(harness, "convert_path", fake_convert)
    report = run_manifest(manifest, tmp_path / "report.json", allow_cloud=False)
    serialized = json.dumps(report)

    assert actual_secret not in serialized
    assert expected_secret not in serialized
    assert expected_fact_secret not in serialized
    assert report["fixtures"][0]["checks"]["text"]["status"] == "failed"
    assert report["fixtures"][0]["checks"]["facts"]["status"] == "not_evaluable"
