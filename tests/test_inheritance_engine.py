from __future__ import annotations

from datetime import date
from fractions import Fraction

import pytest

from services.inheritance_engine import _parse_death_date, run_inheritance_case


def _run(
    deaths: dict[str, str | None],
    *,
    parents: dict[str, list[str]] | None = None,
    spouses: list[tuple[str, str]] | None = None,
    owners: set[str] | None = None,
    receive: dict[str, bool] | None = None,
):
    parents = parents or {}
    owners = owners or set()
    receive = receive or {}
    spouse_by_person: dict[str, str] = {}
    for left, right in spouses or []:
        spouse_by_person[left] = right
        spouse_by_person[right] = left

    nodes = [
        {
            "id": f"slot_{person_id}",
            "personId": person_id,
            "parentSlotIds": [f"slot_{parent_id}" for parent_id in parents.get(person_id, [])],
            "spouseSlotId": f"slot_{spouse_by_person[person_id]}" if person_id in spouse_by_person else None,
            "isLandOwner": person_id in owners,
            "willReceive": receive.get(person_id, True),
            "hidden": False,
            "deleted": False,
        }
        for person_id in deaths
    ]
    people = {person_id: {"ngay_chet": death} for person_id, death in deaths.items()}
    return run_inheritance_case({"version": 2, "nodes": nodes}, people)


def _share(result, person_id: str) -> Fraction:
    return Fraction(result["allocations"][person_id]["finalShare"])


def test_fixture_x_y_d_z_matches_exact_expected_fractions():
    result = _run(
        {
            "A": "1995",
            "B": "1996",
            "C": "1997",
            "D": "2016",
            "X": "2011",
            "Y": "2015",
            "Z": "2015",
            "M": None,
            "N": None,
            "O": None,
            "Z2": None,
            "Z3": None,
        },
        parents={
            "X": ["A", "B"],
            "Y": ["C", "D"],
            "Z": ["C", "D"],
            "M": ["X", "Y"],
            "N": ["X", "Y"],
            "O": ["X", "Y"],
            "Z2": ["Z"],
            "Z3": ["Z"],
        },
        spouses=[("A", "B"), ("C", "D"), ("X", "Y")],
        owners={"X", "Y"},
    )

    assert result["status"] == "complete"
    assert [_share(result, person_id) for person_id in ("M", "N", "O")] == [Fraction(59, 192)] * 3
    assert [_share(result, person_id) for person_id in ("Z2", "Z3")] == [Fraction(5, 128)] * 2
    assert result["conservation"] == {"allocated": "1", "unresolved": "0", "total": "1"}


def test_representation_splits_by_branch_at_each_generation_not_flat_descendants():
    result = _run(
        {"X": "2020", "B": None, "Q": "2010", "A": "2009", "D": "2008", "C": None, "E": None, "F": None},
        parents={
            "B": ["X"],
            "Q": ["X"],
            "A": ["Q"],
            "D": ["Q"],
            "C": ["A"],
            "E": ["D"],
            "F": ["D"],
        },
        owners={"X"},
    )

    assert _share(result, "B") == Fraction(1, 2)
    assert _share(result, "C") == Fraction(1, 4)
    assert _share(result, "E") == _share(result, "F") == Fraction(1, 8)


def test_non_owner_child_dead_before_source_has_no_estate_but_descendant_represents():
    result = _run(
        {"X": "2020", "Y": "2010", "Z": None},
        parents={"Y": ["X"], "Z": ["Y"]},
        owners={"X"},
    )

    assert result["status"] == "complete"
    assert _share(result, "Z") == 1
    assert result["allocations"]["Y"]["inheritedShare"] == "0"
    assert result["allocations"]["Y"]["distributedShare"] == "0"
    representation_slots = [item for item in result["requiredSlots"] if item["reason"] == "representation_branch"]
    assert {item["anchorSlotId"] for item in representation_slots} == {"slot_Y"}
    assert representation_slots[0]["slotTypes"] == ["spouse", "child"]
    assert "father" not in representation_slots[0]["slotTypes"]
    assert "mother" not in representation_slots[0]["slotTypes"]


