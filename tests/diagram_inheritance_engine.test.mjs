import test from "node:test";
import assert from "node:assert/strict";
import engine from "../frontend/static/inheritance_engine.js";
import diagramEdges from "../frontend/static/diagram_edges.js";

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

test("diagram edges separate kinship from inheritance flow", () => {
  const people = [
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
  ];
  const result = runInheritanceCase({
    people,
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
  const personById = new Map(people.map((person) => [person.id, person]));
  const nodes = [
    { id: "father", kind: "person", role: "Cha", relationType: "parent", person: personById.get("A") },
    { id: "mother", kind: "person", role: "Mẹ", relationType: "parent", person: personById.get("B") },
    { id: "spouse_father", kind: "person", role: "Cha_vc", relationType: "spouseParent", person: personById.get("C") },
    { id: "spouse_mother", kind: "person", role: "Me_vc", relationType: "spouseParent", person: personById.get("D") },
    { id: "owner", kind: "person", role: "Owner", relationType: "owner", person: personById.get("X"), isLandOwner: true },
    { id: "spouse", kind: "person", role: "Vợ/Chồng", relationType: "spouse", person: personById.get("Y"), isLandOwner: true },
    { id: "child_m", kind: "person", role: "Con", relationType: "child", person: personById.get("M"), parentSlotId: "owner", familyGroupId: "ownerSpouse" },
    { id: "child_n", kind: "person", role: "Con", relationType: "child", person: personById.get("N"), parentSlotId: "owner", familyGroupId: "ownerSpouse" },
    { id: "child_o", kind: "person", role: "Con", relationType: "child", person: personById.get("O"), parentSlotId: "owner", familyGroupId: "ownerSpouse" },
    { id: "sibling_z", kind: "person", role: "Anh/Chị/Em", relationType: "sibling", person: personById.get("Z"), parentSlotId: "spouse_mother", parentPersonId: "D", familyGroupId: "spouseParents" },
    { id: "grandchild_z2", kind: "person", role: "Cháu", relationType: "grandchild", person: personById.get("Z2"), parentSlotId: "sibling_z", parentPersonId: "Z" },
    { id: "grandchild_z3", kind: "person", role: "Cháu", relationType: "grandchild", person: personById.get("Z3"), parentSlotId: "sibling_z", parentPersonId: "Z" },
  ];

  const edges = diagramEdges.buildDiagramEdges(nodes, result);
  const kinshipTargetsFromBirthParents = edges.kinshipEdges
    .filter((edge) => edge.familyKey === diagramEdges.FAMILY_BIRTH)
    .map((edge) => edge.targetNodeId);
  const kinshipTargetsFromSpouseParents = edges.kinshipEdges
    .filter((edge) => edge.familyKey === diagramEdges.FAMILY_SPOUSE)
    .map((edge) => edge.targetNodeId);
  const flowPairs = edges.flowEdges.map((edge) => `${edge.sourceNodeId}->${edge.targetNodeId}`);

  assert.ok(kinshipTargetsFromBirthParents.includes("owner"));
  assert.ok(!kinshipTargetsFromBirthParents.includes("sibling_z"));
  assert.ok(kinshipTargetsFromSpouseParents.includes("spouse"));
  assert.ok(kinshipTargetsFromSpouseParents.includes("sibling_z"));
  assert.ok(edges.kinshipEdges.some((edge) => edge.sourceNodeId === "sibling_z" && edge.targetNodeId === "grandchild_z2"));
  assert.ok(!flowPairs.includes("father->owner"));
  assert.ok(!flowPairs.includes("mother->owner"));
  assert.ok(flowPairs.includes("owner->spouse"));
  assert.ok(flowPairs.includes("spouse->spouse_mother"));
  assert.ok(flowPairs.includes("spouse_mother->child_m"));
  assert.ok(flowPairs.includes("spouse_mother->grandchild_z2"));
  assert.ok(flowPairs.includes("spouse_mother->grandchild_z3"));
});

test("ambiguous sibling is not attached to the birth parent group", () => {
  const edges = diagramEdges.buildDiagramEdges([
    { id: "father", kind: "person", role: "Cha", relationType: "parent", person: { id: "A" } },
    { id: "mother", kind: "person", role: "Mẹ", relationType: "parent", person: { id: "B" } },
    { id: "owner", kind: "person", role: "Owner", relationType: "owner", person: { id: "X" } },
    { id: "sibling_unknown", kind: "person", role: "Anh/Chị/Em", relationType: "sibling", person: { id: "Z" } },
  ], { trace: [] });

  assert.deepEqual(edges.ambiguousSiblingIds, ["sibling_unknown"]);
  assert.ok(!edges.kinshipEdges.some((edge) => edge.targetNodeId === "sibling_unknown"));
});

test("inheritanceDecision refuse excludes person from allocation", () => {
  const result = runInheritanceCase({
    people: [
      { id: "A", death: "2020" },
      { id: "B" },
      { id: "C" },
      { id: "D" },
      { id: "E" },
    ],
    assetOwnerIds: ["A"],
    inheritanceDecisionByPersonId: { B: "refuse", C: "refuse", D: "accept", E: "accept" },
    relationships: {
      parentsByChild: {
        B: ["A"],
        C: ["A"],
        D: ["A"],
        E: ["A"],
      },
    },
  });

  assert.equal(allocationOf(result, "D"), "1/2");
  assert.equal(allocationOf(result, "E"), "1/2");
  assert.equal(allocationOf(result, "B"), "0");
  assert.equal(allocationOf(result, "C"), "0");
});

test("inheritanceDecision unset still counts as entitled but not grouped", () => {
  const result = runInheritanceCase({
    people: [
      { id: "A", death: "2020" },
      { id: "B" },
      { id: "C" },
      { id: "D" },
      { id: "E" },
    ],
    assetOwnerIds: ["A"],
    inheritanceDecisionByPersonId: { B: "refuse", C: "refuse", D: "accept", E: "unset" },
    relationships: {
      parentsByChild: {
        B: ["A"],
        C: ["A"],
        D: ["A"],
        E: ["A"],
      },
    },
  });

  assert.equal(allocationOf(result, "D"), "1/2");
  assert.equal(allocationOf(result, "E"), "1/2");
  assert.equal(allocationOf(result, "B"), "0");
  assert.equal(allocationOf(result, "C"), "0");
});

test("inheritanceDecision overrides willReceive false", () => {
  const result = runInheritanceCase({
    people: [
      { id: "A", death: "2020" },
      { id: "B" },
      { id: "C" },
    ],
    assetOwnerIds: ["A"],
    willReceiveByPersonId: { B: false },
    inheritanceDecisionByPersonId: { B: "accept", C: "unset" },
    relationships: {
      parentsByChild: {
        B: ["A"],
        C: ["A"],
      },
    },
  });

  assert.equal(allocationOf(result, "B"), "1/2");
  assert.equal(allocationOf(result, "C"), "1/2");
});
