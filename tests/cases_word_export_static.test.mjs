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

test("Word export modal is a template picker", () => {
  assert.ok(modalStart >= 0);
  assert.match(exportModal, /modal-dialog/);
  assert.match(exportModal, /id="export-template-list"/);
  assert.match(exportModal, /export-tpl-btn/);
  assert.match(exportModal, /\/cases\/templates\/list-json/);
  assert.match(exportModal, /\/export-word\?template_id=/);
});

test("false refusal labels stay removed", () => {
  assert.doesNotMatch(detail, /title="Từ chối"/);
  assert.match(detail, /title="Không nhận"/);
});
