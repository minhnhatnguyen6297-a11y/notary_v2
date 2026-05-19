import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const formHtml = readFileSync("frontend/templates/cases/form.html", "utf8");
const reactFlowApp = readFileSync("frontend/static/ReactFlowApp.jsx", "utf8");

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

test("ReactFlow app script version is bumped after dataflow fixes", () => {
  assert.match(formHtml, /ReactFlowApp\.jsx\?v=20260518/);
});
