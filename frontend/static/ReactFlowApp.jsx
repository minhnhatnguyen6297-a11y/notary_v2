// ─────────────────────────────────────────────────────────────────────────────
// ReactFlowApp.jsx — Sơ đồ thừa kế (Brick-Wall Layout)
// Không dùng ReactFlow/Dagre. Render thuần HTML/CSS theo tầng.
// ─────────────────────────────────────────────────────────────────────────────
const { useState, useEffect, useCallback, useRef } = React;

const rootElement = document.getElementById("react-flow-root");
const initParticipants = window.__INITIAL_PARTICIPANTS__ || [];
const allCustomers = window.__ALL_CUSTOMERS_DATA__ || [];
const initialOwnerId = document.getElementById("case-nguoi-chet")?.value || "";
const initialEngineState = window.__INITIAL_ENGINE_STATE__ || null;
const initialCaseDiagram = window.__INITIAL_CASE_STATE__?.diagram || {};
const initialV2EngineInput = initialCaseDiagram.engineInput || initialEngineState?.engineInput || null;
const initialV2EngineResult = initialCaseDiagram.engineResult || initialEngineState?.engineResult || null;
const diagramStateStore = window.DiagramStateStore || null;
const diagramEdges = window.DiagramEdges || null;

let backendCalculationCache = {
  inputKey: initialV2EngineInput ? JSON.stringify(initialV2EngineInput) : "",
  result: initialV2EngineResult,
};

let bootstrapSeed = 1;

const BASE_NODE_DEFS = [
  {
    id: "father",
    label: "",
    role: "Cha",
    relationType: "parent",
    bucket: 0,
    allowsShare: true,
    removable: false,
    sourceId: null,
  },
  {
    id: "mother",
    label: "",
    role: "Mẹ",
    relationType: "parent",
    bucket: 0,
    allowsShare: true,
    removable: false,
    sourceId: null,
  },
  {
    id: "spouse_father",
    label: "",
    role: "Cha_vc",
    relationType: "spouseParent",
    bucket: 0,
    allowsShare: true,
    removable: false,
    sourceId: null,
  },
  {
    id: "spouse_mother",
    label: "",
    role: "Me_vc",
    relationType: "spouseParent",
    bucket: 0,
    allowsShare: true,
    removable: false,
    sourceId: null,
  },
  {
    id: "owner",
    label: "",
    role: "Owner",
    relationType: "owner",
    bucket: 1,
    allowsShare: true,
    removable: false,
    sourceId: null,
    isLandOwner: false,
    parentSlotIds: ["father", "mother"],
    spouseSlotId: "spouse",
  },
  {
    id: "spouse",
    label: "",
    role: "Vợ/Chồng",
    relationType: "spouse",
    bucket: 1,
    allowsShare: true,
    removable: false,
    sourceId: "owner",
    spouseOf: "owner",
    parentSlotIds: ["spouse_father", "spouse_mother"],
    spouseSlotId: "owner",
  },
];

function bootstrapId(prefix) {
  bootstrapSeed += 1;
  return `${prefix}_${bootstrapSeed}`;
}

// ─── Data helpers ─────────────────────────────────────────────────────────────

function parseFlexibleDate(value) {
  if (!value) return null;
  const raw = String(value).trim();
  if (!raw) return null;
  const yearOnly = raw.match(/^(\d{4})$/);
  if (yearOnly) {
    const date = new Date(Number(yearOnly[1]), 0, 1);
    return Number.isNaN(date.getTime()) ? null : date;
  }
  const ddmmyyyy = raw.match(/^(\d{1,2})\/(\d{1,2})\/(\d{4})$/);
  if (ddmmyyyy) {
    const date = new Date(Number(ddmmyyyy[3]), Number(ddmmyyyy[2]) - 1, Number(ddmmyyyy[1]));
    return Number.isNaN(date.getTime()) ? null : date;
  }
  const date = new Date(raw);
  return Number.isNaN(date.getTime()) ? null : date;
}

function formatYear(value) {
  if (!value) return null;
  const d = parseFlexibleDate(value);
  if (!d) return String(value).substring(0, 4) || null;
  return String(d.getFullYear());
}

function normalizePersonPayload(rawPerson) {
  if (!rawPerson) return null;
  if (typeof window.toReactPersonShape === "function") {
    const adapted = window.toReactPersonShape(rawPerson);
    if (adapted?.id) {
      return {
        ...adapted,
        id: String(adapted.id || "").trim(),
        name: String(adapted.name || "").trim(),
        doc: String(adapted.doc || "").trim(),
        role: String(adapted.role || rawPerson.role || "").trim(),
        gender: String(adapted.gender || "").trim(),
        birth: String(adapted.birth || "").trim(),
        death: String(adapted.death || "").trim(),
        address: String(adapted.address || "").trim(),
        issue_date: String(adapted.issue_date || "").trim(),
        issue_place: String(adapted.issue_place || "").trim(),
        place_of_origin: String(adapted.place_of_origin || "").trim(),
        share: String(adapted.share ?? rawPerson.share ?? "0"),
        receive: String(adapted.receive ?? rawPerson.receive ?? "1"),
        parentId: String(adapted.parent_id || rawPerson.parent_id || rawPerson.parentId || "").trim(),
      };
    }
  }
  return {
    id: String(rawPerson.id || "").trim(),
    name: String(rawPerson.name || "").trim(),
    doc: String(rawPerson.doc || "").trim(),
    role: String(rawPerson.role || "").trim(),
    gender: String(rawPerson.gender || "").trim(),
    birth: String(rawPerson.birth || "").trim(),
    death: String(rawPerson.death || "").trim(),
    address: String(rawPerson.address || rawPerson.dia_chi || "").trim(),
    issue_date: String(rawPerson.issue_date || rawPerson.ngay_cap || "").trim(),
    issue_place: String(rawPerson.issue_place || rawPerson.noi_cap || "").trim(),
    place_of_origin: String(rawPerson.place_of_origin || rawPerson.nguyen_quan || "").trim(),
    share: String(rawPerson.share ?? "0"),
    receive: String(rawPerson.receive ?? "0"),
    parentId: String(rawPerson.parent_id || rawPerson.parentId || "").trim(),
  };
}

function createLogicalNode(overrides) {
  return {
    id: overrides.id,
    kind: overrides.kind || "person",
    label: overrides.label || "",
    role: overrides.role || "",
    relationType: overrides.relationType || "other",
    bucket: overrides.bucket ?? 1,
    allowsShare: overrides.allowsShare !== false,
    removable: overrides.removable !== false,
    person: overrides.person || null,
    sharePercent: overrides.sharePercent || "0.00",
    willReceive: overrides.willReceive === true,
    parentSlotIds: Array.isArray(overrides.parentSlotIds)
      ? overrides.parentSlotIds.map((item) => String(item || "").trim()).filter(Boolean)
      : [],
    spouseSlotId: overrides.spouseSlotId || null,
    parentSlotId: overrides.parentSlotId || "",
    parentPersonId: overrides.parentPersonId || "",
    familyGroupId: overrides.familyGroupId || "",
    sourceId: overrides.sourceId || null,
    spouseOf: overrides.spouseOf || "",
    disabledReason: overrides.disabledReason || "",
    deathComparison: overrides.deathComparison || "unknown",
    insightLines: overrides.insightLines || [],
    autoGenerated: !!overrides.autoGenerated,
    autoAnchorId: overrides.autoAnchorId || "",
    requiredRelation: overrides.requiredRelation || "",
    requiredAnchorId: overrides.requiredAnchorId || "",
    isLandOwner: overrides.isLandOwner || false,
    traceLabel: overrides.traceLabel || "",
  };
}

function createBaseNodes() {
  const base = BASE_NODE_DEFS.map((def) => createLogicalNode(def));
  base.push(
    createLogicalNode({
      id: "child_1",
      label: "",
      role: "Con",
      relationType: "child",
      bucket: 2,
      allowsShare: true,
      removable: true,
      sourceId: "owner",
      parentSlotId: "owner",
      parentSlotIds: ["owner", "spouse"],
      familyGroupId: "ownerSpouse",
    })
  );
  return base;
}

function createDynamicNode(prefix, config) {
  return createLogicalNode({ id: bootstrapId(prefix), ...config });
}

function findCustomerById(customerId) {
  if (typeof window.resolveCustomerById === "function") {
    const resolved = window.resolveCustomerById(customerId);
    if (resolved) return resolved;
  }
  return allCustomers.find((item) => String(item.id) === String(customerId)) || null;
}

function resolveCustomerForDrop(rawPayload) {
  if (!rawPayload) return null;
  const explicitId = rawPayload.customerId || rawPayload.id;
  const resolved = explicitId ? findCustomerById(explicitId) : null;
  return normalizePersonPayload(resolved || rawPayload);
}

function validateAssignment(logicalNodes, nodeId, person, targetNodes = logicalNodes) {
  const candidate = normalizePersonPayload(person);
  if (!candidate?.id) return { ok: false, reason: "Không xác định được khách hàng." };
  const targetNode = targetNodes.find((node) => node.id === nodeId);
  const isValidTarget = targetNode?.kind === "person";
  if (!isValidTarget) return { ok: false, reason: "Ô nhận không hợp lệ." };
  if (targetNode.kind === "person" && targetNode.person && String(targetNode.person.id) !== String(candidate.id)) {
    return { ok: false, reason: "Ô này đã có người. Hãy thả vào ô trống." };
  }
  const duplicate = logicalNodes.find(
    (node) => node.id !== nodeId && node.kind === "person" && node.person && String(node.person.id) === String(candidate.id)
  );
  if (duplicate) return { ok: false, reason: `${candidate.name || "Người này"} đã có mặt trong sơ đồ.` };
  return { ok: true, person: candidate, targetNode };
}

function deriveParentPersonId(nodes, node) {
  if (node.parentSlotId && node.parentSlotId !== "owner") {
    return nodes.find((c) => c.id === node.parentSlotId)?.person?.id || node.parentPersonId || "";
  }
  if (node.role === "Con") {
    return nodes.find((c) => c.id === "owner")?.person?.id || "";
  }
  return node.parentPersonId || "";
}

function buildAssignedNode(node, nodes, person) {
  const candidate = normalizePersonPayload(person);
  return {
    ...node,
    person: candidate,
    parentPersonId: deriveParentPersonId(nodes, node),
    willReceive: false,
    sharePercent: "0.00",
  };
}

