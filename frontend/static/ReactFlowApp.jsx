// ─────────────────────────────────────────────────────────────────────────────
// ReactFlowApp.jsx — Sơ đồ thừa kế (Brick-Wall Layout)
// Không dùng ReactFlow/Dagre. Render thuần HTML/CSS theo tầng.
// ─────────────────────────────────────────────────────────────────────────────
const { useState, useEffect, useCallback, useRef } = React;

const rootElement = document.getElementById("react-flow-root");
const initParticipants = window.__INITIAL_PARTICIPANTS__ || [];
const allCustomers = window.__ALL_CUSTOMERS_DATA__ || [];
const initialOwnerId = document.getElementById("case-nguoi-chet")?.value || "";

let bootstrapSeed = 1;

const BASE_NODE_DEFS = [
  {
    id: "father",
    label: "Cha ruột",
    role: "Cha",
    relationType: "parent",
    bucket: 0,
    allowsShare: true,
    removable: false,
    sourceId: null,
  },
  {
    id: "mother",
    label: "Mẹ ruột",
    role: "Mẹ",
    relationType: "parent",
    bucket: 0,
    allowsShare: true,
    removable: false,
    sourceId: null,
  },
  {
    id: "spouse_father",
    label: "Cha vợ/chồng",
    role: "Cha_vc",
    relationType: "spouseParent",
    bucket: 0,
    allowsShare: false,
    removable: false,
    sourceId: null,
  },
  {
    id: "spouse_mother",
    label: "Mẹ vợ/chồng",
    role: "Me_vc",
    relationType: "spouseParent",
    bucket: 0,
    allowsShare: false,
    removable: false,
    sourceId: null,
  },
  {
    id: "owner",
    label: "Chủ đất",
    role: "Owner",
    relationType: "owner",
    bucket: 1,
    allowsShare: false,
    removable: false,
    sourceId: null,
    isLandOwner: true,
  },
  {
    id: "spouse",
    label: "Vợ/Chồng",
    role: "Vợ/Chồng",
    relationType: "spouse",
    bucket: 1,
    allowsShare: true,
    removable: false,
    sourceId: "owner",
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
    receive: String(rawPerson.receive ?? "1"),
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
    manualShare: overrides.manualShare || "",
    willReceive: overrides.willReceive ?? (overrides.allowsShare !== false),
    parentSlotId: overrides.parentSlotId || "",
    parentPersonId: overrides.parentPersonId || "",
    sourceId: overrides.sourceId || null,
    disabledReason: overrides.disabledReason || "",
    deathComparison: overrides.deathComparison || "unknown",
    insightLines: overrides.insightLines || [],
    ghostAction: overrides.ghostAction || "",
    ghostLabel: overrides.ghostLabel || "",
    isLandOwner: overrides.isLandOwner || false,
  };
}