def test_spouse_of_representation_anchor_only_receives_from_anchor_independent_estate():
    result = _run(
        {"X": "2020", "Y": "2010", "S": None, "Z": None},
        parents={"Y": ["X"], "Z": ["Y", "S"]},
        spouses=[("Y", "S")],
        owners={"X", "Y"},
    )

    assert result["status"] == "complete"
    assert _share(result, "S") == Fraction(1, 6)
    assert _share(result, "Z") == Fraction(5, 6)
    z_terms = next(item["terms"] for item in result["breakdowns"] if item["personId"] == "Z")
    assert {(term["sourcePersonId"], term["fraction"]) for term in z_terms} == {("Y", "1/6"), ("X", "2/3")}


def test_person_receiving_from_multiple_estates_keeps_each_source_in_breakdown():
    result = _run(
        {"X": "2010", "Y": "2020", "M": None},
        parents={"M": ["X", "Y"]},
        spouses=[("X", "Y")],
        owners={"X", "Y"},
    )

    assert result["status"] == "complete"
    assert _share(result, "M") == 1
    terms = next(item["terms"] for item in result["breakdowns"] if item["personId"] == "M")
    assert {term.get("sourcePersonId") for term in terms} == {"X", "Y"}


def test_person_dead_after_source_receives_then_opens_later_estate():
    result = _run(
        {"X": "2010", "Y": "2020", "Z": None, "W": None},
        parents={"Y": ["X"], "Z": ["Y", "W"]},
        spouses=[("Y", "W")],
        owners={"X"},
        receive={"Y": False},
    )

    assert result["status"] == "complete"
    assert result["allocations"]["Y"]["inheritedShare"] == "1"
    assert result["allocations"]["Y"]["distributedShare"] == "1"
    assert _share(result, "Z") == _share(result, "W") == Fraction(1, 2)


def test_same_day_spouses_do_not_receive_cross_estates():
    result = _run(
        {"A": "15/06/2020", "B": "15/06/2020", "C": None},
        parents={"C": ["A", "B"]},
        spouses=[("A", "B")],
        owners={"A", "B"},
    )

    assert result["status"] == "complete"
    assert _share(result, "C") == 1
    assert result["allocations"]["A"]["inheritedShare"] == "0"
    assert result["allocations"]["B"]["inheritedShare"] == "0"
    assert result["warnings"] == []


def test_year_only_dates_normalize_to_same_day_snapshot():
    result = _run(
        {"A": "2015", "B": "2015", "C": None},
        parents={"C": ["A", "B"]},
        spouses=[("A", "B")],
        owners={"A", "B"},
    )
    assert result["status"] == "complete"
    assert _share(result, "C") == 1


def test_full_death_date_is_preserved_while_year_only_uses_first_of_january():
    assert _parse_death_date("23/07/2026") == date(2026, 7, 23)
    assert _parse_death_date("2026") == date(2026, 1, 1)


def test_five_living_land_owners_each_keep_one_fifth():
    ids = {"A", "B", "C", "D", "E"}
    result = _run({person_id: None for person_id in ids}, owners=ids)

    assert result["status"] == "complete"
    assert {_share(result, person_id) for person_id in ids} == {Fraction(1, 5)}


def test_living_land_owner_keeps_base_when_receive_is_off():
    result = _run({"A": None}, owners={"A"}, receive={"A": False})
    assert result["status"] == "complete"
    assert _share(result, "A") == 1
    assert result["allocations"]["A"]["baseShare"] == "1"


def test_living_nonreceiver_is_removed_without_opening_representation():
    result = _run(
        {"X": "2020", "A": None, "A1": None, "B": None},
        parents={"A": ["X"], "A1": ["A"], "B": ["X"]},
        owners={"X"},
        receive={"A": False},
    )

    assert result["status"] == "complete"
    assert _share(result, "A") == _share(result, "A1") == 0
    assert _share(result, "B") == 1