function assignPersonToNode(nodes, nodeId, person) {
  const displacedPersons = [];
  const nextNodes = nodes.map((node) => {
    if (node.id !== nodeId) return node;
    if (node.person && String(node.person.id) !== String(person.id)) {
      displacedPersons.push(normalizePersonPayload(node.person));
    }
    return buildAssignedNode(node, nodes, person);
  });
  return { nodes: nextNodes, displacedPersons };
}

function collectPrunableNodeIds(nodes, targetId) {
  const toRemove = new Set([targetId]);
  let changed = true;
  while (changed) {
    changed = false;
    nodes.forEach((node) => {
      if (toRemove.has(node.id)) return;
      if (node.id !== targetId && node.parentSlotId && toRemove.has(node.parentSlotId)) { toRemove.add(node.id); changed = true; return; }
      if (node.id !== targetId && node.relationType === "sibling" && node.sourceId && toRemove.has(node.sourceId)) { toRemove.add(node.id); changed = true; }
    });
  }
  return toRemove;
}

function collectRemovedPeople(nodes, targetId) {
  const ids = collectPrunableNodeIds(nodes, targetId);
  return nodes
    .filter((node) => ids.has(node.id) && node.person)
    .map((node) => normalizePersonPayload(node.person));
}

function clearAssignedNode(node) {
  return {
    ...node,
    person: null,
    isLandOwner: false,
    willReceive: false,
    sharePercent: "0.00",
  };
}

function bridgeWorkflowUpdates(transitions) {
  if (!Array.isArray(transitions) || !transitions.length) return;
  if (typeof window.updateCustomerWorkflow === "function") {
    window.updateCustomerWorkflow(transitions, {}, { refreshPool: true });
  }
}

function buildOwnerPayload() {
  if (!initialOwnerId) return null;
  const customer = findCustomerById(initialOwnerId);
  return customer ? normalizePersonPayload(customer) : null;
}

function pickSiblingSource(nodes, participant) {
  const fromParentId = nodes.find(
    (node) =>
      node.kind === "person" &&
      (node.role === "Cha" || node.role === "Mẹ" || node.role === "Cha_vc" || node.role === "Me_vc") &&
      node.person &&
      String(node.person.id) === String(participant.parentId || "")
  );
  if (fromParentId) return fromParentId.id;
  const fatherNode = nodes.find((node) => node.id === "father" && node.person);
  if (fatherNode) return fatherNode.id;
  const motherNode = nodes.find((node) => node.id === "mother" && node.person);
  if (motherNode) return motherNode.id;
  const spouseFatherNode = nodes.find((node) => node.id === "spouse_father" && node.person);
  if (spouseFatherNode) return spouseFatherNode.id;
  const spouseMotherNode = nodes.find((node) => node.id === "spouse_mother" && node.person);
  if (spouseMotherNode) return spouseMotherNode.id;
  return "owner";
}

// ─── Hydrate from saved participants ─────────────────────────────────────────

function hydrateEngineStateNodes() {
  const savedNodes = Array.isArray(initialV2EngineInput?.nodes)
    ? initialV2EngineInput.nodes
    : initialEngineState?.nodes;
  if (!Array.isArray(savedNodes) || !savedNodes.length) {
    return null;
  }
  const nodes = savedNodes.map((saved) => {
    if (saved.hidden || saved.deleted) return null;
    const personId = String(saved.personId || saved.person?.id || "").trim();
    const resolvedPerson = personId ? normalizePersonPayload(findCustomerById(personId) || saved.person || { id: personId }) : null;
    return createLogicalNode({
      id: saved.id,
      kind: saved.kind || "person",
      label: saved.label,
      role: saved.roleLabel || saved.role,
      relationType: saved.relationType,
      bucket: saved.bucket,
      allowsShare: saved.allowsShare !== false,
      removable: saved.removable !== false,
      sourceId: saved.sourceId || null,
      parentSlotIds: saved.parentSlotIds,
      spouseSlotId: saved.spouseSlotId,
      spouseOf: saved.spouseOf || (saved.id === "spouse" ? "owner" : ""),
      parentSlotId: saved.parentSlotId || "",
      parentPersonId: saved.parentPersonId || saved.parentId || "",
      familyGroupId: saved.familyGroupId || "",
      person: resolvedPerson,
      willReceive: saved.willReceive === true || saved.inheritanceDecision === "accept",
      isLandOwner: !!saved.isLandOwner || (Array.isArray(initialEngineState?.assetOwnerIds) && initialEngineState.assetOwnerIds.map(String).includes(personId)),
    });
  }).filter((node) => Boolean(node));
  return nodes;
}

function hydrateInitialNodes() {
  const engineNodes = hydrateEngineStateNodes();
  if (engineNodes) return engineNodes;

  let nodes = createBaseNodes();
  const ownerPayload = buildOwnerPayload();
  if (ownerPayload) {
    nodes = nodes.map((node) =>
      node.id === "owner" ? { ...node, person: ownerPayload, willReceive: false, isLandOwner: true } : node
    );
  }

  const delayedGrandchildren = [];
  const delayedBranchSpouses = [];

  initParticipants.map(normalizePersonPayload).forEach((participant) => {
    if (!participant || !participant.id) return;

    if (participant.role === "Owner") {
      nodes = nodes.map((node) =>
        node.id === "owner" ? { ...node, person: participant, willReceive: false, isLandOwner: true } : node
      );
      return;
    }

    const sharePercent = participant.share && participant.share !== "None" ? String(participant.share) : "0.00";
    const defaultWillReceive = participant.receive === "1" && !participant.death;

    if (participant.role === "Cha") {
      nodes = nodes.map((node) =>
        node.id === "father" ? { ...node, person: participant, sharePercent, willReceive: defaultWillReceive } : node
      );
      return;
    }
    if (participant.role === "Mẹ") {
      nodes = nodes.map((node) =>
        node.id === "mother" ? { ...node, person: participant, sharePercent, willReceive: defaultWillReceive } : node
      );
      return;
    }
    if (participant.role === "Cha_vc") {
      nodes = nodes.map((node) =>
        node.id === "spouse_father" ? { ...node, person: participant, willReceive: defaultWillReceive } : node
      );
      return;
    }
    if (participant.role === "Me_vc") {
      nodes = nodes.map((node) =>
        node.id === "spouse_mother" ? { ...node, person: participant, willReceive: defaultWillReceive } : node
      );
      return;
    }
    if (participant.role === "Vợ/Chồng") {
      nodes = nodes.map((node) =>
        node.id === "spouse" ? { ...node, person: participant, sharePercent, willReceive: defaultWillReceive, spouseOf: "owner" } : node
      );
      return;
    }
    if (participant.role === "Con") {
      const target = nodes.find((node) => node.kind === "person" && node.relationType === "child" && !node.person);
      if (target) {
        nodes = nodes.map((node) =>
          node.id === target.id
            ? { ...node, person: participant, sharePercent, willReceive: defaultWillReceive, parentPersonId: buildOwnerPayload()?.id || "", familyGroupId: "ownerSpouse" }
            : node
        );
      } else {
        nodes = [
          ...nodes,
            createDynamicNode("child", {
            label: "", role: "Con", relationType: "child", bucket: 2,
            allowsShare: true, removable: true, sourceId: "owner", parentSlotId: "owner",
            familyGroupId: "ownerSpouse",
            parentPersonId: buildOwnerPayload()?.id || "",
            person: participant, sharePercent, willReceive: defaultWillReceive,
          }),
        ];
      }
      return;
    }
    if (participant.role === "Anh/Chị/Em") {
      nodes = [
        ...nodes,
        createDynamicNode("sibling", {
          label: "Anh/Chị/Em", role: "Anh/Chị/Em", relationType: "sibling", bucket: 1,
          allowsShare: true, removable: true,
          sourceId: pickSiblingSource(nodes, participant),
          parentPersonId: participant.parentId || "",
          familyGroupId: participant.familyGroupId || "",
          person: participant, sharePercent, willReceive: defaultWillReceive,
        }),
      ];
      return;
    }
    if (participant.role === "Con_dau_re") { delayedBranchSpouses.push(participant); return; }
    if (participant.role === "Cháu") { delayedGrandchildren.push(participant); }
  });

  delayedBranchSpouses.forEach((participant) => {
    const parentNode =
      nodes.find((node) => node.kind === "person" && node.relationType === "child" && node.person && String(node.person.id) === String(participant.parentId || "")) ||
      nodes.find((node) => node.kind === "person" && node.relationType === "child" && node.person);
    if (!parentNode) return;
    nodes = [
      ...nodes,
      createDynamicNode("branch_spouse", {
        label: "Vợ/Chồng của nhánh", role: "Con_dau_re", relationType: "branchSpouse", bucket: 3,
        allowsShare: true, removable: true, sourceId: parentNode.id, parentSlotId: parentNode.id,
        parentPersonId: parentNode.person?.id || participant.parentId || "",
        familyGroupId: `spouse:${parentNode.id}`,
        person: participant, sharePercent: participant.share || "0.00",
        willReceive: participant.receive === "1" && !participant.death,
      }),
    ];
  });

  delayedGrandchildren.forEach((participant) => {
    const parentNode =
      nodes.find((node) =>
        node.kind === "person" &&
        ["child", "sibling", "grandchild"].includes(node.relationType) &&
        node.person &&
        String(node.person.id) === String(participant.parentId || "")
      ) ||
      nodes.find((node) => node.kind === "person" && node.relationType === "child" && node.person);
    if (!parentNode) return;
    nodes = [
      ...nodes,
      createDynamicNode("grandchild", {
        label: "Con thế vị", role: "Cháu", relationType: "grandchild", bucket: 3,
        allowsShare: true, removable: true, sourceId: parentNode.id, parentSlotId: parentNode.id,
        parentPersonId: parentNode.person?.id || participant.parentId || "",
        familyGroupId: `descendant:${parentNode.id}`,
        person: participant, sharePercent: participant.share || "0.00",
        willReceive: participant.receive === "1" && !participant.death,
      }),
    ];
  });

  return nodes;
}

// ─── Inheritance calculation ──────────────────────────────────────────────────

