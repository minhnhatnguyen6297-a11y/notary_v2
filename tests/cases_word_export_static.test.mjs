import assert from "node:assert/strict";
import fs from "node:fs";
import test from "node:test";

const formPath = new URL("../frontend/templates/cases/form.html", import.meta.url);
const detailPath = new URL("../frontend/templates/cases/detail.html", import.meta.url);
const casesRouterPath = new URL("../routers/cases.py", import.meta.url);
const form = fs.readFileSync(formPath, "utf8");
const detail = fs.readFileSync(detailPath, "utf8");
const casesRouter = fs.readFileSync(casesRouterPath, "utf8");
const modalStart = form.lastIndexOf("<!-- Modal Xuất văn bản -->");
const exportModal = form.slice(modalStart);

test("Word export modal is a minimal template picker", () => {
  assert.ok(modalStart >= 0);
  assert.match(exportModal, /modal-dialog modal-sm/);
  assert.match(exportModal, /id="export-template-list"/);
  assert.match(exportModal, /export-template-radio/);
  assert.match(exportModal, /\/cases\/templates\/list-json/);
  assert.match(exportModal, /\/export-word\?template_id=/);
  assert.doesNotMatch(exportModal, /export-format/);
  assert.doesNotMatch(exportModal, /export-selected-info/);
});

test("legacy Word preview paths and false refusal labels stay removed", () => {
  assert.doesNotMatch(form, /live-preview|liveEditor|Quill/);
  assert.doesNotMatch(casesRouter, /export-word-legacy|live-preview|export-preview|export-draft/);
  assert.doesNotMatch(detail, /title="Từ chối"/);
  assert.match(detail, /title="Không nhận"/);
});
