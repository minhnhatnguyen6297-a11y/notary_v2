# MarkItDown/Qwen POC Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Verify a policy-gated MarkItDown adapter can create a provenance-aware
`ConversionEnvelope v0.experimental` without changing production OCR.

**Architecture:** The POC is isolated in `tools/document_conversion_poc/`. Its
router hashes and classifies the input, runs local MarkItDown with plugins off,
and permits an injected OpenAI-compatible Qwen adapter only after an allow
decision. It writes measurement JSON and never writes the production DB.

**Tech Stack:** Python 3.10+, MarkItDown, markitdown-ocr, OpenAI SDK, pytest.

**Spec:** `D:\systemdocs\MIN50_IMPLEMENTATION_SPEC.md` W2/W3 and
`D:\systemdocs\SYSTEM_ARCHITECTURE.md` §6.5-6.8.

## Global Constraints

- Do not modify `routers/ocr_ai.py`, its native DashScope calls, DB schema, or
  production document-intake API.
- Plugins must not process an unclassified input. Every cloud OCR call needs
  `OcrDecision(allow=True, reason, policy_version)`.
- Keep Qwen credentials in environment variables only. Fixtures are synthetic.
- Do not create a file in `contracts/` or represent this as a production API.
- The compatible transport is a hypothesis; it does not replace native DashScope
  until a measured result is reviewed.

## File structure

| File | Responsibility |
|---|---|
| `requirements-poc-markitdown.txt` | Optional POC dependencies; production requirements unchanged |
| `tools/document_conversion_poc/models.py` | Envelope, segment, OCR-call, warning/error models |
| `tools/document_conversion_poc/policy.py` | Source router and cloud allow/deny decision |
| `tools/document_conversion_poc/converter.py` | Local conversion and envelope construction |
| `tools/document_conversion_poc/qwen_compatible.py` | Environment-configured OpenAI-compatible adapter |
| `tools/document_conversion_poc/harness.py` | Manifest batch runner and JSON report |
| `tests/test_document_conversion_poc.py` | Generated synthetic-input tests |
| `docs/superpowers/specs/2026-09-11-markitdown-qwen-poc.md` | Manual cloud-test/result record |

### Task 1: POC-only dependency boundary and data models

**Files:**

- Create: `requirements-poc-markitdown.txt`
- Create: `tools/document_conversion_poc/__init__.py`
- Create: `tools/document_conversion_poc/models.py`
- Test: `tests/test_document_conversion_poc.py`

**Interfaces:** `ConversionEnvelope.for_source(source_path: Path, source_bytes:
bytes) -> ConversionEnvelope`; `to_dict() -> dict`; constant version exactly
`v0.experimental`.

- [ ] **Step 1: Write the failing test**

```python
def test_envelope_is_json_safe_and_has_experimental_version():
    envelope = ConversionEnvelope.for_source(Path("sample.docx"), b"synthetic")
    assert envelope.to_dict()["contract_version"] == "v0.experimental"
    assert envelope.to_dict()["source"]["sha256"]
```

- [ ] **Step 2: Run it to verify it fails**

Run: `venv\Scripts\python.exe -m pytest tests/test_document_conversion_poc.py -k envelope -q`

Expected: FAIL with import error for the missing POC module.

- [ ] **Step 3: Implement the smallest model surface**

Add `markitdown`, `markitdown-ocr`, and `openai` only to the POC requirements
file. Implement immutable source/converter/content/segment/OCR/warning/error
records. SHA-256, size, MIME hint and UTC ISO-8601 time are mandatory; secret
values and source bytes are never serialised.

- [ ] **Step 4: Run the focused test**

Run: `venv\Scripts\python.exe -m pytest tests/test_document_conversion_poc.py -k envelope -q`

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add requirements-poc-markitdown.txt tools/document_conversion_poc tests/test_document_conversion_poc.py
git commit -m "test: add document conversion POC models"
```

### Task 2: Deterministic router and OCR gate

**Files:**

- Create: `tools/document_conversion_poc/policy.py`
- Modify: `tests/test_document_conversion_poc.py`

**Interfaces:** `classify_source(path: Path, data: bytes) -> str`; `decide_ocr(
route: str, *, policy_version: str, allow_cloud: bool) -> OcrDecision`.

- [ ] **Step 1: Write failing table-driven tests**

```python
@pytest.mark.parametrize(
    ("suffix", "data", "route"),
    [(".docx", b"PK\x03\x04", "local"), (".xlsx", b"PK\x03\x04", "local"),
     (".pdf", b"%PDF-1.7\ntext", "local"), (".png", b"\x89PNG\r\n\x1a\n", "ocr_candidate"),
     (".exe", b"MZ", "unsupported")],
)
def test_classify_source(suffix, data, route):
    assert classify_source(Path("sample" + suffix), data) == route

