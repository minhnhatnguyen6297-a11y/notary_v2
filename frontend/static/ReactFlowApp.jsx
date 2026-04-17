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
  return {
    id: String(rawPerson.id || "").trim(),
    name: String(rawPerson.name || "").trim(),
    doc: String(rawPerson.doc || "").trim(),
    role: String(rawPerson.role || "").trim(),
    gender: String(rawPerson.gender || "").trim(),
    birth: String(rawPerson.birth || "").trim(),
    death: String(rawPerson.death || "").trim(),
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
  return allCustomers.find((item) => String(item.id) === String(customerId)) || null;
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

const CARD_WIDTH = 168;

const S = {
  card: (isDragOver, isOccupied, isDead, isGhost) => ({
    width: CARD_WIDTH,
    minHeight: isGhost ? 52 : isOccupied ? 128 : 88,
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
    padding: "8px 10px",
    position: "relative",
    cursor: isGhost ? "pointer" : "default",
    transition: "border .12s, background .12s, box-shadow .12s",
    flexShrink: 0,
    opacity: isDead ? 0.88 : 1,
    filter: isDead ? "grayscale(.18)" : "none",
    boxSizing: "border-box",
  }),
  label: {
    fontSize: 10, fontWeight: 800, textTransform: "uppercase",
    letterSpacing: ".07em", color: "#64748b", marginBottom: 4,
    whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis",
  },
  name: { fontSize: 13, fontWeight: 800, color: "#0f172a", lineHeight: 1.3, wordBreak: "break-word" },
  meta: { fontSize: 11, color: "#64748b", marginTop: 2 },
  placeholder: { fontSize: 11, color: "#9ca3af", textAlign: "center", padding: "8px 0" },
  insightChip: (color) => ({
    fontSize: 10, color, background: color + "18",
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
    marginTop: 8, paddingTop: 6, borderTop: "1px solid rgba(148,163,184,.2)",
  },
  shareLabel: { fontSize: 11, display: "flex", alignItems: "center", gap: 4, color: "#374151", cursor: "pointer" },
  sharePct: {
    fontSize: 11, fontWeight: 800, color: "#c2410c",
    background: "#fff7ed", borderRadius: 999, padding: "1px 6px",
  },
  manualInput: {
    width: "100%", marginTop: 6, fontSize: 11, padding: "3px 6px",
    borderRadius: 6, border: "1px solid #cbd5e1", boxSizing: "border-box",
  },
};

function BrickCard({ node, onAssign, onRemove, onToggleReceive, onToggleLandOwner, onMoveWithin, onShareInputChange, onGhostExpand, shareMode }) {
  const [isDragOver, setIsDragOver] = useState(false);
  const isOccupied = !!node.person;
  const isDead = !!node.person?.death;
  const isGhost = node.kind === "ghost";
  const canToggleReceive = isOccupied && node.allowsShare && !node.disabledReason && !isDead && node.role !== "Owner";

  if (isGhost) {
    return (
      <div
        style={S.card(false, false, false, true)}
        onClick={() => node.ghostAction && onGhostExpand ? onGhostExpand(node.id) : null}
      >
        <div style={{ fontSize: 11, color: "#7c3aed", fontWeight: 700, textAlign: "center", padding: "4px 0" }}>
          {node.ghostLabel}
        </div>
      </div>
    );
  }

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
        onAssign(node.id, payload);
        // Remove the person row from the HTML pool after assigning to diagram
        if (payload.id) {
          const poolRow = document.querySelector(`#people-pool .person-row[data-id="${payload.id}"]`);
          if (poolRow) poolRow.remove();
        }
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
      style={S.card(isDragOver, isOccupied, isDead, false)}
      draggable={isOccupied}
      onDragStart={handleDragStart}
      onDragOver={handleDragOver}
      onDragLeave={handleDragLeave}
      onDrop={handleDrop}
    >
      {/* Label row */}
      <div style={S.label}>{node.label}</div>

      {/* Land owner badge */}
      <span
        style={S.landBadge(!!node.isLandOwner)}
        title="Chủ sử dụng đất"
        onClick={(e) => { e.stopPropagation(); if (isOccupied) onToggleLandOwner(node.id); }}
      >★</span>

      {/* Remove button */}
      {isOccupied && (
        <button style={S.removeBtn} onClick={() => onRemove(node.id)} title="Xoá">×</button>
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
}

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

// A pair of nodes (primary + optional spouse/partner node)
function PairUnit({ primaryNode, spouseNode, handlers, shareMode }) {
  const showConnector = !!spouseNode;
  return (
    <div style={{ display: "flex", alignItems: "flex-start", gap: 0 }}>
      <BrickCard node={primaryNode} {...handlers} shareMode={shareMode} />
      <PairConnector show={showConnector} />
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

function TieredDiagram({ resolvedNodes, handlers, shareMode, warnings }) {
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
            <PairConnector show={!!(father && mother)} />
            {mother && <BrickCard node={mother} {...handlers} shareMode={shareMode} />}
          </div>
        )}
        {(spFather || spMother) && (
          <>
            <div style={{ width: 1, background: "#e2e8f0", alignSelf: "stretch", margin: "0 6px" }} />
            <div style={{ display: "flex", alignItems: "flex-start", gap: 0 }}>
              {spFather && <BrickCard node={spFather} {...handlers} shareMode={shareMode} />}
              <PairConnector show={!!(spFather && spMother)} />
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
            <PairConnector show={!!spouse} />
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
              <GhostButton key={g.id} node={g} onGhostExpand={handlers.onGhostExpand} />
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
                  <PairConnector show />
                  {branchSpouseNode.kind === "ghost"
                    ? <GhostButton node={branchSpouseNode} onGhostExpand={handlers.onGhostExpand} />
                    : <BrickCard node={branchSpouseNode} {...handlers} shareMode={shareMode} />
                  }
                </>
              )}
            </div>
          );
        })}
        {ghostChildren.map((g) => (
          <GhostButton key={g.id} node={g} onGhostExpand={handlers.onGhostExpand} />
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
                  <GhostButton key={g.id} node={g} onGhostExpand={handlers.onGhostExpand} />
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
      {/* Warnings */}
      {warnings && warnings.length > 0 && (
        <div style={{
          margin: "10px 16px 0", padding: "8px 12px", background: "#fffbeb",
          border: "1px solid #fcd34d", borderRadius: 8, fontSize: 11, color: "#92400e",
        }}>
          {warnings.map((w, i) => <div key={i}>⚠ {w}</div>)}
        </div>
      )}

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
    return nodes.filter((node) => !toRemove.has(node.id));
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
        const parentPersonId =
          node.parentSlotId && node.parentSlotId !== "owner"
            ? prevNodes.find((c) => c.id === node.parentSlotId)?.person?.id || node.parentPersonId || ""
            : node.role === "Con" ? prevNodes.find((c) => c.id === "owner")?.person?.id || "" : node.parentPersonId || "";
        return { ...node, person, parentPersonId, willReceive: node.allowsShare && !person.death && node.role !== "Owner" ? true : false, manualShare: "", sharePercent: "0.00" };
      });
      return ensureSpareChildNode(nextNodes);
    });
  }, []);

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
          if (n.id === targetNodeId) return { ...n, person, willReceive: n.allowsShare && !person.death && n.role !== "Owner" };
          return n;
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
    onAssign,
    onRemove,
    onMoveWithin,
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
