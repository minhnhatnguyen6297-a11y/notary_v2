from pathlib import Path
import json

import pytest

from tools.document_conversion_poc.models import ConversionEnvelope
from tools.document_conversion_poc.policy import classify_source, decide_ocr


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


def test_wave_riff_is_unsupported_and_cannot_be_allowed_for_ocr():
    route = classify_source(Path("sample.wav"), b"RIFF\x00\x00\x00\x00WAVE")

    assert route == "unsupported"
    assert not decide_ocr(route, policy_version="poc-1", allow_cloud=True).allow