def test_ocr_gate_denies_without_explicit_permission():
    assert not decide_ocr("ocr_candidate", policy_version="poc-1", allow_cloud=False).allow
```

- [ ] **Step 2: Run it to verify it fails**

Run: `venv\Scripts\python.exe -m pytest tests/test_document_conversion_poc.py -k "classify or gate" -q`

Expected: FAIL because policy functions do not exist.

- [ ] **Step 3: Implement the minimal route policy**

Route DOCX/XLSX and PDF whose extracted text is non-empty locally; PDF with no
extractable text and raster signatures become `ocr_candidate`. `.doc` is
`legacy_doc_external`: `notary_v2` has no IFilter adapter, so the POC must emit
a handoff/warning rather than pretend it converted it; Windows IFilter remains
the `upload_lab` owner path. All other types are unsupported. Deny all cloud
calls unless the candidate route has `allow_cloud=True`; denied paths record a
reason and no provider call.

- [ ] **Step 4: Run focused tests**

Run: `venv\Scripts\python.exe -m pytest tests/test_document_conversion_poc.py -k "classify or gate" -q`

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add tools/document_conversion_poc/policy.py tests/test_document_conversion_poc.py
git commit -m "feat: add policy-gated conversion router POC"
```

### Task 3: Local MarkItDown conversion with provenance fallback

**Files:**

- Create: `tools/document_conversion_poc/converter.py`
- Modify: `tests/test_document_conversion_poc.py`

**Interfaces:** `convert_path(path: Path, *, allow_cloud: bool, converter:
Callable[[Path], str], ocr: OcrClient | None) -> ConversionEnvelope`.

- [ ] **Step 1: Write a failing local-route test**

```python
def test_docx_local_route_never_calls_ocr(tmp_path):
    path = write_synthetic_docx(tmp_path / "contract.docx", "Nguyễn Văn A")
    ocr = Mock()
    envelope = convert_path(path, allow_cloud=True, converter=fake_converter, ocr=ocr)
    assert envelope.content == "Nguyễn Văn A"
    assert ocr.call_count == 0
    assert envelope.segments[0].source_ref is None
    assert "provenance_unavailable" in envelope.warnings
```

- [ ] **Step 2: Run it to verify it fails**

Run: `venv\Scripts\python.exe -m pytest tests/test_document_conversion_poc.py -k local_route -q`

Expected: FAIL because `convert_path` does not exist.

- [ ] **Step 3: Implement local conversion**

The concrete adapter instantiates `MarkItDown(enable_plugins=False)` and reads
`result.markdown`. Build one segment with null source reference plus
`provenance_unavailable`; converter exceptions become structured errors so a
batch continues. The injected converter keeps unit tests offline.

- [ ] **Step 4: Run focused tests**

Run: `venv\Scripts\python.exe -m pytest tests/test_document_conversion_poc.py -k local_route -q`

Expected: PASS and mock OCR call count zero.

- [ ] **Step 5: Commit**

```powershell
git add tools/document_conversion_poc/converter.py tests/test_document_conversion_poc.py
git commit -m "feat: add local MarkItDown conversion POC"
```

### Task 4: Explicit compatible Qwen adapter

**Files:**

- Create: `tools/document_conversion_poc/qwen_compatible.py`
- Modify: `tools/document_conversion_poc/converter.py`
- Modify: `tests/test_document_conversion_poc.py`

**Interfaces:** `QwenCompatibleOcr.from_environment() -> QwenCompatibleOcr`;
`extract(image_bytes: bytes, mime_type: str) -> str`. Required environment names
are `QWEN_COMPATIBLE_BASE_URL`, `QWEN_COMPATIBLE_API_KEY`, and
`QWEN_COMPATIBLE_MODEL`.