function createBaseNodes() {
  const base = BASE_NODE_DEFS.map((def) => createLogicalNode(def));
  base.push(
    createLogicalNode({
      id: "child_1",
      label: "Con ruột",
      role: "Con",
      relationType: "child",
      bucket: 2,
      allowsShare: true,
      removable: true,
      sourceId: "owner",
      parentSlotId: "owner",
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

function validateAssignment(logicalNodes, nodeId, person) {
  const candidate = normalizePersonPayload(person);
  if (!candidate?.id) return { ok: false, reason: "Không xác định được khách hàng." };
  const targetNode = logicalNodes.find((node) => node.id === nodeId);
  if (!targetNode || targetNode.kind !== "person") return { ok: false, reason: "Ô nhận không hợp lệ." };
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
  if (node.kind === "ghost") {
    if (node.ghostAction === "addSibling") {
      return {
        ...node,
        kind: "person",
        label: "Anh/Chi/Em",
        role: "Anh/Chi/Em",
        relationType: "sibling",
        allowsShare: true,
        removable: true,
        person: candidate,
        parentPersonId: deriveParentPersonId(nodes, node),
        willReceive: !candidate?.death,
        manualShare: "",
        sharePercent: "0.00",
      };
    }
    if (node.ghostAction === "addGrandchild") {
      return {
        ...node,
        kind: "person",
        label: "Con the vi",
        role: "Chau",
        relationType: "grandchild",
        allowsShare: true,
        removable: true,
        person: candidate,
        parentPersonId: deriveParentPersonId(nodes, node),
        willReceive: !candidate?.death,
        manualShare: "",
        sharePercent: "0.00",
      };
    }
    if (node.ghostAction === "addBranchSpouse") {
      return {
        ...node,
        kind: "person",
        label: "Vo/Chong cua nhanh",
        role: "Con_dau_re",
        relationType: "branchSpouse",
        allowsShare: true,
        removable: true,
        person: candidate,
        parentPersonId: deriveParentPersonId(nodes, node),
        willReceive: !candidate?.death,
        manualShare: "",
        sharePercent: "0.00",
      };
    }
  }
  return {
    ...node,
    person: candidate,
    parentPersonId: deriveParentPersonId(nodes, node),
    willReceive: node.allowsShare && !candidate?.death && node.role !== "Owner" ? true : false,
    manualShare: "",
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
  return { nodes: ensureSpareChildNode(nextNodes), displacedPersons };
}

function collectPrunableNodeIds(nodes, targetId) {
  const toRemove = new Set([targetId]);
  let changed = true;
  while (changed) {
    changed = false;
    nodes.forEach((node) => {
      if (toRemove.has(node.id)) return;
      if (node.parentSlotId && toRemove.has(node.parentSlotId)) { toRemove.add(node.id); changed = true; return; }
      if (node.relationType === "sibling" && node.sourceId && toRemove.has(node.sourceId)) { toRemove.add(node.id); changed = true; }
    });
  }
  return toRemove;
}

function collectRemovedPeople(nodes, targetId) {
  const target = nodes.find((node) => node.id === targetId);
  if (!target) return [];
  if (!target.removable) return target.person ? [normalizePersonPayload(target.person)] : [];
  const ids = collectPrunableNodeIds(nodes, targetId);
  return nodes
    .filter((node) => ids.has(node.id) && node.person)
    .map((node) => normalizePersonPayload(node.person));
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

function ensureSpareChildNode(nodes) {
  const childNodes = nodes.filter((node) => node.kind === "person" && node.relationType === "child");
  if (!childNodes.length || childNodes.some((node) => !node.person)) return nodes;
  return [
    ...nodes,
    createDynamicNode("child", {
      label: "Con ruột",
      role: "Con",
      relationType: "child",
      bucket: 2,
      allowsShare: true,
      removable: true,
      sourceId: "owner",
      parentSlotId: "owner",
    }),
  ];
}

function pickSiblingSource(nodes, participant) {
  const fromParentId = nodes.find(
    (node) =>
      node.kind === "person" &&
      (node.role === "Cha" || node.role === "Mẹ") &&
      node.person &&
      String(node.person.id) === String(participant.parentId || "")
  );
  if (fromParentId) return fromParentId.id;
  const fatherNode = nodes.find((node) => node.id === "father" && node.person);
  if (fatherNode) return fatherNode.id;
  const motherNode = nodes.find((node) => node.id === "mother" && node.person);
  if (motherNode) return motherNode.id;
  return "owner";
}

// ─── Hydrate from saved participants ─────────────────────────────────────────

function hydrateInitialNodes() {
  let nodes = createBaseNodes();
  const ownerPayload = buildOwnerPayload();
  if (ownerPayload) {
    nodes = nodes.map((node) =>
      node.id === "owner" ? { ...node, person: ownerPayload, willReceive: false } : node
    );
  }

  const delayedGrandchildren = [];
  const delayedBranchSpouses = [];

  initParticipants.map(normalizePersonPayload).forEach((participant) => {
    if (!participant || !participant.id) return;

    if (participant.role === "Owner") {
      nodes = nodes.map((node) =>
        node.id === "owner" ? { ...node, person: participant, willReceive: false } : node
      );
      return;
    }

    const sharePercent = participant.share && participant.share !== "None" ? String(participant.share) : "0.00";
    const defaultWillReceive = participant.receive !== "0" && !participant.death;

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
        node.id === "spouse_father" ? { ...node, person: participant, willReceive: false } : node
      );
      return;
    }
    if (participant.role === "Me_vc") {
      nodes = nodes.map((node) =>
        node.id === "spouse_mother" ? { ...node, person: participant, willReceive: false } : node
      );
      return;
    }
    if (participant.role === "Vợ/Chồng") {
      nodes = nodes.map((node) =>
        node.id === "spouse" ? { ...node, person: participant, sharePercent, willReceive: defaultWillReceive } : node
      );
      return;
    }
    if (participant.role === "Con") {
      const target = nodes.find((node) => node.kind === "person" && node.relationType === "child" && !node.person);
      if (target) {
        nodes = nodes.map((node) =>
          node.id === target.id
            ? { ...node, person: participant, sharePercent, willReceive: defaultWillReceive, parentPersonId: buildOwnerPayload()?.id || "" }
            : node
        );
      } else {
        nodes = [
          ...nodes,
          createDynamicNode("child", {
            label: "Con ruột", role: "Con", relationType: "child", bucket: 2,
            allowsShare: true, removable: true, sourceId: "owner", parentSlotId: "owner",
            parentPersonId: buildOwnerPayload()?.id || "",
            person: participant, sharePercent, willReceive: defaultWillReceive,
          }),
        ];
      }
      nodes = ensureSpareChildNode(nodes);
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
        person: participant, sharePercent: participant.share || "0.00",
        willReceive: participant.receive !== "0" && !participant.death,
      }),
    ];
  });

  delayedGrandchildren.forEach((participant) => {
    const parentNode =
      nodes.find((node) => node.kind === "person" && node.relationType === "child" && node.person && String(node.person.id) === String(participant.parentId || "")) ||
      nodes.find((node) => node.kind === "person" && node.relationType === "child" && node.person);
    if (!parentNode) return;
    nodes = [
      ...nodes,
      createDynamicNode("grandchild", {
        label: "Con thế vị", role: "Cháu", relationType: "grandchild", bucket: 3,
        allowsShare: true, removable: true, sourceId: parentNode.id, parentSlotId: parentNode.id,
        parentPersonId: parentNode.person?.id || participant.parentId || "",
        person: participant, sharePercent: participant.share || "0.00",
        willReceive: participant.receive !== "0" && !participant.death,
      }),
    ];
  });

  return ensureSpareChildNode(nodes);
}

// ─── Inheritance calculation ──────────────────────────────────────────────────

function compareDeathDates(ownerDeathDate, personDeathDate) {
  if (!ownerDeathDate || !personDeathDate) return "unknown";
  const ownerTs = ownerDeathDate.getTime();
  const personTs = personDeathDate.getTime();
  if (personTs < ownerTs) return "predeceased";
  if (personTs > ownerTs) return "postdeceased";
  return "simultaneous";
}

function survivesAt(personDeathDate, eventDeathDate) {
  if (!eventDeathDate) return !personDeathDate;
  if (!personDeathDate) return true;
  return personDeathDate.getTime() > eventDeathDate.getTime();
}

function getBaseInsight(node, deathComparison) {
  if (!node.person) return ["Thả người vào ô này để bổ sung quan hệ."];
  if (node.role === "Owner") return ["Người để lại di sản, không tham gia chia suất."];
  if (!node.person.death) return ["Đang còn sống, có thể tham gia chia suất nếu bật nhận."];
  if (deathComparison === "predeceased") return ["Chết trước chủ đất, ưu tiên mở nhánh thế vị."];
  if (deathComparison === "postdeceased") return ["Chết sau chủ đất, ưu tiên nhánh thừa kế chuyển tiếp."];
  if (deathComparison === "simultaneous") return ["Chết cùng thời điểm, cần đối chiếu giấy chứng tử."];
  return ["Đã có thông tin ngày chết, cần bổ sung nhánh liên quan nếu cần."];
}

function buildModelWarnings(models, shareMode) {
  const warnings = [];
  const owner = models.find((node) => node.role === "Owner" && node.person);
  const spouse = models.find((node) => node.role === "Vợ/Chồng" && node.person);

  if (owner?.person && spouse?.person) {
    const ownerGender = String(owner.person.gender || "").trim();
    const spouseGender = String(spouse.person.gender || "").trim();
    if (ownerGender && spouseGender && ownerGender === spouseGender) {
      warnings.push("Chủ đất và vợ/chồng đang cùng giới tính, cần kiểm tra lại quan hệ.");
    }
  }

  const parentNodes = models.filter((node) => node.person && (node.role === "Cha" || node.role === "Mẹ"));
  const childNodes = models.filter((node) => node.person && node.relationType === "child");
  childNodes.forEach((child) => {
    parentNodes.forEach((parent) => {
      const parentBirth = parseFlexibleDate(parent.person.birth);
      const childBirth = parseFlexibleDate(child.person.birth);
      if (!parentBirth || !childBirth) return;
      if (childBirth.getTime() < parentBirth.getTime()) {
        warnings.push(`${child.person.name} có ngày sinh sớm hơn ${parent.person.name}, cần kiểm tra lại.`);
        return;
      }
      const ageDiff = childBirth.getFullYear() - parentBirth.getFullYear();
      if (ageDiff >= 0 && ageDiff < 18) {
        warnings.push(`${child.person.name} và ${parent.person.name} có chênh lệch tuổi dưới 18 năm.`);
      }
    });
  });

  const firstLineReceivers = models.filter(
    (node) => node.person && (node.role === "Cha" || node.role === "Mẹ" || node.role === "Vợ/Chồng" || node.relationType === "child")
  );
  const siblingNodes = models.filter((node) => node.person && node.relationType === "sibling");
  if (!firstLineReceivers.some((node) => !node.disabledReason && node.willReceive) && siblingNodes.length > 0) {
    warnings.push("Hàng thừa kế thứ nhất đang trống hoặc bị loại hết, nhánh anh/chị/em được đưa vào xem xét.");
  }

  models.forEach((node) => {
    if (!node.person || !node.person.death) return;
    if (node.relationType === "child") {
      const hasBranchData = models.some(
        (candidate) => candidate.kind === "person" && candidate.parentSlotId === node.id && !!candidate.person
      );
      if (!hasBranchData) warnings.push(`${node.person.name} đã mất nhưng chưa mở nhánh phát sinh.`);
    }
  });

  if (shareMode === "manual") {
    const manualParticipants = models.filter(
      (node) => node.kind === "person" && node.person && node.allowsShare && !node.disabledReason && node.willReceive
    );
    const total = manualParticipants.reduce((sum, node) => sum + Number(node.sharePercent || 0), 0);
    if (manualParticipants.length > 0 && Math.abs(total - 100) > 0.009) {
      warnings.push(`Tổng tỷ lệ đang là ${total.toFixed(2)}%, cần đưa về 100%.`);
    }
  }

  return Array.from(new Set(warnings));
}

function buildBranchRecipients(models, ownerDeathDate, node) {
  if (!node.person) return [];
  if (!node.person.death) return node.willReceive && !node.disabledReason ? [node] : [];
  const nodeDeathDate = parseFlexibleDate(node.person.death);
  const descendants = models.filter(
    (candidate) =>
      candidate.kind === "person" && candidate.parentSlotId === node.id && candidate.relationType === "grandchild" &&
      candidate.person && !candidate.disabledReason && candidate.willReceive &&
      survivesAt(parseFlexibleDate(candidate.person.death), nodeDeathDate)
  );
  const branchSpouses = models.filter(
    (candidate) =>
      candidate.kind === "person" && candidate.parentSlotId === node.id && candidate.relationType === "branchSpouse" &&
      candidate.person && !candidate.disabledReason && candidate.willReceive &&
      survivesAt(parseFlexibleDate(candidate.person.death), nodeDeathDate)
  );
  if (node.deathComparison === "postdeceased") return [...branchSpouses, ...descendants];
  return descendants;
}

function roundAllocations(allocation) {
  const entries = Array.from(allocation.entries()).filter(([, rawPercent]) => rawPercent > 0);
  const rounded = new Map();
  if (!entries.length) return rounded;
  let usedBasisPoints = 0;
  entries.forEach(([nodeId, rawPercent], index) => {
    if (index === entries.length - 1) { rounded.set(nodeId, (10000 - usedBasisPoints) / 100); return; }
    const basisPoints = Math.floor(rawPercent * 100);
    usedBasisPoints += basisPoints;
    rounded.set(nodeId, basisPoints / 100);
  });
  return rounded;
}

function calculateInheritance(models, shareMode) {
  const owner = models.find((node) => node.role === "Owner" && node.person);
  const ownerDeathDate = parseFlexibleDate(owner?.person?.death);

  let nextModels = models.map((node) => {
    const nextNode = { ...node };
    nextNode.sharePercent = node.sharePercent || "0.00";
    if (!node.person) { nextNode.disabledReason = ""; return nextNode; }
    if (node.role === "Owner") {
      nextNode.willReceive = false; nextNode.sharePercent = "0.00";
      nextNode.disabledReason = "Người để lại di sản."; return nextNode;
    }
    if (!node.allowsShare) {
      nextNode.willReceive = false; nextNode.sharePercent = "0.00";
      nextNode.disabledReason = "Nút quan hệ, không tham gia chia suất."; return nextNode;
    }
    if (node.person.death) {
      nextNode.willReceive = false;
      if (node.relationType === "child") {
        if (node.deathComparison === "postdeceased") nextNode.disabledReason = "Đã mất sau chủ đất, cần phần xuống nhánh chuyển tiếp.";
        else if (node.deathComparison === "predeceased") nextNode.disabledReason = "Đã mất trước chủ đất, cần mở nhánh thế vị.";
        else if (node.deathComparison === "simultaneous") nextNode.disabledReason = "Mất cùng thời điểm, cần kiểm tra hồ sơ.";
        else nextNode.disabledReason = "Đã mất, cần mở nhánh phát sinh.";
      } else if (node.relationType === "parent") nextNode.disabledReason = "Đã mất, có thể cần nhánh anh/chị/em.";
      else if (node.relationType === "sibling") nextNode.disabledReason = "Đã mất, cần kiểm tra nhánh tiếp theo.";
      else nextNode.disabledReason = "Đã mất, không nhận trực tiếp.";
      nextNode.sharePercent = "0.00"; return nextNode;
    }
    nextNode.disabledReason = "";
    if (typeof nextNode.willReceive !== "boolean") nextNode.willReceive = true;
    return nextNode;
  });

  if (shareMode === "manual") {
    return nextModels.map((node) => {
      if (!node.person || !node.allowsShare || node.disabledReason || !node.willReceive) return { ...node, sharePercent: "0.00" };
      const manualNumber = Number(node.manualShare || node.sharePercent || 0);
      const safeValue = Number.isFinite(manualNumber) && manualNumber > 0 ? manualNumber : 0;
      return { ...node, sharePercent: safeValue.toFixed(2) };
    });
  }

  nextModels = nextModels.map((node) => ({ ...node, sharePercent: "0.00" }));

  const parents = nextModels.filter(
    (node) => node.person && (node.role === "Cha" || node.role === "Mẹ") && !node.disabledReason && node.willReceive &&
      survivesAt(parseFlexibleDate(node.person.death), ownerDeathDate)
  );
  const spouse = nextModels.find(
    (node) => node.person && node.role === "Vợ/Chồng" && !node.disabledReason && node.willReceive &&
      survivesAt(parseFlexibleDate(node.person.death), ownerDeathDate)
  );
  const children = nextModels.filter((node) => node.person && node.relationType === "child");

  const firstLineUnits = [
    ...parents.map((node) => [node]),
    ...(spouse ? [[spouse]] : []),
    ...children.map((child) => buildBranchRecipients(nextModels, ownerDeathDate, child)).filter((unit) => unit.length > 0),
  ];

  let activeUnits = firstLineUnits;
  if (!activeUnits.length) {
    activeUnits = nextModels
      .filter((node) => node.person && node.relationType === "sibling" && !node.disabledReason && node.willReceive &&
        survivesAt(parseFlexibleDate(node.person.death), ownerDeathDate))
      .map((node) => [node]);
  }
  if (!activeUnits.length) return nextModels;

  const allocation = new Map();
  const unitPercent = 100 / activeUnits.length;
  activeUnits.forEach((unit) => {
    const activeRecipients = unit.filter((node) => node.person && !node.disabledReason && node.willReceive);
    if (!activeRecipients.length) return;
    const split = unitPercent / activeRecipients.length;
    activeRecipients.forEach((recipient) => { allocation.set(recipient.id, (allocation.get(recipient.id) || 0) + split); });
  });

  const rounded = roundAllocations(allocation);
  return nextModels.map((node) => {
    if (!rounded.has(node.id)) return { ...node, sharePercent: "0.00" };
    return { ...node, sharePercent: Number(rounded.get(node.id)).toFixed(2) };
  });
}

function resolveSubRelations(nodes, shareMode) {
  const owner = nodes.find((node) => node.role === "Owner" && node.person);
  const ownerDeathDate = parseFlexibleDate(owner?.person?.death);

  let resolvedNodes = nodes.map((node) => {
    const person = node.person ? normalizePersonPayload(node.person) : null;
    const deathComparison = person && node.role !== "Owner"
      ? compareDeathDates(ownerDeathDate, parseFlexibleDate(person.death))
      : "unknown";
    return { ...node, person, deathComparison, insightLines: getBaseInsight(node, deathComparison) };
  });

  resolvedNodes = calculateInheritance(resolvedNodes, shareMode);

  const ghostNodes = [];
  const hasDeadFather = resolvedNodes.some((candidate) => candidate.id === "father" && candidate.person && candidate.person.death);
  resolvedNodes.forEach((node) => {
    if (!node.person || !node.person.death) return;

    if ((node.role === "Cha" || (node.role === "Mẹ" && !hasDeadFather)) && node.person.id) {
      ghostNodes.push(createLogicalNode({
        id: `ghost_sibling_${node.id}`, kind: "ghost", label: "Thêm anh/chị/em",
        role: "Anh/Chị/Em", relationType: "ghostSibling", bucket: 1,
        allowsShare: false, removable: false, sourceId: node.id,
        parentSlotId: node.id, parentPersonId: node.person.id,
        ghostAction: "addSibling", ghostLabel: "+ Thêm Anh/Chị/Em",
      }));
    }

    if (node.relationType === "child") {
      ghostNodes.push(createLogicalNode({
        id: `ghost_grandchild_${node.id}`, kind: "ghost", label: "Thêm con thế vị",
        role: "Cháu", relationType: "ghostGrandchild", bucket: 3,
        allowsShare: false, removable: false, sourceId: node.id,
        parentSlotId: node.id, parentPersonId: node.person.id,
        ghostAction: "addGrandchild", ghostLabel: "+ Thêm Cháu thế vị",
      }));

      if (node.deathComparison === "postdeceased") {
        const hasBranchSpouse = resolvedNodes.some(
          (candidate) => candidate.kind === "person" && candidate.parentSlotId === node.id && candidate.relationType === "branchSpouse"
        );
        if (!hasBranchSpouse) {
          ghostNodes.push(createLogicalNode({
            id: `ghost_branch_spouse_${node.id}`, kind: "ghost", label: "Thêm vợ/chồng của nhánh",
            role: "Con_dau_re", relationType: "ghostBranchSpouse", bucket: 3,
            allowsShare: false, removable: false, sourceId: node.id,
            parentSlotId: node.id, parentPersonId: node.person.id,
            ghostAction: "addBranchSpouse", ghostLabel: "+ Thêm Dâu/Rể",
          }));
        }
      }
    }
  });

  const mergedNodes = [...resolvedNodes.filter((node) => node.kind !== "ghost"), ...ghostNodes];
  const warnings = buildModelWarnings(mergedNodes, shareMode);
  return { nodes: mergedNodes, warnings };
}

// ─── Brick-Wall Render Components ────────────────────────────────────────────

const CARD_WIDTH = 140;

const S = {
  card: (isDragOver, isOccupied, isDead, isGhost) => ({
    width: CARD_WIDTH,
    minHeight: isGhost ? 52 : isOccupied ? 90 : 60,
    border: isGhost
      ? "2px dashed #c084fc"
      : isDragOver
      ? "2px solid #2563eb"
      : isOccupied
      ? "2px solid #d97706"
      : "2px dashed #9ca3af",
    borderRadius: 12,
    background: isGhost
      ? "rgba(245,243,255,.7)"
      : isDragOver
      ? "linear-gradient(180deg,#eff6ff,#dbeafe)"
      : isOccupied
      ? isDead
        ? "linear-gradient(180deg,#f8fafc,#eef2f7)"
        : "linear-gradient(180deg,#fff7ed,#fffdf7)"
      : "#f8fafc",
    boxShadow: isDragOver
      ? "0 0 0 3px rgba(37,99,235,.2), 0 4px 12px rgba(15,23,42,.08)"
      : "0 2px 8px rgba(15,23,42,.07)",
    padding: "6px 8px",
    position: "relative",
    cursor: isGhost ? "pointer" : "default",
    transition: "border .12s, background .12s, box-shadow .12s",
    flexShrink: 0,
    opacity: isDead ? 0.88 : 1,
    filter: isDead ? "grayscale(.18)" : "none",
    boxSizing: "border-box",
  }),
  label: {
    fontSize: 8, fontWeight: 700, color: "#94a3b8", marginBottom: 4,
    whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis",
  },
  name: { fontSize: 12, fontWeight: 800, color: "#0f172a", lineHeight: 1.25, wordBreak: "break-word" },
  meta: { fontSize: 11, color: "#64748b", marginTop: 2 },
  placeholder: { fontSize: 10, color: "#9ca3af", textAlign: "center", padding: "4px 0" },
  insightChip: (color) => ({
    fontSize: 9, color, background: color + "18",
    borderRadius: 6, padding: "2px 6px", marginTop: 4, lineHeight: 1.4,
  }),
  landBadge: (active) => ({
    position: "absolute", top: 6, right: 6,
    fontSize: 12, cursor: "pointer", color: active ? "#d97706" : "#cbd5e1",
    lineHeight: 1, userSelect: "none",
    title: "Chủ sử dụng đất",
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
  manualInput: {
    width: "100%", marginTop: 6, fontSize: 11, padding: "3px 6px",
    borderRadius: 6, border: "1px solid #cbd5e1", boxSizing: "border-box",
  },
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

function buildArrowPoints(centerX, tipY) {
  return `${centerX},${tipY} ${centerX - 6},${tipY - 5} ${centerX + 6},${tipY - 5}`;
}

function appendBracketConnector(lines, arrows, parentBox, childBoxes, options = {}) {
  const validChildren = childBoxes.filter(Boolean);
  if (!parentBox || !validChildren.length) return;
  const parentX = getBoxCenterX(parentBox);
  const parentY = getBoxBottomY(parentBox) + (options.parentGap ?? 6);
  const childStops = validChildren.map((box) => ({
    centerX: getBoxCenterX(box),
    lineEndY: Math.max(box.top - (options.childGap ?? 10), parentY + 14),
    arrowTipY: Math.max(box.top - 3, parentY + 18),
  }));
  const minChildTop = Math.min(...childStops.map((item) => item.lineEndY));
  if (minChildTop <= parentY) return;
  const barY = Math.max(parentY + 12, parentY + Math.round((minChildTop - parentY) * 0.45));
  const leftX = Math.min(...childStops.map((item) => item.centerX));
  const rightX = Math.max(...childStops.map((item) => item.centerX));
  const keyPrefix = options.key || "connector";

  lines.push({ x1: parentX, y1: parentY, x2: parentX, y2: barY, key: `${keyPrefix}:stem` });
  lines.push({ x1: leftX, y1: barY, x2: rightX, y2: barY, key: `${keyPrefix}:bar` });
  childStops.forEach((item, index) => {
    lines.push({
      x1: item.centerX,
      y1: barY,
      x2: item.centerX,
      y2: item.lineEndY,
      key: `${keyPrefix}:drop:${index}`,
    });
    arrows.push({
      points: buildArrowPoints(item.centerX, item.arrowTipY),
      key: `${keyPrefix}:arrow:${index}`,
    });
  });
}

const BrickCard = React.forwardRef(function BrickCard(
  { node, onAssign, onRemove, onToggleReceive, onToggleLandOwner, onMoveWithin, onShareInputChange, onGhostExpand, onValidateAssign, shareMode },
  ref
) {
  const [isDragOver, setIsDragOver] = useState(false);
  const isOccupied = !!node.person;
  const isDead = !!node.person?.death;
  const isGhost = node.kind === "ghost";
  const canToggleReceive = isOccupied && node.allowsShare && !node.disabledReason && !isDead && node.role !== "Owner";
  const displayLabel = isGhost
    ? (node.ghostAction === "addGrandchild"
      ? "Con the vi"
      : node.ghostAction === "addBranchSpouse"
      ? "Vo/Chong cua nhanh"
      : node.ghostAction === "addSibling"
      ? "Anh/Chi/Em"
      : node.label)
    : node.label;

  const handleDragOver = (e) => {
    e.preventDefault(); e.stopPropagation();
    // Don't set dropEffect — let browser pick compatible value with source's effectAllowed
    setIsDragOver(true);
  };
  const handleDragLeave = (e) => {
    if (!e.currentTarget.contains(e.relatedTarget)) setIsDragOver(false);
  };
  const handleDrop = (e) => {
    e.preventDefault(); e.stopPropagation();
    setIsDragOver(false);
    // Try application/json first (our own drag), fall back to Text (SortableJS/other)
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
          { id: result.person.id, patch: { deleted: false, inPool: false, inDiagram: true } },
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

  return (
    <div
      ref={ref}
      style={S.card(isDragOver, isOccupied, isDead, isGhost)}
      draggable={isOccupied}
      onDragStart={handleDragStart}
      onDragOver={handleDragOver}
      onDragLeave={handleDragLeave}
      onDrop={handleDrop}
    >
      {/* Label row */}
      <div style={S.label}>{displayLabel}</div>

      {/* Land owner badge */}
      <span
        style={S.landBadge(!!node.isLandOwner)}
        title="Chủ sử dụng đất"
        onClick={(e) => { e.stopPropagation(); if (isOccupied) onToggleLandOwner(node.id); }}
      >★</span>

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

          {node.allowsShare && (
            <div style={S.receiveRow}>
              <label style={S.shareLabel}>
                <input
                  type="checkbox"
                  checked={!!node.willReceive}
                  disabled={!canToggleReceive}
                  onChange={() => onToggleReceive(node.id)}
                />
                Nhận
              </label>
              {node.willReceive && (
                <span style={S.sharePct}>{Number(node.sharePercent || 0).toFixed(2)}%</span>
              )}
            </div>
          )}

          {shareMode === "manual" && node.allowsShare && node.willReceive && !node.disabledReason && (
            <input
              type="number" min="0" max="100" step="0.01"
              style={S.manualInput}
              value={node.manualShare || node.sharePercent || "0"}
              onChange={(e) => onShareInputChange && onShareInputChange(node.id, e.target.value)}
            />
          )}
        </>
      )}
    </div>
  );
});

// Connector symbol between paired nodes
function PairConnector({ show }) {
  if (!show) return <div style={{ width: 20, flexShrink: 0 }} />;
  return (
    <div style={{
      width: 24, flexShrink: 0, display: "flex", alignItems: "center",
      justifyContent: "center", fontSize: 14, color: "#d97706", fontWeight: 900,
    }}>↔</div>
  );
}

function SvgPairConnector({ show }) {
  if (!show) return <div style={{ width: 20, flexShrink: 0 }} />;
  return (
    <div style={{ width: 28, height: 24, flexShrink: 0, display: "flex", alignItems: "center", justifyContent: "center" }}>
      <svg width="28" height="16" viewBox="0 0 28 16" aria-hidden="true">
        <line x1="5" y1="8" x2="23" y2="8" stroke="#d97706" strokeWidth="1.75" strokeDasharray="4 3" strokeLinecap="round" />
        <polyline points="7,5 3,8 7,11" fill="none" stroke="#d97706" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round" />
        <polyline points="21,5 25,8 21,11" fill="none" stroke="#d97706" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round" />
      </svg>
    </div>
  );
}

// A pair of nodes (primary + optional spouse/partner node)
function PairUnit({ primaryNode, spouseNode, handlers, shareMode }) {
  const showConnector = !!spouseNode;
  return (
    <div style={{ display: "flex", alignItems: "flex-start", gap: 0 }}>
      <BrickCard node={primaryNode} {...handlers} shareMode={shareMode} />
      <SvgPairConnector show={showConnector} />
      {spouseNode && <BrickCard node={spouseNode} {...handlers} shareMode={shareMode} />}
    </div>
  );
}

// Ghost button for tier
function GhostButton({ node, onGhostExpand }) {
  return (
    <div
      style={{
        width: 120, minHeight: 52, border: "2px dashed #c084fc",
        borderRadius: 12, background: "rgba(245,243,255,.7)",
        display: "flex", alignItems: "center", justifyContent: "center",
        cursor: "pointer", flexShrink: 0,
      }}
      onClick={() => onGhostExpand(node.id)}
    >
      <span style={{ fontSize: 11, color: "#7c3aed", fontWeight: 700 }}>{node.ghostLabel}</span>
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

function TieredDiagramLegacy({ resolvedNodes, handlers, shareMode, warnings }) {
  const handleDragOver = (e) => { e.preventDefault(); e.dataTransfer.dropEffect = "copy"; };
  const handleDrop = (e) => e.preventDefault();

  const personNodes = resolvedNodes.filter((n) => n.kind === "person");
  const ghostNodes = resolvedNodes.filter((n) => n.kind === "ghost");

  // ── Tier 0: Cha Mẹ ──────────────────────────────────────────────────────────
  function renderTier0() {
    const father = personNodes.find((n) => n.id === "father");
    const mother = personNodes.find((n) => n.id === "mother");
    const spFather = personNodes.find((n) => n.id === "spouse_father");
    const spMother = personNodes.find((n) => n.id === "spouse_mother");
    if (!father && !mother && !spFather && !spMother) return null;
    return (
      <div style={{ display: "flex", flexWrap: "wrap", gap: 10, alignItems: "flex-start" }}>
        {(father || mother) && (
          <div style={{ display: "flex", alignItems: "flex-start", gap: 0 }}>
            {father && <BrickCard node={father} {...handlers} shareMode={shareMode} />}
            <SvgPairConnector show={!!(father && mother)} />
            {mother && <BrickCard node={mother} {...handlers} shareMode={shareMode} />}
          </div>
        )}
        {(spFather || spMother) && (
          <>
            <div style={{ width: 1, background: "#e2e8f0", alignSelf: "stretch", margin: "0 6px" }} />
            <div style={{ display: "flex", alignItems: "flex-start", gap: 0 }}>
              {spFather && <BrickCard node={spFather} {...handlers} shareMode={shareMode} />}
              <SvgPairConnector show={!!(spFather && spMother)} />
              {spMother && <BrickCard node={spMother} {...handlers} shareMode={shareMode} />}
            </div>
          </>
        )}
      </div>
    );
  }

  // ── Tier 1: Chủ Đất ─────────────────────────────────────────────────────────
  function renderTier1() {
    const owner = personNodes.find((n) => n.id === "owner");
    const spouse = personNodes.find((n) => n.id === "spouse");
    const siblings = personNodes.filter((n) => n.relationType === "sibling");
    const ghostSiblings = ghostNodes.filter((n) => n.relationType === "ghostSibling");
    return (
      <div style={{ display: "flex", flexWrap: "wrap", gap: 10, alignItems: "flex-start" }}>
        {/* Owner + Spouse pair */}
        {owner && (
          <div style={{ display: "flex", alignItems: "flex-start", gap: 0 }}>
            <BrickCard node={owner} {...handlers} shareMode={shareMode} />
            <SvgPairConnector show={!!spouse} />
            {spouse && <BrickCard node={spouse} {...handlers} shareMode={shareMode} />}
          </div>
        )}
        {/* Siblings */}
        {(siblings.length > 0 || ghostSiblings.length > 0) && (
          <>
            <div style={{ width: 1, background: "#e2e8f0", alignSelf: "stretch", margin: "0 6px" }} />
            {siblings.map((sib) => (
              <BrickCard key={sib.id} node={sib} {...handlers} shareMode={shareMode} />
            ))}
            {ghostSiblings.map((g) => (
              <BrickCard key={g.id} node={g} {...handlers} shareMode={shareMode} />
            ))}
          </>
        )}
      </div>
    );
  }

  // ── Tier 2: Con ─────────────────────────────────────────────────────────────
  function renderTier2() {
    const children = personNodes.filter((n) => n.relationType === "child");
    const ghostChildren = ghostNodes.filter((n) => n.ghostAction === "addChild");

    return (
      <div style={{ display: "flex", flexWrap: "wrap", gap: 12, alignItems: "flex-start" }}>
        {children.map((child) => {
          const branchSpouseNode =
            personNodes.find((n) => n.relationType === "branchSpouse" && n.parentSlotId === child.id) ||
            ghostNodes.find((n) => n.relationType === "ghostBranchSpouse" && n.parentSlotId === child.id);
          const hasBranchSpouseSlot = !!branchSpouseNode;
          return (
            <div key={child.id} style={{ display: "flex", alignItems: "flex-start", gap: 0 }}>
              <BrickCard node={child} {...handlers} shareMode={shareMode} />
              {hasBranchSpouseSlot && (
                <>
                  <SvgPairConnector show />
                  {branchSpouseNode.kind === "ghost"
                    ? <BrickCard node={branchSpouseNode} {...handlers} shareMode={shareMode} />
                    : <BrickCard node={branchSpouseNode} {...handlers} shareMode={shareMode} />
                  }
                </>
              )}
            </div>
          );
        })}
        {ghostChildren.map((g) => (
          <BrickCard key={g.id} node={g} {...handlers} shareMode={shareMode} />
        ))}
      </div>
    );
  }

  // ── Tier 3: Cháu ─────────────────────────────────────────────────────────────
  function renderTier3() {
    const grandchildren = personNodes.filter((n) => n.relationType === "grandchild");
    const ghostGrandchildren = ghostNodes.filter((n) => n.relationType === "ghostGrandchild");
    const allParentIds = Array.from(new Set([
      ...grandchildren.map((n) => n.parentSlotId),
      ...ghostGrandchildren.map((n) => n.parentSlotId),
    ]));
    if (!allParentIds.length) return null;

    return (
      <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
        {allParentIds.map((parentId) => {
          const parentNode = personNodes.find((n) => n.id === parentId);
          const branchLabel = parentNode?.person?.name || parentId;
          const branchGrandchildren = grandchildren.filter((n) => n.parentSlotId === parentId);
          const branchGhosts = ghostGrandchildren.filter((n) => n.parentSlotId === parentId);
          return (
            <div key={parentId}>
              <div style={{ fontSize: 10, color: "#8b5cf6", fontWeight: 700, marginBottom: 6, letterSpacing: ".04em" }}>
                Nhánh của {branchLabel}:
              </div>
              <div style={{ display: "flex", flexWrap: "wrap", gap: 10, alignItems: "flex-start" }}>
                {branchGrandchildren.map((gc) => (
                  <BrickCard key={gc.id} node={gc} {...handlers} shareMode={shareMode} />
                ))}
                {branchGhosts.map((g) => (
                  <BrickCard key={g.id} node={g} {...handlers} shareMode={shareMode} />
                ))}
              </div>
            </div>
          );
        })}
      </div>
    );
  }

  const tier0Content = renderTier0();
  const tier1Content = renderTier1();
  const tier2Content = renderTier2();
  const tier3Content = renderTier3();

  return (
    <div
      style={{ width: "100%", height: "100%", overflowY: "auto", boxSizing: "border-box" }}
      onDragOver={handleDragOver}
      onDrop={handleDrop}
    >
      {/* Tier 0 */}
      {tier0Content && (
        <div style={{ borderTop: "2px solid #e2e8f0", padding: "12px 16px 16px" }}>
          <TierHeader def={TIER_DEFS[0]} />
          {tier0Content}
        </div>
      )}

      {/* Tier 1 */}
      {tier1Content && (
        <div style={{ borderTop: "2px solid #e2e8f0", padding: "12px 16px 16px" }}>
          <TierHeader def={TIER_DEFS[1]} />
          {tier1Content}
        </div>
      )}

      {/* Tier 2 */}
      {tier2Content && (
        <div style={{ borderTop: "2px solid #e2e8f0", padding: "12px 16px 16px" }}>
          <TierHeader def={TIER_DEFS[2]} />
          {tier2Content}
        </div>
      )}

      {/* Tier 3 — only when exists */}
      {tier3Content && (
        <div style={{ borderTop: "2px solid #e2e8f0", padding: "12px 16px 16px" }}>
          <TierHeader def={TIER_DEFS[3]} />
          {tier3Content}
        </div>
      )}
    </div>
  );
}

// ─── FamilyTreeApp (main component) ─────────────────────────────────────────

function TieredDiagram({ resolvedNodes, handlers, shareMode, warnings }) {
  const containerRef = useRef(null);
  const contentRef = useRef(null);
  const nodeRefs = useRef({});
  const groupRefs = useRef({});
  const drawFrameRef = useRef(0);
  const [connectorModel, setConnectorModel] = useState({ width: 0, height: 0, lines: [], arrows: [] });

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

  const personNodes = resolvedNodes.filter((n) => n.kind === "person");
  const ghostNodes = resolvedNodes.filter((n) => n.kind === "ghost");
  const father = personNodes.find((n) => n.id === "father");
  const mother = personNodes.find((n) => n.id === "mother");
  const spFather = personNodes.find((n) => n.id === "spouse_father");
  const spMother = personNodes.find((n) => n.id === "spouse_mother");
  const owner = personNodes.find((n) => n.id === "owner");
  const spouse = personNodes.find((n) => n.id === "spouse");
  const siblings = personNodes.filter((n) => n.relationType === "sibling");
  const ghostSiblings = ghostNodes.filter((n) => n.relationType === "ghostSibling");
  const children = personNodes.filter((n) => n.relationType === "child");
  const ghostChildren = ghostNodes.filter((n) => n.ghostAction === "addChild");
  const grandchildren = personNodes.filter((n) => n.relationType === "grandchild");
  const ghostGrandchildren = ghostNodes.filter((n) => n.relationType === "ghostGrandchild");
  const allGrandchildParentIds = Array.from(new Set([
    ...grandchildren.map((n) => n.parentSlotId),
    ...ghostGrandchildren.map((n) => n.parentSlotId),
  ]));

  const drawConnectors = useCallback(() => {
    const contentElement = contentRef.current;
    if (!contentElement) return;

    const getNodeBox = (nodeId) => getRelativeBox(nodeRefs.current[nodeId], contentElement);
    const getGroupBox = (groupId) => getRelativeBox(groupRefs.current[groupId], contentElement);
    const lines = [];
    const arrows = [];

    const ownerSiblingTargets = [
      owner?.person ? getNodeBox("owner") : null,
      ...siblings.filter((node) => !!node.person).map((node) => getNodeBox(node.id)),
    ].filter(Boolean);

    if ((father?.person || mother?.person) && ownerSiblingTargets.length) {
      appendBracketConnector(lines, arrows, getGroupBox("birthParentsPair"), ownerSiblingTargets, { key: "birth-family" });
    }

    if ((spFather?.person || spMother?.person) && spouse?.person) {
      appendBracketConnector(lines, arrows, getGroupBox("spouseParentsPair"), [getNodeBox("spouse")], { key: "spouse-family" });
    }

    const occupiedChildBoxes = children
      .filter((node) => !!node.person)
      .map((node) => getNodeBox(node.id))
      .filter(Boolean);

    if (owner?.person && occupiedChildBoxes.length) {
      appendBracketConnector(lines, arrows, getNodeBox("owner"), occupiedChildBoxes, { key: "owner-children" });
    }

    children.forEach((child) => {
      if (!child.person) return;
      const branchBox = getGroupBox(`grandchildBranch:${child.id}`);
      if (!branchBox) return;
      appendBracketConnector(
        lines,
        arrows,
        getGroupBox(`childPair:${child.id}`) || getNodeBox(child.id),
        [branchBox],
        { key: `child-branch:${child.id}`, childGap: 12 }
      );
    });

    setConnectorModel({
      width: Math.max(contentElement.scrollWidth, contentElement.clientWidth),
      height: Math.max(contentElement.scrollHeight, contentElement.clientHeight),
      lines,
      arrows,
    });
  }, [children, father, mother, owner, siblings, spFather, spMother, spouse]);

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
  }, [scheduleConnectorDraw, resolvedNodes]);

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

  function renderTier0() {
    if (!father && !mother && !spFather && !spMother) return null;
    return (
      <div style={{ display: "flex", flexWrap: "wrap", gap: 10, alignItems: "flex-start" }}>
        {(father || mother) && (
          <div ref={setGroupRef("birthParentsPair")} style={{ display: "flex", alignItems: "flex-start", gap: 0 }}>
            {father && <BrickCard ref={setNodeRef(father.id)} node={father} {...handlers} shareMode={shareMode} />}
            <SvgPairConnector show={!!(father && mother)} />
            {mother && <BrickCard ref={setNodeRef(mother.id)} node={mother} {...handlers} shareMode={shareMode} />}
          </div>
        )}
        {(spFather || spMother) && (
          <>
            <div style={{ width: 1, background: "#e2e8f0", alignSelf: "stretch", margin: "0 6px" }} />
            <div ref={setGroupRef("spouseParentsPair")} style={{ display: "flex", alignItems: "flex-start", gap: 0 }}>
              {spFather && <BrickCard ref={setNodeRef(spFather.id)} node={spFather} {...handlers} shareMode={shareMode} />}
              <SvgPairConnector show={!!(spFather && spMother)} />
              {spMother && <BrickCard ref={setNodeRef(spMother.id)} node={spMother} {...handlers} shareMode={shareMode} />}
            </div>
          </>
        )}
      </div>
    );
  }

  function renderTier1() {
    return (
      <div style={{ display: "flex", flexWrap: "wrap", gap: 10, alignItems: "flex-start" }}>
        {owner && (
          <div ref={setGroupRef("ownerPair")} style={{ display: "flex", alignItems: "flex-start", gap: 0 }}>
            <BrickCard ref={setNodeRef(owner.id)} node={owner} {...handlers} shareMode={shareMode} />
            <SvgPairConnector show={!!spouse} />
            {spouse && <BrickCard ref={setNodeRef(spouse.id)} node={spouse} {...handlers} shareMode={shareMode} />}
          </div>
        )}
        {(siblings.length > 0 || ghostSiblings.length > 0) && (
          <>
            <div style={{ width: 1, background: "#e2e8f0", alignSelf: "stretch", margin: "0 6px" }} />
            <div ref={setGroupRef("siblingsGroup")} style={{ display: "flex", flexWrap: "wrap", gap: 10, alignItems: "flex-start" }}>
              {siblings.map((sib) => (
                <BrickCard key={sib.id} ref={setNodeRef(sib.id)} node={sib} {...handlers} shareMode={shareMode} />
              ))}
              {ghostSiblings.map((g) => (
                <BrickCard key={g.id} ref={setNodeRef(g.id)} node={g} {...handlers} shareMode={shareMode} />
              ))}
            </div>
          </>
        )}
      </div>
    );
  }

  function renderTier2() {
    return (
      <div ref={setGroupRef("childrenRow")} style={{ display: "flex", flexWrap: "wrap", gap: 12, alignItems: "flex-start" }}>
        {children.map((child) => {
          const branchSpouseNode =
            personNodes.find((n) => n.relationType === "branchSpouse" && n.parentSlotId === child.id) ||
            ghostNodes.find((n) => n.relationType === "ghostBranchSpouse" && n.parentSlotId === child.id);
          const hasBranchSpouseSlot = !!branchSpouseNode;
          return (
            <div key={child.id} ref={setGroupRef(`childPair:${child.id}`)} style={{ display: "flex", alignItems: "flex-start", gap: 0 }}>
              <BrickCard ref={setNodeRef(child.id)} node={child} {...handlers} shareMode={shareMode} />
              {hasBranchSpouseSlot && (
                <>
                  <SvgPairConnector show />
                  {branchSpouseNode.kind === "ghost"
                    ? <BrickCard ref={setNodeRef(branchSpouseNode.id)} node={branchSpouseNode} {...handlers} shareMode={shareMode} />
                    : <BrickCard ref={setNodeRef(branchSpouseNode.id)} node={branchSpouseNode} {...handlers} shareMode={shareMode} />
                  }
                </>
              )}
            </div>
          );
        })}
        {ghostChildren.map((g) => (
          <BrickCard key={g.id} ref={setNodeRef(g.id)} node={g} {...handlers} shareMode={shareMode} />
        ))}
      </div>
    );
  }

  function renderTier3() {
    if (!allGrandchildParentIds.length) return null;
    return (
      <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
        {allGrandchildParentIds.map((parentId) => {
          const parentNode = personNodes.find((n) => n.id === parentId);
          const branchLabel = parentNode?.person?.name || parentId;
          const branchGrandchildren = grandchildren.filter((n) => n.parentSlotId === parentId);
          const branchGhosts = ghostGrandchildren.filter((n) => n.parentSlotId === parentId);
          return (
            <div key={parentId} ref={setGroupRef(`grandchildBranch:${parentId}`)}>
              <div style={{ fontSize: 10, color: "#8b5cf6", fontWeight: 700, marginBottom: 6, letterSpacing: ".04em" }}>
                {"Nh\u00E1nh c\u1EE7a "}{branchLabel}:
              </div>
              <div style={{ display: "flex", flexWrap: "wrap", gap: 10, alignItems: "flex-start" }}>
                {branchGrandchildren.map((gc) => (
                  <BrickCard key={gc.id} ref={setNodeRef(gc.id)} node={gc} {...handlers} shareMode={shareMode} />
                ))}
                {branchGhosts.map((g) => (
                  <BrickCard key={g.id} ref={setNodeRef(g.id)} node={g} {...handlers} shareMode={shareMode} />
                ))}
              </div>
            </div>
          );
        })}
      </div>
    );
  }

  const tier0Content = renderTier0();
  const tier1Content = renderTier1();
  const tier2Content = renderTier2();
  const tier3Content = renderTier3();

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
          {connectorModel.lines.map((line) => (
            <line
              key={line.key}
              x1={line.x1}
              y1={line.y1}
              x2={line.x2}
              y2={line.y2}
              stroke="#94a3b8"
              strokeWidth="1.6"
              strokeLinecap="round"
            />
          ))}
          {connectorModel.arrows.map((arrow) => (
            <polygon key={arrow.key} points={arrow.points} fill="#64748b" />
          ))}
        </svg>

        <div style={{ position: "relative", zIndex: 1 }}>
          {tier0Content && (
            <div style={{ borderTop: "2px solid #e2e8f0", padding: "12px 16px 16px" }}>
              <TierHeader def={TIER_DEFS[0]} />
              {tier0Content}
            </div>
          )}

          {tier1Content && (
            <div style={{ borderTop: "2px solid #e2e8f0", padding: "12px 16px 16px" }}>
              <TierHeader def={TIER_DEFS[1]} />
              {tier1Content}
            </div>
          )}

          {tier2Content && (
            <div style={{ borderTop: "2px solid #e2e8f0", padding: "12px 16px 16px" }}>
              <TierHeader def={TIER_DEFS[2]} />
              {tier2Content}
            </div>
          )}

          {tier3Content && (
            <div style={{ borderTop: "2px solid #e2e8f0", padding: "12px 16px 16px" }}>
              <TierHeader def={TIER_DEFS[3]} />
              {tier3Content}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

function FamilyTreeApp() {
  const counterRef = useRef(Date.now());
  const [logicalNodes, setLogicalNodes] = useState(() => hydrateInitialNodes());
  const [shareMode, setShareMode] = useState("auto");
  const [resolvedNodes, setResolvedNodes] = useState([]);
  const [warnings, setWarnings] = useState([]);

  const nextId = useCallback((prefix) => {
    counterRef.current += 1;
    return `${prefix}_${counterRef.current}`;
  }, []);

  const pruneLinkedNodes = useCallback((nodes, targetId) => {
    if (targetId === "__noop__") return nodes.slice();
    const toRemove = collectPrunableNodeIds(nodes, targetId);
    return nodes.filter((node) => !toRemove.has(node.id));
  }, []);

  const materializeGhostNode = useCallback((node, prevNodes, person) => {
    if (!node) return node;
    const parentPersonId =
      node.parentSlotId && node.parentSlotId !== "owner"
        ? prevNodes.find((candidate) => candidate.id === node.parentSlotId)?.person?.id || node.parentPersonId || ""
        : node.role === "Con" ? prevNodes.find((candidate) => candidate.id === "owner")?.person?.id || "" : node.parentPersonId || "";
    if (node.kind !== "ghost") {
      return {
        ...node,
        person,
        parentPersonId,
        willReceive: node.allowsShare && !person.death && node.role !== "Owner" ? true : false,
        manualShare: "",
        sharePercent: "0.00",
      };
    }

    const sharedProps = {
      ...node,
      kind: "person",
      person,
      parentPersonId,
      allowsShare: true,
      removable: true,
      willReceive: !person.death,
      manualShare: "",
      sharePercent: "0.00",
    };

    if (node.ghostAction === "addSibling") {
      return { ...sharedProps, label: "Anh/Chá»‹/Em", role: "Anh/Chá»‹/Em", relationType: "sibling" };
    }
    if (node.ghostAction === "addGrandchild") {
      return { ...sharedProps, label: "Con tháº¿ vá»‹", role: "ChÃ¡u", relationType: "grandchild" };
    }
    if (node.ghostAction === "addBranchSpouse") {
      return { ...sharedProps, label: "Vá»£/Chá»“ng cá»§a nhÃ¡nh", role: "Con_dau_re", relationType: "branchSpouse" };
    }
    return sharedProps;
  }, []);

  const onAssign = useCallback((nodeId, rawPerson) => {
    const person = normalizePersonPayload(rawPerson);
    if (!person || !person.id) return;
    setLogicalNodes((prevNodes) => {
      const duplicate = prevNodes.find(
        (node) => node.id !== nodeId && node.kind === "person" && node.person && String(node.person.id) === String(person.id)
      );
      if (duplicate) { window.alert(`${person.name || "Người này"} đã có mặt trong sơ đồ.`); return prevNodes; }
      const nextNodes = prevNodes.map((node) => {
        if (node.id !== nodeId) return node;
        return materializeGhostNode(node, prevNodes, person);
      });
      return ensureSpareChildNode(nextNodes);
    });
  }, [materializeGhostNode]);

  const onRemove = useCallback((nodeId) => {
    setLogicalNodes((prevNodes) => {
      const target = prevNodes.find((node) => node.id === nodeId);
      if (!target) return prevNodes;
      if (!target.removable) {
        return prevNodes.map((node) =>
          node.id === nodeId ? { ...node, person: null, willReceive: false, manualShare: "", sharePercent: "0.00" } : node
        );
      }
      return ensureSpareChildNode(pruneLinkedNodes(prevNodes, nodeId));
    });
  }, [pruneLinkedNodes]);

  const onMoveWithin = useCallback((sourceNodeId, targetNodeId) => {
    setLogicalNodes((prev) => {
      const source = prev.find((n) => n.id === sourceNodeId);
      if (!source?.person) return prev;
      const person = source.person;
      return ensureSpareChildNode(
        prev.map((n) => {
          if (n.id === sourceNodeId) return { ...n, person: null, willReceive: false, sharePercent: "0.00", manualShare: "" };
          if (n.id === targetNodeId) return materializeGhostNode(n, prev, person);
          return n;
        })
      );
    });
  }, [materializeGhostNode]);

  const preflightAssign = useCallback((nodeId, rawPerson) => {
    return validateAssignment(logicalNodes, nodeId, normalizePersonPayload(rawPerson));
  }, [logicalNodes]);

  const commitAssign = useCallback((nodeId, rawPerson) => {
    const person = normalizePersonPayload(rawPerson);
    const validation = validateAssignment(logicalNodes, nodeId, person);
    if (!validation.ok) return validation;
    const preview = assignPersonToNode(logicalNodes, nodeId, validation.person);
    setLogicalNodes((prevNodes) => {
      const recheck = validateAssignment(prevNodes, nodeId, validation.person);
      if (!recheck.ok) return prevNodes;
      return assignPersonToNode(prevNodes, nodeId, validation.person).nodes;
    });
    return { ok: true, person: validation.person, displacedPersons: preview.displacedPersons };
  }, [logicalNodes]);

  const removeWithWorkflow = useCallback((nodeId) => {
    const affectedPeople = collectRemovedPeople(logicalNodes, nodeId);
    onRemove(nodeId);
    // Chỉ cập nhật inDiagram — HTML tree là projection riêng biệt, không được tự xóa inTree từ đây
    bridgeWorkflowUpdates(affectedPeople.map((person) => ({
      id: person.id,
      patch: { inDiagram: false, inPool: true },
    })));
  }, [logicalNodes, onRemove]);

  const moveWithinDiagram = useCallback((sourceNodeId, targetNodeId) => {
    setLogicalNodes((prev) => {
      const source = prev.find((n) => n.id === sourceNodeId);
      if (!source?.person) return prev;
      const sourcePerson = normalizePersonPayload(source.person);
      const target = prev.find((n) => n.id === targetNodeId);
      const targetPerson = target?.person ? normalizePersonPayload(target.person) : null;
      return ensureSpareChildNode(
        prev.map((node) => {
          if (node.id === sourceNodeId) {
            if (!targetPerson) return { ...node, person: null, willReceive: false, sharePercent: "0.00", manualShare: "" };
            return buildAssignedNode(node, prev, targetPerson);
          }
          if (node.id === targetNodeId) return buildAssignedNode(node, prev, sourcePerson);
          return node;
        })
      );
    });
  }, []);

  const onToggleReceive = useCallback((nodeId) => {
    setLogicalNodes((prevNodes) =>
      prevNodes.map((node) =>
        node.id === nodeId
          ? { ...node, willReceive: !node.willReceive, manualShare: shareMode === "manual" && node.willReceive ? "0" : node.manualShare }
          : node
      )
    );
  }, [shareMode]);

  const onToggleLandOwner = useCallback((nodeId) => {
    setLogicalNodes((prev) => prev.map((n) => n.id === nodeId ? { ...n, isLandOwner: !n.isLandOwner } : n));
  }, []);

  const onEnableManualMode = useCallback((nodeId) => {
    setShareMode("manual");
    setLogicalNodes((prevNodes) =>
      prevNodes.map((node) => {
        if (node.id === nodeId) return { ...node, manualShare: node.sharePercent || "0.00" };
        if (!node.person || !node.allowsShare || node.disabledReason || !node.willReceive) return node;
        return { ...node, manualShare: node.sharePercent || "0.00" };
      })
    );
  }, []);

  const onResetAutoMode = useCallback(() => {
    setShareMode("auto");
    setLogicalNodes((prevNodes) => prevNodes.map((node) => ({ ...node, manualShare: "" })));
  }, []);

  const onShareInputChange = useCallback((nodeId, value) => {
    setLogicalNodes((prevNodes) =>
      prevNodes.map((node) => node.id === nodeId ? { ...node, manualShare: value } : node)
    );
  }, []);

  useEffect(() => {
    const handleParticipantRecordUpdated = (evt) => {
      const person = normalizePersonPayload(evt?.detail?.customer || evt?.detail);
      if (!person?.id) return;
      setLogicalNodes((prevNodes) =>
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
  }, []);

  const onGhostExpand = useCallback((nodeId) => {
    setLogicalNodes((prevNodes) => {
      const ghostNode = resolveSubRelations(prevNodes, shareMode).nodes.find((node) => node.id === nodeId);
      if (!ghostNode) return prevNodes;

      if (ghostNode.ghostAction === "addSibling") {
        return [...prevNodes, createLogicalNode({
          id: nextId("sibling"), label: "Anh/Chị/Em", role: "Anh/Chị/Em",
          relationType: "sibling", bucket: 1, allowsShare: true, removable: true,
          sourceId: ghostNode.sourceId, parentSlotId: ghostNode.parentSlotId,
          parentPersonId: ghostNode.parentPersonId, willReceive: true,
        })];
      }
      if (ghostNode.ghostAction === "addGrandchild") {
        return [...prevNodes, createLogicalNode({
          id: nextId("grandchild"), label: "Con thế vị", role: "Cháu",
          relationType: "grandchild", bucket: 3, allowsShare: true, removable: true,
          sourceId: ghostNode.sourceId, parentSlotId: ghostNode.parentSlotId,
          parentPersonId: ghostNode.parentPersonId, willReceive: true,
        })];
      }
      if (ghostNode.ghostAction === "addBranchSpouse") {
        const alreadyExists = prevNodes.some(
          (node) => node.kind === "person" && node.parentSlotId === ghostNode.parentSlotId && node.relationType === "branchSpouse"
        );
        if (alreadyExists) return prevNodes;
        return [...prevNodes, createLogicalNode({
          id: nextId("branch_spouse"), label: "Vợ/Chồng của nhánh", role: "Con_dau_re",
          relationType: "branchSpouse", bucket: 3, allowsShare: true, removable: true,
          sourceId: ghostNode.sourceId, parentSlotId: ghostNode.parentSlotId,
          parentPersonId: ghostNode.parentPersonId, willReceive: true,
        })];
      }
      return prevNodes;
    });
  }, [nextId, shareMode]);

  const addChildNode = useCallback(() => {
    setLogicalNodes((prevNodes) => {
      const hasEmptyChild = prevNodes.some((node) => node.kind === "person" && node.relationType === "child" && !node.person);
      if (hasEmptyChild) return prevNodes;
      return [...prevNodes, createLogicalNode({
        id: nextId("child"), label: "Con ruột", role: "Con", relationType: "child", bucket: 2,
        allowsShare: true, removable: true, sourceId: "owner", parentSlotId: "owner",
        parentPersonId: prevNodes.find((node) => node.id === "owner")?.person?.id || "",
        willReceive: true,
      })];
    });
  }, [nextId]);

  // ── Main effect: resolve + dispatch ──────────────────────────────────────────
  useEffect(() => {
    const resolved = resolveSubRelations(logicalNodes, shareMode);
    setResolvedNodes(resolved.nodes);
    setWarnings(resolved.warnings);

    const participants = resolved.nodes
      .filter((n) => n.kind === "person" && n.person)
      .map((n) => ({
        id: n.person.id, role: n.role, name: n.person.name,
        doc: n.person.doc, gender: n.person.gender,
        birth: n.person.birth, death: n.person.death,
        address: n.person.address,
        issue_date: n.person.issue_date,
        issue_place: n.person.issue_place,
        place_of_origin: n.person.place_of_origin,
        willReceive: !!n.willReceive,
        sharePercent: n.sharePercent || "0.00",
        share: n.sharePercent || "0.00",
        disabledReason: n.disabledReason || "",
        relationType: n.relationType,
        deathComparison: n.deathComparison || "unknown",
        parentId: n.parentPersonId || "",
        isLandOwner: !!n.isLandOwner,
      }));

    window.dispatchEvent(new CustomEvent("onFamilyTreeUpdate", {
      detail: { participants, warnings: resolved.warnings, shareMode, updatedAt: new Date().toISOString() },
    }));
  }, [logicalNodes, shareMode]);

  const handlers = {
    onAssign: commitAssign,
    onRemove: removeWithWorkflow,
    onMoveWithin: moveWithinDiagram,
    onValidateAssign: preflightAssign,
    onToggleReceive,
    onToggleLandOwner,
    onEnableManualMode,
    onResetAutoMode,
    onShareInputChange,
    onGhostExpand,
  };

  return (
    <div style={{ width: "100%", height: "100%", display: "flex", flexDirection: "column", position: "relative" }}>
      {/* Toolbar */}
      <div style={{
        padding: "8px 14px", background: "#fff", borderBottom: "1px solid #e2e8f0",
        display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap", flexShrink: 0,
      }}>
        <button
          type="button"
          onClick={addChildNode}
          style={{
            border: "1px solid #e2e8f0", borderRadius: 999, background: "#f8fafc",
            color: "#0f172a", padding: "5px 12px", fontWeight: 700, fontSize: 12,
            cursor: "pointer", boxShadow: "0 1px 4px rgba(15,23,42,.06)",
          }}
        >
          + Thêm Con
        </button>

        <span style={{
          borderRadius: 999,
          background: shareMode === "manual" ? "#dbeafe" : "#fef3c7",
          color: shareMode === "manual" ? "#1d4ed8" : "#92400e",
          padding: "5px 10px", fontSize: 11, fontWeight: 800,
        }}>
          {shareMode === "manual" ? "Chia tay" : "Tự động"}
        </span>

        {shareMode === "manual" && (
          <button
            type="button"
            onClick={onResetAutoMode}
            style={{
              border: "none", borderRadius: 999, background: "#fff", color: "#1d4ed8",
              padding: "5px 10px", fontWeight: 700, fontSize: 11,
              boxShadow: "0 1px 4px rgba(15,23,42,.06)", cursor: "pointer",
            }}
          >
            Đặt lại auto
          </button>
        )}
      </div>

      {/* Diagram */}
      <div style={{ flex: 1, overflow: "hidden", position: "relative" }}>
        <TieredDiagram
          resolvedNodes={resolvedNodes}
          handlers={handlers}
          shareMode={shareMode}
          warnings={warnings}
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
