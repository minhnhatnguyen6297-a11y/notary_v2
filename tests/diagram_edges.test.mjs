import assert from "node:assert/strict";
import { createRequire } from "node:module";
import test from "node:test";

const require = createRequire(import.meta.url);
const { buildKinshipEdges, getKinshipFamilyKey, FAMILY_AMBIGUOUS } = require("../frontend/static/diagram_edges.js");

const person = (id) => ({ id });

test("kinship edges follow explicit parent branches", () => {
  const nodes = [
    { id: "father", role: "Cha", person: person("A") },
    { id: "mother", role: "Mẹ", person: person("B") },
    { id: "spouse_father", role: "Cha_vc", person: person("C") },
    { id: "spouse_mother", role: "Me_vc", person: person("D") },
    { id: "owner", relationType: "owner", person: person("X") },
    { id: "spouse", relationType: "spouse", spouseOf: "owner", person: person("Y") },
    { id: "z", relationType: "sibling", parentSlotId: "spouse_father", person: person("Z") },
    { id: "z2", relationType: "grandchild", parentSlotId: "z", person: person("Z2") },
  ];

  const { kinshipEdges, ambiguousSiblingIds } = buildKinshipEdges(nodes);
  const edgeTo = (targetNodeId) => kinshipEdges.find((edge) => edge.targetNodeId === targetNodeId);

  assert.deepEqual(edgeTo("owner").sourceNodeIds, ["father", "mother"]);
  assert.deepEqual(edgeTo("spouse").sourceNodeIds, ["spouse_father", "spouse_mother"]);
  assert.deepEqual(edgeTo("z").sourceNodeIds, ["spouse_father", "spouse_mother"]);
  assert.equal(edgeTo("z2").sourceNodeId, "z");
  assert.deepEqual(ambiguousSiblingIds, []);
});

test("missing sibling parent stays ambiguous instead of falling back to owner parents", () => {
  const nodes = [
    { id: "father", role: "Cha", person: person("A") },
    { id: "mother", role: "Mẹ", person: person("B") },
    { id: "owner", relationType: "owner", person: person("X") },
    { id: "z", relationType: "sibling", person: person("Z") },
  ];

  const { kinshipEdges, ambiguousSiblingIds } = buildKinshipEdges(nodes);

  assert.equal(getKinshipFamilyKey(nodes[3], nodes), FAMILY_AMBIGUOUS);
  assert.deepEqual(ambiguousSiblingIds, ["z"]);
  assert.equal(kinshipEdges.some((edge) => edge.targetNodeId === "z"), false);
});

test("direct child relation belongs only to the owner spouse family", () => {
  const nodes = [
    { id: "owner", relationType: "owner", person: person("X") },
    { id: "spouse", relationType: "spouse", spouseOf: "owner", person: person("Y") },
    { id: "m", relationType: "child", parentSlotId: "owner", person: person("M") },
  ];

  const { kinshipEdges } = buildKinshipEdges(nodes);
  const edge = kinshipEdges.find((item) => item.targetNodeId === "m");

  assert.deepEqual(edge.sourceNodeIds, ["owner", "spouse"]);
});
