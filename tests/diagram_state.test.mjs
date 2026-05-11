import test from "node:test";
import assert from "node:assert/strict";
import { createRequire } from "node:module";

const require = createRequire(import.meta.url);
const { createStore, normalizeSnapshot } = require("../frontend/static/diagram_state.js");

test("normalizeSnapshot fills safe defaults", () => {
  const snapshot = normalizeSnapshot(null);
  assert.deepEqual(snapshot.participants, []);
  assert.deepEqual(snapshot.warnings, []);
  assert.equal(snapshot.shareMode, "auto");
  assert.equal(snapshot.engineState, null);
  assert.equal(snapshot.updatedAt, "");
});

test("subscribe replays current snapshot immediately", () => {
  const store = createStore({ participants: [{ id: "1" }], updatedAt: "t1" });
  let current = null;
  const unsubscribe = store.subscribe((snapshot) => {
    current = snapshot;
  });
  assert.equal(current.updatedAt, "t1");
  unsubscribe();
});

test("saving defers publish until unlocked", () => {
  const calls = [];
  const store = createStore({ participants: [], updatedAt: "t0" }, (snapshot) => calls.push(snapshot.updatedAt));
  store.setSaving(true);
  store.publish({ participants: [{ id: "2" }], updatedAt: "t2" });
  assert.deepEqual(calls, []);
  assert.equal(store.getCommittedState().updatedAt, "t2");
  store.setSaving(false);
  assert.deepEqual(calls, ["t2"]);
});

test("busy counter increments and decrements safely", () => {
  const store = createStore({});
  assert.equal(store.getBusyCount(), 0);
  store.incrementBusy();
  store.incrementBusy();
  assert.equal(store.isBusy(), true);
  assert.equal(store.getBusyCount(), 2);
  store.decrementBusy();
  store.decrementBusy();
  store.decrementBusy();
  assert.equal(store.getBusyCount(), 0);
  assert.equal(store.isBusy(), false);
});