function buildEngineInput(models) {
  const personNodes = models.filter((node) => node.kind === "person");
  const nodeIds = new Set(personNodes.map((node) => String(node.id || "").trim()).filter(Boolean));

  function parentSlotIdsFor(node) {
    const explicit = Array.isArray(node.parentSlotIds)
      ? node.parentSlotIds.map((item) => String(item || "").trim()).filter((item) => nodeIds.has(item))
      : [];
    const parentIds = [...explicit];
    const legacyParentSlotId = ["spouse", "branchSpouse"].includes(node.relationType)
      ? ""
      : String(node.parentSlotId || "").trim();
    if (legacyParentSlotId && nodeIds.has(legacyParentSlotId)) parentIds.push(legacyParentSlotId);
    if (!parentIds.length && node.parentPersonId) {
      const parentNode = personNodes.find(
        (candidate) => String(candidate.person?.id || "") === String(node.parentPersonId)
      );
      if (parentNode) parentIds.push(parentNode.id);
    }
    personNodes.forEach((candidate) => {
      if (candidate.requiredRelation === "parent" && candidate.requiredAnchorId === node.id) {
        parentIds.push(candidate.id);
      }
    });
    if (node.id === "owner") parentIds.push("father", "mother");
    if (node.id === "spouse") parentIds.push("spouse_father", "spouse_mother");
    const anchorId = parentIds[0];
    if (anchorId) {
      const coParent = personNodes.find(
        (candidate) => candidate.id !== node.id && (
          candidate.spouseSlotId === anchorId ||
          candidate.spouseOf === anchorId ||
          personNodes.find((item) => item.id === anchorId)?.spouseSlotId === candidate.id ||
          personNodes.find((item) => item.id === anchorId)?.spouseOf === candidate.id
        )
      );
      if (coParent) parentIds.push(coParent.id);
      if (anchorId === "owner" && nodeIds.has("spouse")) parentIds.push("spouse");
    }
    return Array.from(new Set(parentIds.filter((item) => nodeIds.has(item)))).slice(0, 2);
  }

  function spouseSlotIdFor(node) {
    const explicit = String(node.spouseSlotId || "").trim();
    if (explicit && nodeIds.has(explicit)) return explicit;
    const spouseOf = String(node.spouseOf || "").trim();
    if (spouseOf && nodeIds.has(spouseOf)) return spouseOf;
    const reverse = personNodes.find(
      (candidate) => candidate.id !== node.id && (
        candidate.spouseSlotId === node.id || candidate.spouseOf === node.id
      )
    );
    if (reverse) return reverse.id;
    if (node.id === "owner" && nodeIds.has("spouse")) return "spouse";
    if (node.id === "spouse" && nodeIds.has("owner")) return "owner";
    return null;
  }

  const nodes = personNodes.map((node) => ({
    id: node.id,
    personId: node.person ? String(node.person.id) : null,
    relationType: node.relationType,
    roleLabel: node.role || "",
    parentSlotIds: parentSlotIdsFor(node),
    spouseSlotId: spouseSlotIdFor(node),
    isLandOwner: !!node.isLandOwner,
    willReceive: node.willReceive === true,
    hidden: node.hidden === true,
    deleted: node.deleted === true,
  }));
  return {
    version: 2,
    nodes,
  };
}

function applyEngineResult(models, engineResult) {
  const allocations = engineResult?.allocations || {};
  return models.map((node) => {
    if (!node.person) return { ...node, sharePercent: "0.00", disabledReason: "" };
    const personId = String(node.person.id);
    const allocation = allocations[personId] || {};
    const finalPercent = allocation.displayPercent || "0.00";
    const nextNode = {
      ...node,
      sharePercent: finalPercent,
      traceLabel: "",
      disabledReason: "",
    };
    if (node.willReceive) {
      nextNode.traceLabel = "Người nhận";
    }
    return nextNode;
  });
}

function runDiagramEngine(models) {
  const engineInput = buildEngineInput(models);
  const inputKey = JSON.stringify(engineInput);
  const engineResult = backendCalculationCache.inputKey === inputKey
    ? backendCalculationCache.result
    : null;
  return {
    nodes: engineResult
      ? applyEngineResult(models, engineResult)
      : models.map((node) => ({ ...node, sharePercent: "0.00" })),
    engineState: {
      ...(engineResult || {}),
      version: 2,
      nodes: engineInput.nodes,
      engineInput,
      engineResult,
      calculationStatus: engineResult ? engineResult.status : "calculating",
    },
  };
}

const REQUIRED_STATIC_SLOTS = {
  owner: { father: "father", mother: "mother", spouse: "spouse" },
  spouse: { father: "spouse_father", mother: "spouse_mother", spouse: "owner" },
};

function resolveSubRelations(nodes) {
  const normalized = nodes
    .filter((node) => node.kind !== "ghost")
    .map((node) => ({
      ...node,
      person: node.person ? normalizePersonPayload(node.person) : null,
      insightLines: [],
      deathComparison: "unknown",
    }));
  const engineRun = runDiagramEngine(normalized);
  const requirements = engineRun.engineState?.engineResult?.requiredSlots || [];
  const requirementIds = new Set();
  const warnings = [];
  let resolvedNodes = engineRun.nodes.map((node) => {
    const isStaticSlot = ["father", "mother", "spouse_father", "spouse_mother", "spouse", "child_1"].includes(node.id);
    return isStaticSlot && !node.person ? { ...node, hidden: true } : node;
  });

  function findNode(nodeId) {
    return resolvedNodes.find((node) => node.id === nodeId);
  }

  function replaceNode(nodeId, updater) {
    resolvedNodes = resolvedNodes.map((node) => node.id === nodeId ? updater(node) : node);
  }

  function ensureParentSlots(anchor, slotTypes, reason) {
    const canonicalAnchor = buildEngineInput(resolvedNodes).nodes.find((node) => node.id === anchor.id);
    const parentIds = (canonicalAnchor?.parentSlotIds || []).filter((nodeId) => findNode(nodeId));
    const neededTypes = ["father", "mother"].filter((slotType) => slotTypes.includes(slotType));
    neededTypes.forEach((slotType, index) => {
      let slotId = REQUIRED_STATIC_SLOTS[anchor.id]?.[slotType] || parentIds[index] || "";
      if (!slotId) slotId = `required_${reason}_${anchor.id}_${slotType}`;
      let slot = findNode(slotId);
      if (!slot) {
        slot = createLogicalNode({
          id: slotId,
          role: slotType === "father" ? "Cha" : "Mẹ",
          relationType: "requiredParent",
          bucket: Math.max(0, Number(anchor.bucket || 1) - 1),
          allowsShare: true,
          removable: true,
          autoGenerated: true,
          autoAnchorId: anchor.id,
          requiredRelation: "parent",
          requiredAnchorId: anchor.id,
        });
        resolvedNodes.push(slot);
      } else if (!slot.person) {
        replaceNode(slotId, (node) => ({ ...node, hidden: false }));
      }
      requirementIds.add(slotId);
      if (!parentIds.includes(slotId)) parentIds.push(slotId);
    });
    replaceNode(anchor.id, (node) => ({ ...node, parentSlotIds: parentIds.slice(0, 2) }));
  }

  function ensureSpouseSlot(anchor, reason) {
    const existing = resolvedNodes.find((node) =>
      node.id !== anchor.id && (
        node.id === REQUIRED_STATIC_SLOTS[anchor.id]?.spouse ||
        node.spouseSlotId === anchor.id ||
        node.spouseOf === anchor.id ||
        anchor.spouseSlotId === node.id ||
        anchor.spouseOf === node.id
      )
    );
    const slotId = existing?.id || `required_${reason}_${anchor.id}_spouse`;
    if (!existing) {
      resolvedNodes.push(createLogicalNode({
        id: slotId,
        role: anchor.id === "owner" ? "Vợ/Chồng" : "Con_dau_re",
        relationType: anchor.id === "owner" ? "spouse" : "branchSpouse",
        bucket: anchor.bucket,
        allowsShare: true,
        removable: true,
        parentSlotId: anchor.id,
        spouseOf: anchor.id,
        spouseSlotId: anchor.id,
        familyGroupId: `spouse:${anchor.id}`,
        autoGenerated: true,
        autoAnchorId: anchor.id,
        requiredRelation: "spouse",
        requiredAnchorId: anchor.id,
      }));
    } else if (!existing.person) {
      replaceNode(slotId, (node) => ({ ...node, hidden: false }));
    }
    replaceNode(anchor.id, (node) => ({ ...node, spouseSlotId: slotId }));
    requirementIds.add(slotId);
  }

  function ensureChildSlots(anchor, reason, minimumEmptyChildSlots) {
    const children = () => resolvedNodes.filter((node) =>
      node.kind === "person" && (
        node.parentSlotId === anchor.id ||
        (Array.isArray(node.parentSlotIds) && node.parentSlotIds.includes(anchor.id))
      ) && !["spouse", "branchSpouse"].includes(node.relationType)
    );
    const minimum = Math.max(1, Number(minimumEmptyChildSlots || 1));
    const existingEmpty = children().filter((node) => !node.person).slice(0, minimum);
    existingEmpty.forEach((node) => {
      replaceNode(node.id, (item) => ({ ...item, hidden: false }));
      requirementIds.add(node.id);
    });
    let emptyCount = existingEmpty.length;
    let index = 1;
    while (emptyCount < minimum) {
      let slotId = anchor.id === "owner" && !findNode("child_1") ? "child_1" : `required_${reason}_${anchor.id}_child_${index}`;
      while (findNode(slotId)) {
        const existing = findNode(slotId);
        if (!existing.person) {
          replaceNode(slotId, (node) => ({ ...node, hidden: false }));
          requirementIds.add(slotId);
          emptyCount += 1;
          break;
        }
        index += 1;
        slotId = `required_${reason}_${anchor.id}_child_${index}`;
      }
      if (emptyCount >= minimum) break;
      const spouseSlotId = findNode(anchor.spouseSlotId)?.id || null;
      resolvedNodes.push(createLogicalNode({
        id: slotId,
        role: anchor.id === "owner" ? "Con" : "Cháu",
        relationType: anchor.id === "owner" ? "child" : "grandchild",
        bucket: Math.min(3, Number(anchor.bucket || 1) + 1),
        allowsShare: true,
        removable: true,
        parentSlotId: anchor.id,
        parentSlotIds: [anchor.id, spouseSlotId].filter(Boolean),
        familyGroupId: `descendant:${anchor.id}`,
        autoGenerated: true,
        autoAnchorId: anchor.id,
        requiredRelation: "child",
        requiredAnchorId: anchor.id,
      }));
      requirementIds.add(slotId);
      emptyCount += 1;
      index += 1;
    }
    children().filter((node) => !node.person).forEach((node) => requirementIds.add(node.id));
  }

  requirements.forEach((requirement) => {
    const anchor = findNode(String(requirement.anchorSlotId || ""));
    if (!anchor?.person) return;
    const slotTypes = Array.isArray(requirement.slotTypes) ? requirement.slotTypes : [];
    if (slotTypes.includes("father") || slotTypes.includes("mother")) {
      ensureParentSlots(anchor, slotTypes, requirement.reason || "estate");
    }
    if (slotTypes.includes("spouse")) ensureSpouseSlot(findNode(anchor.id), requirement.reason || "estate");
    if (slotTypes.includes("child")) {
      ensureChildSlots(findNode(anchor.id), requirement.reason || "estate", requirement.minimumEmptyChildSlots);
    }
  });

  resolvedNodes = resolvedNodes.filter((node) => {
    if (!node.autoGenerated || node.person || requirementIds.has(node.id)) return true;
    return false;
  });
  resolvedNodes.forEach((node) => {
    if (node.autoGenerated && node.person && !requirementIds.has(node.id)) {
      warnings.push(`${node.person.name || "Người đã chọn"}: quan hệ này không còn được engine yêu cầu; hãy kiểm tra hoặc xóa thủ công.`);
    }
  });

  const engineWarnings = (engineRun.engineState?.warnings || []).map((warning) => warning.message || warning.code || String(warning));
  const engineErrors = (engineRun.engineState?.errors || []).map((error) => error.message || error.code || String(error));
  const unresolvedWarnings = (engineRun.engineState?.unresolvedEstates || []).map(
    (item) => `Di sản của người #${item.sourcePersonId || "?"} chưa có người nhận hợp lệ.`
  );
  return {
    nodes: resolvedNodes,
    warnings: Array.from(new Set([...warnings, ...engineWarnings, ...engineErrors, ...unresolvedWarnings])),
    engineState: engineRun.engineState,
  };
}

