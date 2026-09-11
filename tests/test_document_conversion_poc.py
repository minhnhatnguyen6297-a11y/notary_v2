import json
import hashlib
from pathlib import Path

from tools.document_conversion_poc.models import ConversionEnvelope


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
