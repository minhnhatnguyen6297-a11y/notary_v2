import test from "node:test";
import assert from "node:assert/strict";
import engine from "../frontend/static/inheritance_engine.js";

const { runInheritanceCase } = engine;

function allocationOf(result, id) {
  return result.allocations[String(id)]?.finalFraction || "0";
}

function receivedOf(result, id) {
  return result.allocations[String(id)]?.receivedFraction || "0";
}

test("fixture X/Y/D/Z resolves required fractions", () => {
  const result = runInheritanceCase({
    people: [
      { id: "X", name: "X", death: "2011" },
      { id: "Y", name: "Y", death: "2015" },
      { id: "M", name: "M" },
      { id: "N", name: "N" },
      { id: "O", name: "O" },
      { id: "A", name: "A", death: "1995" },
      { id: "B", name: "B", death: "1996" },
      { id: "C", name: "C", death: "1997" },
      { id: "D", name: "D", death: "2016" },
      { id: "Z", name: "Z", death: "2015" },
      { id: "Z2", name: "Z2" },
      { id: "Z3", name: "Z3" },
    ],
    assetOwnerIds: ["X", "Y"],
    relationships: {
      spousesByPerson: { X: ["Y"], C: ["D"] },
      parentsByChild: {
        X: ["A", "B"],
        Y: ["C", "D"],
        M: ["X", "Y"],
        N: ["X", "Y"],
        O: ["X", "Y"],
        Z: ["C", "D"],
        Z2: ["Z"],
        Z3: ["Z"],
      },
    },
  });

  assert.equal(allocationOf(result, "M"), "59/192");
  assert.equal(allocationOf(result, "N"), "59/192");
  assert.equal(allocationOf(result, "O"), "59/192");
  assert.equal(allocationOf(result, "Z2"), "5/128");
  assert.equal(allocationOf(result, "Z3"), "5/128");
});

test("five asset owners split base ownership equally", () => {
  const result = runInheritanceCase({
    people: ["A", "B", "C", "D", "E"].map((id) => ({ id })),
    assetOwnerIds: ["A", "B", "C", "D", "E"],
  });

  for (const id of ["A", "B", "C", "D", "E"]) {
    assert.equal(allocationOf(result, id), "1/5");
    assert.equal(result.allocations[id].displayPercent, "20.00");
  }
});

test("receive=false rejects inherited inflow but keeps base ownership", () => {
  const result = runInheritanceCase({
    people: [
      { id: "A", death: "2020" },
      { id: "B" },
      { id: "C" },
    ],
    assetOwnerIds: ["A", "B"],
    willReceiveByPersonId: { B: false },
    relationships: {
      spousesByPerson: { A: ["B"] },
      parentsByChild: { C: ["A", "B"] },
    },
  });

  assert.equal(allocationOf(result, "B"), "1/2");
  assert.equal(allocationOf(result, "C"), "1/2");
});

test("representation only walks down children of a predeceased child", () => {
  const result = runInheritanceCase({
    people: [
      { id: "X", death: "2020" },
      { id: "A", death: "2019" },
      { id: "O" },
      { id: "SpouseA" },
    ],
    assetOwnerIds: ["X"],
    relationships: {
      parentsByChild: {
        A: ["X"],
        O: ["A", "SpouseA"],
      },
      spousesByPerson: { A: ["SpouseA"] },
    },
  });

  assert.equal(allocationOf(result, "O"), "1");
  assert.equal(allocationOf(result, "SpouseA"), "0");
});

test("parent predeceased — excluded from first line, receives nothing", () => {
  // Cha chết trước chủ đất → không nhận. Chỉ vợ và con nhận.
  const result = runInheritanceCase({
    people: [
      { id: "Owner", death: "2020" },
      { id: "Father", death: "2010" },
      { id: "Spouse" },
      { id: "Child" },
    ],
    assetOwnerIds: ["Owner"],
    relationships: {
      parentsByChild: { Owner: ["Father"] },
      spousesByPerson: { Owner: ["Spouse"] },
      childrenByParent: { Owner: ["Child"] },
    },
  });

  assert.equal(allocationOf(result, "Father"), "0");
  assert.equal(allocationOf(result, "Spouse"), "1/2");
  assert.equal(allocationOf(result, "Child"), "1/2");
});

test("parent survives decedent — receives share in first line", () => {
  // Cha chết sau chủ đất (2025 > 2020) → thuộc hàng 1, nhận ngang vợ và con.
  // Father sau đó chết và không có heir → finalFraction = 0, nhưng inheritedShare = 1/3.
  const result = runInheritanceCase({
    people: [
      { id: "Owner", death: "2020" },
      { id: "Father", death: "2025" },
      { id: "Spouse" },
      { id: "Child" },
    ],
    assetOwnerIds: ["Owner"],
    relationships: {
      parentsByChild: { Owner: ["Father"] },
      spousesByPerson: { Owner: ["Spouse"] },
      childrenByParent: { Owner: ["Child"] },
    },
  });

  // Father đã nhận 1/3 khi Owner chết, sau đó Father chết → Child thế vị Owner nhận thêm 1/3 từ Father
  assert.equal(receivedOf(result, "Father"), "1/3");
  assert.equal(allocationOf(result, "Spouse"), "1/3");
  assert.equal(allocationOf(result, "Child"), "2/3"); // 1/3 từ Owner + 1/3 thế vị từ Father
});

test("same-day death uses snapshot — no cross-inheritance within the day", () => {
  // A và B chết cùng ngày. A là chủ. B là heir của A.
  // B không được nhận từ A trong snapshot, vì B cũng chết cùng ngày (treated as predeceased for representation).
  // Con của B (C) sẽ thế vị B nếu B chết cùng ngày A.
  const result = runInheritanceCase({
    people: [
      { id: "A", death: "2020-01-01" },
      { id: "B", death: "2020-01-01" },
      { id: "C" },
    ],
    assetOwnerIds: ["A"],
    relationships: {
      childrenByParent: { A: ["B"], B: ["C"] },
    },
  });

  // B cùng ngày → treated as predeceased for representation → C thế vị
  assert.equal(allocationOf(result, "B"), "0");
  assert.equal(allocationOf(result, "C"), "1");
  // Warning phải được phát
  const codes = result.warnings.map((w) => w.code);
  assert.ok(codes.includes("same_day_treated_as_predeceased_for_representation"), "expected same_day warning");
});

test("multi-level representation — grandchild also predeceased", () => {
  // X chết 2020. Con A chết 2019. Cháu B chết 2018. Chắt C còn sống → thế vị 3 cấp.
  const result = runInheritanceCase({
    people: [
      { id: "X", death: "2020" },
      { id: "A", death: "2019" },
      { id: "B", death: "2018" },
      { id: "C" },
    ],
    assetOwnerIds: ["X"],
    relationships: {
      childrenByParent: { X: ["A"], A: ["B"], B: ["C"] },
    },
  });

  assert.equal(allocationOf(result, "A"), "0");
  assert.equal(allocationOf(result, "B"), "0");
  assert.equal(allocationOf(result, "C"), "1");
});

test("missing asset owner emits warning and produces zero allocations", () => {
  const result = runInheritanceCase({
    people: [{ id: "A" }, { id: "B" }],
    assetOwnerIds: [],
  });

  assert.equal(allocationOf(result, "A"), "0");
  assert.ok(result.warnings.some((w) => w.code === "missing_asset_owner"));
});
