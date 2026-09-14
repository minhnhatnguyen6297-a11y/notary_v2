from pathlib import Path
import json
from unittest.mock import Mock

import pytest

from tools.document_conversion_poc.converter import convert_path
from tools.document_conversion_poc.models import ConversionEnvelope
from tools.document_conversion_poc.policy import classify_source, decide_ocr


def write_synthetic_docx(path: Path, text: str) -> Path:
    """Create a minimal synthetic ZIP-signature DOCX fixture for routing tests."""

    path.write_bytes(b"PK\x03\x04synthetic-docx")
    path.with_suffix(path.suffix + ".expected.txt").write_text(text, encoding="utf-8")
    return path


def fake_converter(path: Path) -> str:
    return path.with_suffix(path.suffix + ".expected.txt").read_text(encoding="utf-8")


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
