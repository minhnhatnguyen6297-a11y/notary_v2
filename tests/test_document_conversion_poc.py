import json
import hashlib
from pathlib import Path

import fitz

from tools.document_conversion_poc.models import ConversionEnvelope
from tools.document_conversion_poc.policy import classify_source, decide_ocr


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
