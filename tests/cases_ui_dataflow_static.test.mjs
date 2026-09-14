import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const formHtml = readFileSync("frontend/templates/cases/form.html", "utf8");
const reactFlowApp = readFileSync("frontend/static/ReactFlowApp.jsx", "utf8");

function scope(start, end) {
  const from = formHtml.indexOf(start);
  const to = formHtml.indexOf(end, from + start.length);
  assert.ok(from >= 0 && to > from, `missing static scope: ${start}`);
  return formHtml.slice(from, to);
}

test("stage rows are not labeled or submitted as not-in-diagram records", () => {
  assert.equal(formHtml.includes("Chưa vào sơ đồ"), false);
  assert.equal(formHtml.includes("Trong sơ đồ"), false);
  assert.equal(formHtml.includes('querySelectorAll(\'#ocr-staging-area .ocr-staged-row[data-state="pending"]\')'), false);
});

test("restoring staging data does not force pool membership off", () => {
  const loadStagingMatch = formHtml.match(/loadStagingFromStorage\s*=\s*function\s*\(\)\s*{[\s\S]*?window\.loadStagingFromStorage\s*=\s*loadStagingFromStorage;/);
  assert.ok(loadStagingMatch, "loadStagingFromStorage block should exist");
  assert.equal(/inPool\s*:\s*false/.test(loadStagingMatch[0]), false);
});

test("removing from diagram clears stale tree state and returns the person to pool", () => {
  assert.match(
    reactFlowApp,
    /patch:\s*{\s*inDiagram:\s*false,\s*inTree:\s*false,\s*inPool:\s*true,\s*deleted:\s*false\s*}/
  );
  assert.match(
    formHtml,
    /setCustomerWorkflowState\(id,\s*{\s*inDiagram:\s*false,\s*inTree:\s*false,\s*inPool:\s*true,\s*deleted:\s*false\s*}\)/
  );
});

test("workflow restore guard allows explicit undelete from diagram removal", () => {
  assert.match(formHtml, /const\s+explicitUndelete\s*=/);
  assert.match(
    formHtml,
    /window\.__CUSTOMER_WORKFLOW__\[id\]\?\.deleted\s*&&\s*!explicitUndelete\s*&&[\s\S]*?next\.inPool\s*=\s*false;/
  );
});

test("land owner star is clickable and wired to the toggle handler", () => {
  assert.equal(reactFlowApp.includes('cursor: "not-allowed"'), false);
  assert.match(reactFlowApp, /onToggleLandOwner\?\.\(node\.id\)/);
  assert.match(reactFlowApp, /onMouseDown=\{\(e\)\s*=>\s*\{\s*e\.preventDefault\(\);\s*e\.stopPropagation\(\);\s*\}\}/);
});

test("case state is posted and hydrated so stage survives reload", () => {
  assert.match(formHtml, /name="case_state_json"\s+id="case-state-json"/);
  assert.match(formHtml, /window\.__INITIAL_CASE_STATE__/);
  assert.match(formHtml, /function collectCaseStateSnapshot\(/);
  assert.match(formHtml, /caseStateInput\.value\s*=\s*JSON\.stringify\(collectCaseStateSnapshot\(/);
  assert.match(formHtml, /hydrateStagingFromCaseState\(/);
});

test("Stage commits explicitly and diagram snapshots use only committed Stage", () => {
  assert.match(formHtml, /function getCommittedStageSnapshot\(/);
  assert.match(formHtml, /function persistCommittedStageSnapshot\(/);
  assert.match(formHtml, /\/stage-update/);
  const snapshot = formHtml.match(/function collectCaseStateSnapshot\([\s\S]*?\n    }/);
  assert.ok(snapshot);
  assert.match(snapshot[0], /const stage = stageOverride \|\| getCommittedStageSnapshot\(\)/);
  assert.equal(snapshot[0].includes("querySelectorAll('#ocr-staging-area"), false);
  const normalizer = scope("function normalizeCommittedStageRecord", "window.__COMMITTED_STAGE_SNAPSHOT__");
  assert.match(normalizer, /hasOwnProperty\.call\(source, key\)\) return String\(source\[key\] \?\? ''\)/);
  assert.match(normalizer, /if \(Object\.prototype\.hasOwnProperty\.call\(source, fallback\)\)/);
  assert.match(formHtml, /function clearOcrTempAfterStageCommit\([\s\S]*?window\.clearOcrTempAfterStageCommit/);
  const save = scope("async function saveParticipantDraftRows", "function _updateStagingCount");
  assert.match(save, /await window\.persistCommittedStageSnapshot\?\.\(/);
  assert.match(save, /if \(failedCount === 0\) window\.clearOcrTempAfterStageCommit\?\./);
});

test("Stage drafts do not auto-save or mutate Pool before Cập nhật", () => {
  const draft = scope("window.addToOcrStaging = function", "function hydrateDraftRowsFromExistingParticipants");
  assert.equal(draft.includes("_queueDraftRowSave("), false);
  assert.equal(draft.includes("_saveStagingRow("), false);
  assert.equal(draft.includes("staged-pool-btn"), false);
  assert.match(draft, /stage-remove-btn/);
  assert.equal(draft.includes("updateCustomerWorkflow("), false);
  const submit = scope("document.getElementById('case-form')?.addEventListener('submit'", "// Load React app");
  assert.equal(submit.includes("saveParticipantDraftRows"), false);
  assert.equal(submit.includes("flushPendingDebounces"), false);
  assert.equal(submit.includes("persistCommittedStageSnapshot"), false);
});

test("Pool derives from committed Stage minus assignments and rejected commits roll back", () => {
  const pool = scope("function derivePoolVisibility", "function syncParticipantProjectionInDom");
  assert.match(pool, /function getPoolCandidateCustomerIds\(\)[\s\S]*?getCommittedStageSnapshot\(\)/);
  assert.match(pool, /function getDiagramAssignedStageIds\(\)[\s\S]*?engineState\?\.nodes/);
  assert.match(pool, /getPoolCandidateCustomerIds\(\)[\s\S]*?!getDiagramAssignedStageIds\(\)\.has/);
  assert.equal(pool.includes("Object.keys(window.__CUSTOMER_REGISTRY__)"), false);
  assert.equal(pool.includes("updateCustomerWorkflow(record.id"), false);
  assert.match(formHtml, /const previousStage = getCommittedStageSnapshot\(\);[\s\S]*?setCommittedStageSnapshot\(previousStage\);/);
  assert.match(formHtml, /const stage = collectDraftStageSnapshot\(options\.excludeRows\);[\s\S]*?setCommittedStageSnapshot\(stage\);/);
  assert.equal(formHtml.includes("/*\n      Array.from(document.querySelectorAll('#ocr-staging-area"), false);
});

test("Stage sources stay draft-only and removal cannot mutate customer or Diagram before commit", () => {
  const imported = scope("imported.forEach((customer)", "if (typeof window.__pushCaseDebugEvent__");
  assert.match(imported, /window\.addToOcrStaging\(customer/);
  assert.equal(imported.includes("loadPool("), false);
  const manual = scope("function addPersonEditRow", "document.getElementById('btn-add-person')");
  assert.match(manual, /window\.addToOcrStaging\(\{\}/);
  assert.equal(manual.includes("commitCustomerToPool"), false);
  assert.equal(formHtml.match(/(?<!function )commitCustomerToPool\(/g), null);
  const remove = scope("document.getElementById('ocr-staging-area')?.addEventListener('click'", "})(); // end OCR module");
  assert.equal((formHtml.match(/closest\('\.stage-remove-btn'\)/g) || []).length, 1);
  assert.equal(/stage-remove-btn[^\n]*addEventListener|addEventListener[^\n]*stage-remove-btn/.test(formHtml), false);
  assert.match(remove, /row\.remove\(\);[\s\S]*?_updateStagingCount\(\);[\s\S]*?_syncAllDraftRowStates\(\);/);
  assert.equal(remove.includes("updateCustomerWorkflow"), false);
  assert.equal(remove.includes("loadPool("), false);
  assert.equal(remove.includes("removeStagingFromStorage"), false);
});

test("final-row removal can commit an empty Stage snapshot", () => {
  const save = scope("async function saveParticipantDraftRows", "function _updateStagingCount");
  assert.equal(/if \(!rows\.length\)[\s\S]*?return/.test(save), false);
  assert.match(formHtml, /function _updateStagingCount\([\s\S]*?saveBtn\.disabled = false;/);
  assert.match(save, /const rows = Array\.from\(document\.querySelectorAll\('#ocr-staging-area \.ocr-staged-row'\)\);[\s\S]*?await window\.persistCommittedStageSnapshot\?\.\(\{ latestEngineState, treeState, excludeRows: failedRows \}\);/);
  assert.match(save, /await window\.persistCommittedStageSnapshot\?\.\([\s\S]*?if \(failedCount === 0\) window\.clearOcrTempAfterStageCommit\?\./);
  const persist = scope("async function persistCommittedStageSnapshot", "window.getCommittedStageSnapshot");
  assert.match(persist, /const stage = collectDraftStageSnapshot\(options\.excludeRows\);/);
  assert.match(persist, /case_state_json: payload/);
  assert.match(persist, /else if \(caseStateInput\) caseStateInput\.value = payload;/);
});

test("OCR is Qwen-only, saves only on Lưu, and modal close retains temporary images", () => {
  const ocr = scope("window.ocrExtractAll = async function", "function clearOcrTempAfterStageCommit");
  assert.match(ocr, /fetch\('\/api\/ocr\/analyze'/);
  for (const legacy of ["tryQRScan", "ocrExtractLocal", "ocr-btn-extract-local", "qrDataUrl", "jsQR", "RapidOCR"]) {
    assert.equal(formHtml.includes(legacy), false);
  }
  assert.equal(ocr.includes("resetOcrWorkingResults();"), false);
  assert.equal(ocr.includes("flushOcrResultsWhenModalHidden"), false);
  assert.equal(formHtml.includes("autoStageOcrResults"), false);
  assert.match(formHtml, /id="ocr-btn-save-results"/);
  assert.match(formHtml, /function saveOcrResultsToStage\([\s\S]*?skipDuplicateGuard: true/);
  const close = scope("document.getElementById('ocrModal')?.addEventListener('hidden.bs.modal'", "// ── OCR Staging Area");
  assert.equal(close.includes("ocrResults ="), false);
  assert.equal(close.includes("imageQueue ="), false);
});

test("Diagram accepts and retains only committed Stage people", () => {
  assert.match(reactFlowApp, /function isCommittedStagePerson\(/);
  assert.match(reactFlowApp, /!explicitId \|\| !isCommittedStagePerson\(explicitId\)/);
  assert.match(reactFlowApp, /caseStagePersonsCommitted/);
  assert.match(reactFlowApp, /pruneLinkedNodes\(nextNodes, node\.id/);
});

test("ReactFlow app script version is bumped after dataflow fixes", () => {
  assert.match(formHtml, /ReactFlowApp\.jsx\?v=20260518/);
});
