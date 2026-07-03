# Phase 1 OCR Flow Alignment Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Align the person CCCD AI OCR modal with `docs/case_user_flow_spec.md` Phase 1 so OCR temp data is only staged by the explicit `Luu` action and is never hiddenly cleared by close/AI OCR.

**Architecture:** Keep this phase UI-only unless a failing test proves a backend contract issue. `frontend/templates/cases/form.html` owns OCR modal state (`imageQueue`, `ocrResults`) and staging handoff; Phase 1 must separate modal close, OCR extraction, explicit OCR `Luu`, and explicit clear into different actions. Use static Node tests to lock dangerous side effects before editing the large template.

**Tech Stack:** Jinja2 template with vanilla JavaScript, Bootstrap modal events, Node built-in `node:test`, existing `verify.bat`.

---

## Scope

This plan implements only Phase 1 OCR CCCD person UI behavior.

In scope:
- `AI OCR` result accumulation in OCR modal.
- OCR modal footer button from `Dong` to `Luu`.
- OCR modal `x` and hidden event side effects.
- OCR temporary image/result retention.
- Person-only staging handoff from OCR modal to stage.
- Local OCR and property/marriage OCR visibility in this modal.
- Static tests that guard the flow.

Out of scope:
- OCR backend parser/pairing changes in `routers/ocr_ai.py`.
- Local OCR engine rewrite.
- Stage `Cap nhat` persistence and cascade.
- Pool source-of-truth refactor.
- Diagram save/cascade/edge refactor.

## Files

- Modify: `docs/case_user_flow_spec.md`
  - Keep `Phase 1: OCR CCCD nguoi` open issues updated.
- Modify: `frontend/templates/cases/form.html`
  - Separate OCR modal close from save/clear.
  - Add explicit OCR `Luu` button behavior.
  - Preserve old OCR results when adding more images.
  - Keep `Xem anh` working by retaining `imageQueue`.
  - Remove/disable Local OCR in the current person OCR phase.
  - Ignore or hide property/marriage results in this person phase.
- Modify: `tests/cases_ui_dataflow_static.test.mjs`
  - Add guard tests for Phase 1 OCR modal behavior.

## Required Pre-Work For Any Agent

- [ ] Read `AGENTS.md` sections 1 and 2.
- [ ] Read `docs/case_user_flow_spec.md` sections 1 through 6, section 11, and section 13 `Phase 1: OCR CCCD nguoi`.
- [ ] State these unresolved Phase 1 items before implementation: `OCR-1` through `OCR-8`, `OCR-R1` through `OCR-R4`.
- [ ] Print scope lock before code edits:

```text
TASK: Align Phase 1 OCR modal flow with case_user_flow_spec
TIER: NORMAL
FILE SE DUNG:
- frontend/templates/cases/form.html
- tests/cases_ui_dataflow_static.test.mjs
- docs/case_user_flow_spec.md
FILE KHONG DUNG:
- routers/ocr_ai.py
- routers/ocr_local.py
- tasks.py
- models.py
- database.py
- frontend/static/ReactFlowApp.jsx
RUI RO:
- form.html lon, de anh huong ngoai y muon neu sua lan sang stage/pool/diagram
- can giu nut thung rac la hanh vi clear duy nhat cua OCR temp trong Phase 1
TEST:
- node --test tests/cases_ui_dataflow_static.test.mjs
- .\verify.bat
TRANG THAI SCOPE: LOCKED
```

## Task 1: Add Static Guard Tests For OCR Phase 1

**Files:**
- Modify: `tests/cases_ui_dataflow_static.test.mjs`

- [ ] **Step 1: Add failing tests that capture the dangerous current behavior**

Add these tests near the existing case UI static tests:

