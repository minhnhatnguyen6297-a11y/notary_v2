import json
import hashlib
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import fitz
from docx import Document
from PIL import Image

from tools.document_conversion_poc import converter as converter_module
from tools.document_conversion_poc.converter import convert_path
from tools.document_conversion_poc.models import ConversionEnvelope
from tools.document_conversion_poc.policy import classify_source, decide_ocr
from tools.document_conversion_poc.qwen_compatible import QwenCompatibleOcr


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
    assert requests[0]["messages"][0]["content"][1]["image_url"]["url"].startswith(
        "data:image/png;base64,"
    )


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