function buildParticipantsPayload(resolvedNodes) {
  return resolvedNodes
    .filter((node) => node.kind === "person" && node.person)
    .map((node) => ({
      id: node.person.id,
      role: node.role,
      name: node.person.name,
      doc: node.person.doc,
      gender: node.person.gender,
      birth: node.person.birth,
      death: node.person.death,
      address: node.person.address,
      issue_date: node.person.issue_date,
      issue_place: node.person.issue_place,
      place_of_origin: node.person.place_of_origin,
      willReceive: node.willReceive === true,
      sharePercent: node.sharePercent || "0.00",
      share: node.sharePercent || "0.00",
      disabledReason: node.disabledReason || "",
      relationType: node.relationType,
      deathComparison: node.deathComparison || "unknown",
      parentId: node.parentPersonId || "",
      familyGroupId: node.familyGroupId || "",
      isLandOwner: !!node.isLandOwner,
    }));
}

function formatBreakdownLine(item) {
  const person = findCustomerById(item?.personId);
  const name = person?.ho_ten || person?.name || `#${item?.personId || "?"}`;
  const terms = (item?.terms || []).map((term) => {
    if (term.kind === "base") return `${term.fraction} (phần sở hữu)`;
    const source = findCustomerById(term.sourcePersonId);
    const sourceName = source?.ho_ten || source?.name || `#${term.sourcePersonId || "?"}`;
    if (term.kind !== "representation") return `${term.fraction} (${sourceName})`;
    const branchNames = (term.viaBranchPersonIds || []).map((personId) => {
      const branchPerson = findCustomerById(personId);
      return branchPerson?.ho_ten || branchPerson?.name || `#${personId}`;
    });
    return `${term.fraction} (${sourceName}, thế vị nhánh ${branchNames.join(" → ")})`;
  });
  return `${name} nhận: ${item?.total || "0"}${terms.length ? ` = ${terms.join(" + ")}` : ""}`;
}

function buildCommittedSnapshot(logicalNodes, shareMode) {
  const resolved = resolveSubRelations(logicalNodes, shareMode);
  const snapshot = {
    participants: buildParticipantsPayload(resolved.nodes),
    warnings: resolved.warnings,
    shareMode,
    engineState: resolved.engineState || null,
    engineInput: resolved.engineState?.engineInput || null,
    engineResult: resolved.engineState?.engineResult || null,
    calculationStatus: resolved.engineState?.calculationStatus || "calculating",
    updatedAt: new Date().toISOString(),
  };
  return {
    logicalNodes,
    resolvedNodes: resolved.nodes,
    warnings: resolved.warnings,
    diagramEngineState: resolved.engineState || null,
    snapshot,
  };
}

function createFallbackDiagramStore(initialSnapshot, onPublish) {
  const subscribers = new Set();
  let snapshot = initialSnapshot;
  let pendingSnapshot = null;
  let saving = false;
  let busyCount = 0;

  function emit(nextSnapshot) {
    snapshot = nextSnapshot;
    if (typeof onPublish === "function") onPublish(snapshot);
    subscribers.forEach((cb) => cb(snapshot));
    return snapshot;
  }

  return {
    getCommittedState: () => snapshot,
    publish(nextSnapshot) {
      if (saving) {
        pendingSnapshot = nextSnapshot;
        snapshot = nextSnapshot;
        return snapshot;
      }
      pendingSnapshot = null;
      return emit(nextSnapshot);
    },
    subscribe(cb) {
      if (typeof cb !== "function") return () => {};
      subscribers.add(cb);
      cb(snapshot);
      return () => subscribers.delete(cb);
    },
    isSaving: () => saving,
    setSaving(nextSaving) {
      saving = !!nextSaving;
      if (!saving && pendingSnapshot) {
        const replay = pendingSnapshot;
        pendingSnapshot = null;
        emit(replay);
      }
    },
    incrementBusy() {
      busyCount += 1;
      return busyCount;
    },
    decrementBusy() {
      busyCount = Math.max(0, busyCount - 1);
      return busyCount;
    },
    getBusyCount: () => busyCount,
    isBusy: () => busyCount > 0,
  };
}

// ─── Brick-Wall Render Components ────────────────────────────────────────────

const CARD_WIDTH = 140;
const CARD_MIN_WIDTH = 100;
const CARD_CONNECTOR_WIDTH = 28;
const TIER_UNIT_GAP = 12;

const S = {
  card: (isDragOver, isOccupied, isDead) => ({
    width: "100%",
    minHeight: isOccupied ? 108 : 56,
    border: isDragOver
      ? "2px solid #2563eb"
      : isOccupied
      ? "2px solid #d97706"
      : "2px dashed #9ca3af",
    borderRadius: 12,
    background: isDragOver
      ? "linear-gradient(180deg,#eff6ff,#dbeafe)"
      : isOccupied
      ? isDead
        ? "linear-gradient(180deg,#f8fafc,#eef2f7)"
        : "linear-gradient(180deg,#fff7ed,#fffdf7)"
      : "#f8fafc",
    boxShadow: isDragOver
      ? "0 0 0 3px rgba(37,99,235,.2), 0 4px 12px rgba(15,23,42,.08)"
      : "0 2px 8px rgba(15,23,42,.07)",
    padding: "6px 8px 8px",
    position: "relative",
    cursor: "default",
    transition: "border .12s, background .12s, box-shadow .12s",
    flexShrink: 0,
    opacity: isDead ? 0.88 : 1,
    filter: isDead ? "grayscale(.18)" : "none",
    boxSizing: "border-box",
    overflow: "hidden",
    display: "flex",
    flexDirection: "column",
  }),
  name: { fontSize: 14, fontWeight: 800, color: "#0f172a", lineHeight: 1.25, wordBreak: "break-word" },
  meta: { fontSize: 12, color: "#64748b", marginTop: 3 },
  placeholder: { fontSize: 10, color: "#9ca3af", textAlign: "center", padding: "4px 0" },
  insightChip: (color) => ({
    fontSize: 9, color, background: color + "18",
    borderRadius: 6, padding: "2px 6px", marginTop: 4, lineHeight: 1.4,
  }),
  landBadge: (active) => ({
    position: "absolute", top: 6, right: 6,
    fontSize: 12, cursor: "pointer", color: active ? "#d97706" : "#cbd5e1",
    lineHeight: 1, userSelect: "none",
    title: "Đồng chủ sở hữu",
  }),
  removeBtn: {
    position: "absolute", top: 4, right: 22,
    width: 18, height: 18, borderRadius: "50%",
    background: "#ef4444", color: "#fff", border: "none",
    cursor: "pointer", fontSize: 11, lineHeight: "18px", textAlign: "center",
    padding: 0,
  },
  receiveRow: {
    display: "flex", alignItems: "center", justifyContent: "space-between",
    marginTop: 6, paddingTop: 5, borderTop: "1px solid rgba(148,163,184,.2)",
  },
  shareLabel: { fontSize: 10, display: "flex", alignItems: "center", gap: 4, color: "#475569", cursor: "pointer" },
  sharePct: {
    fontSize: 10, fontWeight: 700, color: "#64748b",
    background: "#f8fafc", borderRadius: 999, padding: "1px 6px",
  },
  actionRow: {
    display: "flex", gap: 3, marginTop: "auto", paddingTop: 6,
  },
  actionButton: (active, color) => ({
    flex: 1,
    fontSize: 9,
    fontWeight: 700,
    color: active ? "#fff" : color,
    background: active ? color : "#fff",
    border: `1px solid ${color}`,
    borderRadius: 6,
    padding: "3px 0",
    cursor: "pointer",
    lineHeight: 1.3,
    opacity: active ? 1 : 0.85,
    transition: "all .12s",
  }),
};

function getRelativeBox(element, rootElement) {
  if (!element || !rootElement) return null;
  const rect = element.getBoundingClientRect();
  const rootRect = rootElement.getBoundingClientRect();
  if (!rect.width && !rect.height) return null;
  return {
    left: rect.left - rootRect.left,
    top: rect.top - rootRect.top,
    width: rect.width,
    height: rect.height,
    right: rect.right - rootRect.left,
    bottom: rect.bottom - rootRect.top,
  };
}

function getBoxCenterX(box) {
  return box.left + (box.width / 2);
}

function getBoxBottomY(box) {
  return box.top + box.height;
}

function getBoxCenterY(box) {
  return box.top + (box.height / 2);
}

function getCombinedBox(boxes) {
  const valid = boxes.filter(Boolean);
  if (!valid.length) return null;
  const left = Math.min(...valid.map((box) => box.left));
  const top = Math.min(...valid.map((box) => box.top));
  const right = Math.max(...valid.map((box) => box.right));
  const bottom = Math.max(...valid.map((box) => box.bottom));
  return { left, top, right, bottom, width: right - left, height: bottom - top };
}