```js
test("OCR modal close does not stage or clear temporary OCR data", () => {
  const hiddenBlock = formHtml.match(/document\.getElementById\('ocrModal'\)\?\.addEventListener\('hidden\.bs\.modal'[\s\S]*?\n\s*\}\);/);
  assert.ok(hiddenBlock, "ocrModal hidden.bs.modal handler should exist");
  assert.equal(hiddenBlock[0].includes("autoStageOcrResults("), false);
  assert.equal(hiddenBlock[0].includes("ocrResults = []"), false);
  assert.equal(hiddenBlock[0].includes("imageQueue = []"), false);
});

test("AI OCR does not reset old working results before extracting more images", () => {
  const extractBlock = formHtml.match(/window\.ocrExtractAll\s*=\s*async function\s*\(\)\s*{[\s\S]*?document\.getElementById\('ocr-btn-text'\)\.innerHTML/);
  assert.ok(extractBlock, "ocrExtractAll block should exist");
  assert.equal(extractBlock[0].includes("resetOcrWorkingResults()"), false);
});

test("OCR modal has an explicit save button and no footer dismiss-only Dong button", () => {
  const ocrFooterBlock = formHtml.match(/<div class="modal-footer py-2 justify-content-between">[\s\S]*?<!--\s*\/Modal OCR/);
  assert.ok(ocrFooterBlock, "OCR modal footer block should exist");
  assert.match(ocrFooterBlock[0], /id="ocr-btn-save-results"/);
  assert.equal(ocrFooterBlock[0].includes('data-bs-dismiss="modal"'), false);
});

test("OCR staging allows missing-side and duplicate person rows", () => {
  const autoStageBlock = formHtml.match(/(?:async\s+)?function autoStageOcrResults\([^)]*\)\s*{[\s\S]*?\n\s*\}/);
  assert.ok(autoStageBlock, "autoStageOcrResults block should exist");
  assert.equal(autoStageBlock[0].includes("hasBlockingPersonWarnings("), false);
  assert.equal(autoStageBlock[0].includes("isDocAlreadyInCase("), false);
  assert.equal(autoStageBlock[0].includes("isDocAlreadyInStaging("), false);
});

test("Local OCR control is hidden or disabled for the current Phase 1 person OCR flow", () => {
  assert.equal(formHtml.includes("ocr-btn-extract-local"), false);
  assert.equal(formHtml.includes('onclick="ocrExtractLocal()"'), false);
});
```

- [ ] **Step 2: Run the static tests and confirm they fail before implementation**

Run:

```powershell
node --test tests/cases_ui_dataflow_static.test.mjs
```

Expected before implementation:

```text
not ok ... OCR modal close does not stage or clear temporary OCR data
not ok ... AI OCR does not reset old working results before extracting more images
not ok ... OCR modal has an explicit save button and no footer dismiss-only Dong button
not ok ... OCR staging allows missing-side and duplicate person rows
not ok ... Local OCR control is hidden or disabled for the current Phase 1 person OCR flow
```

## Task 2: Split OCR Modal Close From OCR Save

**Files:**
- Modify: `frontend/templates/cases/form.html`

- [ ] **Step 1: Replace the footer `Dong` button with explicit `Luu`**

Find the OCR modal footer button around the OCR modal footer and replace the dismiss-only button with:

```html
<button type="button" class="btn btn-sm btn-success" id="ocr-btn-save-results">
  <i class="bi bi-check2-circle me-1"></i>Luu
</button>
```

- [ ] **Step 2: Wire `Luu` to explicit staging only**

Inside the OCR module, after `autoStageOcrResults` is defined and before the module closes, add:

```js
function saveOcrResultsToStage() {
  const result = autoStageOcrResults({ allowMissingSides: true, allowDuplicates: true });
  if (result?.stagedCount) {
    showToast(`Da day ${result.stagedCount} dong OCR xuong stage`, 'success');
  } else {
    showToast('Chua co dong OCR nguoi nao de luu', 'warning');
  }
  return result;
}

window.saveOcrResultsToStage = saveOcrResultsToStage;
document.getElementById('ocr-btn-save-results')?.addEventListener('click', saveOcrResultsToStage);
```

- [ ] **Step 3: Make `hidden.bs.modal` passive**

Replace the current OCR modal hidden handler body with:

```js
document.getElementById('ocrModal')?.addEventListener('hidden.bs.modal', () => {
  if (typeof window.__pushCaseDebugEvent__ === 'function') {
    window.__pushCaseDebugEvent__('OCR_MODAL_HIDDEN_PASSIVE', {
      queueCount: Array.isArray(imageQueue) ? imageQueue.length : 0,
      resultCount: Array.isArray(ocrResults) ? ocrResults.length : 0
    });
  }
});
```