- [ ] **Step 1: Write failing allow/deny tests**

```python
def test_allowed_image_sends_one_data_url_to_fake_client(tmp_path):
    ocr = QwenCompatibleOcr(client=FakeClient("CCCD 012345678901"), model="test")
    envelope = convert_path(write_png(tmp_path / "id.png"), allow_cloud=True,
                            converter=fake_converter, ocr=ocr)
    assert envelope.ocr_calls[0].status == "completed"

def test_denied_image_never_calls_client(tmp_path):
    ocr = Mock()
    envelope = convert_path(write_png(tmp_path / "id.png"), allow_cloud=False,
                            converter=fake_converter, ocr=ocr)
    assert ocr.extract.call_count == 0
```

- [ ] **Step 2: Run it to verify it fails**

Run: `venv\Scripts\python.exe -m pytest tests/test_document_conversion_poc.py -k "allowed_image or denied_image" -q`

Expected: FAIL because compatible adapter does not exist.

- [ ] **Step 3: Implement environment and error boundary**

Build `OpenAI(base_url=..., api_key=...)` only in `from_environment()`. Send one
data URL via chat completions, hash input and measure duration. Map HTTP/timeout
errors to `PocError(code="ocr_request_failed", retryable=...)`; never log raw
image, response, URL query, or API key. Real cloud testing remains opt-in.

- [ ] **Step 4: Run focused tests**

Run: `venv\Scripts\python.exe -m pytest tests/test_document_conversion_poc.py -k "allowed_image or denied_image" -q`

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add tools/document_conversion_poc/qwen_compatible.py tools/document_conversion_poc/converter.py tests/test_document_conversion_poc.py
git commit -m "feat: add Qwen-compatible OCR POC adapter"
```

### Task 5: Harness and result record

**Files:**

- Create: `tools/document_conversion_poc/harness.py`
- Create: `docs/superpowers/specs/2026-09-11-markitdown-qwen-poc.md`
- Modify: `tests/test_document_conversion_poc.py`

**Interfaces:** `run_manifest(manifest_path: Path, output_path: Path, *,
allow_cloud: bool) -> dict`; report includes route, duration, warnings/errors,
cloud-call count, partial failures and POC revision.

- [ ] **Step 1: Write a failing partial-failure test**

```python
def test_harness_reports_partial_failure_without_aborting_batch(tmp_path):
    report = run_manifest(write_manifest(tmp_path, ["ok.docx", "bad.bin"]),
                          tmp_path / "report.json", allow_cloud=False)
    assert report["summary"] == {"total": 2, "completed": 1, "failed": 1}
```

- [ ] **Step 2: Run it to verify it fails**

Run: `venv\Scripts\python.exe -m pytest tests/test_document_conversion_poc.py -k partial_failure -q`

Expected: FAIL because the harness does not exist.

- [ ] **Step 3: Implement harness and result template**

Write report JSON atomically. The template records baseline commit, package
versions, fixture hashes, latency, memory measurement method, cloud-call count,
cost estimate, pass/fail table, and `adopt`/`reject`/`iterate` conclusion. Tests
generate fixture files under `tmp_path`; do not commit customer or binary data.

- [ ] **Step 4: Run all POC tests and offline CLI smoke**

Run: `venv\Scripts\python.exe -m pytest tests/test_document_conversion_poc.py -q`

Expected: PASS.

Run: `venv\Scripts\python.exe -m tools.document_conversion_poc.harness --help`

Expected: usage output and no cloud call.

- [ ] **Step 5: Commit**

```powershell
git add tools/document_conversion_poc docs/superpowers/specs/2026-09-11-markitdown-qwen-poc.md tests/test_document_conversion_poc.py
git commit -m "test: add conversion POC measurement harness"
```

## Self-review

- Spec coverage: routing/gate = Task 2; local adapter/provenance = Task 3;
  compatible Qwen = Task 4; manifest, measurements and partial failure = Task 5.
- No placeholders: every task supplies exact path, test, command and expected
  result. Cloud smoke is opt-in by security policy; all unit behavior uses fakes.
- Interface consistency: Tasks 3-5 use `ConversionEnvelope`, `OcrDecision`,
  `OcrClient`, and `convert_path` established in Tasks 1-4.
