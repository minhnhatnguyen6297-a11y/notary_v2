const { useState, useEffect, useCallback, useRef } = React;
const ReactFlowLib = window.ReactFlow || {};
const {
  ReactFlow,
  Controls,
  Background,
  Handle,
  Position,
} = ReactFlowLib;

const dagreLib = window.dagre;
const rootElement = document.getElementById("react-flow-root");
const initParticipants = window.__INITIAL_PARTICIPANTS__ || [];
const allCustomers = window.__ALL_CUSTOMERS_DATA__ || [];
const initialOwnerId = document.getElementById("case-nguoi-chet")?.value || "";

const NODE_WIDTH = 290;
const GHOST_WIDTH = 220;
const NODE_HEIGHT = 205;
const EMPTY_HEIGHT = 118;
const GHOST_HEIGHT = 98;
const LAYOUT_GAP_Y = 220;
const LAYOUT_MARGIN_X = 40;

let bootstrapSeed = 1;

const BASE_NODE_DEFS = [
  {
    id: "father",
    label: "Cha ruột",
    role: "Cha",
    relationType: "parent",
    bucket: 0,
    handles: ["source"],
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
    handles: ["source"],
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
    handles: ["source"],
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
    handles: ["source"],
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
    handles: ["target", "source", "right"],
    allowsShare: false,
    removable: false,
    sourceId: null,
  },
  {
    id: "spouse",
    label: "Vợ/Chồng",
    role: "Vợ/Chồng",
    relationType: "spouse",
    bucket: 1,
    handles: ["left"],
    allowsShare: true,
    removable: false,
    sourceId: "owner",
  },
];

function bootstrapId(prefix) {
  bootstrapSeed += 1;
  return `${prefix}_${bootstrapSeed}`;
}

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

function formatDisplayDate(value) {
  return value ? String(value) : "—";
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
    handles: overrides.handles || ["target", "source"],
    allowsShare: overrides.allowsShare !== false,
    removable: overrides.removable !== false,
    person: overrides.person || null,
    sharePercent: overrides.sharePercent || "0.00",
    manualShare: overrides.manualShare || "",
    willReceive: overrides.willReceive ?? (overrides.allowsShare !== false),
    parentSlotId: overrides.parentSlotId || "",
    parentPersonId: overrides.parentPersonId || "",
    sourceId: overrides.sourceId || null,
    sourceHandle: overrides.sourceHandle || null,
    targetHandle: overrides.targetHandle || null,
    disabledReason: overrides.disabledReason || "",
    deathComparison: overrides.deathComparison || "unknown",
    insightLines: overrides.insightLines || [],
    ghostAction: overrides.ghostAction || "",
    ghostLabel: overrides.ghostLabel || "",
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
      handles: ["target", "source", "right"],
      allowsShare: true,
      removable: true,
      sourceId: "owner",
      parentSlotId: "owner",
    })
  );
  return base;
}

