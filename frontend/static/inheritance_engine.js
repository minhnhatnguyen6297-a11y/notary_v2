// Deterministic inheritance engine for the cases diagram.
// Source of truth: asset owners (*) + explicit tree relationships + receive toggles.
(function initInheritanceEngine(global) {
  "use strict";

  function absBigInt(value) {
    return value < 0n ? -value : value;
  }

  function gcdBigInt(a, b) {
    let x = absBigInt(a);
    let y = absBigInt(b);
    while (y !== 0n) {
      const t = y;
      y = x % y;
      x = t;
    }
    return x || 1n;
  }

  class Fraction {
    constructor(num, den = 1n) {
      let n = typeof num === "bigint" ? num : BigInt(num || 0);
      let d = typeof den === "bigint" ? den : BigInt(den || 1);
      if (d === 0n) throw new Error("Fraction denominator cannot be zero");
      if (d < 0n) {
        n = -n;
        d = -d;
      }
      const g = gcdBigInt(n, d);
      this.num = n / g;
      this.den = d / g;
    }
    static zero() { return new Fraction(0n, 1n); }
    static one() { return new Fraction(1n, 1n); }
    static from(value) {
      if (value instanceof Fraction) return value;
      if (Array.isArray(value)) return new Fraction(BigInt(value[0]), BigInt(value[1]));
      if (typeof value === "string" && value.includes("/")) {
        const [n, d] = value.split("/");
        return new Fraction(BigInt(n), BigInt(d));
      }
      return new Fraction(BigInt(value || 0), 1n);
    }
    add(other) {
      const rhs = Fraction.from(other);
      return new Fraction(this.num * rhs.den + rhs.num * this.den, this.den * rhs.den);
    }
    sub(other) {
      const rhs = Fraction.from(other);
      return new Fraction(this.num * rhs.den - rhs.num * this.den, this.den * rhs.den);
    }
    divInt(value) {
      return new Fraction(this.num, this.den * BigInt(value || 1));
    }
    isZero() {
      return this.num === 0n;
    }
    toNumber() {
      return Number(this.num) / Number(this.den);
    }
    toPercentNumber() {
      return this.toNumber() * 100;
    }
    toPercentString(digits = 2) {
      return this.toPercentNumber().toFixed(digits);
    }
    toString() {
      return this.den === 1n ? String(this.num) : `${this.num}/${this.den}`;
    }
    toJSON() {
      return this.toString();
    }
  }

  function idOf(value) {
    return String(value || "").trim();
  }

  function addSet(map, key, value) {
    const k = idOf(key);
    const v = idOf(value);
    if (!k || !v || k === v) return;
    if (!map.has(k)) map.set(k, new Set());
    map.get(k).add(v);
  }

  function parseDateKey(value) {
    if (!value) return "";
    const raw = String(value).trim();
    if (!raw) return "";
    const yearOnly = raw.match(/^(\d{4})$/);
    if (yearOnly) return `${yearOnly[1]}-01-01`;
    const ddmmyyyy = raw.match(/^(\d{1,2})\/(\d{1,2})\/(\d{4})$/);
    if (ddmmyyyy) {
      return [
        ddmmyyyy[3],
        String(ddmmyyyy[2]).padStart(2, "0"),
        String(ddmmyyyy[1]).padStart(2, "0"),
      ].join("-");
    }
    const date = new Date(raw);
    if (Number.isNaN(date.getTime())) return "";
    return [
      String(date.getFullYear()).padStart(4, "0"),
      String(date.getMonth() + 1).padStart(2, "0"),
      String(date.getDate()).padStart(2, "0"),
    ].join("-");
  }

  function compareDeath(person, eventDateKey) {
    const deathKey = parseDateKey(person && person.death);
    if (!deathKey) return "alive";
    if (!eventDateKey) return "unknown";
    if (deathKey < eventDateKey) return "before";
    if (deathKey > eventDateKey) return "after";
    return "same";
  }

  function normalizePerson(raw) {
    if (!raw) return null;
    const id = idOf(raw.id || raw.personId || raw.customer_id || raw.customerId);
    if (!id) return null;
    return {
      id,
      name: String(raw.name || raw.ho_ten || "").trim(),
      death: String(raw.death || raw.ngay_chet || "").trim(),
      birth: String(raw.birth || raw.ngay_sinh || "").trim(),
      raw,
    };
  }

  function uniqueIds(values) {
    return Array.from(new Set((values || []).map(idOf).filter(Boolean)));
  }

  function buildGraph(input) {
    const people = new Map();
    const parentsByChild = new Map();
    const childrenByParent = new Map();
    const spousesByPerson = new Map();

    (input.people || []).forEach((raw) => {
      const person = normalizePerson(raw);
      if (person) people.set(person.id, person);
    });

    function ensurePerson(raw) {
      const person = normalizePerson(raw);
      if (person && !people.has(person.id)) people.set(person.id, person);
      return person;
    }

    function linkParent(parentId, childId) {
      const parent = idOf(parentId);
      const child = idOf(childId);
      if (!parent || !child || parent === child) return;
      addSet(parentsByChild, child, parent);
      addSet(childrenByParent, parent, child);
    }

    function linkSpouse(a, b) {
      const left = idOf(a);
      const right = idOf(b);
      if (!left || !right || left === right) return;
      addSet(spousesByPerson, left, right);
      addSet(spousesByPerson, right, left);
    }

    const rel = input.relationships || {};
    Object.entries(rel.parentsByChild || {}).forEach(([childId, parentIds]) => {
      (parentIds || []).forEach((parentId) => linkParent(parentId, childId));
    });
    Object.entries(rel.childrenByParent || {}).forEach(([parentId, childIds]) => {
      (childIds || []).forEach((childId) => linkParent(parentId, childId));
    });
    Object.entries(rel.spousesByPerson || {}).forEach(([personId, spouseIds]) => {
      (spouseIds || []).forEach((spouseId) => linkSpouse(personId, spouseId));
    });

    const nodes = input.nodes || [];
    nodes.forEach((node) => ensurePerson(node.person || { id: node.personId, name: node.name, death: node.death, birth: node.birth }));

    const ownerNode = nodes.find((node) => idOf(node.relationType) === "owner" || idOf(node.role) === "Owner");
    const ownerId = idOf(ownerNode && (ownerNode.personId || ownerNode.person && ownerNode.person.id));
    const spouseNode = nodes.find((node) => idOf(node.relationType) === "spouse");
    const spouseId = idOf(spouseNode && (spouseNode.personId || spouseNode.person && spouseNode.person.id));
    if (ownerId && spouseId) linkSpouse(ownerId, spouseId);

    nodes.forEach((node) => {
      const personId = idOf(node.personId || node.person && node.person.id);
      if (!personId) return;
      const relationType = idOf(node.relationType);
      const role = idOf(node.role);
      const parentPersonId = idOf(node.parentPersonId || node.parentId);

      if (relationType === "parent" && ownerId) linkParent(personId, ownerId);
      if (relationType === "spouseParent" && spouseId) linkParent(personId, spouseId);
      if (relationType === "child") {
        linkParent(parentPersonId || ownerId, personId);
        if (spouseId) linkParent(spouseId, personId);
      }
      if (relationType === "grandchild") linkParent(parentPersonId, personId);
      if (relationType === "sibling") linkParent(parentPersonId, personId);
      if (relationType === "branchSpouse") linkSpouse(parentPersonId, personId);
    });

    return { people, parentsByChild, childrenByParent, spousesByPerson };
  }

  function makeLedger(people) {
    const ledger = new Map();
    function row(personId) {
      const id = idOf(personId);
      if (!ledger.has(id)) {
        ledger.set(id, {
          personId: id,
          baseShare: Fraction.zero(),
          inheritedShare: Fraction.zero(),
          distributedShare: Fraction.zero(),
          finalShare: Fraction.zero(),
          inflowShare: Fraction.zero(),
          displayPercent: "0.00",
          finalFraction: "0",
          receivedFraction: "0",
          distributedFraction: "0",
          isDead: !!parseDateKey(people.get(id) && people.get(id).death),
        });
      }
      return ledger.get(id);
    }
    return { ledger, row };
  }

  function serializeLedger(ledger) {
    const result = {};
    ledger.forEach((entry, personId) => {
      result[personId] = {
        ...entry,
        baseShare: entry.baseShare.toString(),
        inheritedShare: entry.inheritedShare.toString(),
        distributedShare: entry.distributedShare.toString(),
        finalShare: entry.finalShare.toString(),
        inflowShare: entry.inflowShare.toString(),
      };
    });
    return result;
  }

  function runInheritanceCase(input = {}) {
    const graph = buildGraph(input);
    const people = graph.people;
    const warnings = [];
    const trace = [];
    const assetOwnerIds = uniqueIds(input.assetOwnerIds || (input.nodes || []).filter((node) => node.isLandOwner).map((node) => node.personId || node.person && node.person.id));
    const willReceive = input.willReceiveByPersonId || {};
    const holdings = new Map();
    const { ledger, row } = makeLedger(people);

    function getHolding(personId) {
      return holdings.get(idOf(personId)) || Fraction.zero();
    }
    function addHolding(personId, amount) {
      const id = idOf(personId);
      holdings.set(id, getHolding(id).add(amount));
    }
    function setHolding(personId, amount) {
      holdings.set(idOf(personId), Fraction.from(amount));
    }
    function acceptsInheritance(personId) {
      const id = idOf(personId);
      if (Object.prototype.hasOwnProperty.call(willReceive, id)) return !!willReceive[id];
      return true;
    }
    function childrenOf(personId) {
      return Array.from(graph.childrenByParent.get(idOf(personId)) || []);
    }
    function parentsOf(personId) {
      return Array.from(graph.parentsByChild.get(idOf(personId)) || []);
    }
    function spousesOf(personId) {
      return Array.from(graph.spousesByPerson.get(idOf(personId)) || []);
    }

    if (!assetOwnerIds.length) {
      warnings.push({ code: "missing_asset_owner", message: "Chưa chọn chủ sở hữu tài sản bằng nút *." });
    } else {
      const base = Fraction.one().divInt(assetOwnerIds.length);
      assetOwnerIds.forEach((personId) => {
        addHolding(personId, base);
        row(personId).baseShare = row(personId).baseShare.add(base);
      });
    }

    const deathGroups = new Map();
    people.forEach((person) => {
      const key = parseDateKey(person.death);
      if (!key) return;
      if (!deathGroups.has(key)) deathGroups.set(key, []);
      deathGroups.get(key).push(person.id);
    });

    function representationRecipients(branchRootId, eventDateKey, seen = new Set()) {
      const rootId = idOf(branchRootId);
      if (!rootId || seen.has(rootId)) return [];
      seen.add(rootId);
      const units = [];
      childrenOf(rootId).forEach((childId) => {
        const child = people.get(childId);
        const cmp = compareDeath(child, eventDateKey);
        if (cmp === "alive" || cmp === "after") {
          if (acceptsInheritance(childId)) units.push(childId);
          return;
        }
        if (cmp === "same") {
          warnings.push({
            code: "same_day_treated_as_predeceased_for_representation",
            personId: childId,
          });
        }
        units.push(...representationRecipients(childId, eventDateKey, seen));
      });
      return uniqueIds(units);
    }

    function firstLineUnits(decedentId, eventDateKey) {
      const candidates = [
        ...parentsOf(decedentId).map((id) => ({ id, relation: "parent" })),
        ...spousesOf(decedentId).map((id) => ({ id, relation: "spouse" })),
        ...childrenOf(decedentId).map((id) => ({ id, relation: "child" })),
      ];
      const units = [];
      const seenCandidate = new Set();
      candidates.forEach((candidate) => {
        const heirId = idOf(candidate.id);
        if (!heirId || heirId === idOf(decedentId) || seenCandidate.has(heirId)) return;
        seenCandidate.add(heirId);
        const person = people.get(heirId);
        const cmp = compareDeath(person, eventDateKey);
        if (cmp === "alive" || cmp === "after") {
          if (acceptsInheritance(heirId)) units.push([heirId]);
          return;
        }
        if (candidate.relation === "child") {
          if (cmp === "same") {
            warnings.push({
              code: "same_day_treated_as_predeceased_for_representation",
              personId: heirId,
            });
          }
          const represented = representationRecipients(heirId, eventDateKey);
          if (represented.length) units.push(represented);
        }
      });
      return units;
    }

    Array.from(deathGroups.keys()).sort().forEach((eventDateKey) => {
      const group = deathGroups.get(eventDateKey) || [];
      const snapshots = group.map((decedentId) => ({ decedentId, estate: getHolding(decedentId) }));
      const pending = new Map();
      snapshots.forEach(({ decedentId, estate }) => {
        if (estate.isZero()) return;
        setHolding(decedentId, Fraction.zero());
        const entry = row(decedentId);
        entry.distributedShare = entry.distributedShare.add(estate);
        const units = firstLineUnits(decedentId, eventDateKey);
        if (!units.length) {
          warnings.push({ code: "undistributed_estate", personId: decedentId, fraction: estate.toString() });
          trace.push({ type: "undistributed", decedentId, eventDateKey, fraction: estate.toString() });
          return;
        }
        const unitShare = estate.divInt(units.length);
        units.forEach((unit) => {
          const recipientShare = unitShare.divInt(unit.length);
          unit.forEach((recipientId) => {
            const id = idOf(recipientId);
            pending.set(id, (pending.get(id) || Fraction.zero()).add(recipientShare));
            const receiver = row(id);
            receiver.inflowShare = receiver.inflowShare.add(recipientShare);
            receiver.inheritedShare = receiver.inheritedShare.add(recipientShare);
            trace.push({
              type: "flow",
              from: decedentId,
              to: id,
              eventDateKey,
              fraction: recipientShare.toString(),
            });
          });
        });
      });
      pending.forEach((amount, personId) => addHolding(personId, amount));
    });

    people.forEach((person) => {
      const entry = row(person.id);
      entry.finalShare = getHolding(person.id);
      entry.finalFraction = entry.finalShare.toString();
      entry.receivedFraction = entry.inheritedShare.toString();
      entry.distributedFraction = entry.distributedShare.toString();
      entry.displayPercent = entry.finalShare.toPercentString(2);
    });

    return {
      schemaVersion: 1,
      engineVersion: "2026-04-29",
      assetOwnerIds,
      allocations: serializeLedger(ledger),
      trace,
      warnings,
    };
  }

  const api = { Fraction, parseDateKey, runInheritanceCase };
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  global.InheritanceEngine = api;
})(typeof window !== "undefined" ? window : globalThis);
