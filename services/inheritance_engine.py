"""Authoritative inheritance calculation for the case diagram.

The engine is intentionally pure: callers provide diagram nodes and person
records, and receive a JSON-serializable result. Database and HTTP concerns
belong to the router layer.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime
from decimal import Decimal, ROUND_HALF_UP
from fractions import Fraction
from typing import Any, Mapping


ENGINE_VERSION = 2


def _value(record: Any, *names: str) -> Any:
    for name in names:
        if isinstance(record, Mapping) and name in record:
            return record[name]
        if hasattr(record, name):
            return getattr(record, name)
    return None


def _person_id(value: Any) -> str:
    return "" if value is None else str(value).strip()


def _parse_death_date(value: Any) -> date | None:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value

    text = str(value).strip()
    if not text:
        return None
    if len(text) == 4 and text.isdigit():
        return date(int(text), 1, 1)
    if len(text) == 10 and text[2] == "/" and text[5] == "/":
        return datetime.strptime(text, "%d/%m/%Y").date()
    try:
        return date.fromisoformat(text[:10])
    except ValueError as exc:
        raise ValueError(f"Ngày chết không hợp lệ: {text}") from exc


def _fraction_text(value: Fraction) -> str:
    return str(value.numerator) if value.denominator == 1 else f"{value.numerator}/{value.denominator}"


def _percent_text(value: Fraction) -> str:
    percent = (Decimal(value.numerator) * 100 / Decimal(value.denominator)).quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP
    )
    return f"{percent:.2f}"


def _error(code: str, message: str, **details: Any) -> dict[str, Any]:
    return {"code": code, "message": message, **details}


def _empty_result(errors: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "engineVersion": ENGINE_VERSION,
        "status": "invalid",
        "allocations": {},
        "breakdowns": [],
        "requiredSlots": [],
        "warnings": [],
        "errors": errors,
        "unresolvedEstates": [],
        "conservation": {"allocated": "0", "unresolved": "0", "total": "0"},
    }


def _validate_and_build_graph(
    engine_input: Mapping[str, Any], people_by_id: Mapping[Any, Any]
) -> tuple[dict[str, dict[str, Any]], dict[str, Any], list[dict[str, Any]]]:
    errors: list[dict[str, Any]] = []
    if engine_input.get("version") != ENGINE_VERSION:
        errors.append(_error("invalid_version", "Diagram phải dùng version 2."))

    raw_nodes = engine_input.get("nodes")
    if not isinstance(raw_nodes, list):
        return {}, {}, errors + [_error("invalid_nodes", "nodes phải là một danh sách.")]

    nodes: dict[str, dict[str, Any]] = {}
    active_people: dict[str, dict[str, Any]] = {}
    normalized_people = {_person_id(key): value for key, value in people_by_id.items()}

    for index, raw in enumerate(raw_nodes):
        if not isinstance(raw, Mapping):
            errors.append(_error("invalid_node", "Node phải là object.", index=index))
            continue
        slot_id = _person_id(raw.get("id"))
        if not slot_id:
            errors.append(_error("missing_node_id", "Node thiếu id.", index=index))
            continue
        if slot_id in nodes:
            errors.append(_error("duplicate_node_id", "Node id bị trùng.", nodeId=slot_id))
            continue

        parent_ids = raw.get("parentSlotIds", [])
        if parent_ids is None:
            parent_ids = []
        if not isinstance(parent_ids, list):
            errors.append(_error("invalid_parent_slots", "parentSlotIds phải là danh sách.", nodeId=slot_id))
            parent_ids = []

        boolean_values: dict[str, bool] = {}
        for field, default in (
            ("isLandOwner", False),
            ("willReceive", True),
            ("hidden", False),
            ("deleted", False),
        ):
            value = raw.get(field, default)
            if not isinstance(value, bool):
                errors.append(
                    _error("invalid_boolean", f"{field} phải là boolean.", nodeId=slot_id, field=field)
                )
                value = default
            boolean_values[field] = value

        person_id = _person_id(raw.get("personId")) or None
        node = {
            "id": slot_id,
            "personId": person_id,
            "parentSlotIds": [_person_id(item) for item in parent_ids],
            "spouseSlotId": _person_id(raw.get("spouseSlotId")) or None,
            **boolean_values,
        }
        nodes[slot_id] = node

        if not person_id or node["hidden"] or node["deleted"]:
            continue
        if person_id in active_people:
            errors.append(
                _error(
                    "duplicate_person",
                    "Một người không được xuất hiện ở hai node đang hoạt động.",
                    personId=person_id,
                )
            )
            continue
        if person_id not in normalized_people:
            errors.append(
                _error("unknown_person", "Người trên Diagram không tồn tại trong Stage/DB.", personId=person_id)
            )
            continue
        active_people[person_id] = node

    for node in active_people.values():
        if len(node["parentSlotIds"]) > 2:
            errors.append(
                _error("too_many_parents", "Một người chỉ có tối đa hai cha/mẹ.", nodeId=node["id"])
            )
        for parent_id in node["parentSlotIds"]:
            if not parent_id or parent_id not in nodes:
                errors.append(
                    _error("dangling_parent", "Quan hệ cha/mẹ trỏ tới node không tồn tại.", nodeId=node["id"])
                )
            elif parent_id == node["id"]:
                errors.append(_error("self_parent", "Một người không thể là cha/mẹ của chính mình.", nodeId=node["id"]))
        spouse_id = node["spouseSlotId"]
        if spouse_id:
            if spouse_id not in nodes:
                errors.append(
                    _error("dangling_spouse", "Quan hệ vợ/chồng trỏ tới node không tồn tại.", nodeId=node["id"])
                )
            elif spouse_id == node["id"]:
                errors.append(_error("self_spouse", "Một người không thể là vợ/chồng của chính mình.", nodeId=node["id"]))
            else:
                other = nodes[spouse_id]
                if other.get("spouseSlotId") not in (None, node["id"]):
                    errors.append(
                        _error("spouse_conflict", "Quan hệ vợ/chồng bị lệch.", nodeId=node["id"])
                    )

    children_by_person: dict[str, set[str]] = defaultdict(set)
    parents_by_person: dict[str, set[str]] = defaultdict(set)
    spouses_by_person: dict[str, set[str]] = defaultdict(set)
    person_by_slot = {node["id"]: person_id for person_id, node in active_people.items()}

    for child_id, node in active_people.items():
        for parent_slot_id in node["parentSlotIds"]:
            parent_id = person_by_slot.get(parent_slot_id)
            if not parent_id:
                continue
            children_by_person[parent_id].add(child_id)
            parents_by_person[child_id].add(parent_id)
        spouse_id = person_by_slot.get(node["spouseSlotId"] or "")
        if spouse_id:
            spouses_by_person[child_id].add(spouse_id)
            spouses_by_person[spouse_id].add(child_id)

    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(person_id: str) -> None:
        if person_id in visiting:
            errors.append(_error("ancestry_cycle", "Quan hệ huyết thống tạo thành chu kỳ.", personId=person_id))
            return
        if person_id in visited:
            return
        visiting.add(person_id)
        for child_id in children_by_person.get(person_id, set()):
            visit(child_id)
        visiting.remove(person_id)
        visited.add(person_id)

    for person_id in active_people:
        visit(person_id)

    deaths: dict[str, date | None] = {}
    for person_id in active_people:
        raw_death = _value(
            normalized_people[person_id], "ngay_chet", "death_date", "deathDate", "death"
        )
        try:
            deaths[person_id] = _parse_death_date(raw_death)
        except ValueError as exc:
            errors.append(_error("invalid_death_date", str(exc), personId=person_id))

    owners = [person_id for person_id, node in active_people.items() if node["isLandOwner"]]
    if not owners:
        errors.append(_error("missing_land_owner", "Chưa chọn Chủ đất."))

    graph = {
        "people": normalized_people,
        "nodesByPerson": active_people,
        "personBySlot": person_by_slot,
        "children": children_by_person,
        "parents": parents_by_person,
        "spouses": spouses_by_person,
        "deaths": deaths,
        "owners": owners,
    }
    return nodes, graph, errors


def run_inheritance_case(
    engine_input: Mapping[str, Any], people_by_id: Mapping[Any, Any]
) -> dict[str, Any]:
    """Calculate exact final ownership from Diagram V2 input."""

    if not isinstance(engine_input, Mapping) or not isinstance(people_by_id, Mapping):
        return _empty_result([_error("invalid_input", "Dữ liệu engine không hợp lệ.")])

    _nodes, graph, errors = _validate_and_build_graph(engine_input, people_by_id)
    if errors:
        return _empty_result(errors)

    nodes_by_person: dict[str, dict[str, Any]] = graph["nodesByPerson"]
    children: dict[str, set[str]] = graph["children"]
    parents: dict[str, set[str]] = graph["parents"]
    spouses: dict[str, set[str]] = graph["spouses"]
    deaths: dict[str, date | None] = graph["deaths"]
    owners: list[str] = graph["owners"]

    holdings = {person_id: Fraction(0) for person_id in nodes_by_person}
    base_shares = {person_id: Fraction(0) for person_id in nodes_by_person}
    inherited_shares = {person_id: Fraction(0) for person_id in nodes_by_person}
    distributed_shares = {person_id: Fraction(0) for person_id in nodes_by_person}
    terms: dict[str, list[dict[str, Any]]] = defaultdict(list)
    required_slots: dict[tuple[str, str], dict[str, Any]] = {}
    unresolved_estates: list[dict[str, Any]] = []

    base = Fraction(1, len(owners))
    for person_id in owners:
        holdings[person_id] += base
        base_shares[person_id] += base
        terms[person_id].append({"kind": "base", "fraction": _fraction_text(base)})

    def add_requirement(person_id: str, reason: str) -> None:
        node = nodes_by_person[person_id]
        key = (node["id"], reason)
        slot_types = ["father", "mother", "spouse", "child"] if reason == "active_estate" else ["spouse", "child"]
        required_slots[key] = {
            "anchorSlotId": node["id"],
            "reason": reason,
            "slotTypes": slot_types,
            "minimumEmptyChildSlots": 1,
        }

    def death_comparison(person_id: str, event_date: date) -> str:
        death = deaths[person_id]
        if death is None:
            return "alive"
        if death < event_date:
            return "before"
        if death == event_date:
            return "same"
        return "after"

    def accepts(person_id: str, comparison: str) -> bool:
        return comparison == "after" or (
            comparison == "alive" and nodes_by_person[person_id]["willReceive"]
        )

    def descendant_plan(
        person_id: str, event_date: date, via: tuple[str, ...], stack: frozenset[str]
    ) -> dict[str, Any] | None:
        if person_id in stack:
            return None
        comparison = death_comparison(person_id, event_date)
        if comparison in ("alive", "after"):
            if not accepts(person_id, comparison):
                return None
            return {"type": "person", "personId": person_id, "via": list(via)}

        add_requirement(person_id, "representation_branch")
        plans = []
        next_stack = stack | {person_id}
        for child_id in sorted(children.get(person_id, set())):
            plan = descendant_plan(child_id, event_date, via + (person_id,), next_stack)
            if plan is not None:
                plans.append(plan)
        if not plans:
            return None
        return {"type": "split", "children": plans}

    def first_line_units(source_id: str, event_date: date) -> list[dict[str, Any]]:
        units: list[dict[str, Any]] = []
        seen_direct: set[str] = set()
        for person_id in sorted(parents.get(source_id, set()) | spouses.get(source_id, set())):
            comparison = death_comparison(person_id, event_date)
            if person_id not in seen_direct and accepts(person_id, comparison):
                units.append({"type": "person", "personId": person_id, "via": []})
                seen_direct.add(person_id)
        for child_id in sorted(children.get(source_id, set())):
            plan = descendant_plan(child_id, event_date, (), frozenset({source_id}))
            if plan is not None:
                units.append(plan)
        return units

    def credit(plan: dict[str, Any], amount: Fraction, source_id: str) -> None:
        if plan["type"] == "split":
            child_plans = plan["children"]
            child_share = amount / len(child_plans)
            for child_plan in child_plans:
                credit(child_plan, child_share, source_id)
            return

        person_id = plan["personId"]
        holdings[person_id] += amount
        inherited_shares[person_id] += amount
        via = plan["via"]
        term = {
            "kind": "representation" if via else "inheritance",
            "fraction": _fraction_text(amount),
            "sourcePersonId": source_id,
        }
        if via:
            term["viaBranchPersonIds"] = via
        terms[person_id].append(term)

    death_groups: dict[date, list[str]] = defaultdict(list)
    for person_id, death in deaths.items():
        if death is not None:
            death_groups[death].append(person_id)

    for event_date in sorted(death_groups):
        day_estates = {
            person_id: holdings[person_id]
            for person_id in death_groups[event_date]
            if holdings[person_id] > 0
        }
        for source_id, estate in day_estates.items():
            holdings[source_id] = Fraction(0)
            distributed_shares[source_id] += estate
            add_requirement(source_id, "active_estate")

        for source_id, estate in day_estates.items():
            units = first_line_units(source_id, event_date)
            if not units:
                unresolved_estates.append(
                    {
                        "sourcePersonId": source_id,
                        "eventDate": event_date.isoformat(),
                        "fraction": _fraction_text(estate),
                        "reason": "no_valid_heir",
                    }
                )
                continue
            unit_share = estate / len(units)
            for unit in units:
                credit(unit, unit_share, source_id)

    allocated = sum(holdings.values(), Fraction(0))
    unresolved = sum(
        (Fraction(item["fraction"]) for item in unresolved_estates), Fraction(0)
    )
    total = allocated + unresolved
    if total != 1:
        return _empty_result(
            [_error("conservation_failed", "Tổng tài sản sau tính toán không bằng 1.", total=_fraction_text(total))]
        )

    allocations: dict[str, dict[str, str]] = {}
    breakdowns: list[dict[str, Any]] = []
    for person_id in sorted(nodes_by_person):
        final_share = holdings[person_id]
        allocations[person_id] = {
            "baseShare": _fraction_text(base_shares[person_id]),
            "inheritedShare": _fraction_text(inherited_shares[person_id]),
            "distributedShare": _fraction_text(distributed_shares[person_id]),
            "finalShare": _fraction_text(final_share),
            "displayPercent": _percent_text(final_share),
        }
        if final_share > 0:
            breakdowns.append(
                {
                    "personId": person_id,
                    "total": _fraction_text(final_share),
                    "terms": terms[person_id],
                }
            )

    return {
        "engineVersion": ENGINE_VERSION,
        "status": "incomplete" if unresolved else "complete",
        "allocations": allocations,
        "breakdowns": breakdowns,
        "requiredSlots": list(required_slots.values()),
        "warnings": [],
        "errors": [],
        "unresolvedEstates": unresolved_estates,
        "conservation": {
            "allocated": _fraction_text(allocated),
            "unresolved": _fraction_text(unresolved),
            "total": _fraction_text(total),
        },
    }
