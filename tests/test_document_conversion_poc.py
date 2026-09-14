from pathlib import Path
import json

from tools.document_conversion_poc.models import ConversionEnvelope


def test_envelope_is_json_safe_and_has_experimental_version():
    envelope = ConversionEnvelope.for_source(Path("sample.docx"), b"synthetic")

    assert envelope.to_dict()["contract_version"] == "v0.experimental"
    assert envelope.to_dict()["source"]["sha256"]
    json.dumps(envelope.to_dict())
