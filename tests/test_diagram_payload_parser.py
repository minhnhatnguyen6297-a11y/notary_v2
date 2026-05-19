import json
import inspect
import sqlite3
import tempfile
import unittest
from pathlib import Path

import database
from models import Customer, InheritanceCase, Property
from routers.cases import (
    DiagramPayloadValidationError,
    _normalize_case_state_json,
    _normalize_diagram_payload,
    _parse_case_diagram_payload,
    _resolve_posted_participants,
    _validate_case_refs,
    create,
    edit,
)


def _customer(cid: int, name: str) -> Customer:
    return Customer(id=cid, ho_ten=name)


def _property(pid: int) -> Property:
    return Property(id=pid, so_serial=f"SER-{pid}", dia_chi=f"Dia chi {pid}")


def _payload(nodes):
    return json.dumps({
        "version": 2,
        "updatedAt": "2026-05-11T10:00:00.000Z",
        "nodes": nodes,
    })


class CaseStateSchemaTests(unittest.TestCase):
    def test_inheritance_case_model_declares_case_state_json_column(self):
        self.assertIn("case_state_json", InheritanceCase.__table__.columns)
        column = InheritanceCase.__table__.columns["case_state_json"]
        self.assertEqual(str(column.type).upper(), "TEXT")

    def test_inheritance_cases_schema_migration_adds_case_state_json(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            db_path = Path(tmp_dir) / "legacy.db"
            con = sqlite3.connect(db_path)
            cur = con.cursor()
            cur.execute(
                """
                CREATE TABLE inheritance_cases (
                    id INTEGER PRIMARY KEY,
                    nguoi_chet_id INTEGER NOT NULL,
                    tai_san_id INTEGER NOT NULL,
                    ngay_lap_ho_so DATE NOT NULL
                )
                """
            )
            con.commit()
            con.close()

            original_db_path = database.DB_PATH
            try:
                database.DB_PATH = db_path
                database.migrate_inheritance_cases_schema()
            finally:
                database.DB_PATH = original_db_path

            con = sqlite3.connect(db_path)
            cur = con.cursor()
            cur.execute("PRAGMA table_info(inheritance_cases)")
            columns = {row[1] for row in cur.fetchall()}
            con.close()

        self.assertIn("case_state_json", columns)


class CaseStatePayloadTests(unittest.TestCase):
    def test_create_and_edit_accept_case_state_json_form_field(self):
        self.assertIn("case_state_json", inspect.signature(create).parameters)
        self.assertIn("case_state_json", inspect.signature(edit).parameters)

    def test_normalize_case_state_json_accepts_stage_and_diagram(self):
        raw = json.dumps({
            "schemaVersion": 1,
            "stage": [{"id": "z3", "ho_ten": "z3"}],
            "diagram": {"assignments": {}, "engineState": {"nodes": []}},
        })

        normalized = json.loads(_normalize_case_state_json(raw))

        self.assertEqual(normalized["stage"][0]["ho_ten"], "z3")
        self.assertEqual(normalized["diagram"]["assignments"], {})

    def test_normalize_case_state_json_rejects_non_object_payload(self):
        with self.assertRaises(DiagramPayloadValidationError):
            _normalize_case_state_json("[]")


class DiagramPayloadParserTests(unittest.TestCase):
    def test_normalize_diagram_payload_accepts_nullable_relation_fields(self):
        payload = _payload([
            {
                "id": "owner",
                "kind": "person",
                "role": "Owner",
                "relationType": "owner",
                "personId": "1",
                "parentSlotId": "",
                "parentPersonId": "",
                "familyGroupId": "",
                "sourceId": "",
                "willReceive": True,
            }
        ])

        normalized = _normalize_diagram_payload(payload)

        self.assertEqual(normalized["version"], 2)
        self.assertEqual(normalized["nodes"][0]["id"], "owner")
        self.assertIsNone(normalized["nodes"][0]["parentSlotId"])
        self.assertIsNone(normalized["nodes"][0]["parentPersonId"])

    def test_parse_case_diagram_payload_returns_non_owner_participants_only(self):
        customers = {
            "1": _customer(1, "Owner"),
            "2": _customer(2, "Child A"),
            "3": _customer(3, "Child B"),
        }
        payload = _payload([
            {"id": "owner", "kind": "person", "role": "Owner", "relationType": "owner", "personId": "1", "willReceive": False},
            {"id": "child_1", "kind": "person", "role": "Con", "relationType": "child", "personId": "2", "parentPersonId": "1", "willReceive": True},
            {"id": "child_2", "kind": "person", "role": "Con", "relationType": "child", "personId": "3", "parentPersonId": "1", "willReceive": False},
        ])

        participants, participant_ids, engine_state = _parse_case_diagram_payload(payload, customers, "1")

        self.assertEqual(participant_ids, {2, 3})
        self.assertEqual([p.customer_id for p in participants], [2, 3])
        self.assertEqual(participants[0].parent_customer_id, 1)
        self.assertFalse(participants[1].co_nhan_tai_san)
        self.assertEqual(json.loads(engine_state)["nodes"][0]["id"], "owner")

    def test_parse_case_diagram_payload_rejects_owner_mismatch(self):
        customers = {"1": _customer(1, "Dead"), "2": _customer(2, "Wrong Owner")}
        payload = _payload([
            {"id": "owner", "kind": "person", "role": "Owner", "relationType": "owner", "personId": "2", "willReceive": False}
        ])

        with self.assertRaises(DiagramPayloadValidationError) as exc:
            _parse_case_diagram_payload(payload, customers, "1")

        self.assertIn("Owner", str(exc.exception))

    def test_parse_case_diagram_payload_rejects_duplicate_active_person(self):
        customers = {"1": _customer(1, "Dead"), "2": _customer(2, "Duplicate")}
        payload = _payload([
            {"id": "owner", "kind": "person", "role": "Owner", "relationType": "owner", "personId": "1"},
            {"id": "child_1", "kind": "person", "role": "Con", "relationType": "child", "personId": "2"},
            {"id": "child_2", "kind": "person", "role": "Con", "relationType": "child", "personId": "2"},
        ])

        with self.assertRaises(DiagramPayloadValidationError) as exc:
            _parse_case_diagram_payload(payload, customers, "1")

        self.assertIn("trùng", str(exc.exception))

    def test_parse_case_diagram_payload_rejects_unknown_parent(self):
        customers = {"1": _customer(1, "Dead"), "2": _customer(2, "Child")}
        payload = _payload([
            {"id": "owner", "kind": "person", "role": "Owner", "relationType": "owner", "personId": "1"},
            {"id": "child_1", "kind": "person", "role": "Con", "relationType": "child", "personId": "2", "parentPersonId": "999"},
        ])

        with self.assertRaises(DiagramPayloadValidationError) as exc:
            _parse_case_diagram_payload(payload, customers, "1")

        self.assertIn("parentPersonId", str(exc.exception))

    def test_normalize_diagram_payload_requires_version_two(self):
        payload = json.dumps({"updatedAt": "2026-05-11T10:00:00.000Z", "nodes": []})

        with self.assertRaises(DiagramPayloadValidationError) as exc:
            _normalize_diagram_payload(payload)

        self.assertIn("version", str(exc.exception))

    def test_validate_case_refs_flags_unknown_customer_and_property(self):
        field_errors = {}
        errors = []

        _validate_case_refs(
            nguoi_chet_id="999",
            tai_san_id="2",
            selected_property_ids=[2, 3],
            customers_by_id={"1": _customer(1, "Known")},
            properties_by_id={2: _property(2)},
            field_errors=field_errors,
            errors=errors,
        )

        self.assertTrue(field_errors["nguoi_chet_id"])
        self.assertTrue(errors)

    def test_resolve_posted_participants_falls_back_to_legacy_inputs(self):
        customers = [_customer(1, "Dead"), _customer(2, "Legacy Child")]

        participants, participant_ids, engine_state, raw_payload = _resolve_posted_participants(
            all_customers=customers,
            deceased_customer_id="1",
            diagram_payload="",
            participant_id=["2"],
            participant_role=["Con"],
            participant_share=["0"],
            participant_receive=["1"],
            participant_parent_id=["1"],
            engine_state_json="",
        )

        self.assertEqual(participant_ids, {2})
        self.assertEqual(participants[0].customer_id, 2)
        self.assertEqual(participants[0].parent_customer_id, 1)
        self.assertIsNone(engine_state)
        self.assertEqual(raw_payload, "")


if __name__ == "__main__":
    unittest.main()