function getKinshipSourcePoint(sourceBox, targetBox) {
  if (!sourceBox || !targetBox) return null;
  const sourceX = getBoxCenterX(sourceBox);
  const targetY = getBoxCenterY(targetBox);
  if (targetY >= getBoxCenterY(sourceBox)) {
    return { x: sourceX, y: sourceBox.bottom + 4 };
  }
  return { x: sourceX, y: sourceBox.top - 4 };
}

function getFlowOrientation(sourceBox, targetBox) {
  if (!sourceBox || !targetBox) return null;
  const sourceCenter = { x: getBoxCenterX(sourceBox), y: getBoxCenterY(sourceBox) };
  const targetCenter = { x: getBoxCenterX(targetBox), y: getBoxCenterY(targetBox) };
  const dx = targetCenter.x - sourceCenter.x;
  const dy = targetCenter.y - sourceCenter.y;
  if (Math.abs(dx) > Math.abs(dy)) {
    return {
      sourceSide: dx >= 0 ? "right" : "left",
      targetSide: dx >= 0 ? "left" : "right",
      sourceCenter,
      targetCenter,
      dx,
      dy,
    };
  }
  return {
    sourceSide: dy >= 0 ? "bottom" : "top",
    targetSide: dy >= 0 ? "top" : "bottom",
    sourceCenter,
    targetCenter,
    dx,
    dy,
  };
}

function slotSortValue(box, side) {
  if (side === "top" || side === "bottom") return getBoxCenterX(box);
  return getBoxCenterY(box);
}

function buildEdgeSlotMap(edges, keyBuilder, valueBuilder) {
  const groups = new Map();
  edges.forEach((edge) => {
    const key = keyBuilder(edge);
    if (!key) return;
    if (!groups.has(key)) groups.set(key, []);
    groups.get(key).push(edge);
  });
  const slotMap = new Map();
  groups.forEach((group) => {
    group.sort((left, right) => valueBuilder(left) - valueBuilder(right));
    group.forEach((edge, index) => {
      slotMap.set(edge.id, { index, count: group.length });
    });
  });
  return slotMap;
}

function getSlottedCardPoint(box, side, slotIndex, slotCount, mode) {
  if (!box) return null;
  const count = Math.max(slotCount || 1, 1);
  const index = Math.max(slotIndex || 0, 0);
  const slotRatio = (index + 1) / (count + 1);
  if (side === "top" || side === "bottom") {
    const padding = Math.min(18, box.width * 0.16);
    const usable = Math.max(box.width - (padding * 2), 12);
    const x = box.left + padding + (usable * slotRatio);
    const y = side === "top"
      ? (mode === "target" ? box.top + 1 : box.top - 4)
      : (mode === "target" ? box.bottom - 1 : box.bottom + 4);
    return { x, y };
  }
  const padding = Math.min(18, box.height * 0.16);
  const usable = Math.max(box.height - (padding * 2), 12);
  const y = box.top + padding + (usable * slotRatio);
  const x = side === "left"
    ? (mode === "target" ? box.left + 1 : box.left - 4)
    : (mode === "target" ? box.right - 1 : box.right + 4);
  return { x, y };
}

function buildOrthogonalPath(points) {
  if (!points || points.length < 2) return "";
  const [first, ...rest] = points;
  return `M ${first.x} ${first.y}` + rest.map((p) => ` L ${p.x} ${p.y}`).join("");
}

const BrickCard = React.forwardRef(function BrickCard(
  { node, onAssign, onRemove, onToggleReceiver, onToggleLandOwner, onMoveWithin, onValidateAssign, width },
  ref
) {
  const [isDragOver, setIsDragOver] = useState(false);
  const isOccupied = !!node.person;
  const isDead = !!node.person?.death;

  const handleDragOver = (e) => {
    e.preventDefault(); e.stopPropagation();
    setIsDragOver(true);
  };
  const handleDragLeave = (e) => {
    if (!e.currentTarget.contains(e.relatedTarget)) setIsDragOver(false);
  };
  const handleDrop = (e) => {
    e.preventDefault(); e.stopPropagation();
    setIsDragOver(false);
    let raw = e.dataTransfer.getData("application/json");
    if (!raw) raw = e.dataTransfer.getData("Text");
    if (!raw) return;
    try {
      const payload = JSON.parse(raw);
      if (payload.sourceNodeId && payload.sourceNodeId !== node.id) {
        onMoveWithin(payload.sourceNodeId, node.id);
      } else {
        const person = resolveCustomerForDrop(payload);
        const validation = onValidateAssign ? onValidateAssign(node.id, person) : { ok: true, person };
        if (!validation.ok) {
          window.alert(validation.reason);
          return;
        }
        const result = onAssign(node.id, validation.person);
        if (!result?.ok) return;
        bridgeWorkflowUpdates([
          { id: result.person.id, patch: { inPool: false, inDiagram: true } },
          ...((result.displacedPersons || []).map((displaced) => ({
            id: displaced.id,
            patch: { inDiagram: false, inTree: false, inPool: true },
          }))),
        ]);
      }
    } catch (err) { console.error("BrickCard drop error", err); }
  };
  const handleDragStart = (e) => {
    if (!isOccupied) return;
    e.dataTransfer.setData("application/json", JSON.stringify({ ...node.person, sourceNodeId: node.id }));
    e.dataTransfer.effectAllowed = "all";
  };

  const cardStyle = S.card(isDragOver, isOccupied, isDead);
  const finalStyle = width !== undefined ? { ...cardStyle, width, minWidth: width, maxWidth: width } : cardStyle;

  const canDecide = isOccupied && !isDead && node.allowsShare !== false;
  const isLandOwnerActive = !!node.isLandOwner;
  const isReceiverActive = node.willReceive === true;
  const shareColor = isReceiverActive ? "#0f172a" : "#475569";
  const shareTitle = isReceiverActive ? "Người nhận" : "Tỷ lệ hiện tại";

  return (
    <div
      ref={ref}
      style={finalStyle}
      draggable={isOccupied}
      onDragStart={handleDragStart}
      onDragOver={handleDragOver}
      onDragLeave={handleDragLeave}
      onDrop={handleDrop}
    >
      {/* Remove button */}
      {isOccupied && (
        <button type="button" style={S.removeBtn} onClick={() => onRemove(node.id)} title="Xoá">×</button>
      )}

      {/* Person content */}
      {!isOccupied ? (
        <div style={S.placeholder}>Thả người<br />vào đây...</div>
      ) : (
        <>
          <div style={S.name}>{node.person.name}</div>
          <div style={S.meta}>
            {formatYear(node.person.birth) || "?"}{isDead ? ` · ✝${formatYear(node.person.death)}` : ""}
          </div>

          {node.disabledReason ? (
            <div style={S.insightChip("#92400e")}>{node.disabledReason}</div>
          ) : null}

          {node.traceLabel ? (
            <div style={S.insightChip("#475569")}>{node.traceLabel}</div>
          ) : null}

          <div style={S.receiveRow}>
            <span style={S.shareLabel}>{node.traceLabel || (isLandOwnerActive ? "Sở hữu" : "Tỷ lệ")}</span>
            <span style={{ ...S.sharePct, color: shareColor }} title={shareTitle}>
              {Number(node.sharePercent || 0).toFixed(2)}%
            </span>
          </div>

          {/* Bottom action buttons */}
          <div style={S.actionRow}>
            <button
              type="button"
              style={S.actionButton(isLandOwnerActive, "#f59e0b")}
              title="Chủ đất"
              onClick={(e) => { e.stopPropagation(); onToggleLandOwner?.(node.id); }}
            >Chủ đất</button>
            <button
              type="button"
              style={S.actionButton(isReceiverActive, "#16a34a")}
              title="Nhận"
              disabled={!canDecide}
              onClick={(e) => { e.stopPropagation(); onToggleReceiver?.(node.id); }}
            >Nhận</button>
          </div>
        </>
      )}
    </div>
  );
});

function SvgPairConnector({ show, style }) {
  if (!show) return <div style={{ width: 20, flexShrink: 0, ...style }} />;
  return (
    <div style={{ width: CARD_CONNECTOR_WIDTH, height: 24, flexShrink: 0, display: "flex", alignItems: "center", justifyContent: "center", ...style }}>
      <svg width="28" height="16" viewBox="0 0 28 16" aria-hidden="true">
        <line x1="2" y1="8" x2="26" y2="8" stroke="#64748b" strokeWidth="1.5" strokeLinecap="round" opacity="0.65" />
        <text x="14" y="11" textAnchor="middle" fontSize="9" fill="#64748b" opacity="0.75">♡</text>
      </svg>
    </div>
  );
}

// ─── Tier header ──────────────────────────────────────────────────────────────

const TIER_DEFS = [
  { bucket: 0, label: "Tầng 1 — Cha Mẹ",           accent: "#94a3b8" },
  { bucket: 1, label: "Tầng 2 — Chủ Đất",           accent: "#f59e0b" },
  { bucket: 2, label: "Tầng 3 — Con",               accent: "#3b82f6" },
  { bucket: 3, label: "Tầng 4 — Cháu (Con Thế Vị)", accent: "#8b5cf6" },
];

function TierHeader({ def }) {
  return (
    <div style={{
      display: "flex", alignItems: "center", gap: 8,
      fontSize: 10, fontWeight: 800, textTransform: "uppercase",
      letterSpacing: ".09em", color: "#64748b", marginBottom: 12,
    }}>
      <div style={{ width: 3, height: 14, borderRadius: 2, background: def.accent, flexShrink: 0 }} />
      {def.label}
    </div>
  );
}

// ─── TieredDiagram ────────────────────────────────────────────────────────────