- [ ] **Step 4: Remove hidden auto-flush calls**

Remove calls to:

```js
flushOcrResultsWhenModalHidden('ai_ocr_completed');
flushOcrResultsWhenModalHidden('local_ocr_completed');
```

Do not replace them with any auto-stage behavior.

## Task 3: Preserve OCR Results Across Multiple AI OCR Runs

**Files:**
- Modify: `frontend/templates/cases/form.html`

- [ ] **Step 1: Remove reset before AI extraction**

In `window.ocrExtractAll`, delete:

```js
resetOcrWorkingResults();
```

- [ ] **Step 2: Add new person results above old results**

Replace the current push block for AI person results:

```js
ocrResults.push(...persons.map(p => ({
  type: 'person',
  data: p,
  source: String(p.source_type || 'AI').toUpperCase(),
  source_type: String(p.source_type || 'AI').toUpperCase(),
  side: p.side || 'unknown',
  filename: Array.isArray(p._files) && p._files.length ? p._files[0] : '',
  _files: Array.isArray(p._files) ? p._files.slice() : [],
  warnings: Array.isArray(p.warnings) ? p.warnings.slice() : [],
  raw_text: p._raw_text || '',
})));
```

with:

```js
const newPersonResults = persons.map(p => ({
  type: 'person',
  data: p,
  source: String(p.source_type || 'AI').toUpperCase(),
  source_type: String(p.source_type || 'AI').toUpperCase(),
  side: p.side || 'unknown',
  filename: Array.isArray(p._files) && p._files.length ? p._files[0] : '',
  _files: Array.isArray(p._files) ? p._files.slice() : [],
  warnings: Array.isArray(p.warnings) ? p.warnings.slice() : [],
  raw_text: p._raw_text || '',
}));
ocrResults.unshift(...newPersonResults);
```

- [ ] **Step 3: Do not append property/marriage results in Phase 1**

Remove or guard these lines from the person OCR modal path:

```js
ocrResults.push(...properties.map(p => ({ type: 'property', data: p, source: 'AI', source_type: 'AI' })));
ocrResults.push(...marriages.map(m => ({ type: 'marriage', data: m, source: 'AI', source_type: 'AI' })));
```

Preferred Phase 1 behavior:

```js
if (properties.length || marriages.length) {
  console.info('Ignoring non-person OCR results in Phase 1 person OCR modal', {
    propertyCount: properties.length,
    marriageCount: marriages.length,
  });
}
```

## Task 4: Make OCR `Luu` Permissive And User-Controlled

**Files:**
- Modify: `frontend/templates/cases/form.html`

- [ ] **Step 1: Change `autoStageOcrResults` to accept options and return counts**

Change the function signature from:

```js
async function autoStageOcrResults() {
```

to:

```js
function autoStageOcrResults(options = {}) {
  const allowMissingSides = options.allowMissingSides !== false;
  const allowDuplicates = options.allowDuplicates !== false;
```

- [ ] **Step 2: Remove missing-side blocking**

Delete this block:

```js
if (hasBlockingPersonWarnings(r)) {
  if (card) {
    card.style.borderColor = '#f59e0b';
    card.style.background = '#fffbeb';
  }
  continue;
}
```

If warning styling is still useful, keep it non-blocking:

```js
if (!allowMissingSides && hasBlockingPersonWarnings(r)) {
  continue;
}
```

For Phase 1 calls, pass `allowMissingSides: true`.

- [ ] **Step 3: Remove duplicate blocking for OCR save**

Delete or bypass this block when `allowDuplicates` is true:

```js
if (docKey && (isDocAlreadyInCase(docKey) || isDocAlreadyInStaging(docKey))) {
  r._added = true;
  duplicateCount += 1;
  if (card) {
    card.style.borderColor = '#94a3b8';
    card.style.background = '#f8fafc';
  }
  continue;
}
```

Use:

```js
if (!allowDuplicates && docKey && (isDocAlreadyInCase(docKey) || isDocAlreadyInStaging(docKey))) {
  duplicateCount += 1;
  continue;
}
```

- [ ] **Step 4: Ensure staging add bypasses duplicate guard for OCR save**