def test_dead_child_branch_without_descendants_is_removed_from_denominator():
    result = _run(
        {"X": "2020", "B": "2010", "C": None},
        parents={"B": ["X"], "C": ["X"]},
        owners={"X"},
    )

    assert result["status"] == "complete"
    assert _share(result, "C") == 1
    assert result["unresolvedEstates"] == []


def test_estate_without_any_valid_receiver_is_incomplete_and_conserved():
    result = _run(
        {"X": "2020", "A": None},
        parents={"A": ["X"]},
        owners={"X"},
        receive={"A": False},
    )

    assert result["status"] == "incomplete"
    assert result["unresolvedEstates"] == [
        {"sourcePersonId": "X", "eventDate": "2020-01-01", "fraction": "1", "reason": "no_valid_heir"}
    ]
    assert result["conservation"] == {"allocated": "0", "unresolved": "1", "total": "1"}


def _invalid_result(nodes, people):
    return run_inheritance_case({"version": 2, "nodes": nodes}, people)


@pytest.mark.parametrize(
    ("nodes", "people", "code"),
    [
        (
            [{"id": "a", "personId": "A", "parentSlotIds": ["missing"], "isLandOwner": True}],
            {"A": {"ngay_chet": None}},
            "dangling_parent",
        ),
        (
            [
                {"id": "a1", "personId": "A", "parentSlotIds": [], "isLandOwner": True},
                {"id": "a2", "personId": "A", "parentSlotIds": []},
            ],
            {"A": {"ngay_chet": None}},
            "duplicate_person",
        ),
        (
            [
                {"id": "a", "personId": "A", "parentSlotIds": ["b"], "isLandOwner": True},
                {"id": "b", "personId": "B", "parentSlotIds": ["a"]},
            ],
            {"A": {"ngay_chet": None}, "B": {"ngay_chet": None}},
            "ancestry_cycle",
        ),
        (
            [{"id": "a", "personId": "A", "parentSlotIds": [], "spouseSlotId": "a", "isLandOwner": True}],
            {"A": {"ngay_chet": None}},
            "self_spouse",
        ),
        (
            [
                {"id": "a", "personId": "A", "parentSlotIds": ["b", "c", "d"], "isLandOwner": True},
                {"id": "b", "personId": "B", "parentSlotIds": []},
                {"id": "c", "personId": "C", "parentSlotIds": []},
                {"id": "d", "personId": "D", "parentSlotIds": []},
            ],
            {key: {"ngay_chet": None} for key in "ABCD"},
            "too_many_parents",
        ),
    ],
)
def test_invalid_graphs_are_rejected(nodes, people, code):
    result = _invalid_result(nodes, people)
    assert result["status"] == "invalid"
    assert code in {error["code"] for error in result["errors"]}


def test_boolean_flags_reject_string_false_instead_of_treating_it_as_true():
    result = _invalid_result(
        [
            {"id": "x", "personId": "X", "parentSlotIds": [], "isLandOwner": True},
            {
                "id": "a",
                "personId": "A",
                "parentSlotIds": ["x"],
                "willReceive": "false",
            },
        ],
        {"X": {"ngay_chet": "2020"}, "A": {"ngay_chet": None}},
    )

    assert result["status"] == "invalid"
    assert "invalid_boolean" in {error["code"] for error in result["errors"]}


def test_explicit_parents_do_not_fallback_unrelated_person_to_land_owner_branch():
    result = _run(
        {"X": "2020", "C": None, "D": None, "Z": None},
        parents={"Z": ["C", "D"]},
        owners={"X"},
    )

    assert result["status"] == "incomplete"
    assert _share(result, "Z") == 0
    assert result["unresolvedEstates"][0]["sourcePersonId"] == "X"