function TieredDiagram({ resolvedNodes, handlers, shareMode, warnings, engineState }) {
  const containerRef = useRef(null);
  const contentRef = useRef(null);
  const nodeRefs = useRef({});
  const groupRefs = useRef({});
  const drawFrameRef = useRef(0);
  const [connectorModel, setConnectorModel] = useState({ width: 0, height: 0, kinshipPaths: [] });
  const [cardWidth, setCardWidth] = useState(CARD_WIDTH);

  const handleDragOver = (e) => { e.preventDefault(); e.dataTransfer.dropEffect = "copy"; };
  const handleDrop = (e) => e.preventDefault();

  const setNodeRef = useCallback((nodeId) => (element) => {
    if (element) nodeRefs.current[nodeId] = element;
    else delete nodeRefs.current[nodeId];
  }, []);

  const setGroupRef = useCallback((groupId) => (element) => {
    if (element) groupRefs.current[groupId] = element;
    else delete groupRefs.current[groupId];
  }, []);

  const personNodes = resolvedNodes.filter((n) => n.kind === "person" && !n.hidden);
  const father = personNodes.find((n) => n.id === "father");
  const mother = personNodes.find((n) => n.id === "mother");
  const spFather = personNodes.find((n) => n.id === "spouse_father");
  const spMother = personNodes.find((n) => n.id === "spouse_mother");
  const owner = personNodes.find((n) => n.id === "owner");
  const spouse = personNodes.find((n) => n.relationType === "spouse" && (n.spouseOf === "owner" || n.id === "spouse"));
  const siblings = personNodes.filter((n) => n.relationType === "sibling");
  const kinshipFamilyOf = (node) => diagramEdges?.getKinshipFamilyKey ? diagramEdges.getKinshipFamilyKey(node, resolvedNodes) : "";
  const birthSiblings = siblings.filter((node) => kinshipFamilyOf(node) === diagramEdges?.FAMILY_BIRTH);
  const spouseSiblings = siblings.filter((node) => kinshipFamilyOf(node) === diagramEdges?.FAMILY_SPOUSE);
  const ambiguousSiblings = siblings.filter((node) => ![diagramEdges?.FAMILY_BIRTH, diagramEdges?.FAMILY_SPOUSE].includes(kinshipFamilyOf(node)));
  const children = personNodes.filter((n) => n.relationType === "child");
  const grandchildren = personNodes.filter((n) => n.relationType === "grandchild");
  const requiredParents = personNodes.filter((n) => n.relationType === "requiredParent");
  const personNodeById = new Map(personNodes.map((node) => [node.id, node]));
  const allGrandchildParentIds = Array.from(new Set([
    ...grandchildren.map((n) => n.parentSlotId),
  ].filter(Boolean)));
  const siblingGrandchildParentIds = allGrandchildParentIds.filter((parentId) =>
    personNodeById.get(parentId)?.relationType === "sibling"
  );
  const deeperGrandchildParentIds = allGrandchildParentIds.filter((parentId) =>
    personNodeById.get(parentId)?.relationType !== "sibling"
  );

  function getBranchSpouseFor(childId) {
    return (
      personNodes.find((n) => n.relationType === "branchSpouse" && n.parentSlotId === childId) ||
      personNodes.find((n) => n.relationType === "branchSpouse" && n.spouseOf === childId)
    );
  }

  const computeCardWidth = useCallback(() => {
    const container = containerRef.current;
    if (!container) return CARD_WIDTH;
    const availableWidth = Math.max(320, container.clientWidth - 48);
    const counts = [];
    if (father || mother || requiredParents.some((node) => node.bucket === 0)) {
      counts.push((father ? 1 : 0) + (mother ? 1 : 0) + requiredParents.filter((node) => node.bucket === 0).length);
    }
    if (spFather || spMother) counts.push((spFather ? 1 : 0) + (spMother ? 1 : 0));
    const tier1Count = (owner ? 1 : 0) +
      requiredParents.filter((node) => node.bucket === 1).length +
      birthSiblings.length + spouseSiblings.length + ambiguousSiblings.length;
    if (tier1Count > 0) counts.push(tier1Count);
    const tier2Count = children.length + siblingGrandchildParentIds.length + requiredParents.filter((node) => node.bucket === 2).length;
    if (tier2Count > 0) counts.push(tier2Count);
    let tier3Count = 0;
    deeperGrandchildParentIds.forEach((parentId) => {
      tier3Count += grandchildren.filter((n) => n.parentSlotId === parentId).length;
    });
    if (tier3Count > 0) counts.push(tier3Count);
    const maxUnits = Math.max(1, ...counts);
    const raw = Math.floor(availableWidth / maxUnits);
    return Math.max(CARD_MIN_WIDTH, Math.min(CARD_WIDTH, raw));
  }, [father, mother, spFather, spMother, owner, birthSiblings, spouseSiblings, ambiguousSiblings, children, siblingGrandchildParentIds, grandchildren, deeperGrandchildParentIds, requiredParents]);

  useEffect(() => {
    const updateWidth = () => setCardWidth(computeCardWidth());
    updateWidth();
    window.addEventListener("resize", updateWidth);
    let observer = null;
    if (typeof ResizeObserver !== "undefined" && containerRef.current) {
      observer = new ResizeObserver(updateWidth);
      observer.observe(containerRef.current);
    }
    return () => {
      window.removeEventListener("resize", updateWidth);
      if (observer) observer.disconnect();
    };
  }, [computeCardWidth]);

  const drawConnectors = useCallback(() => {
    const contentElement = contentRef.current;
    if (!contentElement) return;

    const getNodeBox = (nodeId) => getRelativeBox(nodeRefs.current[nodeId], contentElement);

    const edgeModel = diagramEdges?.buildDiagramEdges
      ? diagramEdges.buildDiagramEdges(resolvedNodes)
      : { kinshipEdges: [] };

    const paths = [];

    // Group kinship edges by source pair/single for T-junctions.
    const edgeGroups = new Map();
    (edgeModel.kinshipEdges || []).forEach((edge) => {
      const sourceKey = (edge.sourceNodeIds || [edge.sourceNodeId]).filter(Boolean).sort().join("+");
      if (!edgeGroups.has(sourceKey)) edgeGroups.set(sourceKey, []);
      edgeGroups.get(sourceKey).push(edge);
    });

    edgeGroups.forEach((edges, sourceKey) => {
      const sourceNodeIds = sourceKey.split("+").filter(Boolean);
      const sourceBoxes = sourceNodeIds.map(getNodeBox).filter(Boolean);
      if (!sourceBoxes.length) return;
      const sourceBox = sourceBoxes.length > 1 ? getCombinedBox(sourceBoxes) : sourceBoxes[0];
      const sourceCenterX = getBoxCenterX(sourceBox);
      const sourceBottomY = getBoxBottomY(sourceBox);

      const targetBoxes = edges.map((edge) => ({ edge, box: getNodeBox(edge.targetNodeId) })).filter((item) => item.box);
      if (!targetBoxes.length) return;

      const targetXs = targetBoxes.map((item) => getBoxCenterX(item.box));
      const minTargetTop = Math.min(...targetBoxes.map((item) => item.box.top));
      const branchY = sourceBottomY + Math.max(14, (minTargetTop - sourceBottomY) * 0.42);

      paths.push({
        key: `kin-drop:${sourceKey}`,
        d: buildOrthogonalPath([{ x: sourceCenterX, y: sourceBottomY + 2 }, { x: sourceCenterX, y: branchY }]),
      });

      const leftX = Math.min(sourceCenterX, ...targetXs);
      const rightX = Math.max(sourceCenterX, ...targetXs);
      paths.push({
        key: `kin-branch:${sourceKey}`,
        d: buildOrthogonalPath([{ x: leftX, y: branchY }, { x: rightX, y: branchY }]),
      });

      targetBoxes.forEach((item, index) => {
        const targetCenterX = getBoxCenterX(item.box);
        paths.push({
          key: `kin-target:${sourceKey}:${index}:${item.edge.targetNodeId}`,
          d: buildOrthogonalPath([{ x: targetCenterX, y: branchY }, { x: targetCenterX, y: item.box.top - 2 }]),
        });
      });
    });

    setConnectorModel({
      width: Math.max(contentElement.scrollWidth, contentElement.clientWidth),
      height: Math.max(contentElement.scrollHeight, contentElement.clientHeight),
      kinshipPaths: paths,
    });
  }, [resolvedNodes]);

  const scheduleConnectorDraw = useCallback(() => {
    if (drawFrameRef.current) window.cancelAnimationFrame(drawFrameRef.current);
    drawFrameRef.current = window.requestAnimationFrame(() => {
      drawFrameRef.current = 0;
      drawConnectors();
    });
  }, [drawConnectors]);

  useEffect(() => {
    scheduleConnectorDraw();
    return () => {
      if (drawFrameRef.current) {
        window.cancelAnimationFrame(drawFrameRef.current);
        drawFrameRef.current = 0;
      }
    };
  }, [scheduleConnectorDraw, resolvedNodes, cardWidth]);

  useEffect(() => {
    const contentElement = contentRef.current;
    const containerElement = containerRef.current;
    const handleResize = () => scheduleConnectorDraw();
    window.addEventListener("resize", handleResize);
    let observer = null;
    if (typeof ResizeObserver !== "undefined" && (contentElement || containerElement)) {
      observer = new ResizeObserver(() => scheduleConnectorDraw());
      if (contentElement) observer.observe(contentElement);
      if (containerElement) observer.observe(containerElement);
    }
    return () => {
      window.removeEventListener("resize", handleResize);
      if (observer) observer.disconnect();
    };
  }, [scheduleConnectorDraw]);

  function renderUnit(unit) {
    if (unit.type === "pair") {
      return (
        <div key={unit.key} ref={setGroupRef(unit.groupId)} style={{ display: "flex", alignItems: "flex-start", gap: 0, flexShrink: 0 }}>
          <BrickCard ref={setNodeRef(unit.primary.id)} node={unit.primary} {...handlers} shareMode={shareMode} width={cardWidth} />
          <SvgPairConnector show={!!unit.spouse} />
          {unit.spouse && <BrickCard ref={setNodeRef(unit.spouse.id)} node={unit.spouse} {...handlers} shareMode={shareMode} width={cardWidth} />}
        </div>
      );
    }
    if (unit.type === "person") {
      return <BrickCard key={unit.key} ref={setNodeRef(unit.node.id)} node={unit.node} {...handlers} shareMode={shareMode} width={cardWidth} />;
    }
    if (unit.type === "branch") {
      return (
        <div key={unit.key} ref={setGroupRef(unit.groupId)} style={{ display: "flex", flexDirection: "column", gap: 6, flexShrink: 0 }}>
          <div style={{ fontSize: 10, color: "#8b5cf6", fontWeight: 700, letterSpacing: ".04em", textAlign: "center", whiteSpace: "nowrap" }}>
            {"Nhánh của "}{unit.label}:
          </div>
          <div style={{ display: "flex", gap: TIER_UNIT_GAP, flexShrink: 0 }}>
            {unit.nodes.map((n) => (
              <BrickCard key={n.id} ref={setNodeRef(n.id)} node={n} {...handlers} shareMode={shareMode} width={cardWidth} />
            ))}
          </div>
        </div>
      );
    }
    return null;
  }

  function renderTierRow(units, tierDef) {
    if (!units.length) return null;
    return (
      <div style={{ borderTop: "2px solid #e2e8f0", padding: "12px 16px 16px" }}>
        <TierHeader def={tierDef} />
        <div style={{ overflowX: "auto", width: "100%" }}>
          <div style={{ display: "flex", justifyContent: "center", gap: TIER_UNIT_GAP, padding: "0 8px", minWidth: "max-content" }}>
            {units.map((unit) => renderUnit(unit))}
          </div>
        </div>
      </div>
    );
  }

  function buildTier0Units() {
    const units = [];
    if (father || mother) {
      if (father && mother) {
        units.push({ type: "pair", key: "birthParents", groupId: "birthParentsPair", primary: father, spouse: mother });
      } else if (father) {
        units.push({ type: "person", key: father.id, node: father });
      } else if (mother) {
        units.push({ type: "person", key: mother.id, node: mother });
      }
    }
    if (spFather || spMother) {
      if (spFather && spMother) {
        units.push({ type: "pair", key: "spouseParents", groupId: "spouseParentsPair", primary: spFather, spouse: spMother });
      } else if (spFather) {
        units.push({ type: "person", key: spFather.id, node: spFather });
      } else if (spMother) {
        units.push({ type: "person", key: spMother.id, node: spMother });
      }
    }
    requiredParents.filter((node) => node.bucket === 0).forEach((node) => units.push(personUnit(node)));
    return units;
  }

  function personUnit(node) {
    return { type: "person", key: node.id, node };
  }

  function buildTier1Units() {
    const units = [];
    if (owner && spouse) {
      units.push({ type: "pair", key: "ownerPair", groupId: "ownerPair", primary: owner, spouse: spouse });
    } else {
      if (owner) units.push({ type: "person", key: owner.id, node: owner });
      if (spouse) units.push({ type: "person", key: spouse.id, node: spouse });
    }
    requiredParents.filter((node) => node.bucket === 1).forEach((node) => units.push(personUnit(node)));
    birthSiblings.forEach((sib) => units.push(personUnit(sib)));
    spouseSiblings.forEach((sib) => units.push(personUnit(sib)));
    ambiguousSiblings.forEach((sib) => units.push(personUnit(sib)));
    return units;
  }

  function buildTier2Units() {
    const units = [];
    requiredParents.filter((node) => node.bucket === 2).forEach((node) => units.push(personUnit(node)));
    children.forEach((child) => {
      const branchSpouse = getBranchSpouseFor(child.id);
      if (branchSpouse) {
        units.push({ type: "pair", key: `childPair:${child.id}`, groupId: `childPair:${child.id}`, primary: child, spouse: branchSpouse });
      } else {
        units.push({ type: "person", key: child.id, node: child });
      }
    });
    siblingGrandchildParentIds.forEach((parentId) => {
      const parentNode = personNodeById.get(parentId);
      const branchGrandchildren = grandchildren.filter((n) => n.parentSlotId === parentId);
      if (branchGrandchildren.length) {
        units.push({
          type: "branch",
          key: `grandchildBranch:${parentId}`,
          groupId: `grandchildBranch:${parentId}`,
          label: parentNode?.person?.name || parentId,
          nodes: branchGrandchildren,
        });
      }
    });
    return units;
  }

  function buildTier3Units() {
    const units = [];
    deeperGrandchildParentIds.forEach((parentId) => {
      const parentNode = personNodeById.get(parentId);
      const branchGrandchildren = grandchildren.filter((n) => n.parentSlotId === parentId);
      if (branchGrandchildren.length) {
        units.push({
          type: "branch",
          key: `grandchildBranch:${parentId}`,
          groupId: `grandchildBranch:${parentId}`,
          label: parentNode?.person?.name || parentId,
          nodes: branchGrandchildren,
        });
      }
    });
    return units;
  }

  const tier0Content = renderTierRow(buildTier0Units(), TIER_DEFS[0]);
  const tier1Content = renderTierRow(buildTier1Units(), TIER_DEFS[1]);
  const tier2Content = renderTierRow(buildTier2Units(), TIER_DEFS[2]);
  const tier3Content = renderTierRow(buildTier3Units(), TIER_DEFS[3]);

  return (
    <div
      ref={containerRef}
      style={{ width: "100%", height: "100%", overflowY: "auto", boxSizing: "border-box" }}
      onDragOver={handleDragOver}
      onDrop={handleDrop}
    >
      <div ref={contentRef} style={{ position: "relative", minHeight: "100%" }}>
        <svg
          width={connectorModel.width}
          height={connectorModel.height}
          style={{ position: "absolute", inset: 0, pointerEvents: "none", overflow: "visible", zIndex: 0 }}
          aria-hidden="true"
        >
          <defs>
            <marker id="kinship-arrow" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="5" markerHeight="5" orient="auto-start-reverse">
              <path d="M 0 0 L 10 5 L 0 10 z" fill="#94a3b8" opacity="0.42" />
            </marker>
          </defs>
          {connectorModel.kinshipPaths.map((path) => (
            <path
              key={path.key}
              d={path.d}
              fill="none"
              stroke="#94a3b8"
              strokeWidth="1.4"
              strokeLinecap="round"
              opacity="0.55"
              markerEnd="url(#kinship-arrow)"
            />
          ))}
        </svg>

        <div style={{ position: "relative", zIndex: 1 }}>
          {tier0Content}
          {tier1Content}
          {tier2Content}
          {tier3Content}
        </div>
      </div>
    </div>
  );
}