Change the staging call to:

```js
const added = window.addToOcrStaging
  ? window.addToOcrStaging(d, { source: 'ocr', skipDuplicateGuard: allowDuplicates })
  : false;
```

- [ ] **Step 5: Return a result object**

At the end of `autoStageOcrResults`, return:

```js
return { stagedCount, duplicateCount, rowCount: persons.length };
```

## Task 5: Remove Local OCR From Phase 1 UI Surface

**Files:**
- Modify: `frontend/templates/cases/form.html`

- [ ] **Step 1: Remove the Local OCR button from the person OCR modal**

Remove the button with:

```html
id="ocr-btn-extract-local"
```

- [ ] **Step 2: Stop queue rendering from targeting the removed Local OCR button**

Guard or remove references like:

```js
document.getElementById('ocr-btn-extract-local').disabled = !imageQueue.length;
```

Use the safe optional form if the function is shared:

```js
const localBtn = document.getElementById('ocr-btn-extract-local');
if (localBtn) localBtn.disabled = !imageQueue.length;
```

- [ ] **Step 3: Keep the Local OCR function untouched unless required by lint**

Do not edit `routers/ocr_local.py`, `tasks.py`, or backend local OCR. If unused frontend function remains but no button calls it, leave it for the later Local OCR rewrite unless a test requires removal.

## Task 6: Verify Image Preview Retention

**Files:**
- Modify: `frontend/templates/cases/form.html` only if needed by tests.

- [ ] **Step 1: Confirm `findPreviewItemsForCard` still reads from retained `imageQueue`**

Check that these lines remain conceptually intact:

```js
(Array.isArray(result?._files) ? result._files : []).forEach(pushName);
(Array.isArray(result?.data?._files) ? result.data._files : []).forEach(pushName);
imageQueue.forEach((item) => {
  if (!item || !(item.dataUrl || item.qrDataUrl)) return;
  if (fileNames.includes(normalizePreviewFileName(item.name))) {
    matches.push(item);
  }
});
```

- [ ] **Step 2: Add a static guard for preview matching**

Add this test:

```js
test("OCR result preview still maps result _files to retained imageQueue items", () => {
  assert.match(formHtml, /function findPreviewItemsForCard\(result,\s*data\)/);
  assert.match(formHtml, /Array\.isArray\(result\?\._files\)/);
  assert.match(formHtml, /Array\.isArray\(result\?\.data\?\._files\)/);
  assert.match(formHtml, /imageQueue\.forEach\(\(item\)\s*=>/);
});
```

## Task 7: Run Verification And Update Spec Tracker

**Files:**
- Modify: `docs/case_user_flow_spec.md`

- [ ] **Step 1: Run focused static tests**

Run:

```powershell
node --test tests/cases_ui_dataflow_static.test.mjs
```

Expected:

```text
# pass ...
# fail 0
```

- [ ] **Step 2: Run repo verify**

Run:

```powershell
.\verify.bat
```

Expected:

```text
verify passed
```

If output differs, report the failing step and do not mark Phase 1 resolved.

- [ ] **Step 3: Update `docs/case_user_flow_spec.md` Phase 1 tracker**

For each fixed issue, update:

```text
- `OCR-1`: resolved 2026-06-17, verified by `node --test tests/cases_ui_dataflow_static.test.mjs` and `.\verify.bat`.
```

Only mark `OCR-R*` rule questions resolved if the user explicitly answered the rule.

## Self-Review Checklist

- [ ] `x` modal only hides/minimizes and does not stage/clear/reset/flush.
- [ ] OCR footer `Luu` is the only OCR modal action that pushes OCR temp data to stage.
- [ ] `AI OCR` never clears old OCR results.
- [ ] New OCR results appear above older results.
- [ ] Missing front/back does not block staging.
- [ ] Duplicate CCCD does not block staging.
- [ ] `Xem anh` still maps one result to one or multiple source images.
- [ ] Local OCR is not exposed in this Phase 1 person OCR UI.
- [ ] Property/marriage OCR results are not rendered into the Phase 1 person OCR modal.
- [ ] Stage `Cap nhat`, pool, and diagram behavior are not refactored in this phase.
