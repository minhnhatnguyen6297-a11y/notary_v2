# MarkItDown + Qwen-compatible OCR POC result record

Status: implementation record; no production adoption decision has been made.

## Scope and safety

This record covers the isolated `tools/document_conversion_poc` proof of
concept. It does not change `notary_v2` production OCR, database schema, or
the native DashScope endpoint. The compatible OpenAI surface is a second
provider integration surface that remains a hypothesis until measured.

The harness accepts synthetic fixture paths from a JSON manifest and never
stores source bytes, credentials, raw prompts, or OCR responses. Cloud OCR is
denied unless the caller explicitly enables it and injects an OCR client.

## Reproduction

```powershell
python -m pytest tests/test_document_conversion_poc.py -q
python -m tools.document_conversion_poc.harness --help
python -m tools.document_conversion_poc.harness .\fixtures\manifest.json .\artifacts\report.json
```

Manifest format:

```json
{"sources": [{"path": "fixtures/sample.docx"}, {"path": "fixtures/sample.png"}]}
```

The harness writes the report through a same-directory temporary file and
`os.replace`, so an interrupted run cannot leave a partially-written report.

## Report fields and acceptance table

Each report records the POC revision, installed package versions, fixture
SHA-256 values, route, per-fixture latency, warnings, structured errors,
cloud-call count, aggregate duration, and peak Python allocation measured by
`tracemalloc`. `estimated_cloud_cost_usd` is zero for the offline run; a real
provider run must replace it with the provider's measured estimate and record
the model/configuration without recording secrets.

| Check | Pass condition | Result source |
|---|---|---|
| Deterministic routing | DOCX/XLSX/text PDF local; scanned PDF/raster OCR candidate; unsupported and legacy DOC never cloud | `policy.py` + report routes |
| OCR gate | No provider call without explicit allow decision | `converter.py` + cloud-call count |
| Local conversion | MarkItDown plugins disabled | `converter.py` |
| Provenance boundary | Text PDF emits page-addressable local segments; formats without a stable locator retain explicit unavailable provenance | `converter.py` + `models.py` + warnings |
| Batch resilience | One fixture failure does not abort later fixtures | `summary` and `partial_failure` |
| Compatible transport | Payload/MIME/base64/error and timeout behavior measured with fakes before any cloud smoke | `qwen_compatible.py` tests |

## Decision rule

`adopt` is allowed only when all checks pass on the agreed golden dataset,
including a separately approved cloud smoke. Any failed fixture, missing
provenance, unexpected provider response, or unacceptable latency/cost yields
`iterate`; `reject` is reserved for a measured result that cannot meet the
system constraints. This document is a result template until those measurements
are supplied.
