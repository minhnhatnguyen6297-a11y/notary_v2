// Pure helpers for the inheritance diagram visual edges.
// Kinship edges help read family structure; flow edges come from engine trace.
(function initDiagramEdges(global) {
  "use strict";

  const FAMILY_BIRTH = "birthParents";
  const FAMILY_SPOUSE = "spouseParents";
  const FAMILY_OWNER = "ownerSpouse";
  const FAMILY_AMBIGUOUS = "ambiguousSibling";

  function idOf(value) {
    return String(value || "").trim();
  }

  function personIdOf(node) {
    return idOf(node && (node.personId || node.person && node.person.id));
  }

  function createIndex(nodes) {
    const nodeById = new Map();
    const nodeByPersonId = new Map();
    (nodes || []).forEach((node) => {
      if (!node || !node.id) return;
      nodeById.set(idOf(node.id), node);
      const personId = personIdOf(node);
      if (personId && !nodeByPersonId.has(personId)) nodeByPersonId.set(personId, node);
    });
    return { nodeById, nodeByPersonId };
  }

  function isBirthParent(node) {
    return !!node && (node.id === "father" || node.id === "mother" || node.role === "Cha" || node.role === "Mẹ");
  }

  function isSpouseParent(node) {
    return !!node && (
      node.id === "spouse_father" ||
      node.id === "spouse_mother" ||
      node.role === "Cha_vc" ||
      node.role === "Me_vc"
    );
  }

  function siblingFamilyKey(node, index) {
    const explicit = idOf(node && node.familyGroupId);
    if (explicit) return explicit;
    const parentSlotId = idOf(node && (node.parentSlotId || node.sourceId));
    const parentPersonId = idOf(node && node.parentPersonId);
    const parentNode =
      (parentSlotId && index.nodeById.get(parentSlotId)) ||
      (parentPersonId && index.nodeByPersonId.get(parentPersonId));
    if (isBirthParent(parentNode)) return FAMILY_BIRTH;
    if (isSpouseParent(parentNode)) return FAMILY_SPOUSE;
    return FAMILY_AMBIGUOUS;
  }

  function getKinshipFamilyKey(node, nodes) {
    const relationType = idOf(node && node.relationType);
    if (relationType === "child") return FAMILY_OWNER;
    if (relationType === "sibling" || relationType === "ghostSibling") {
      return siblingFamilyKey(node, createIndex(nodes || []));
    }
    if (relationType === "grandchild" || relationType === "ghostGrandchild") {
      const parentSlotId = idOf(node && node.parentSlotId);
      return parentSlotId ? `descendant:${parentSlotId}` : "";
    }
    return idOf(node && node.familyGroupId);
  }

  function hasNode(index, nodeId) {
    return !!index.nodeById.get(idOf(nodeId));
  }

  function hasSourcePerson(index, nodeId) {
    const node = index.nodeById.get(idOf(nodeId));
    return !!(node && node.person);
  }

  function addKinship(edges, seen, edge) {
    if (!edge || !edge.targetNodeId) return;
    const sourceKey = (edge.sourceNodeIds || []).join("+") || edge.sourceNodeId || "";
    const key = `${edge.familyKey || "kin"}:${sourceKey}->${edge.targetNodeId}`;
    if (seen.has(key)) return;
    seen.add(key);
    edges.push({ ...edge, id: key, kind: "kinship" });
  }

  function buildKinshipEdges(nodes) {
    const index = createIndex(nodes || []);
    const edges = [];
    const seen = new Set();
    const personNodes = (nodes || []).filter((node) => node && node.kind !== "ghost");
    const siblingNodes = (nodes || []).filter((node) => ["sibling", "ghostSibling"].includes(idOf(node.relationType)));
    const childNodes = (nodes || []).filter((node) => ["child", "ghostChild"].includes(idOf(node.relationType)) || node.ghostAction === "addChild");
    const grandchildNodes = (nodes || []).filter((node) =>
      ["grandchild", "ghostGrandchild"].includes(idOf(node.relationType)) || node.ghostAction === "addGrandchild"
    );

    const birthSourceIds = ["father", "mother"].filter((nodeId) => hasSourcePerson(index, nodeId));
    const spouseParentSourceIds = ["spouse_father", "spouse_mother"].filter((nodeId) => hasSourcePerson(index, nodeId));
    const ownerSourceIds = ["owner", "spouse"].filter((nodeId) => hasSourcePerson(index, nodeId));

    if (birthSourceIds.length && hasSourcePerson(index, "owner")) {
      addKinship(edges, seen, { sourceNodeIds: birthSourceIds, targetNodeId: "owner", familyKey: FAMILY_BIRTH });
    }
    siblingNodes
      .filter((node) => siblingFamilyKey(node, index) === FAMILY_BIRTH)
      .forEach((node) => addKinship(edges, seen, { sourceNodeIds: birthSourceIds, targetNodeId: node.id, familyKey: FAMILY_BIRTH }));

    if (spouseParentSourceIds.length && hasSourcePerson(index, "spouse")) {
      addKinship(edges, seen, { sourceNodeIds: spouseParentSourceIds, targetNodeId: "spouse", familyKey: FAMILY_SPOUSE });
    }
    siblingNodes
      .filter((node) => siblingFamilyKey(node, index) === FAMILY_SPOUSE)
      .forEach((node) => addKinship(edges, seen, { sourceNodeIds: spouseParentSourceIds, targetNodeId: node.id, familyKey: FAMILY_SPOUSE }));

    childNodes.forEach((node) => {
      if (!ownerSourceIds.length) return;
      addKinship(edges, seen, { sourceNodeIds: ownerSourceIds, targetNodeId: node.id, familyKey: FAMILY_OWNER });
    });

    grandchildNodes.forEach((node) => {
      const parentSlotId = idOf(node.parentSlotId);
      if (!parentSlotId || !hasSourcePerson(index, parentSlotId)) return;
      addKinship(edges, seen, { sourceNodeId: parentSlotId, targetNodeId: node.id, familyKey: `descendant:${parentSlotId}` });
    });

    const ambiguousSiblingIds = personNodes
      .filter((node) => idOf(node.relationType) === "sibling" && siblingFamilyKey(node, index) === FAMILY_AMBIGUOUS)
      .map((node) => node.id);

    return { kinshipEdges: edges, ambiguousSiblingIds };
  }

  function buildFlowEdges(nodes, engineState) {
    const index = createIndex(nodes || []);
    const edges = [];
    const seen = new Set();
    ((engineState && engineState.trace) || []).forEach((entry) => {
      if (!entry || entry.type !== "flow") return;
      const sourceNode = index.nodeByPersonId.get(idOf(entry.from));
      const targetNode = index.nodeByPersonId.get(idOf(entry.to));
      if (!sourceNode || !targetNode || sourceNode.id === targetNode.id) return;
      const key = `flow:${sourceNode.id}->${targetNode.id}`;
      if (seen.has(key)) return;
      seen.add(key);
      edges.push({
        id: key,
        kind: "flow",
        sourceNodeId: sourceNode.id,
        targetNodeId: targetNode.id,
        fromPersonId: idOf(entry.from),
        toPersonId: idOf(entry.to),
        fraction: entry.fraction || "0",
        eventDateKey: entry.eventDateKey || "",
      });
    });
    return edges;
  }

  function buildDiagramEdges(nodes, engineState) {
    const kinship = buildKinshipEdges(nodes || []);
    return {
      kinshipEdges: kinship.kinshipEdges,
      flowEdges: buildFlowEdges(nodes || [], engineState || {}),
      ambiguousSiblingIds: kinship.ambiguousSiblingIds,
    };
  }

  const api = {
    FAMILY_BIRTH,
    FAMILY_SPOUSE,
    FAMILY_OWNER,
    FAMILY_AMBIGUOUS,
    buildDiagramEdges,
    buildFlowEdges,
    buildKinshipEdges,
    getKinshipFamilyKey,
  };

  if (typeof module !== "undefined" && module.exports) module.exports = api;
  global.DiagramEdges = api;
})(typeof window !== "undefined" ? window : globalThis);