function FamilyTreeApp() {
  const calculationSequenceRef = useRef(0);
  const calculationAbortRef = useRef(null);
  const initialNodesRef = useRef(null);
  if (!initialNodesRef.current) {
    initialNodesRef.current = hydrateInitialNodes();
  }
  const [shareMode] = useState("auto");
  const logicalNodesRef = useRef(initialNodesRef.current);
  const initialCommittedRef = useRef(null);
  if (!initialCommittedRef.current) {
    initialCommittedRef.current = buildCommittedSnapshot(initialNodesRef.current, "auto");
  }
  const [logicalNodes, setLogicalNodes] = useState(() => initialNodesRef.current);
  const [resolvedNodes, setResolvedNodes] = useState(() => initialCommittedRef.current.resolvedNodes);
  const [warnings, setWarnings] = useState(() => initialCommittedRef.current.warnings);
  const [diagramEngineState, setDiagramEngineState] = useState(() => initialCommittedRef.current.diagramEngineState);
  const [showBreakdown, setShowBreakdown] = useState(false);
  const diagramStoreRef = useRef(null);
  if (!diagramStoreRef.current) {
    const initialSnapshot = initialCommittedRef.current.snapshot;
    const onPublish = (snapshot) => {
      window.__FAMILY_TREE_STATE__ = snapshot;
      window.dispatchEvent(new CustomEvent("onFamilyTreeUpdate", { detail: snapshot }));
    };
    diagramStoreRef.current = diagramStateStore?.createStore
      ? diagramStateStore.createStore(initialSnapshot, onPublish)
      : createFallbackDiagramStore(initialSnapshot, onPublish);
  }

  const applyCommittedState = useCallback((committed) => {
    setResolvedNodes(committed.resolvedNodes);
    setWarnings(committed.warnings);
    setDiagramEngineState(committed.diagramEngineState);
    diagramStoreRef.current.publish(committed.snapshot);
  }, []);

  const requestCalculation = useCallback((nodes) => {
    const engineInput = buildEngineInput(nodes);
    const inputKey = JSON.stringify(engineInput);
    const sequence = calculationSequenceRef.current + 1;
    calculationSequenceRef.current = sequence;
    calculationAbortRef.current?.abort();
    const controller = new AbortController();
    calculationAbortRef.current = controller;
    const store = diagramStoreRef.current;
    store.incrementBusy();

    fetch("/cases/diagram/calculate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ engineInput }),
      signal: controller.signal,
    })
      .then(async (response) => {
        const result = await response.json().catch(() => null);
        if (!response.ok || !result) {
          throw new Error(result?.detail || `diagram_calculate_${response.status}`);
        }
        return result;
      })
      .then((result) => {
        if (sequence !== calculationSequenceRef.current) return;
        backendCalculationCache = { inputKey, result };
        applyCommittedState(buildCommittedSnapshot(logicalNodesRef.current, shareMode));
      })
      .catch((error) => {
        if (error?.name === "AbortError" || sequence !== calculationSequenceRef.current) return;
        const result = {
          engineVersion: 2,
          status: "invalid",
          allocations: {},
          breakdowns: [],
          requiredSlots: [],
          warnings: [],
          errors: [{ code: "calculation_failed", message: error?.message || "Không thể tính sơ đồ." }],
          unresolvedEstates: [],
          conservation: { allocated: "0", unresolved: "0", total: "0" },
        };
        backendCalculationCache = { inputKey, result };
        applyCommittedState(buildCommittedSnapshot(logicalNodesRef.current, shareMode));
      })
      .finally(() => {
        store.decrementBusy();
      });
  }, [applyCommittedState, shareMode]);

  const commitLogicalNodes = useCallback((updater, reason = "") => {
    const previousNodes = logicalNodesRef.current;
    const nextNodes = typeof updater === "function" ? updater(previousNodes) : updater;
    if (!Array.isArray(nextNodes)) return previousNodes;
    logicalNodesRef.current = nextNodes;
    const committed = buildCommittedSnapshot(nextNodes, shareMode);
    setLogicalNodes(nextNodes);
    applyCommittedState(committed);
    requestCalculation(nextNodes);
    return nextNodes;
  }, [applyCommittedState, requestCalculation, shareMode]);

  useEffect(() => {
    requestCalculation(logicalNodesRef.current);
    return () => calculationAbortRef.current?.abort();
  }, [requestCalculation]);

  const pruneLinkedNodes = useCallback((nodes, targetId, options = {}) => {
    if (targetId === "__noop__") return nodes.slice();
    const toRemove = collectPrunableNodeIds(nodes, targetId);
    const keepTarget = options.keepTarget === true;
    return nodes
      .filter((node) => {
        if (node.id === targetId) return keepTarget;
        return !toRemove.has(node.id);
      })
      .map((node) => (node.id === targetId ? clearAssignedNode(node) : node));
  }, []);

  const onRemove = useCallback((nodeId) => {
    commitLogicalNodes((prevNodes) => {
      const target = prevNodes.find((node) => node.id === nodeId);
      if (!target) return prevNodes;
      if (!target.removable) {
        return pruneLinkedNodes(prevNodes, nodeId, { keepTarget: true });
      }
      return pruneLinkedNodes(prevNodes, nodeId);
    });
  }, [commitLogicalNodes, pruneLinkedNodes]);

  const preflightAssign = useCallback((nodeId, rawPerson) => {
    const currentNodes = logicalNodesRef.current;
    const resolved = resolveSubRelations(currentNodes, shareMode).nodes;
    return validateAssignment(currentNodes, nodeId, normalizePersonPayload(rawPerson), resolved);
  }, [shareMode]);

  const commitAssign = useCallback((nodeId, rawPerson) => {
    const person = normalizePersonPayload(rawPerson);
    const currentNodes = logicalNodesRef.current;
    const resolved = resolveSubRelations(currentNodes, shareMode).nodes;
    const validation = validateAssignment(currentNodes, nodeId, person, resolved);
    if (!validation.ok) return validation;
    commitLogicalNodes((prevNodes) => {
      const prevResolved = resolveSubRelations(prevNodes, shareMode).nodes;
      let baseNodes = prevNodes;
      const autoTarget = prevResolved.find((n) => n.id === nodeId && n.autoGenerated && !prevNodes.some((p) => p.id === nodeId));
      if (autoTarget) {
        baseNodes = [...prevNodes, { ...autoTarget, autoGenerated: false }];
      }
      const recheck = validateAssignment(baseNodes, nodeId, validation.person, prevResolved);
      if (!recheck.ok) return prevNodes;
      return assignPersonToNode(baseNodes, nodeId, validation.person).nodes;
    });
    return { ok: true, person: validation.person, displacedPersons: [] };
  }, [commitLogicalNodes, shareMode]);

  const removeWithWorkflow = useCallback((nodeId) => {
    const affectedPeople = collectRemovedPeople(logicalNodesRef.current, nodeId);
    onRemove(nodeId);
    bridgeWorkflowUpdates(affectedPeople.map((person) => ({
      id: person.id,
      patch: { inDiagram: false, inTree: false, inPool: true },
    })));
  }, [onRemove]);

  const moveWithinDiagram = useCallback((sourceNodeId, targetNodeId) => {
    if (sourceNodeId === targetNodeId) return;
    const currentNodes = logicalNodesRef.current;
    const currentSource = currentNodes.find((node) => node.id === sourceNodeId);
    const currentSourcePerson = normalizePersonPayload(currentSource?.person);
    const currentResolved = resolveSubRelations(currentNodes, shareMode).nodes;
    const currentTarget = currentResolved.find((node) => node.id === targetNodeId);
    if (currentTarget?.person && String(currentTarget.person.id) !== String(currentSourcePerson?.id || "")) {
      window.alert("Node đã có người. Hãy xóa node đích trước khi kéo thẻ khác vào.");
      return;
    }
    const affectedPeople = collectRemovedPeople(logicalNodesRef.current, sourceNodeId);
    const sourcePerson = logicalNodesRef.current.find((node) => node.id === sourceNodeId)?.person;
    const dependentPeople = affectedPeople.filter((person) => String(person.id) !== String(sourcePerson?.id || ""));
    commitLogicalNodes((prev) => {
      const source = prev.find((n) => n.id === sourceNodeId);
      if (!source?.person) return prev;
      const sourcePerson = normalizePersonPayload(source.person);
      const resolved = resolveSubRelations(prev, shareMode).nodes;
      const target = resolved.find((n) => n.id === targetNodeId);
      if (target?.person && String(target.person.id) !== String(sourcePerson?.id || "")) {
        window.alert("Node đã có người. Hãy xóa node đích trước khi kéo thẻ khác vào.");
        return prev;
      }
      const baseNodesRaw = pruneLinkedNodes(prev, sourceNodeId, { keepTarget: true });
      let baseNodes = baseNodesRaw;
      if (target && target.autoGenerated && !baseNodesRaw.some((p) => p.id === targetNodeId)) {
        baseNodes = [...baseNodesRaw, { ...target, autoGenerated: false }];
      }
      return baseNodes.map((node) => {
        if (node.id === targetNodeId) return buildAssignedNode(node, baseNodes, sourcePerson);
        return node;
      });
    });
    bridgeWorkflowUpdates(dependentPeople.map((person) => ({
      id: person.id,
      patch: { inDiagram: false, inTree: false, inPool: true },
    })));
  }, [commitLogicalNodes, pruneLinkedNodes, shareMode]);

  const onToggleReceiver = useCallback((nodeId) => {
    commitLogicalNodes((prevNodes) =>
      prevNodes.map((node) => {
        if (node.id !== nodeId) return node;
        return {
          ...node,
          willReceive: !node.willReceive,
        };
      })
    );
  }, [commitLogicalNodes]);

  const onToggleLandOwner = useCallback((nodeId) => {
    commitLogicalNodes((prev) => prev.map((node) =>
      node.id === nodeId ? { ...node, isLandOwner: !node.isLandOwner } : node
    ));
  }, [commitLogicalNodes]);

  useEffect(() => {
    const handleParticipantRecordUpdated = (evt) => {
      const person = normalizePersonPayload(evt?.detail?.customer || evt?.detail);
      if (!person?.id) return;
      commitLogicalNodes((prevNodes) =>
        prevNodes.map((node) => {
          if (!node.person || String(node.person.id) !== String(person.id)) return node;
          return {
            ...node,
            person: {
              ...node.person,
              ...person,
            },
          };
        })
      );
    };
    window.addEventListener("caseParticipantRecordUpdated", handleParticipantRecordUpdated);
    return () => window.removeEventListener("caseParticipantRecordUpdated", handleParticipantRecordUpdated);
  }, [commitLogicalNodes]);

  useEffect(() => {
    const handleStagePersonsCommitted = (evt) => {
      const stageIds = new Set((evt?.detail?.stageIds || []).map((id) => String(id)));
      const removedIds = new Set((evt?.detail?.removedIds || []).map((id) => String(id)).filter(Boolean));
      const returnedPeopleById = new Map();
      commitLogicalNodes((prevNodes) => {
        let nextNodes = prevNodes;
        removedIds.forEach((removedId) => {
          const anchor = nextNodes.find((node) => {
            const personId = String(node.person?.id || node.personId || "").trim();
            return personId === removedId;
          });
          if (!anchor) return;
          collectRemovedPeople(nextNodes, anchor.id).forEach((person) => {
            if (person?.id && stageIds.has(String(person.id))) returnedPeopleById.set(String(person.id), person);
          });
          nextNodes = pruneLinkedNodes(nextNodes, anchor.id, { keepTarget: anchor.removable === false });
        });
        return nextNodes
          .map((node) => {
            const personId = String(node.person?.id || node.personId || "").trim();
            if (!personId || stageIds.has(personId)) return node;
            if (node.removable === false) {
              return clearAssignedNode(node);
            }
            return null;
          })
          .filter((node) => Boolean(node));
      });
      bridgeWorkflowUpdates(Array.from(returnedPeopleById.values()).map((person) => ({
        id: person.id,
        patch: { inDiagram: false, inTree: false, inPool: true },
      })));
    };
    window.addEventListener("caseStagePersonsCommitted", handleStagePersonsCommitted);
    return () => window.removeEventListener("caseStagePersonsCommitted", handleStagePersonsCommitted);
  }, [commitLogicalNodes, pruneLinkedNodes]);

  // ── Main effect: resolve + dispatch ──────────────────────────────────────────
  useEffect(() => {
    const store = diagramStoreRef.current;
    const api = {
      ready: true,
      getCommittedState: () => store.getCommittedState(),
      subscribe: (cb) => store.subscribe(cb),
      isSaving: () => store.isSaving(),
      setSaving: (nextSaving) => store.setSaving(nextSaving),
      getBusyCount: () => store.getBusyCount(),
      isBusy: () => store.isBusy(),
    };
    window.__DIAGRAM_API__ = api;
    applyCommittedState(initialCommittedRef.current);
    window.dispatchEvent(new CustomEvent("diagram-api-ready"));
    return () => {
      if (window.__DIAGRAM_API__ === api) {
        delete window.__DIAGRAM_API__;
      }
    };
  }, [applyCommittedState]);

  const handlers = {
    onAssign: commitAssign,
    onRemove: removeWithWorkflow,
    onMoveWithin: moveWithinDiagram,
    onValidateAssign: preflightAssign,
    onToggleReceiver,
    onToggleLandOwner,
  };
  const breakdowns = diagramEngineState?.engineResult?.breakdowns || diagramEngineState?.breakdowns || [];

  return (
    <div style={{ width: "100%", height: "100%", display: "flex", flexDirection: "column", position: "relative" }}>
      {/* Toolbar */}
      <div style={{
        padding: "8px 14px", background: "#fff", borderBottom: "1px solid #e2e8f0",
        display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap", flexShrink: 0,
      }}>
        <span style={{
          borderRadius: 999,
          background: "#fef3c7",
          color: "#92400e",
          padding: "5px 10px", fontSize: 11, fontWeight: 800,
        }}>
          Engine tự động
        </span>
        <button
          type="button"
          disabled={!breakdowns.length}
          onClick={() => setShowBreakdown((visible) => !visible)}
          style={{
            border: "1px solid #cbd5e1", borderRadius: 999, background: "#fff",
            color: "#334155", padding: "5px 12px", fontWeight: 700, fontSize: 12,
            cursor: breakdowns.length ? "pointer" : "not-allowed", opacity: breakdowns.length ? 1 : 0.5,
          }}
        >
          {showBreakdown ? "Ẩn cách tính" : "Xem cách tính"}
        </button>
      </div>

      {showBreakdown && breakdowns.length > 0 && (
        <div style={{ padding: "8px 14px", background: "#f8fafc", borderBottom: "1px solid #e2e8f0", fontSize: 12 }}>
          {breakdowns.map((item) => (
            <div key={item.personId} style={{ padding: "3px 0", color: "#334155" }}>
              {formatBreakdownLine(item)}
            </div>
          ))}
        </div>
      )}

      {/* Diagram */}
      <div style={{ flex: 1, overflow: "hidden", position: "relative" }}>
        <TieredDiagram
          resolvedNodes={resolvedNodes}
          handlers={handlers}
          shareMode={shareMode}
          warnings={warnings}
          engineState={diagramEngineState}
        />
      </div>
    </div>
  );
}

// ─── Bootstrap ────────────────────────────────────────────────────────────────

if (!rootElement) {
  console.warn("react-flow-root not found");
} else {
  const root = ReactDOM.createRoot(rootElement);
  root.render(<FamilyTreeApp />);
}
