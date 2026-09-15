# MarkItDown/Qwen POC result record

Status: **not run / no decision**

This is the result record for the isolated
`tools/document_conversion_poc/` experiment. It is not a production OCR result,
integration contract, or approval to modify the existing document-intake flow.

## Strict synthetic-fixture manifest

The harness accepts one JSON object with a non-empty `fixtures` list. Each
fixture must supply every field below. Paths are relative to the manifest
directory and cannot be absolute or contain `..`; the resolved path must remain
under that directory. Before conversion, the harness computes the SHA-256 and
content-derived MIME type, reports both, and rejects either mismatch without
calling the converter.

```json
{
  "fixtures": [
    {
      "sample_id": "synthetic-docx-001",
      "path": "fixtures/synthetic-contract.docx",
      "sha256": "<64 lowercase hex characters>",
      "mime": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
      "sensitivity": "synthetic",
      "expected_text": "Expected synthetic content",
      "expected_facts": [],
      "expected_route": "local",
      "required_provenance": false
    }
  ]
}
```

Only synthetic or demonstrably de-identified fixtures may be used. Do not
commit source documents, images, OCR responses containing personal data, or
secrets. Record fixture metadata and hashes, never fixture contents.

## Run identity

| Field | Value |
| --- | --- |
| Run date/time (UTC) | `TBD` |
| POC revision | `2026-09-11-markitdown-qwen-poc` |
| Baseline commit | `TBD` |
| Manifest path | `TBD` |
| Cloud explicitly allowed | `false` |
| Memory measurement method | `tracemalloc_peak_bytes (Python allocations only)` |

Record package versions from the generated report, not from dependency pins.

| Package | Version |
| --- | --- |
| `markitdown` | `TBD` |
| `markitdown-ocr` | `TBD` |
| `openai` | `TBD` |

## Fixture measurements and assessment

The JSON report stores declared source metadata plus actual SHA-256, MIME, route,
facts availability, and provenance availability for every fixture. It never
serializes fixture-derived text/facts or manifest `expected_text`/
`expected_facts` values: those four fields are represented only by safe
presence/type/length-or-count/SHA-256 metadata. Text comparison and any fact
evaluation occur only in memory. The report also stores expected/actual check
metadata, status/reason, duration, per-fixture peak memory, cloud-call count,
token count, cost estimate, warnings, structured errors, `partial_failure`,
`pass`, and reasons. A requested fact check is `not_evaluable` and non-passing
because fact extraction is not implemented in this POC; an empty
`expected_facts` list is explicitly `not_applicable`.

| Sample ID | SHA/MIME valid | Expected vs actual route/text/provenance | Facts status | Duration (ms) | Peak memory (bytes) | Cloud calls | Tokens/cost | Warnings/errors | Pass/fail/reasons |
| --- | --- | --- | --- | ---: | ---: | ---: | --- | --- | --- |
| `TBD` | `TBD` | `TBD` | `TBD` | `TBD` | `TBD` | `TBD` | `TBD` | `TBD` | `TBD` |

`token_count.value` is `null` with status `unavailable` because the POC adapter
does not expose token usage. Cost is `0.0 USD` with status `no_cloud_calls` for
an offline run; if a cloud call is made it is `null` with
`unavailable_no_provider_price_schedule` until an approved provider price basis
is recorded.

The global summary separately records `total`, `completed`, `failed`, `passed`,
and `not_passed`. Completion means that fixture processing did not produce a
structured conversion/integrity error; it does not turn a non-evaluable fact
check into a pass.

## Decision

Decision: **`adopt` / `reject` / `iterate` — TBD**

Rationale: `TBD`

An `adopt` result still requires separate review before any production change.
