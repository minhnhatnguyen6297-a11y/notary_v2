"""Validate sourced research records without inventing expected results."""

import json
from fractions import Fraction
from pathlib import Path

from services.inheritance_engine import run_inheritance_case


FIXTURE = Path(__file__).parent / "fixtures" / "inheritance_research_cases.json"
STATUSES = {"accepted", "ambiguous", "source_error", "out_of_scope", "duplicate_source"}
CONFIDENCE_LEVELS = {"high", "medium", "low"}


def _load():
    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
    assert payload["schema_version"] == 1
    return payload


def test_research_catalog_has_at_least_twenty_unique_records_and_sources():
    payload = _load()
    cases = payload["cases"]
    assert len(cases) >= 20
    assert len({case["id"] for case in cases}) == len(cases)
    assert len(payload["sources"]) >= 5


def test_every_record_has_source_and_explicit_status():
    payload = _load()
    assert payload["accessed_at"]
    for case in payload["cases"]:
        assert case["status"] in STATUSES
        source = payload["sources"][case["source_id"]]
        assert source["url"].startswith("http")
        assert source["title"] and source["unit"]
        assert case["facts"] and case["source_result"]
        assert isinstance(case["assumptions"], list) and all(case["assumptions"])
        assert case["confidence"] in CONFIDENCE_LEVELS
        assert (case["expected"] is not None) == (case["status"] == "accepted")


def test_accepted_oracles_are_exact_and_conserve_one():
    for case in _load()["cases"]:
        if case["status"] != "accepted":
            continue
        shares = {key: Fraction(value) for key, value in case["expected"]["final_shares"].items()}
        assert shares
        assert sum(shares.values(), Fraction(0)) == 1


def test_accepted_engine_cases_match_their_published_fraction_oracles():
    for case in _load()["cases"]:
        if case["status"] != "accepted":
            continue
        model = case["engine"]
        spouse_by_person = {}
        for left, right in model["spouses"]:
            spouse_by_person[left] = right
            spouse_by_person[right] = left
        nodes = [
            {
                "id": f"slot_{person_id}",
                "personId": person_id,
                "parentSlotIds": [f"slot_{parent_id}" for parent_id in model["parents"].get(person_id, [])],
                "spouseSlotId": f"slot_{spouse_by_person[person_id]}" if person_id in spouse_by_person else None,
                "isLandOwner": person_id in model["owners"],
                "willReceive": True,
                "hidden": False,
                "deleted": False,
            }
            for person_id in model["deaths"]
        ]
        result = run_inheritance_case(
            {"version": 2, "nodes": nodes},
            {person_id: {"ngay_chet": death} for person_id, death in model["deaths"].items()},
        )
        assert result["status"] == "complete", case["id"]
        assert result["conservation"] == {
            "allocated": "1",
            "unresolved": "0",
            "total": "1",
        }, case["id"]

        breakdowns = {item["personId"]: item for item in result["breakdowns"]}
        for person_id, expected in case["expected"]["final_shares"].items():
            expected_share = Fraction(expected)
            assert Fraction(result["allocations"][person_id]["finalShare"]) == expected_share, case["id"]
            breakdown = breakdowns[person_id]
            assert Fraction(breakdown["total"]) == expected_share, case["id"]
            assert sum(
                (Fraction(term["fraction"]) for term in breakdown["terms"]),
                Fraction(0),
            ) == expected_share, case["id"]

        slot_types_by_reason = {
            "active_estate": ["father", "mother", "spouse", "child"],
            "representation_branch": ["spouse", "child"],
        }
        for requirement in result["requiredSlots"]:
            assert requirement["reason"] in slot_types_by_reason, case["id"]
            assert requirement["slotTypes"] == slot_types_by_reason[requirement["reason"]], case["id"]
