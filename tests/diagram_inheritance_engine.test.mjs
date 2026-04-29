import test from "node:test";
import assert from "node:assert/strict";
import engine from "../frontend/static/inheritance_engine.js";

const { runInheritanceCase } = engine;

function allocationOf(result, id) {
  return result.allocations[String(id)]?.finalFraction || "0";
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