function createDynamicNode(prefix, config) {
  return createLogicalNode({
    id: bootstrapId(prefix),
    ...config,
  });
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
  if (!childNodes.length || childNodes.some((node) => !node.person)) {
    return nodes;
  }
  return [
    ...nodes,
    createDynamicNode("child", {
      label: "Con ruột",
      role: "Con",
      relationType: "child",
      bucket: 2,
      handles: ["target", "source", "right"],
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

function hydrateInitialNodes() {
  let nodes = createBaseNodes();
  const ownerPayload = buildOwnerPayload();
  if (ownerPayload) {
    nodes = nodes.map((node) =>
      node.id === "owner"
        ? {
            ...node,
            person: ownerPayload,
            willReceive: false,
          }
        : node
    );
  }

  const delayedGrandchildren = [];
  const delayedBranchSpouses = [];

  initParticipants.map(normalizePersonPayload).forEach((participant) => {
    if (!participant || !participant.id) return;

    if (participant.role === "Owner") {
      nodes = nodes.map((node) =>
        node.id === "owner"
          ? {
              ...node,
              person: participant,
              willReceive: false,
            }
          : node
      );
      return;
    }

    const sharePercent = participant.share && participant.share !== "None" ? String(participant.share) : "0.00";
    const defaultWillReceive = participant.receive !== "0" && !participant.death;

    if (participant.role === "Cha") {
      nodes = nodes.map((node) =>
        node.id === "father"
          ? { ...node, person: participant, sharePercent, willReceive: defaultWillReceive }
          : node
      );
      return;
    }
    if (participant.role === "Mẹ") {
      nodes = nodes.map((node) =>
        node.id === "mother"
          ? { ...node, person: participant, sharePercent, willReceive: defaultWillReceive }
          : node
      );
      return;
    }
    if (participant.role === "Cha_vc") {
      nodes = nodes.map((node) =>
        node.id === "spouse_father"
          ? { ...node, person: participant, willReceive: false }
          : node
      );
      return;
    }
    if (participant.role === "Me_vc") {
      nodes = nodes.map((node) =>
        node.id === "spouse_mother"
          ? { ...node, person: participant, willReceive: false }
          : node
      );
      return;
    }
    if (participant.role === "Vợ/Chồng") {
      nodes = nodes.map((node) =>
        node.id === "spouse"
          ? { ...node, person: participant, sharePercent, willReceive: defaultWillReceive }
          : node
      );
      return;
    }
    if (participant.role === "Con") {
      const target = nodes.find(
        (node) => node.kind === "person" && node.relationType === "child" && !node.person
      );
      if (target) {
        nodes = nodes.map((node) =>
          node.id === target.id
            ? {
                ...node,
                person: participant,
                sharePercent,
                willReceive: defaultWillReceive,
                parentPersonId: buildOwnerPayload()?.id || "",
              }
            : node
        );
      } else {
        nodes = [
          ...nodes,
          createDynamicNode("child", {
            label: "Con ruột",
            role: "Con",
            relationType: "child",
            bucket: 2,
            handles: ["target", "source", "right"],
            allowsShare: true,
            removable: true,
            sourceId: "owner",
            parentSlotId: "owner",
            parentPersonId: buildOwnerPayload()?.id || "",
            person: participant,
            sharePercent,
            willReceive: defaultWillReceive,
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
          label: "Anh/Chị/Em",
          role: "Anh/Chị/Em",
          relationType: "sibling",
          bucket: 1,
          handles: ["target", "source"],
          allowsShare: true,
          removable: true,
          sourceId: pickSiblingSource(nodes, participant),
          parentPersonId: participant.parentId || "",
          person: participant,
          sharePercent,
          willReceive: defaultWillReceive,
        }),
      ];
      return;
    }
    if (participant.role === "Con_dau_re") {
      delayedBranchSpouses.push(participant);
      return;
    }
    if (participant.role === "Cháu") {
      delayedGrandchildren.push(participant);
    }
  });

  delayedBranchSpouses.forEach((participant) => {
    const parentNode =
      nodes.find(
        (node) =>
          node.kind === "person" &&
          node.relationType === "child" &&
          node.person &&
          String(node.person.id) === String(participant.parentId || "")
      ) || nodes.find((node) => node.kind === "person" && node.relationType === "child" && node.person);
    if (!parentNode) return;
    nodes = [
      ...nodes,
      createDynamicNode("branch_spouse", {
        label: "Vợ/Chồng của nhánh",
        role: "Con_dau_re",
        relationType: "branchSpouse",
        bucket: 3,
        handles: ["left"],
        allowsShare: true,
        removable: true,
        sourceId: parentNode.id,
        sourceHandle: "right",
        parentSlotId: parentNode.id,
        parentPersonId: parentNode.person?.id || participant.parentId || "",
        person: participant,
        sharePercent: participant.share || "0.00",
        willReceive: participant.receive !== "0" && !participant.death,
      }),
    ];
  });

  delayedGrandchildren.forEach((participant) => {
    const parentNode =
      nodes.find(
        (node) =>
          node.kind === "person" &&
          node.relationType === "child" &&
          node.person &&
          String(node.person.id) === String(participant.parentId || "")
      ) || nodes.find((node) => node.kind === "person" && node.relationType === "child" && node.person);
    if (!parentNode) return;
    nodes = [
      ...nodes,
      createDynamicNode("grandchild", {
        label: "Con thế vị",
        role: "Cháu",
        relationType: "grandchild",
        bucket: 3,
        handles: ["target"],
        allowsShare: true,
        removable: true,
        sourceId: parentNode.id,
        parentSlotId: parentNode.id,
        parentPersonId: parentNode.person?.id || participant.parentId || "",
        person: participant,
        sharePercent: participant.share || "0.00",
        willReceive: participant.receive !== "0" && !participant.death,
      }),
    ];
  });

  return ensureSpareChildNode(nodes);
}

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
  if (!node.person) {
    return ["Thả người vào ô này để bổ sung quan hệ."];
  }
  if (node.role === "Owner") {
    return ["Người để lại di sản, không tham gia chia suất."];
  }
  if (!node.person.death) {
    return ["Đang còn sống, có thể tham gia chia suất nếu bật nhận."];
  }
  if (deathComparison === "predeceased") {
    return ["Chết trước chủ đất, ưu tiên mở nhánh thế vị."];
  }
  if (deathComparison === "postdeceased") {
    return ["Chết sau chủ đất, ưu tiên nhánh thừa kế chuyển tiếp."];
  }
  if (deathComparison === "simultaneous") {
    return ["Chết cùng thời điểm, cần đối chiếu giấy chứng tử."];
  }
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

  const parentNodes = models.filter(
    (node) => node.person && (node.role === "Cha" || node.role === "Mẹ" || node.role === "Vợ/Chồng")
  );
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
    (node) =>
      node.person &&
      (node.role === "Cha" || node.role === "Mẹ" || node.role === "Vợ/Chồng" || node.relationType === "child")
  );
  const siblingNodes = models.filter((node) => node.person && node.relationType === "sibling");
  if (!firstLineReceivers.some((node) => !node.disabledReason && node.willReceive) && siblingNodes.length > 0) {
    warnings.push("Hàng thừa kế thứ nhất đang trống hoặc bị loại hết, nhánh anh/chị/em được đưa vào xem xét.");
  }

  models.forEach((node) => {
    if (!node.person || !node.person.death) return;
    if (node.relationType === "child") {
      const hasBranchData = models.some(
        (candidate) =>
          candidate.kind === "person" &&
          candidate.parentSlotId === node.id &&
          !!candidate.person
      );
      if (!hasBranchData) {
        warnings.push(`${node.person.name} đã mất nhưng chưa mở nhánh phát sinh.`);
      }
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
  if (!node.person.death) {
    return node.willReceive && !node.disabledReason ? [node] : [];
  }

  const nodeDeathDate = parseFlexibleDate(node.person.death);
  const descendants = models.filter(
    (candidate) =>
      candidate.kind === "person" &&
      candidate.parentSlotId === node.id &&
      candidate.relationType === "grandchild" &&
      candidate.person &&
      !candidate.disabledReason &&
      candidate.willReceive &&
      survivesAt(parseFlexibleDate(candidate.person.death), nodeDeathDate)
  );
  const branchSpouses = models.filter(
    (candidate) =>
      candidate.kind === "person" &&
      candidate.parentSlotId === node.id &&
      candidate.relationType === "branchSpouse" &&
      candidate.person &&
      !candidate.disabledReason &&
      candidate.willReceive &&
      survivesAt(parseFlexibleDate(candidate.person.death), nodeDeathDate)
  );

  if (node.deathComparison === "postdeceased") {
    return [...branchSpouses, ...descendants];
  }
  if (node.deathComparison === "predeceased" || node.deathComparison === "simultaneous") {
    return descendants;
  }
  return descendants;
}

function roundAllocations(allocation) {
  const entries = Array.from(allocation.entries()).filter(([, rawPercent]) => rawPercent > 0);
  const rounded = new Map();
  if (!entries.length) return rounded;

  let usedBasisPoints = 0;
  entries.forEach(([nodeId, rawPercent], index) => {
    if (index === entries.length - 1) {
      rounded.set(nodeId, (10000 - usedBasisPoints) / 100);
      return;
    }
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

    if (!node.person) {
      nextNode.disabledReason = "";
      return nextNode;
    }
    if (node.role === "Owner") {
      nextNode.willReceive = false;
      nextNode.sharePercent = "0.00";
      nextNode.disabledReason = "Người để lại di sản.";
      return nextNode;
    }
    if (!node.allowsShare) {
      nextNode.willReceive = false;
      nextNode.sharePercent = "0.00";
      nextNode.disabledReason = "Nut quan he, khong tham gia chia suat.";
      return nextNode;
    }
    if (node.person.death) {
      nextNode.willReceive = false;
      if (node.relationType === "child") {
        if (node.deathComparison === "postdeceased") {
          nextNode.disabledReason = "Da mat sau chu dat, can phan xuong nhanh chuyen tiep.";
        } else if (node.deathComparison === "predeceased") {
          nextNode.disabledReason = "Đã mất trước chủ đất, cần mở nhánh thế vị.";
        } else if (node.deathComparison === "simultaneous") {
          nextNode.disabledReason = "Mat cung thoi diem, can kiem tra ho so.";
        } else {
          nextNode.disabledReason = "Da mat, can mo nhanh phat sinh.";
        }
      } else if (node.relationType === "parent") {
        nextNode.disabledReason = "Da mat, co the can nhanh anh/chi/em.";
      } else if (node.relationType === "sibling") {
        nextNode.disabledReason = "Da mat, can kiem tra nhanh tiep theo.";
      } else {
        nextNode.disabledReason = "Da mat, khong nhan truc tiep.";
      }
      nextNode.sharePercent = "0.00";
      return nextNode;
    }

    nextNode.disabledReason = "";
    if (typeof nextNode.willReceive !== "boolean") {
      nextNode.willReceive = true;
    }
    return nextNode;
  });

  if (shareMode === "manual") {
    nextModels = nextModels.map((node) => {
      if (!node.person || !node.allowsShare || node.disabledReason || !node.willReceive) {
        return { ...node, sharePercent: "0.00" };
      }
      const manualNumber = Number(node.manualShare || node.sharePercent || 0);
      const safeValue = Number.isFinite(manualNumber) && manualNumber > 0 ? manualNumber : 0;
      return {
        ...node,
        sharePercent: safeValue.toFixed(2),
      };
    });
    return nextModels;
  }

  nextModels = nextModels.map((node) => ({ ...node, sharePercent: "0.00" }));

  const parents = nextModels.filter(
    (node) =>
      node.person &&
      (node.role === "Cha" || node.role === "Mẹ") &&
      !node.disabledReason &&
      node.willReceive &&
      survivesAt(parseFlexibleDate(node.person.death), ownerDeathDate)
  );
  const spouse = nextModels.find(
    (node) =>
      node.person &&
      node.role === "Vợ/Chồng" &&
      !node.disabledReason &&
      node.willReceive &&
      survivesAt(parseFlexibleDate(node.person.death), ownerDeathDate)
  );
  const children = nextModels.filter((node) => node.person && node.relationType === "child");

  const firstLineUnits = [
    ...parents.map((node) => [node]),
    ...(spouse ? [[spouse]] : []),
    ...children
      .map((child) => buildBranchRecipients(nextModels, ownerDeathDate, child))
      .filter((unit) => unit.length > 0),
  ];

  let activeUnits = firstLineUnits;
  if (!activeUnits.length) {
    activeUnits = nextModels
      .filter(
        (node) =>
          node.person &&
          node.relationType === "sibling" &&
          !node.disabledReason &&
          node.willReceive &&
          survivesAt(parseFlexibleDate(node.person.death), ownerDeathDate)
      )
      .map((node) => [node]);
  }

  if (!activeUnits.length) {
    return nextModels;
  }

  const allocation = new Map();
  const unitPercent = 100 / activeUnits.length;
  activeUnits.forEach((unit) => {
    const activeRecipients = unit.filter((node) => node.person && !node.disabledReason && node.willReceive);
    if (!activeRecipients.length) return;
    const split = unitPercent / activeRecipients.length;
    activeRecipients.forEach((recipient) => {
      allocation.set(recipient.id, (allocation.get(recipient.id) || 0) + split);
    });
  });

  const rounded = roundAllocations(allocation);
  return nextModels.map((node) => {
    if (!rounded.has(node.id)) {
      return { ...node, sharePercent: "0.00" };
    }
    return {
      ...node,
      sharePercent: Number(rounded.get(node.id)).toFixed(2),
    };
  });
}

function resolveSubRelations(nodes, shareMode) {
  const owner = nodes.find((node) => node.role === "Owner" && node.person);
  const ownerDeathDate = parseFlexibleDate(owner?.person?.death);

  let resolvedNodes = nodes.map((node) => {
    const person = node.person ? normalizePersonPayload(node.person) : null;
    const deathComparison =
      person && node.role !== "Owner"
        ? compareDeathDates(ownerDeathDate, parseFlexibleDate(person.death))
        : "unknown";
    return {
      ...node,
      person,
      deathComparison,
      insightLines: getBaseInsight(node, deathComparison),
    };
  });

  resolvedNodes = calculateInheritance(resolvedNodes, shareMode);

  const ghostNodes = [];
  const hasDeadFather = resolvedNodes.some(
    (candidate) => candidate.id === "father" && candidate.person && candidate.person.death
  );
  resolvedNodes.forEach((node) => {
    if (!node.person || !node.person.death) return;

    if (
      ((node.role === "Cha") || (node.role === "Mẹ" && !hasDeadFather)) &&
      node.person.id
    ) {
      ghostNodes.push(
        createLogicalNode({
          id: `ghost_sibling_${node.id}`,
          kind: "ghost",
          label: "Them anh/chi/em",
          role: "Anh/Chị/Em",
          relationType: "ghostSibling",
          bucket: 1,
          handles: ["target"],
          allowsShare: false,
          removable: false,
          sourceId: node.id,
          parentSlotId: node.id,
          parentPersonId: node.person.id,
          ghostAction: "addSibling",
          ghostLabel: "[+] Thêm Anh/Chị/Em",
        })
      );
    }

    if (node.relationType === "child") {
      ghostNodes.push(
        createLogicalNode({
          id: `ghost_grandchild_${node.id}`,
          kind: "ghost",
          label: "Thêm con thế vị",
          role: "Cháu",
          relationType: "ghostGrandchild",
          bucket: 3,
          handles: ["target"],
          allowsShare: false,
          removable: false,
          sourceId: node.id,
          parentSlotId: node.id,
          parentPersonId: node.person.id,
          ghostAction: "addGrandchild",
          ghostLabel: "[+] Thêm Con thế vị",
        })
      );

      if (node.deathComparison === "postdeceased") {
        const hasBranchSpouse = resolvedNodes.some(
          (candidate) =>
            candidate.kind === "person" &&
            candidate.parentSlotId === node.id &&
            candidate.relationType === "branchSpouse"
        );
        if (!hasBranchSpouse) {
          ghostNodes.push(
            createLogicalNode({
              id: `ghost_branch_spouse_${node.id}`,
              kind: "ghost",
              label: "Them vo/chong cua nhanh",
              role: "Con_dau_re",
              relationType: "ghostBranchSpouse",
              bucket: 3,
              handles: ["left"],
              allowsShare: false,
              removable: false,
              sourceId: node.id,
              sourceHandle: "right",
              parentSlotId: node.id,
              parentPersonId: node.person.id,
              ghostAction: "addBranchSpouse",
              ghostLabel: "[+] Thêm Vợ/Chồng của nhánh",
            })
          );
        }
      }
    }
  });

  const mergedNodes = [...resolvedNodes.filter((node) => node.kind !== "ghost"), ...ghostNodes];
  const warnings = buildModelWarnings(mergedNodes, shareMode);

  return {
    nodes: mergedNodes,
    warnings,
  };
}

function getNodeSize(node) {
  if (node.kind === "ghost") {
    return { width: GHOST_WIDTH, height: GHOST_HEIGHT };
  }
  if (node.person) {
    return { width: NODE_WIDTH, height: NODE_HEIGHT };
  }
  return { width: NODE_WIDTH, height: EMPTY_HEIGHT };
}

function buildEdges(logicalNodes) {
  const edges = [];
  logicalNodes.forEach((node) => {
    if (!node.sourceId) return;
    const sourceExists = logicalNodes.some((candidate) => candidate.id === node.sourceId);
    if (!sourceExists) return;
    edges.push({
      id: `edge_${node.sourceId}_${node.id}`,
      source: node.sourceId,
      target: node.id,
      sourceHandle: node.sourceHandle || undefined,
      targetHandle: node.targetHandle || undefined,
      animated: node.kind === "ghost",
      type: node.relationType === "spouse" || node.relationType === "branchSpouse" ? "step" : "smoothstep",
      style:
        node.kind === "ghost"
          ? { stroke: "#c084fc", strokeDasharray: "6 4" }
          : { stroke: "#94a3b8", strokeWidth: 1.5 },
    });
  });

  edges.push({
    id: "edge_father_owner",
    source: "father",
    target: "owner",
    type: "smoothstep",
    style: { stroke: "#94a3b8", strokeWidth: 1.5 },
  });
  edges.push({
    id: "edge_mother_owner",
    source: "mother",
    target: "owner",
    type: "smoothstep",
    style: { stroke: "#94a3b8", strokeWidth: 1.5 },
  });
  edges.push({
    id: "edge_spouse_father_spouse",
    source: "spouse_father",
    target: "spouse",
    type: "smoothstep",
    style: { stroke: "#cbd5e1", strokeWidth: 1.2 },
  });
  edges.push({
    id: "edge_spouse_mother_spouse",
    source: "spouse_mother",
    target: "spouse",
    type: "smoothstep",
    style: { stroke: "#cbd5e1", strokeWidth: 1.2 },
  });
  edges.push({
    id: "edge_owner_spouse",
    source: "owner",
    target: "spouse",
    sourceHandle: "right",
    targetHandle: "left",
    type: "step",
    style: { stroke: "#d97706", strokeWidth: 1.8 },
  });

  return Array.from(new Map(edges.map((edge) => [edge.id, edge])).values());
}

function buildLayoutedGraph(logicalNodes, handlers, shareMode) {
  const graph = new dagreLib.graphlib.Graph();
  graph.setDefaultEdgeLabel(() => ({}));
  graph.setGraph({
    rankdir: "TB",
    nodesep: 40,
    ranksep: 90,
    marginx: 20,
    marginy: 20,
  });

  logicalNodes.forEach((node) => {
    const { width, height } = getNodeSize(node);
    graph.setNode(node.id, { width, height });
  });

  const edges = buildEdges(logicalNodes);
  edges.forEach((edge) => {
    graph.setEdge(edge.source, edge.target);
  });

  dagreLib.layout(graph);

  const graphNodes = logicalNodes.map((node) => {
    const dagreNode = graph.node(node.id);
    const { width } = getNodeSize(node);
    const y = 60 + node.bucket * LAYOUT_GAP_Y;

    return {
      id: node.id,
      type: "inheritanceNode",
      position: {
        x: (dagreNode?.x || 0) - width / 2 + LAYOUT_MARGIN_X,
        y,
      },
      draggable: false,
      selectable: true,
      data: {
        ...node,
        shareMode,
        onAssign: handlers.onAssign,
        onRemove: handlers.onRemove,
        onToggleReceive: handlers.onToggleReceive,
        onEnableManualMode: handlers.onEnableManualMode,
        onResetAutoMode: handlers.onResetAutoMode,
        onShareInputChange: handlers.onShareInputChange,
        onGhostExpand: handlers.onGhostExpand,
      },
      style: {
        width,
      },
    };
  });

  return {
    nodes: graphNodes,
    edges,
  };
}

function InheritanceNode({ data, id }) {
  const isGhost = data.kind === "ghost";
  const isOccupied = !!data.person;
  const isDead = !!data.person?.death;
  const canToggleReceive = !!data.person && data.allowsShare && !data.disabledReason && !isDead && data.role !== "Owner";
  const nodeBorder = isGhost
    ? "2px dashed #c084fc"
    : isOccupied
    ? "2px solid #d97706"
    : "2px dashed #9ca3af";
  const background = isGhost
    ? "linear-gradient(180deg, rgba(245, 243, 255, 1) 0%, rgba(250, 245, 255, 1) 100%)"
    : isOccupied
    ? isDead
      ? "linear-gradient(180deg, #f8fafc 0%, #eef2f7 100%)"
      : "linear-gradient(180deg, #fff7ed 0%, #fffdf7 100%)"
    : "#f8fafc";

  const handleDragOver = (event) => {
    if (isGhost) return;
    event.preventDefault();
    event.dataTransfer.dropEffect = "copy";
  };

  const handleDrop = (event) => {
    if (isGhost) return;
    event.preventDefault();
    const personStr = event.dataTransfer.getData("application/json");
    if (!personStr) return;
    try {
      const person = JSON.parse(personStr);
      data.onAssign(id, person);
    } catch (error) {
      console.error("Khong doc duoc payload nguoi keo tha", error);
    }
  };

  return (
    <div
      style={{
        minWidth: isGhost ? GHOST_WIDTH : NODE_WIDTH,
        border: nodeBorder,
        borderRadius: 18,
        background,
        boxShadow: "0 12px 28px rgba(15, 23, 42, .10)",
        padding: 14,
        position: "relative",
        color: "#0f172a",
        filter: isDead ? "grayscale(.22)" : "none",
        opacity: isDead ? 0.92 : 1,
      }}
      onDragOver={handleDragOver}
      onDrop={handleDrop}
    >
      {data.handles.includes("target") && <Handle type="target" position={Position.Top} />}
      {data.handles.includes("left") && <Handle id="left" type="target" position={Position.Left} />}
      {data.handles.includes("right") && <Handle id="right" type="source" position={Position.Right} />}

      {isGhost ? (
        <button
          type="button"
          onClick={() => data.onGhostExpand(id)}
          style={{
            width: "100%",
            padding: "14px 12px",
            borderRadius: 14,
            border: "none",
            background: "rgba(255,255,255,.85)",
            color: "#7c3aed",
            fontWeight: 700,
            cursor: "pointer",
          }}
        >
          {data.ghostLabel}
        </button>
      ) : (
        <>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: 8 }}>
            <div>
              <div style={{ fontSize: 11, letterSpacing: ".08em", textTransform: "uppercase", color: "#64748b", fontWeight: 700 }}>
                {data.label}
              </div>
              <div style={{ marginTop: 2, fontSize: 12, color: "#94a3b8" }}>
                {data.role || "Khac"}
              </div>
            </div>
            {isOccupied && data.removable && (
              <button
                type="button"
                onClick={() => data.onRemove(id)}
                style={{
                  border: "none",
                  background: "#ef4444",
                  color: "#fff",
                  borderRadius: 999,
                  width: 26,
                  height: 26,
                  cursor: "pointer",
                }}
              >
                ×
              </button>
            )}
          </div>

          {!isOccupied ? (
            <div style={{ marginTop: 16, fontSize: 13, color: "#94a3b8" }}>
              Thả người vào đây...
            </div>
          ) : (
            <>
              <div style={{ marginTop: 14, borderTop: "1px solid rgba(148, 163, 184, .25)", paddingTop: 10 }}>
                <div style={{ fontSize: 15, fontWeight: 800 }}>{data.person.name}</div>
                <div style={{ marginTop: 4, fontSize: 12, color: "#64748b" }}>
                  CCCD: {data.person.doc || "—"}
                </div>
                <div style={{ marginTop: 4, display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8, fontSize: 12, color: "#475569" }}>
                  <div>Sinh: {formatDisplayDate(data.person.birth)}</div>
                  <div>Chet: {formatDisplayDate(data.person.death)}</div>
                </div>
              </div>

              {data.allowsShare && (
                <div style={{ marginTop: 12, padding: 10, borderRadius: 14, background: "rgba(255,255,255,.78)", border: "1px solid rgba(226,232,240,.9)" }}>
                  <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 8 }}>
                    <label style={{ display: "flex", alignItems: "center", gap: 8, fontSize: 12, color: "#334155" }}>
                      <input
                        type="checkbox"
                        checked={!!data.willReceive}
                        disabled={!canToggleReceive}
                        onChange={() => data.onToggleReceive(id)}
                      />
                      Nhan
                    </label>
                    <span
                      style={{
                        padding: "4px 8px",
                        borderRadius: 999,
                        background: "#fff7ed",
                        color: "#c2410c",
                        fontSize: 12,
                        fontWeight: 800,
                      }}
                    >
                      {Number(data.sharePercent || 0).toFixed(2)}%
                    </span>
                  </div>

                  {data.shareMode === "manual" ? (
                    <div style={{ marginTop: 10, display: "flex", gap: 8 }}>
                      <input
                        type="number"
                        min="0"
                        max="100"
                        step="0.01"
                        value={data.manualShare || data.sharePercent || "0"}
                        disabled={!canToggleReceive}
                        onChange={(event) => data.onShareInputChange(id, event.target.value)}
                        style={{
                          flex: 1,
                          borderRadius: 10,
                          border: "1px solid #cbd5e1",
                          padding: "6px 9px",
                          fontSize: 12,
                        }}
                      />
                      <button
                        type="button"
                        onClick={data.onResetAutoMode}
                        style={{
                          border: "none",
                          borderRadius: 10,
                          padding: "6px 10px",
                          background: "#dbeafe",
                          color: "#1d4ed8",
                          fontSize: 12,
                          fontWeight: 700,
                          cursor: "pointer",
                        }}
                      >
                        Dat lai
                      </button>
                    </div>
                  ) : (
                    <button
                      type="button"
                      onClick={() => data.onEnableManualMode(id)}
                      disabled={!data.person || !!data.disabledReason || data.role === "Owner"}
                      style={{
                        marginTop: 10,
                        width: "100%",
                        border: "none",
                        borderRadius: 10,
                        padding: "7px 10px",
                        background: "#eff6ff",
                        color: "#1d4ed8",
                        fontSize: 12,
                        fontWeight: 700,
                        cursor: "pointer",
                        opacity: !data.person || !!data.disabledReason || data.role === "Owner" ? 0.55 : 1,
                      }}
                    >
                      Chinh sua thu cong
                    </button>
                  )}
                </div>
              )}

              {(data.disabledReason || (data.insightLines && data.insightLines.length > 0)) && (
                <div style={{ marginTop: 10, padding: 10, borderRadius: 14, background: "rgba(15,23,42,.04)" }}>
                  <div style={{ fontSize: 11, fontWeight: 800, letterSpacing: ".06em", textTransform: "uppercase", color: "#475569" }}>
                    Insight
                  </div>
                  {data.disabledReason && (
                    <div style={{ marginTop: 6, fontSize: 12, color: "#b45309" }}>{data.disabledReason}</div>
                  )}
                  {(data.insightLines || []).map((line, index) => (
                    <div key={`${id}_insight_${index}`} style={{ marginTop: 4, fontSize: 12, color: "#475569" }}>
                      {line}
                    </div>
                  ))}
                </div>
              )}
            </>
          )}
        </>
      )}

      {data.handles.includes("source") && <Handle type="source" position={Position.Bottom} />}
    </div>
  );
}

const nodeTypes = {
  inheritanceNode: InheritanceNode,
};

function FamilyTreeApp() {
  const counterRef = useRef(Date.now());
  const [logicalNodes, setLogicalNodes] = useState(() => hydrateInitialNodes());
  const [shareMode, setShareMode] = useState("auto");
  const [graphState, setGraphState] = useState({ nodes: [], edges: [] });

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
        if (node.parentSlotId && toRemove.has(node.parentSlotId)) {
          toRemove.add(node.id);
          changed = true;
          return;
        }
        if (node.relationType === "sibling" && node.sourceId && toRemove.has(node.sourceId)) {
          toRemove.add(node.id);
          changed = true;
        }
      });
    }

    return nodes.filter((node) => !toRemove.has(node.id));
  }, []);

  const onAssign = useCallback((nodeId, rawPerson) => {
    const person = normalizePersonPayload(rawPerson);
    if (!person || !person.id) return;

    setLogicalNodes((prevNodes) => {
      const duplicate = prevNodes.find(
        (node) =>
          node.id !== nodeId &&
          node.kind === "person" &&
          node.person &&
          String(node.person.id) === String(person.id)
      );
      if (duplicate) {
        window.alert(`${person.name || "Nguoi nay"} da co mat trong so do.`);
        return prevNodes;
      }

      const nextNodes = prevNodes.map((node) => {
        if (node.id !== nodeId) return node;
        const parentPersonId =
          node.parentSlotId && node.parentSlotId !== "owner"
            ? prevNodes.find((candidate) => candidate.id === node.parentSlotId)?.person?.id || node.parentPersonId || ""
            : node.role === "Con"
            ? prevNodes.find((candidate) => candidate.id === "owner")?.person?.id || ""
            : node.parentPersonId || "";
        return {
          ...node,
          person,
          parentPersonId,
          willReceive: node.allowsShare && !person.death && node.role !== "Owner" ? true : false,
          manualShare: "",
          sharePercent: "0.00",
        };
      });

      return ensureSpareChildNode(nextNodes);
    });
  }, []);

  const onRemove = useCallback(
    (nodeId) => {
      setLogicalNodes((prevNodes) => {
        const target = prevNodes.find((node) => node.id === nodeId);
        if (!target) return prevNodes;

        if (!target.removable) {
          return prevNodes.map((node) =>
            node.id === nodeId
              ? {
                  ...node,
                  person: null,
                  willReceive: false,
                  manualShare: "",
                  sharePercent: "0.00",
                }
              : node
          );
        }

        return ensureSpareChildNode(pruneLinkedNodes(prevNodes, nodeId));
      });
    },
    [pruneLinkedNodes]
  );

  const onToggleReceive = useCallback(
    (nodeId) => {
      setLogicalNodes((prevNodes) =>
        prevNodes.map((node) =>
          node.id === nodeId
            ? {
                ...node,
                willReceive: !node.willReceive,
                manualShare: shareMode === "manual" && node.willReceive ? "0" : node.manualShare,
              }
            : node
        )
      );
    },
    [shareMode]
  );

  const onEnableManualMode = useCallback((nodeId) => {
    setShareMode("manual");
    setLogicalNodes((prevNodes) =>
      prevNodes.map((node) => {
        if (node.id === nodeId) {
          return {
            ...node,
            manualShare: node.sharePercent || "0.00",
          };
        }
        if (!node.person || !node.allowsShare || node.disabledReason || !node.willReceive) {
          return node;
        }
        return {
          ...node,
          manualShare: node.sharePercent || "0.00",
        };
      })
    );
  }, []);

  const onResetAutoMode = useCallback(() => {
    setShareMode("auto");
    setLogicalNodes((prevNodes) =>
      prevNodes.map((node) => ({
        ...node,
        manualShare: "",
      }))
    );
  }, []);

  const onShareInputChange = useCallback((nodeId, value) => {
    setLogicalNodes((prevNodes) =>
      prevNodes.map((node) =>
        node.id === nodeId
          ? {
              ...node,
              manualShare: value,
            }
          : node
      )
    );
  }, []);

  const onGhostExpand = useCallback(
    (nodeId) => {
      setLogicalNodes((prevNodes) => {
        const ghostNode = resolveSubRelations(prevNodes, shareMode).nodes.find((node) => node.id === nodeId);
        if (!ghostNode) return prevNodes;

        if (ghostNode.ghostAction === "addSibling") {
          return [
            ...prevNodes,
            createLogicalNode({
              id: nextId("sibling"),
              label: "Anh/Chị/Em",
              role: "Anh/Chị/Em",
              relationType: "sibling",
              bucket: 1,
              handles: ["target", "source"],
              allowsShare: true,
              removable: true,
              sourceId: ghostNode.sourceId,
              parentSlotId: ghostNode.parentSlotId,
              parentPersonId: ghostNode.parentPersonId,
              willReceive: true,
            }),
          ];
        }

        if (ghostNode.ghostAction === "addGrandchild") {
          return [
            ...prevNodes,
            createLogicalNode({
              id: nextId("grandchild"),
              label: "Con thế vị",
              role: "Cháu",
              relationType: "grandchild",
              bucket: 3,
              handles: ["target"],
              allowsShare: true,
              removable: true,
              sourceId: ghostNode.sourceId,
              parentSlotId: ghostNode.parentSlotId,
              parentPersonId: ghostNode.parentPersonId,
              willReceive: true,
            }),
          ];
        }

        if (ghostNode.ghostAction === "addBranchSpouse") {
          const alreadyExists = prevNodes.some(
            (node) =>
              node.kind === "person" &&
              node.parentSlotId === ghostNode.parentSlotId &&
              node.relationType === "branchSpouse"
          );
          if (alreadyExists) return prevNodes;
          return [
            ...prevNodes,
            createLogicalNode({
              id: nextId("branch_spouse"),
              label: "Vợ/Chồng của nhánh",
              role: "Con_dau_re",
              relationType: "branchSpouse",
              bucket: 3,
              handles: ["left"],
              allowsShare: true,
              removable: true,
              sourceId: ghostNode.sourceId,
              sourceHandle: "right",
              parentSlotId: ghostNode.parentSlotId,
              parentPersonId: ghostNode.parentPersonId,
              willReceive: true,
            }),
          ];
        }

        return prevNodes;
      });
    },
    [nextId, shareMode]
  );

  const addChildNode = useCallback(() => {
    setLogicalNodes((prevNodes) => {
      const hasEmptyChild = prevNodes.some(
        (node) => node.kind === "person" && node.relationType === "child" && !node.person
      );
      if (hasEmptyChild) return prevNodes;
      return [
        ...prevNodes,
        createLogicalNode({
          id: nextId("child"),
          label: "Con ruột",
          role: "Con",
          relationType: "child",
          bucket: 2,
          handles: ["target", "source", "right"],
          allowsShare: true,
          removable: true,
          sourceId: "owner",
          parentSlotId: "owner",
          parentPersonId: prevNodes.find((node) => node.id === "owner")?.person?.id || "",
          willReceive: true,
        }),
      ];
    });
  }, [nextId]);

  useEffect(() => {
    const resolved = resolveSubRelations(logicalNodes, shareMode);
    const graph = buildLayoutedGraph(
      resolved.nodes,
      {
        onAssign,
        onRemove,
        onToggleReceive,
        onEnableManualMode,
        onResetAutoMode,
        onShareInputChange,
        onGhostExpand,
      },
      shareMode
    );

    setGraphState(graph);

    const participants = resolved.nodes
      .filter((node) => node.kind === "person" && node.person)
      .map((node) => ({
        id: node.person.id,
        role: node.role,
        name: node.person.name,
        doc: node.person.doc,
        gender: node.person.gender,
        birth: node.person.birth,
        death: node.person.death,
        willReceive: !!node.willReceive,
        sharePercent: node.sharePercent || "0.00",
        share: node.sharePercent || "0.00",
        disabledReason: node.disabledReason || "",
        relationType: node.relationType,
        deathComparison: node.deathComparison || "unknown",
        parentId: node.parentPersonId || "",
      }));

    window.dispatchEvent(
      new CustomEvent("onFamilyTreeUpdate", {
        detail: {
          participants,
          warnings: resolved.warnings,
          shareMode,
          updatedAt: new Date().toISOString(),
        },
      })
    );
  }, [
    logicalNodes,
    shareMode,
    onAssign,
    onRemove,
    onToggleReceive,
    onEnableManualMode,
    onResetAutoMode,
    onShareInputChange,
    onGhostExpand,
  ]);

  return (
    <div style={{ width: "100%", height: "100%", position: "relative" }}>
      <div
        style={{
          position: "absolute",
          top: 12,
          left: 12,
          zIndex: 20,
          display: "flex",
          gap: 8,
          alignItems: "center",
          flexWrap: "wrap",
        }}
      >
        <button
          type="button"
          onClick={addChildNode}
          style={{
            border: "none",
            borderRadius: 999,
            background: "#fff",
            color: "#0f172a",
            padding: "8px 14px",
            fontWeight: 700,
            boxShadow: "0 8px 20px rgba(15, 23, 42, .10)",
            cursor: "pointer",
          }}
        >
          + Thêm Con
        </button>
        <span
          style={{
            borderRadius: 999,
            background: shareMode === "manual" ? "#dbeafe" : "#fef3c7",
            color: shareMode === "manual" ? "#1d4ed8" : "#92400e",
            padding: "7px 12px",
            fontSize: 12,
            fontWeight: 800,
          }}
        >
          {shareMode === "manual" ? "Chế độ chia tay" : "Chế độ tự động"}
        </span>
        {shareMode === "manual" && (
          <button
            type="button"
            onClick={onResetAutoMode}
            style={{
              border: "none",
              borderRadius: 999,
              background: "#fff",
              color: "#1d4ed8",
              padding: "8px 14px",
              fontWeight: 700,
              boxShadow: "0 8px 20px rgba(15, 23, 42, .10)",
              cursor: "pointer",
            }}
          >
            Đặt lại auto
          </button>
        )}
      </div>

      <ReactFlow
        nodes={graphState.nodes}
        edges={graphState.edges}
        nodeTypes={nodeTypes}
        fitView
        nodesDraggable={false}
        nodesConnectable={false}
        elementsSelectable
        zoomOnDoubleClick={false}
        minZoom={0.35}
        maxZoom={1.5}
        proOptions={{ hideAttribution: true }}
      >
        <Background gap={24} size={1} color="#e2e8f0" />
        <Controls showInteractive={false} />
      </ReactFlow>
    </div>
  );
}

if (!rootElement || !ReactFlow || !dagreLib) {
  if (rootElement) {
    rootElement.innerHTML =
      '<div style="padding:24px;color:#b91c1c;font-weight:700">Không tải được engine sơ đồ. Vui lòng tải lại trang.</div>';
  }
} else {
  const root = ReactDOM.createRoot(rootElement);
  root.render(<FamilyTreeApp />);
}
