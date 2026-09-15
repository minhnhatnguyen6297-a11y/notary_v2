import json
import inspect
import sqlite3
import tempfile
import unittest
from datetime import date
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from fastapi.responses import JSONResponse
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import database
from models import Customer, InheritanceCase, InheritanceParticipant, Property
from routers.cases import (
    DiagramPayloadValidationError,
    _derive_case_state_json_from_participants,
    _merge_case_state_diagram,
    _merge_case_state_stage,
    _normalize_case_state_json,
    _normalize_diagram_payload,
    _parse_case_diagram_payload,
    _resolve_posted_participants,
    _resolve_v2_case_state,
    _validate_case_refs,
    calculate_diagram,
    create,
    edit,
    update_diagram,
    update_stage,
)


def _customer(cid: int, name: str) -> Customer:
    return Customer(id=cid, ho_ten=name)


def _property(pid: int) -> Property:
    return Property(id=pid, so_serial=f"SER-{pid}", dia_chi=f"Dia chi {pid}")


def _participant(customer: Customer):
    return type("Participant", (), {"customer": customer, "customer_id": customer.id})()


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

    def test_stage_update_accepts_case_state_json_form_field(self):
        self.assertIn("case_state_json", inspect.signature(update_stage).parameters)

    def test_diagram_update_accepts_diagram_only_form_fields(self):
        signature = inspect.signature(update_diagram)
        self.assertIn("case_state_json", signature.parameters)
        self.assertIn("diagram_payload", signature.parameters)
        self.assertIn("engine_state_json", signature.parameters)

    def test_edit_form_derives_case_state_for_legacy_cases(self):
        from routers.cases import edit_form

        source = inspect.getsource(edit_form)

        self.assertIn("_derive_case_state_json_from_participants(participants)", source)

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

    def test_normalize_case_state_json_rejects_duplicate_stage_ids(self):
        raw = json.dumps({
            "schemaVersion": 1,
            "stage": [{"id": "10"}, {"id": "10"}],
            "diagram": {"assignments": {}, "engineState": {"nodes": []}},
        })

        with self.assertRaises(DiagramPayloadValidationError) as exc:
            _normalize_case_state_json(raw)

        self.assertIn("trung", str(exc.exception))

    def test_normalize_case_state_json_rejects_diagram_refs_outside_stage(self):
        raw = json.dumps({
            "schemaVersion": 1,
            "stage": [{"id": "10", "ho_ten": "Kept"}],
            "diagram": {
                "assignments": {"slot_child": "99"},
                "engineState": {"nodes": [{"id": "child", "personId": "99"}]},
            },
        })

        with self.assertRaises(DiagramPayloadValidationError) as exc:
            _normalize_case_state_json(raw)

        self.assertIn("khong co trong stage", str(exc.exception))

    def test_normalize_case_state_json_drops_legacy_edges(self):
        raw = json.dumps({
            "schemaVersion": 1,
            "stage": [
                {"id": "1", "ho_ten": "Nguoi chet"},
                {"id": "2", "ho_ten": "Con hop le"},
            ],
            "diagram": {
                "assignments": {"child_2": "2"},
                "engineState": {
                    "nodes": [
                        {"id": "child_2", "personId": "2"},
                    ],
                    "edges": [
                        {"id": "keep-edge", "source": "child_2", "target": "child_2"},
                        {"id": "drop-edge", "source": "ghost_missing", "target": "child_2"},
                    ],
                },
            },
        })

        normalized = json.loads(_normalize_case_state_json(raw))

        self.assertNotIn("edges", normalized["diagram"]["engineState"])

    def test_normalize_case_state_json_keeps_render_metadata_but_drops_legacy_output(self):
        raw = json.dumps({
            "schemaVersion": 1,
            "stage": [
                {"id": "1", "ho_ten": "Nguoi chet"},
                {"id": "2", "ho_ten": "Con hop le"},
            ],
            "diagram": {
                "assignments": {"child_2": "2"},
                "engineState": {
                    "nodes": [
                        {"id": "child_2", "personId": "2"},
                    ],
                    "edges": [
                        {"id": "keep-edge", "source": "child_2", "target": "child_2"},
                    ],
                    "allocations": {"2": {"displayPercent": "50.00"}},
                    "warnings": [{"code": "demo_warning"}],
                    "trace": [{"type": "flow", "from": "1", "to": "2"}],
                    "viewport": {"x": 120.5, "y": -32.25, "zoom": 0.85},
                    "layoutMeta": {
                        "laneOffsets": {"children": 240},
                        "collapsedBranches": ["child_2"],
                    },
                },
            },
        })

        normalized = json.loads(_normalize_case_state_json(raw))
        normalized_engine_state = normalized["diagram"]["engineState"]

        self.assertNotIn("edges", normalized_engine_state)
        self.assertNotIn("allocations", normalized_engine_state)
        self.assertNotIn("warnings", normalized_engine_state)
        self.assertNotIn("trace", normalized_engine_state)
        self.assertEqual(normalized_engine_state["viewport"]["zoom"], 0.85)
        self.assertEqual(normalized_engine_state["layoutMeta"]["laneOffsets"]["children"], 240)
        self.assertEqual(normalized_engine_state["layoutMeta"]["collapsedBranches"][0], "child_2")

    def test_merge_case_state_diagram_preserves_existing_stage_rows(self):
        existing = json.dumps({
            "schemaVersion": 1,
            "stage": [{"id": "10", "ho_ten": "Stage source"}],
            "diagram": {"assignments": {}, "engineState": {"nodes": []}},
        })
        submitted = json.dumps({
            "schemaVersion": 1,
            "stage": [{"id": "10", "ho_ten": "Draft should not overwrite"}],
            "diagram": {
                "assignments": {"owner": "10"},
                "engineState": {"nodes": [{"id": "owner", "personId": "10"}]},
            },
        })

        merged = json.loads(_merge_case_state_diagram(existing, submitted))

        self.assertEqual(merged["stage"][0]["ho_ten"], "Stage source")
        self.assertEqual(merged["diagram"]["assignments"], {"owner": "10"})

    def test_merge_case_state_diagram_rejects_refs_outside_preserved_stage(self):
        existing = json.dumps({
            "schemaVersion": 1,
            "stage": [{"id": "10", "ho_ten": "Stage source"}],
            "diagram": {"assignments": {}, "engineState": {"nodes": []}},
        })
        submitted = json.dumps({
            "schemaVersion": 1,
            "stage": [{"id": "99", "ho_ten": "Submitted only"}],
            "diagram": {
                "assignments": {"owner": "99"},
                "engineState": {"nodes": [{"id": "owner", "personId": "99"}]},
            },
        })

        with self.assertRaises(DiagramPayloadValidationError):
            _merge_case_state_diagram(existing, submitted)

    def test_merge_case_state_diagram_drops_legacy_output_and_keeps_render_metadata(self):
        existing = json.dumps({
            "schemaVersion": 1,
            "stage": [{"id": "10", "ho_ten": "Stage source"}],
            "diagram": {
                "assignments": {"owner": "10"},
                "engineState": {
                    "nodes": [{"id": "owner", "personId": "10"}],
                    "warnings": [{"code": "old_warning"}],
                },
            },
        })
        submitted = json.dumps({
            "schemaVersion": 1,
            "stage": [{"id": "10", "ho_ten": "Draft should not overwrite"}],
            "diagram": {
                "assignments": {"owner": "10"},
                "engineState": {
                    "nodes": [{"id": "owner", "personId": "10"}],
                    "allocations": {"10": {"displayPercent": "100.00"}},
                    "warnings": [{"code": "new_warning"}],
                    "trace": [{"from": "owner", "to": "owner"}],
                    "viewport": {"x": 12, "y": 24, "zoom": 0.9},
                    "layoutMeta": {"laneOffsets": {"children": 220}},
                },
            },
        })

        merged = json.loads(_merge_case_state_diagram(existing, submitted))
        merged_engine_state = merged["diagram"]["engineState"]

        self.assertEqual(merged["stage"][0]["ho_ten"], "Stage source")
        self.assertEqual(merged["diagram"]["assignments"], {"owner": "10"})
        self.assertNotIn("allocations", merged_engine_state)
        self.assertNotIn("warnings", merged_engine_state)
        self.assertNotIn("trace", merged_engine_state)
        self.assertEqual(merged_engine_state["viewport"]["zoom"], 0.9)
        self.assertEqual(merged_engine_state["layoutMeta"]["laneOffsets"]["children"], 220)

    def test_update_diagram_prunes_payload_people_outside_stage(self):
        case = SimpleNamespace(
            id=77,
            is_locked=False,
            nguoi_chet_id=1,
            case_state_json=json.dumps({
                "schemaVersion": 1,
                "stage": [{"id": "1", "ho_ten": "Nguoi chet"}],
                "diagram": {"assignments": {}, "engineState": {"nodes": []}},
            }),
            engine_state_json=None,
        )
        customers = [_customer(1, "Nguoi chet"), _customer(99, "Nguoi lech stage")]
        submitted_case_state = json.dumps({
            "schemaVersion": 1,
            "stage": [{"id": "1", "ho_ten": "Draft stale"}],
            "diagram": {"assignments": {}, "engineState": {"nodes": []}},
        })
        raw_diagram_payload = _payload([
            {"id": "child_99", "kind": "person", "role": "Con", "relationType": "child", "personId": "99"},
        ])

        class _FakeQuery:
            def __init__(self, *, first_item=None, all_items=None):
                self._first_item = first_item
                self._all_items = all_items or []

            def filter(self, *_args, **_kwargs):
                return self

            def first(self):
                return self._first_item

            def all(self):
                return self._all_items

        class _FakeDb:
            def __init__(self, stored_case, customer_rows):
                self.stored_case = stored_case
                self.customer_rows = customer_rows
                self.committed = False

            def query(self, model):
                if model is InheritanceCase:
                    return _FakeQuery(first_item=self.stored_case)
                if model is Customer:
                    return _FakeQuery(all_items=self.customer_rows)
                raise AssertionError(f"Unexpected model query: {model}")

            def commit(self):
                self.committed = True

        fake_db = _FakeDb(case, customers)
        captured = {}

        def _capture_replace(_db, case_id, participants):
            captured["case_id"] = case_id
            captured["participant_ids"] = [p.customer_id for p in participants]

        with patch("routers.cases._replace_case_participants", _capture_replace):
            result = update_diagram(
                cid=77,
                case_state_json=submitted_case_state,
                diagram_payload=raw_diagram_payload,
                engine_state_json="",
                db=fake_db,
            )

        self.assertTrue(fake_db.committed)
        self.assertEqual(captured["case_id"], 77)
        self.assertEqual(captured["participant_ids"], [])
        self.assertEqual(json.loads(case.case_state_json)["stage"], [{"id": "1", "ho_ten": "Nguoi chet"}])
        self.assertEqual(json.loads(case.engine_state_json)["nodes"], [])
        self.assertEqual(json.loads(result["diagram_payload"])["nodes"], [])

    def test_update_diagram_prefers_case_state_engine_state_over_stale_diagram_payload(self):
        case = SimpleNamespace(
            id=88,
            is_locked=False,
            nguoi_chet_id=1,
            case_state_json=json.dumps({
                "schemaVersion": 1,
                "stage": [
                    {"id": "1", "ho_ten": "Nguoi chet"},
                    {"id": "2", "ho_ten": "Con hop le"},
                ],
                "diagram": {"assignments": {}, "engineState": {"nodes": []}},
            }),
            engine_state_json=None,
        )
        customers = [
            _customer(1, "Nguoi chet"),
            _customer(2, "Con hop le"),
            _customer(99, "Nguoi stale"),
        ]
        submitted_case_state = json.dumps({
            "schemaVersion": 1,
            "stage": [
                {"id": "1", "ho_ten": "Nguoi chet"},
                {"id": "2", "ho_ten": "Con hop le"},
            ],
            "diagram": {
                "assignments": {"child_2": "2"},
                "engineState": {
                    "nodes": [
                        {"id": "child_2", "kind": "person", "role": "Con", "relationType": "child", "personId": "2"},
                    ],
                },
                "updatedAt": "2026-06-22T10:00:00.000Z",
            },
        })
        raw_diagram_payload = _payload([
            {"id": "child_99", "kind": "person", "role": "Con", "relationType": "child", "personId": "99"},
        ])

        class _FakeQuery:
            def __init__(self, *, first_item=None, all_items=None):
                self._first_item = first_item
                self._all_items = all_items or []

            def filter(self, *_args, **_kwargs):
                return self

            def first(self):
                return self._first_item

            def all(self):
                return self._all_items

        class _FakeDb:
            def __init__(self, stored_case, customer_rows):
                self.stored_case = stored_case
                self.customer_rows = customer_rows
                self.committed = False

            def query(self, model):
                if model is InheritanceCase:
                    return _FakeQuery(first_item=self.stored_case)
                if model is Customer:
                    return _FakeQuery(all_items=self.customer_rows)
                raise AssertionError(f"Unexpected model query: {model}")

            def commit(self):
                self.committed = True

        fake_db = _FakeDb(case, customers)
        captured = {}

        def _capture_replace(_db, case_id, participants):
            captured["case_id"] = case_id
            captured["participant_ids"] = [p.customer_id for p in participants]

        with patch("routers.cases._replace_case_participants", _capture_replace):
            result = update_diagram(
                cid=88,
                case_state_json=submitted_case_state,
                diagram_payload=raw_diagram_payload,
                engine_state_json="",
                db=fake_db,
            )

        self.assertTrue(fake_db.committed)
        self.assertEqual(captured["case_id"], 88)
        self.assertEqual(captured["participant_ids"], [2])
        self.assertEqual(json.loads(case.engine_state_json)["nodes"][0]["personId"], "2")
        self.assertEqual(json.loads(result["diagram_payload"])["nodes"][0]["personId"], "2")

    def test_update_diagram_prefers_case_state_engine_state_over_stale_engine_state_json(self):
        case = SimpleNamespace(
            id=88_1,
            is_locked=False,
            nguoi_chet_id=1,
            case_state_json=json.dumps({
                "schemaVersion": 1,
                "stage": [
                    {"id": "1", "ho_ten": "Nguoi chet"},
                    {"id": "2", "ho_ten": "Con hop le"},
                ],
                "diagram": {"assignments": {}, "engineState": {"nodes": []}},
            }),
            engine_state_json=None,
        )
        customers = [
            _customer(1, "Nguoi chet"),
            _customer(2, "Con hop le"),
        ]
        submitted_case_state = json.dumps({
            "schemaVersion": 1,
            "stage": [
                {"id": "1", "ho_ten": "Nguoi chet"},
                {"id": "2", "ho_ten": "Con hop le"},
            ],
            "diagram": {
                "assignments": {"child_fresh": "2"},
                "engineState": {
                    "nodes": [
                        {
                            "id": "child_fresh",
                            "kind": "person",
                            "role": "Con",
                            "relationType": "child",
                            "personId": "2",
                            "parentSlotId": "owner",
                            "sourceId": "owner",
                            "familyGroupId": "ownerSpouse",
                        },
                    ],
                },
                "updatedAt": "2026-06-23T02:00:00.000Z",
            },
        })
        stale_engine_state_json = json.dumps({
            "version": 2,
            "updatedAt": "2026-06-01T00:00:00.000Z",
            "nodes": [
                {
                    "id": "child_stale",
                    "kind": "person",
                    "role": "Con",
                    "relationType": "child",
                    "personId": "2",
                    "parentSlotId": "owner",
                    "sourceId": "owner",
                    "familyGroupId": "ownerSpouse",
                },
            ],
        })

        class _FakeQuery:
            def __init__(self, *, first_item=None, all_items=None):
                self._first_item = first_item
                self._all_items = all_items or []

            def filter(self, *_args, **_kwargs):
                return self

            def first(self):
                return self._first_item

            def all(self):
                return self._all_items

        class _FakeDb:
            def __init__(self, stored_case, customer_rows):
                self.stored_case = stored_case
                self.customer_rows = customer_rows
                self.committed = False

            def query(self, model):
                if model is InheritanceCase:
                    return _FakeQuery(first_item=self.stored_case)
                if model is Customer:
                    return _FakeQuery(all_items=self.customer_rows)
                raise AssertionError(f"Unexpected model query: {model}")

            def commit(self):
                self.committed = True

        fake_db = _FakeDb(case, customers)
        captured = {}

        def _capture_replace(_db, case_id, participants):
            captured["case_id"] = case_id
            captured["participant_ids"] = [p.customer_id for p in participants]

        with patch("routers.cases._replace_case_participants", _capture_replace):
            result = update_diagram(
                cid=881,
                case_state_json=submitted_case_state,
                diagram_payload="",
                engine_state_json=stale_engine_state_json,
                db=fake_db,
            )

        saved_case_state = json.loads(result["case_state_json"])
        saved_engine_state = json.loads(case.engine_state_json)
        self.assertTrue(fake_db.committed)
        self.assertEqual(captured["case_id"], 881)
        self.assertEqual(captured["participant_ids"], [2])
        self.assertEqual(saved_case_state["diagram"]["updatedAt"], "2026-06-23T02:00:00.000Z")
        self.assertEqual(saved_case_state["diagram"]["engineState"]["updatedAt"], "2026-06-23T02:00:00.000Z")
        self.assertEqual(saved_case_state["diagram"]["engineState"]["nodes"][0]["id"], "child_fresh")
        self.assertEqual(saved_engine_state["updatedAt"], "2026-06-23T02:00:00.000Z")
        self.assertEqual(saved_engine_state["nodes"][0]["id"], "child_fresh")
        self.assertEqual(json.loads(result["diagram_payload"])["updatedAt"], "2026-06-23T02:00:00.000Z")
        self.assertEqual(json.loads(result["diagram_payload"])["nodes"][0]["id"], "child_fresh")

    def test_update_diagram_prunes_broken_case_state_engine_nodes_before_save(self):
        case = SimpleNamespace(
            id=89,
            is_locked=False,
            nguoi_chet_id=1,
            case_state_json=json.dumps({
                "schemaVersion": 1,
                "stage": [
                    {"id": "1", "ho_ten": "Nguoi chet"},
                    {"id": "2", "ho_ten": "Chau hop le"},
                ],
                "diagram": {"assignments": {}, "engineState": {"nodes": []}},
            }),
            engine_state_json=None,
        )
        customers = [
            _customer(1, "Nguoi chet"),
            _customer(2, "Chau hop le"),
        ]
        submitted_case_state = json.dumps({
            "schemaVersion": 1,
            "stage": [
                {"id": "1", "ho_ten": "Nguoi chet"},
                {"id": "2", "ho_ten": "Chau hop le"},
            ],
            "diagram": {
                "assignments": {"grandchild_2": "2"},
                "engineState": {
                    "nodes": [
                        {
                            "id": "grandchild_2",
                            "kind": "person",
                            "role": "Chau",
                            "relationType": "grandchild",
                            "personId": "2",
                            "parentPersonId": "99",
                            "parentSlotId": "ghost_99",
                        },
                    ],
                },
                "updatedAt": "2026-06-22T11:00:00.000Z",
            },
        })

        class _FakeQuery:
            def __init__(self, *, first_item=None, all_items=None):
                self._first_item = first_item
                self._all_items = all_items or []

            def filter(self, *_args, **_kwargs):
                return self

            def first(self):
                return self._first_item

            def all(self):
                return self._all_items

        class _FakeDb:
            def __init__(self, stored_case, customer_rows):
                self.stored_case = stored_case
                self.customer_rows = customer_rows
                self.committed = False

            def query(self, model):
                if model is InheritanceCase:
                    return _FakeQuery(first_item=self.stored_case)
                if model is Customer:
                    return _FakeQuery(all_items=self.customer_rows)
                raise AssertionError(f"Unexpected model query: {model}")

            def commit(self):
                self.committed = True

        fake_db = _FakeDb(case, customers)
        captured = {}

        def _capture_replace(_db, case_id, participants):
            captured["case_id"] = case_id
            captured["participant_ids"] = [p.customer_id for p in participants]

        with patch("routers.cases._replace_case_participants", _capture_replace):
            result = update_diagram(
                cid=89,
                case_state_json=submitted_case_state,
                diagram_payload="",
                engine_state_json="",
                db=fake_db,
            )

        saved_case_state = json.loads(result["case_state_json"])
        self.assertTrue(fake_db.committed)
        self.assertEqual(captured["case_id"], 89)
        self.assertEqual(captured["participant_ids"], [])
        self.assertEqual(saved_case_state["diagram"]["assignments"], {})
        self.assertEqual(saved_case_state["diagram"]["engineState"]["nodes"], [])
        self.assertEqual(json.loads(case.engine_state_json)["nodes"], [])

    def test_update_diagram_does_not_keep_hidden_node_in_assignments(self):
        case = SimpleNamespace(
            id=90,
            is_locked=False,
            nguoi_chet_id=1,
            case_state_json=json.dumps({
                "schemaVersion": 1,
                "stage": [
                    {"id": "1", "ho_ten": "Nguoi chet"},
                    {"id": "2", "ho_ten": "Con an"},
                ],
                "diagram": {"assignments": {}, "engineState": {"nodes": []}},
            }),
            engine_state_json=None,
        )
        customers = [_customer(1, "Nguoi chet"), _customer(2, "Con an")]
        submitted_case_state = json.dumps({
            "schemaVersion": 1,
            "stage": [
                {"id": "1", "ho_ten": "Nguoi chet"},
                {"id": "2", "ho_ten": "Con an"},
            ],
            "diagram": {
                "assignments": {"child_hidden": "2"},
                "engineState": {
                    "nodes": [
                        {
                            "id": "child_hidden",
                            "kind": "person",
                            "role": "Con",
                            "relationType": "child",
                            "personId": "2",
                            "hidden": True,
                        },
                    ],
                },
                "updatedAt": "2026-06-22T12:00:00.000Z",
            },
        })

        class _FakeQuery:
            def __init__(self, *, first_item=None, all_items=None):
                self._first_item = first_item
                self._all_items = all_items or []

            def filter(self, *_args, **_kwargs):
                return self

            def first(self):
                return self._first_item

            def all(self):
                return self._all_items

        class _FakeDb:
            def __init__(self, stored_case, customer_rows):
                self.stored_case = stored_case
                self.customer_rows = customer_rows
                self.committed = False

            def query(self, model):
                if model is InheritanceCase:
                    return _FakeQuery(first_item=self.stored_case)
                if model is Customer:
                    return _FakeQuery(all_items=self.customer_rows)
                raise AssertionError(f"Unexpected model query: {model}")

            def commit(self):
                self.committed = True

        fake_db = _FakeDb(case, customers)
        captured = {}

        def _capture_replace(_db, case_id, participants):
            captured["case_id"] = case_id
            captured["participant_ids"] = [p.customer_id for p in participants]

        with patch("routers.cases._replace_case_participants", _capture_replace):
            result = update_diagram(
                cid=90,
                case_state_json=submitted_case_state,
                diagram_payload="",
                engine_state_json="",
                db=fake_db,
            )

        saved_case_state = json.loads(result["case_state_json"])
        self.assertTrue(fake_db.committed)
        self.assertEqual(captured["case_id"], 90)
        self.assertEqual(captured["participant_ids"], [])
        self.assertEqual(saved_case_state["diagram"]["assignments"], {})
        self.assertTrue(saved_case_state["diagram"]["engineState"]["nodes"][0]["hidden"])

    def test_update_diagram_drops_stale_assignment_for_empty_slot(self):
        case = SimpleNamespace(
            id=90_1,
            is_locked=False,
            nguoi_chet_id=1,
            case_state_json=json.dumps({
                "schemaVersion": 1,
                "stage": [
                    {"id": "1", "ho_ten": "Nguoi chet"},
                    {"id": "2", "ho_ten": "Vo/chong trong stage"},
                ],
                "diagram": {"assignments": {}, "engineState": {"nodes": []}},
            }),
            engine_state_json=None,
        )
        customers = [_customer(1, "Nguoi chet"), _customer(2, "Vo/chong trong stage")]
        submitted_case_state = json.dumps({
            "schemaVersion": 1,
            "stage": [
                {"id": "1", "ho_ten": "Nguoi chet"},
                {"id": "2", "ho_ten": "Vo/chong trong stage"},
            ],
            "diagram": {
                "assignments": {"spouse": "2"},
                "engineState": {
                    "nodes": [
                        {
                            "id": "owner",
                            "kind": "person",
                            "role": "Owner",
                            "relationType": "owner",
                            "personId": "1",
                            "bucket": 1,
                            "allowsShare": True,
                            "removable": False,
                        },
                        {
                            "id": "spouse",
                            "kind": "person",
                            "role": "Vợ/Chồng",
                            "relationType": "spouse",
                            "bucket": 1,
                            "allowsShare": True,
                            "removable": False,
                        },
                    ],
                },
                "updatedAt": "2026-06-23T02:30:00.000Z",
            },
        })

        class _FakeQuery:
            def __init__(self, *, first_item=None, all_items=None):
                self._first_item = first_item
                self._all_items = all_items or []

            def filter(self, *_args, **_kwargs):
                return self

            def first(self):
                return self._first_item

            def all(self):
                return self._all_items

        class _FakeDb:
            def __init__(self, stored_case, customer_rows):
                self.stored_case = stored_case
                self.customer_rows = customer_rows
                self.committed = False

            def query(self, model):
                if model is InheritanceCase:
                    return _FakeQuery(first_item=self.stored_case)
                if model is Customer:
                    return _FakeQuery(all_items=self.customer_rows)
                raise AssertionError(f"Unexpected model query: {model}")

            def commit(self):
                self.committed = True

        fake_db = _FakeDb(case, customers)

        with patch("routers.cases._replace_case_participants", lambda *_args, **_kwargs: None):
            result = update_diagram(
                cid=901,
                case_state_json=submitted_case_state,
                diagram_payload="",
                engine_state_json="",
                db=fake_db,
            )

        saved_case_state = json.loads(result["case_state_json"])
        saved_assignments = saved_case_state["diagram"]["assignments"]
        saved_nodes = saved_case_state["diagram"]["engineState"]["nodes"]
        self.assertTrue(fake_db.committed)
        self.assertEqual(saved_assignments, {"owner": "1"})
        self.assertEqual(saved_nodes[1]["id"], "spouse")
        self.assertIsNone(saved_nodes[1].get("personId"))
        self.assertEqual(json.loads(case.engine_state_json)["nodes"][1]["id"], "spouse")

    def test_update_diagram_ignores_ghost_node_with_person_id(self):
        case = SimpleNamespace(
            id=91,
            is_locked=False,
            nguoi_chet_id=1,
            case_state_json=json.dumps({
                "schemaVersion": 1,
                "stage": [
                    {"id": "1", "ho_ten": "Nguoi chet"},
                    {"id": "2", "ho_ten": "Nguoi dang o ghost"},
                ],
                "diagram": {"assignments": {}, "engineState": {"nodes": []}},
            }),
            engine_state_json=None,
        )
        customers = [_customer(1, "Nguoi chet"), _customer(2, "Nguoi dang o ghost")]
        submitted_case_state = json.dumps({
            "schemaVersion": 1,
            "stage": [
                {"id": "1", "ho_ten": "Nguoi chet"},
                {"id": "2", "ho_ten": "Nguoi dang o ghost"},
            ],
            "diagram": {
                "assignments": {"ghost_sibling_owner": "2"},
                "engineState": {
                    "nodes": [
                        {
                            "id": "ghost_sibling_owner",
                            "kind": "ghost",
                            "role": "Anh/Chị/Em",
                            "relationType": "ghostSibling",
                            "personId": "2",
                            "ghostAction": "addSibling",
                        },
                    ],
                },
                "updatedAt": "2026-06-22T13:00:00.000Z",
            },
        })

        class _FakeQuery:
            def __init__(self, *, first_item=None, all_items=None):
                self._first_item = first_item
                self._all_items = all_items or []

            def filter(self, *_args, **_kwargs):
                return self

            def first(self):
                return self._first_item

            def all(self):
                return self._all_items

        class _FakeDb:
            def __init__(self, stored_case, customer_rows):
                self.stored_case = stored_case
                self.customer_rows = customer_rows
                self.committed = False

            def query(self, model):
                if model is InheritanceCase:
                    return _FakeQuery(first_item=self.stored_case)
                if model is Customer:
                    return _FakeQuery(all_items=self.customer_rows)
                raise AssertionError(f"Unexpected model query: {model}")

            def commit(self):
                self.committed = True

        fake_db = _FakeDb(case, customers)
        captured = {}

        def _capture_replace(_db, case_id, participants):
            captured["case_id"] = case_id
            captured["participant_ids"] = [p.customer_id for p in participants]

        with patch("routers.cases._replace_case_participants", _capture_replace):
            result = update_diagram(
                cid=91,
                case_state_json=submitted_case_state,
                diagram_payload="",
                engine_state_json="",
                db=fake_db,
            )

        saved_case_state = json.loads(result["case_state_json"])
        self.assertTrue(fake_db.committed)
        self.assertEqual(captured["case_id"], 91)
        self.assertEqual(captured["participant_ids"], [])
        self.assertEqual(saved_case_state["diagram"]["assignments"], {})
        self.assertEqual(json.loads(case.engine_state_json)["nodes"], [])

    def test_update_diagram_prunes_duplicate_active_person_nodes(self):
        case = SimpleNamespace(
            id=92,
            is_locked=False,
            nguoi_chet_id=1,
            case_state_json=json.dumps({
                "schemaVersion": 1,
                "stage": [
                    {"id": "1", "ho_ten": "Nguoi chet"},
                    {"id": "2", "ho_ten": "Nguoi bi duplicate"},
                ],
                "diagram": {"assignments": {}, "engineState": {"nodes": []}},
            }),
            engine_state_json=None,
        )
        customers = [_customer(1, "Nguoi chet"), _customer(2, "Nguoi bi duplicate")]
        submitted_case_state = json.dumps({
            "schemaVersion": 1,
            "stage": [
                {"id": "1", "ho_ten": "Nguoi chet"},
                {"id": "2", "ho_ten": "Nguoi bi duplicate"},
            ],
            "diagram": {
                "assignments": {
                    "child_2": "2",
                    "grandchild_dup": "2",
                },
                "engineState": {
                    "nodes": [
                        {
                            "id": "child_2",
                            "kind": "person",
                            "role": "Con",
                            "relationType": "child",
                            "personId": "2",
                        },
                        {
                            "id": "grandchild_dup",
                            "kind": "person",
                            "role": "Cháu",
                            "relationType": "grandchild",
                            "personId": "2",
                            "parentPersonId": "2",
                            "parentSlotId": "child_2",
                        },
                    ],
                },
                "updatedAt": "2026-06-22T14:00:00.000Z",
            },
        })

        class _FakeQuery:
            def __init__(self, *, first_item=None, all_items=None):
                self._first_item = first_item
                self._all_items = all_items or []

            def filter(self, *_args, **_kwargs):
                return self

            def first(self):
                return self._first_item

            def all(self):
                return self._all_items

        class _FakeDb:
            def __init__(self, stored_case, customer_rows):
                self.stored_case = stored_case
                self.customer_rows = customer_rows
                self.committed = False

            def query(self, model):
                if model is InheritanceCase:
                    return _FakeQuery(first_item=self.stored_case)
                if model is Customer:
                    return _FakeQuery(all_items=self.customer_rows)
                raise AssertionError(f"Unexpected model query: {model}")

            def commit(self):
                self.committed = True

        fake_db = _FakeDb(case, customers)
        captured = {}

        def _capture_replace(_db, case_id, participants):
            captured["case_id"] = case_id
            captured["participant_ids"] = [p.customer_id for p in participants]

        with patch("routers.cases._replace_case_participants", _capture_replace):
            result = update_diagram(
                cid=92,
                case_state_json=submitted_case_state,
                diagram_payload="",
                engine_state_json="",
                db=fake_db,
            )

        self.assertNotIsInstance(result, JSONResponse)
        saved_case_state = json.loads(result["case_state_json"])
        self.assertTrue(fake_db.committed)
        self.assertEqual(captured["case_id"], 92)
        self.assertEqual(captured["participant_ids"], [2])
        self.assertEqual(saved_case_state["diagram"]["assignments"], {"child_2": "2"})
        self.assertEqual(
            [node["id"] for node in saved_case_state["diagram"]["engineState"]["nodes"]],
            ["child_2"],
        )

    def test_update_diagram_prefers_root_tree_node_over_later_branch_duplicate(self):
        case = SimpleNamespace(
            id=93,
            is_locked=False,
            nguoi_chet_id=1,
            case_state_json=json.dumps({
                "schemaVersion": 1,
                "stage": [
                    {"id": "1", "ho_ten": "Nguoi chet"},
                    {"id": "2", "ho_ten": "Nguoi can giu node goc"},
                    {"id": "3", "ho_ten": "Nguoi neo nhanh"},
                ],
                "diagram": {"assignments": {}, "engineState": {"nodes": []}},
            }),
            engine_state_json=None,
        )
        customers = [
            _customer(1, "Nguoi chet"),
            _customer(2, "Nguoi can giu node goc"),
            _customer(3, "Nguoi neo nhanh"),
        ]
        submitted_case_state = json.dumps({
            "schemaVersion": 1,
            "stage": [
                {"id": "1", "ho_ten": "Nguoi chet"},
                {"id": "2", "ho_ten": "Nguoi can giu node goc"},
                {"id": "3", "ho_ten": "Nguoi neo nhanh"},
            ],
            "diagram": {
                "assignments": {
                    "child_anchor": "3",
                    "grandchild_dup": "2",
                    "child_2": "2",
                },
                "engineState": {
                    "nodes": [
                        {
                            "id": "child_anchor",
                            "kind": "person",
                            "role": "Con",
                            "relationType": "child",
                            "personId": "3",
                            "parentSlotId": "owner",
                            "sourceId": "owner",
                            "familyGroupId": "ownerSpouse",
                        },
                        {
                            "id": "grandchild_dup",
                            "kind": "person",
                            "role": "Cháu",
                            "relationType": "grandchild",
                            "personId": "2",
                            "parentPersonId": "3",
                            "parentSlotId": "child_anchor",
                        },
                        {
                            "id": "child_2",
                            "kind": "person",
                            "role": "Con",
                            "relationType": "child",
                            "personId": "2",
                            "parentSlotId": "owner",
                            "sourceId": "owner",
                            "familyGroupId": "ownerSpouse",
                        },
                    ],
                },
                "updatedAt": "2026-06-22T15:00:00.000Z",
            },
        })

        class _FakeQuery:
            def __init__(self, *, first_item=None, all_items=None):
                self._first_item = first_item
                self._all_items = all_items or []

            def filter(self, *_args, **_kwargs):
                return self

            def first(self):
                return self._first_item

            def all(self):
                return self._all_items

        class _FakeDb:
            def __init__(self, stored_case, customer_rows):
                self.stored_case = stored_case
                self.customer_rows = customer_rows
                self.committed = False

            def query(self, model):
                if model is InheritanceCase:
                    return _FakeQuery(first_item=self.stored_case)
                if model is Customer:
                    return _FakeQuery(all_items=self.customer_rows)
                raise AssertionError(f"Unexpected model query: {model}")

            def commit(self):
                self.committed = True

        fake_db = _FakeDb(case, customers)
        captured = {}

        def _capture_replace(_db, case_id, participants):
            captured["case_id"] = case_id
            captured["participant_ids"] = [p.customer_id for p in participants]

        with patch("routers.cases._replace_case_participants", _capture_replace):
            result = update_diagram(
                cid=93,
                case_state_json=submitted_case_state,
                diagram_payload="",
                engine_state_json="",
                db=fake_db,
            )

        saved_case_state = json.loads(result["case_state_json"])
        self.assertTrue(fake_db.committed)
        self.assertEqual(captured["case_id"], 93)
        self.assertEqual(captured["participant_ids"], [3, 2])
        self.assertEqual(saved_case_state["diagram"]["assignments"], {"child_anchor": "3", "child_2": "2"})
        self.assertEqual(
            [node["id"] for node in saved_case_state["diagram"]["engineState"]["nodes"]],
            ["child_anchor", "child_2"],
        )

    def test_update_diagram_drops_legacy_flow_from_metadata(self):
        case = SimpleNamespace(
            id=94,
            is_locked=False,
            nguoi_chet_id=1,
            case_state_json=json.dumps({
                "schemaVersion": 1,
                "stage": [
                    {"id": "1", "ho_ten": "Nguoi chet"},
                    {"id": "2", "ho_ten": "Nguoi duoc reuse"},
                ],
                "diagram": {"assignments": {}, "engineState": {"nodes": []}},
            }),
            engine_state_json=None,
        )
        customers = [_customer(1, "Nguoi chet"), _customer(2, "Nguoi duoc reuse")]
        submitted_case_state = json.dumps({
            "schemaVersion": 1,
            "stage": [
                {"id": "1", "ho_ten": "Nguoi chet"},
                {"id": "2", "ho_ten": "Nguoi duoc reuse"},
            ],
            "diagram": {
                "assignments": {"child_2": "2"},
                "engineState": {
                    "nodes": [
                        {
                            "id": "child_2",
                            "kind": "person",
                            "role": "Con",
                            "relationType": "child",
                            "personId": "2",
                            "parentSlotId": "owner",
                            "sourceId": "owner",
                            "familyGroupId": "ownerSpouse",
                            "flowFrom": ["owner", "spouse_mother"],
                        },
                    ],
                },
                "updatedAt": "2026-06-22T16:00:00.000Z",
            },
        })

        class _FakeQuery:
            def __init__(self, *, first_item=None, all_items=None):
                self._first_item = first_item
                self._all_items = all_items or []

            def filter(self, *_args, **_kwargs):
                return self

            def first(self):
                return self._first_item

            def all(self):
                return self._all_items

        class _FakeDb:
            def __init__(self, stored_case, customer_rows):
                self.stored_case = stored_case
                self.customer_rows = customer_rows
                self.committed = False

            def query(self, model):
                if model is InheritanceCase:
                    return _FakeQuery(first_item=self.stored_case)
                if model is Customer:
                    return _FakeQuery(all_items=self.customer_rows)
                raise AssertionError(f"Unexpected model query: {model}")

            def commit(self):
                self.committed = True

        fake_db = _FakeDb(case, customers)
        captured = {}

        def _capture_replace(_db, case_id, participants):
            captured["case_id"] = case_id
            captured["participant_ids"] = [p.customer_id for p in participants]

        with patch("routers.cases._replace_case_participants", _capture_replace):
            result = update_diagram(
                cid=94,
                case_state_json=submitted_case_state,
                diagram_payload="",
                engine_state_json="",
                db=fake_db,
            )

        saved_case_state = json.loads(result["case_state_json"])
        self.assertTrue(fake_db.committed)
        self.assertEqual(captured["case_id"], 94)
        self.assertEqual(captured["participant_ids"], [2])
        self.assertNotIn("flowFrom", saved_case_state["diagram"]["engineState"]["nodes"][0])
        self.assertNotIn("flowFrom", json.loads(case.engine_state_json)["nodes"][0])

    def test_update_diagram_drops_duplicate_legacy_flow_metadata(self):
        case = SimpleNamespace(
            id=95,
            is_locked=False,
            nguoi_chet_id=1,
            case_state_json=json.dumps({
                "schemaVersion": 1,
                "stage": [
                    {"id": "1", "ho_ten": "Nguoi chet"},
                    {"id": "2", "ho_ten": "Nguoi duoc giu node canonical"},
                    {"id": "3", "ho_ten": "Nguoi neo nhanh"},
                ],
                "diagram": {"assignments": {}, "engineState": {"nodes": []}},
            }),
            engine_state_json=None,
        )
        customers = [
            _customer(1, "Nguoi chet"),
            _customer(2, "Nguoi duoc giu node canonical"),
            _customer(3, "Nguoi neo nhanh"),
        ]
        submitted_case_state = json.dumps({
            "schemaVersion": 1,
            "stage": [
                {"id": "1", "ho_ten": "Nguoi chet"},
                {"id": "2", "ho_ten": "Nguoi duoc giu node canonical"},
                {"id": "3", "ho_ten": "Nguoi neo nhanh"},
            ],
            "diagram": {
                "assignments": {
                    "child_anchor": "3",
                    "grandchild_dup": "2",
                    "child_2": "2",
                },
                "engineState": {
                    "nodes": [
                        {
                            "id": "child_anchor",
                            "kind": "person",
                            "role": "Con",
                            "relationType": "child",
                            "personId": "3",
                            "parentSlotId": "owner",
                            "sourceId": "owner",
                            "familyGroupId": "ownerSpouse",
                        },
                        {
                            "id": "grandchild_dup",
                            "kind": "person",
                            "role": "ChÃ¡u",
                            "relationType": "grandchild",
                            "personId": "2",
                            "parentPersonId": "3",
                            "parentSlotId": "child_anchor",
                            "flowFrom": ["child_anchor", "spouse_mother"],
                        },
                        {
                            "id": "child_2",
                            "kind": "person",
                            "role": "Con",
                            "relationType": "child",
                            "personId": "2",
                            "parentSlotId": "owner",
                            "sourceId": "owner",
                            "familyGroupId": "ownerSpouse",
                            "flowFrom": ["owner"],
                        },
                    ],
                },
                "updatedAt": "2026-06-22T17:00:00.000Z",
            },
        })

        class _FakeQuery:
            def __init__(self, *, first_item=None, all_items=None):
                self._first_item = first_item
                self._all_items = all_items or []

            def filter(self, *_args, **_kwargs):
                return self

            def first(self):
                return self._first_item

            def all(self):
                return self._all_items

        class _FakeDb:
            def __init__(self, stored_case, customer_rows):
                self.stored_case = stored_case
                self.customer_rows = customer_rows
                self.committed = False

            def query(self, model):
                if model is InheritanceCase:
                    return _FakeQuery(first_item=self.stored_case)
                if model is Customer:
                    return _FakeQuery(all_items=self.customer_rows)
                raise AssertionError(f"Unexpected model query: {model}")

            def commit(self):
                self.committed = True

        fake_db = _FakeDb(case, customers)
        captured = {}

        def _capture_replace(_db, case_id, participants):
            captured["case_id"] = case_id
            captured["participant_ids"] = [p.customer_id for p in participants]

        with patch("routers.cases._replace_case_participants", _capture_replace):
            result = update_diagram(
                cid=95,
                case_state_json=submitted_case_state,
                diagram_payload="",
                engine_state_json="",
                db=fake_db,
            )

        saved_case_state = json.loads(result["case_state_json"])
        self.assertTrue(fake_db.committed)
        self.assertEqual(captured["case_id"], 95)
        self.assertEqual(captured["participant_ids"], [3, 2])
        self.assertEqual(
            [node["id"] for node in saved_case_state["diagram"]["engineState"]["nodes"]],
            ["child_anchor", "child_2"],
        )
        self.assertNotIn("flowFrom", saved_case_state["diagram"]["engineState"]["nodes"][1])
        self.assertNotIn("flowFrom", json.loads(case.engine_state_json)["nodes"][1])

    def test_update_diagram_prunes_empty_slot_attached_to_removed_duplicate_branch(self):
        case = SimpleNamespace(
            id=95_1,
            is_locked=False,
            nguoi_chet_id=1,
            case_state_json=json.dumps({
                "schemaVersion": 1,
                "stage": [
                    {"id": "1", "ho_ten": "Nguoi chet"},
                    {"id": "2", "ho_ten": "Nguoi bi duplicate"},
                    {"id": "3", "ho_ten": "Nguoi neo nhanh"},
                ],
                "diagram": {"assignments": {}, "engineState": {"nodes": []}},
            }),
            engine_state_json=None,
        )
        customers = [
            _customer(1, "Nguoi chet"),
            _customer(2, "Nguoi bi duplicate"),
            _customer(3, "Nguoi neo nhanh"),
        ]
        submitted_case_state = json.dumps({
            "schemaVersion": 1,
            "stage": [
                {"id": "1", "ho_ten": "Nguoi chet"},
                {"id": "2", "ho_ten": "Nguoi bi duplicate"},
                {"id": "3", "ho_ten": "Nguoi neo nhanh"},
            ],
            "diagram": {
                "assignments": {
                    "child_anchor": "3",
                    "grandchild_dup": "2",
                    "child_2": "2",
                },
                "engineState": {
                    "nodes": [
                        {
                            "id": "child_anchor",
                            "kind": "person",
                            "role": "Con",
                            "relationType": "child",
                            "personId": "3",
                            "parentSlotId": "owner",
                            "sourceId": "owner",
                            "familyGroupId": "ownerSpouse",
                            "bucket": 1,
                            "allowsShare": True,
                            "removable": True,
                        },
                        {
                            "id": "grandchild_dup",
                            "kind": "person",
                            "role": "Chau",
                            "relationType": "grandchild",
                            "personId": "2",
                            "parentPersonId": "3",
                            "parentSlotId": "child_anchor",
                            "sourceId": "child_anchor",
                            "familyGroupId": "branch-3",
                            "bucket": 4,
                            "allowsShare": True,
                            "removable": True,
                        },
                        {
                            "id": "child_2",
                            "kind": "person",
                            "role": "Con",
                            "relationType": "child",
                            "personId": "2",
                            "parentSlotId": "owner",
                            "sourceId": "owner",
                            "familyGroupId": "ownerSpouse",
                            "bucket": 1,
                            "allowsShare": True,
                            "removable": True,
                        },
                        {
                            "id": "branch_spouse_orphan",
                            "kind": "person",
                            "role": "Con_dau_re",
                            "relationType": "branchSpouse",
                            "parentPersonId": "2",
                            "parentSlotId": "grandchild_dup",
                            "sourceId": "grandchild_dup",
                            "familyGroupId": "branch-3",
                            "bucket": 4,
                            "allowsShare": True,
                            "removable": True,
                        },
                    ],
                    "edges": [
                        {
                            "id": "orphan-edge",
                            "source": "child_anchor",
                            "target": "branch_spouse_orphan",
                            "kind": "kinship",
                        },
                    ],
                },
                "updatedAt": "2026-06-23T03:00:00.000Z",
            },
        })

        class _FakeQuery:
            def __init__(self, *, first_item=None, all_items=None):
                self._first_item = first_item
                self._all_items = all_items or []

            def filter(self, *_args, **_kwargs):
                return self

            def first(self):
                return self._first_item

            def all(self):
                return self._all_items

        class _FakeDb:
            def __init__(self, stored_case, customer_rows):
                self.stored_case = stored_case
                self.customer_rows = customer_rows
                self.committed = False

            def query(self, model):
                if model is InheritanceCase:
                    return _FakeQuery(first_item=self.stored_case)
                if model is Customer:
                    return _FakeQuery(all_items=self.customer_rows)
                raise AssertionError(f"Unexpected model query: {model}")

            def commit(self):
                self.committed = True

        fake_db = _FakeDb(case, customers)
        captured = {}

        def _capture_replace(_db, case_id, participants):
            captured["case_id"] = case_id
            captured["participant_ids"] = [p.customer_id for p in participants]

        with patch("routers.cases._replace_case_participants", _capture_replace):
            result = update_diagram(
                cid=95_1,
                case_state_json=submitted_case_state,
                diagram_payload="",
                engine_state_json="",
                db=fake_db,
            )

        saved_case_state = json.loads(result["case_state_json"])
        saved_nodes = saved_case_state["diagram"]["engineState"]["nodes"]
        saved_assignments = saved_case_state["diagram"]["assignments"]
        saved_node_ids = [node["id"] for node in saved_nodes]
        self.assertTrue(fake_db.committed)
        self.assertEqual(captured["case_id"], 95_1)
        self.assertEqual(captured["participant_ids"], [3, 2])
        self.assertEqual(saved_assignments, {"child_anchor": "3", "child_2": "2"})
        self.assertEqual(saved_node_ids, ["child_anchor", "child_2"])
        self.assertNotIn("grandchild_dup", saved_node_ids)
        self.assertNotIn("branch_spouse_orphan", saved_node_ids)
        self.assertNotIn("edges", saved_case_state["diagram"]["engineState"])
        self.assertNotIn(
            "branch_spouse_orphan",
            [node["id"] for node in json.loads(case.engine_state_json)["nodes"]],
        )
        self.assertNotIn("edges", json.loads(case.engine_state_json))
        self.assertNotIn("edges", json.loads(result["diagram_payload"]))

    def test_update_diagram_drops_legacy_edges_even_when_endpoints_are_valid(self):
        case = SimpleNamespace(
            id=96,
            is_locked=False,
            nguoi_chet_id=1,
            case_state_json=json.dumps({
                "schemaVersion": 1,
                "stage": [
                    {"id": "1", "ho_ten": "Nguoi chet"},
                    {"id": "2", "ho_ten": "Nguoi duoc giu node canonical"},
                    {"id": "3", "ho_ten": "Nguoi neo nhanh"},
                ],
                "diagram": {"assignments": {}, "engineState": {"nodes": []}},
            }),
            engine_state_json=None,
        )
        customers = [
            _customer(1, "Nguoi chet"),
            _customer(2, "Nguoi duoc giu node canonical"),
            _customer(3, "Nguoi neo nhanh"),
        ]
        submitted_case_state = json.dumps({
            "schemaVersion": 1,
            "stage": [
                {"id": "1", "ho_ten": "Nguoi chet"},
                {"id": "2", "ho_ten": "Nguoi duoc giu node canonical"},
                {"id": "3", "ho_ten": "Nguoi neo nhanh"},
            ],
            "diagram": {
                "assignments": {
                    "child_anchor": "3",
                    "grandchild_dup": "2",
                    "child_2": "2",
                },
                "engineState": {
                    "nodes": [
                        {
                            "id": "child_anchor",
                            "kind": "person",
                            "role": "Con",
                            "relationType": "child",
                            "personId": "3",
                            "parentSlotId": "owner",
                            "sourceId": "owner",
                            "familyGroupId": "ownerSpouse",
                        },
                        {
                            "id": "grandchild_dup",
                            "kind": "person",
                            "role": "ChÃ¡u",
                            "relationType": "grandchild",
                            "personId": "2",
                            "parentPersonId": "3",
                            "parentSlotId": "child_anchor",
                        },
                        {
                            "id": "child_2",
                            "kind": "person",
                            "role": "Con",
                            "relationType": "child",
                            "personId": "2",
                            "parentSlotId": "owner",
                            "sourceId": "owner",
                            "familyGroupId": "ownerSpouse",
                        },
                    ],
                    "edges": [
                        {
                            "id": "keep-edge",
                            "source": "child_anchor",
                            "target": "child_2",
                            "kind": "kinship",
                            "label": "Nhanh hop le",
                            "markerEnd": {"type": "arrowclosed"},
                            "style": {"strokeWidth": 2},
                        },
                        {"id": "drop-edge", "source": "child_anchor", "target": "grandchild_dup", "kind": "kinship"},
                    ],
                },
                "updatedAt": "2026-06-22T18:00:00.000Z",
            },
        })

        class _FakeQuery:
            def __init__(self, *, first_item=None, all_items=None):
                self._first_item = first_item
                self._all_items = all_items or []

            def filter(self, *_args, **_kwargs):
                return self

            def first(self):
                return self._first_item

            def all(self):
                return self._all_items

        class _FakeDb:
            def __init__(self, stored_case, customer_rows):
                self.stored_case = stored_case
                self.customer_rows = customer_rows
                self.committed = False

            def query(self, model):
                if model is InheritanceCase:
                    return _FakeQuery(first_item=self.stored_case)
                if model is Customer:
                    return _FakeQuery(all_items=self.customer_rows)
                raise AssertionError(f"Unexpected model query: {model}")

            def commit(self):
                self.committed = True

        fake_db = _FakeDb(case, customers)
        captured = {}

        def _capture_replace(_db, case_id, participants):
            captured["case_id"] = case_id
            captured["participant_ids"] = [p.customer_id for p in participants]

        with patch("routers.cases._replace_case_participants", _capture_replace):
            result = update_diagram(
                cid=96,
                case_state_json=submitted_case_state,
                diagram_payload="",
                engine_state_json="",
                db=fake_db,
            )

        saved_case_state = json.loads(result["case_state_json"])
        self.assertTrue(fake_db.committed)
        self.assertEqual(captured["case_id"], 96)
        self.assertEqual(captured["participant_ids"], [3, 2])
        self.assertNotIn("edges", saved_case_state["diagram"]["engineState"])
        self.assertNotIn("edges", json.loads(case.engine_state_json))
        self.assertNotIn("edges", json.loads(result["diagram_payload"]))

    def test_update_diagram_drops_legacy_allocations_warnings_and_trace(self):
        case = SimpleNamespace(
            id=97,
            is_locked=False,
            nguoi_chet_id=1,
            case_state_json=json.dumps({
                "schemaVersion": 1,
                "stage": [
                    {"id": "1", "ho_ten": "Nguoi chet"},
                    {"id": "2", "ho_ten": "Con hop le"},
                ],
                "diagram": {"assignments": {}, "engineState": {"nodes": []}},
            }),
            engine_state_json=None,
        )
        customers = [_customer(1, "Nguoi chet"), _customer(2, "Con hop le")]
        submitted_case_state = json.dumps({
            "schemaVersion": 1,
            "stage": [
                {"id": "1", "ho_ten": "Nguoi chet"},
                {"id": "2", "ho_ten": "Con hop le"},
            ],
            "diagram": {
                "assignments": {"child_2": "2"},
                "engineState": {
                    "nodes": [
                        {
                            "id": "child_2",
                            "kind": "person",
                            "role": "Con",
                            "relationType": "child",
                            "personId": "2",
                            "parentSlotId": "owner",
                            "sourceId": "owner",
                            "familyGroupId": "ownerSpouse",
                        },
                    ],
                    "allocations": {
                        "2": {"baseShare": "1/2", "displayPercent": "50.00"},
                    },
                    "warnings": [
                        {"code": "demo_warning", "message": "Warning can giu lai"},
                    ],
                    "trace": [
                        {"type": "flow", "from": "1", "to": "2", "fraction": "1/2"},
                    ],
                },
                "updatedAt": "2026-06-22T19:00:00.000Z",
            },
        })

        class _FakeQuery:
            def __init__(self, *, first_item=None, all_items=None):
                self._first_item = first_item
                self._all_items = all_items or []

            def filter(self, *_args, **_kwargs):
                return self

            def first(self):
                return self._first_item

            def all(self):
                return self._all_items

        class _FakeDb:
            def __init__(self, stored_case, customer_rows):
                self.stored_case = stored_case
                self.customer_rows = customer_rows
                self.committed = False

            def query(self, model):
                if model is InheritanceCase:
                    return _FakeQuery(first_item=self.stored_case)
                if model is Customer:
                    return _FakeQuery(all_items=self.customer_rows)
                raise AssertionError(f"Unexpected model query: {model}")

            def commit(self):
                self.committed = True

        fake_db = _FakeDb(case, customers)
        captured = {}

        def _capture_replace(_db, case_id, participants):
            captured["case_id"] = case_id
            captured["participant_ids"] = [p.customer_id for p in participants]

        with patch("routers.cases._replace_case_participants", _capture_replace):
            result = update_diagram(
                cid=97,
                case_state_json=submitted_case_state,
                diagram_payload="",
                engine_state_json="",
                db=fake_db,
            )

        saved_case_state = json.loads(result["case_state_json"])
        saved_engine_state = saved_case_state["diagram"]["engineState"]
        self.assertTrue(fake_db.committed)
        self.assertEqual(captured["case_id"], 97)
        self.assertEqual(captured["participant_ids"], [2])
        for key in ("allocations", "warnings", "trace"):
            self.assertNotIn(key, saved_engine_state)
            self.assertNotIn(key, json.loads(case.engine_state_json))
            self.assertNotIn(key, json.loads(result["diagram_payload"]))

    def test_update_diagram_preserves_supplemental_render_metadata(self):
        case = SimpleNamespace(
            id=97_1,
            is_locked=False,
            nguoi_chet_id=1,
            case_state_json=json.dumps({
                "schemaVersion": 1,
                "stage": [
                    {"id": "1", "ho_ten": "Nguoi chet"},
                    {"id": "2", "ho_ten": "Con hop le"},
                ],
                "diagram": {"assignments": {}, "engineState": {"nodes": []}},
            }),
            engine_state_json=None,
        )
        customers = [_customer(1, "Nguoi chet"), _customer(2, "Con hop le")]
        submitted_case_state = json.dumps({
            "schemaVersion": 1,
            "stage": [
                {"id": "1", "ho_ten": "Nguoi chet"},
                {"id": "2", "ho_ten": "Con hop le"},
            ],
            "diagram": {
                "assignments": {"child_2": "2"},
                "engineState": {
                    "nodes": [
                        {
                            "id": "child_2",
                            "kind": "person",
                            "role": "Con",
                            "relationType": "child",
                            "personId": "2",
                            "parentSlotId": "owner",
                            "sourceId": "owner",
                            "familyGroupId": "ownerSpouse",
                        },
                    ],
                    "viewport": {"x": 120.5, "y": -32.25, "zoom": 0.85},
                    "layoutMeta": {
                        "laneOffsets": {"children": 240},
                        "collapsedBranches": ["child_2"],
                    },
                },
                "updatedAt": "2026-06-23T01:30:00.000Z",
            },
        })

        class _FakeQuery:
            def __init__(self, *, first_item=None, all_items=None):
                self._first_item = first_item
                self._all_items = all_items or []

            def filter(self, *_args, **_kwargs):
                return self

            def first(self):
                return self._first_item

            def all(self):
                return self._all_items

        class _FakeDb:
            def __init__(self, stored_case, customer_rows):
                self.stored_case = stored_case
                self.customer_rows = customer_rows
                self.committed = False

            def query(self, model):
                if model is InheritanceCase:
                    return _FakeQuery(first_item=self.stored_case)
                if model is Customer:
                    return _FakeQuery(all_items=self.customer_rows)
                raise AssertionError(f"Unexpected model query: {model}")

            def commit(self):
                self.committed = True

        fake_db = _FakeDb(case, customers)

        with patch("routers.cases._replace_case_participants", lambda *_args, **_kwargs: None):
            result = update_diagram(
                cid=971,
                case_state_json=submitted_case_state,
                diagram_payload="",
                engine_state_json="",
                db=fake_db,
            )

        saved_case_state = json.loads(result["case_state_json"])
        saved_engine_state = saved_case_state["diagram"]["engineState"]
        self.assertTrue(fake_db.committed)
        self.assertIn("viewport", saved_engine_state)
        self.assertIn("layoutMeta", saved_engine_state)
        self.assertEqual(saved_engine_state["viewport"]["zoom"], 0.85)
        self.assertEqual(saved_engine_state["layoutMeta"]["laneOffsets"]["children"], 240)
        self.assertEqual(saved_engine_state["layoutMeta"]["collapsedBranches"][0], "child_2")
        self.assertEqual(json.loads(case.engine_state_json)["viewport"]["x"], 120.5)
        self.assertEqual(json.loads(result["diagram_payload"])["viewport"]["zoom"], 0.85)
        self.assertEqual(json.loads(result["diagram_payload"])["layoutMeta"]["laneOffsets"]["children"], 240)
        self.assertEqual(json.loads(result["diagram_payload"])["layoutMeta"]["collapsedBranches"][0], "child_2")

    def test_update_diagram_preserves_empty_structural_slots_without_assigning_them(self):
        case = SimpleNamespace(
            id=98,
            is_locked=False,
            nguoi_chet_id=1,
            case_state_json=json.dumps({
                "schemaVersion": 1,
                "stage": [
                    {"id": "1", "ho_ten": "Nguoi chet"},
                    {"id": "2", "ho_ten": "Con hop le"},
                ],
                "diagram": {"assignments": {}, "engineState": {"nodes": []}},
            }),
            engine_state_json=None,
        )
        customers = [_customer(1, "Nguoi chet"), _customer(2, "Con hop le")]
        submitted_case_state = json.dumps({
            "schemaVersion": 1,
            "stage": [
                {"id": "1", "ho_ten": "Nguoi chet"},
                {"id": "2", "ho_ten": "Con hop le"},
            ],
            "diagram": {
                "assignments": {"child_2": "2"},
                "engineState": {
                    "nodes": [
                        {
                            "id": "owner",
                            "kind": "person",
                            "role": "Owner",
                            "relationType": "owner",
                            "personId": "1",
                            "bucket": 1,
                            "allowsShare": True,
                            "removable": False,
                        },
                        {
                            "id": "mother",
                            "kind": "person",
                            "role": "Mẹ",
                            "relationType": "parent",
                            "bucket": 0,
                            "allowsShare": True,
                            "removable": False,
                        },
                        {
                            "id": "child_2",
                            "kind": "person",
                            "role": "Con",
                            "relationType": "child",
                            "personId": "2",
                            "parentSlotId": "owner",
                            "sourceId": "owner",
                            "familyGroupId": "ownerSpouse",
                            "bucket": 2,
                            "allowsShare": True,
                            "removable": True,
                        },
                    ],
                },
                "updatedAt": "2026-06-22T20:00:00.000Z",
            },
        })

        class _FakeQuery:
            def __init__(self, *, first_item=None, all_items=None):
                self._first_item = first_item
                self._all_items = all_items or []

            def filter(self, *_args, **_kwargs):
                return self

            def first(self):
                return self._first_item

            def all(self):
                return self._all_items

        class _FakeDb:
            def __init__(self, stored_case, customer_rows):
                self.stored_case = stored_case
                self.customer_rows = customer_rows
                self.committed = False

            def query(self, model):
                if model is InheritanceCase:
                    return _FakeQuery(first_item=self.stored_case)
                if model is Customer:
                    return _FakeQuery(all_items=self.customer_rows)
                raise AssertionError(f"Unexpected model query: {model}")

            def commit(self):
                self.committed = True

        fake_db = _FakeDb(case, customers)
        captured = {}

        def _capture_replace(_db, case_id, participants):
            captured["case_id"] = case_id
            captured["participant_ids"] = [p.customer_id for p in participants]

        with patch("routers.cases._replace_case_participants", _capture_replace):
            result = update_diagram(
                cid=98,
                case_state_json=submitted_case_state,
                diagram_payload="",
                engine_state_json="",
                db=fake_db,
            )

        saved_case_state = json.loads(result["case_state_json"])
        saved_engine_nodes = saved_case_state["diagram"]["engineState"]["nodes"]
        saved_assignments = saved_case_state["diagram"]["assignments"]
        self.assertTrue(fake_db.committed)
        self.assertEqual(captured["case_id"], 98)
        self.assertEqual(captured["participant_ids"], [2])
        self.assertEqual(
            [node["id"] for node in saved_engine_nodes],
            ["owner", "mother", "child_2"],
        )
        self.assertNotIn("mother", saved_assignments)
        self.assertEqual(saved_assignments["child_2"], "2")
        self.assertEqual(saved_engine_nodes[1].get("personId"), None)
        self.assertEqual(json.loads(case.engine_state_json)["nodes"][1]["id"], "mother")

    def test_update_diagram_preserves_bucket_allows_share_and_removable_on_saved_nodes(self):
        case = SimpleNamespace(
            id=99,
            is_locked=False,
            nguoi_chet_id=1,
            case_state_json=json.dumps({
                "schemaVersion": 1,
                "stage": [
                    {"id": "1", "ho_ten": "Nguoi chet"},
                    {"id": "2", "ho_ten": "Con hop le"},
                ],
                "diagram": {"assignments": {}, "engineState": {"nodes": []}},
            }),
            engine_state_json=None,
        )
        customers = [_customer(1, "Nguoi chet"), _customer(2, "Con hop le")]
        submitted_case_state = json.dumps({
            "schemaVersion": 1,
            "stage": [
                {"id": "1", "ho_ten": "Nguoi chet"},
                {"id": "2", "ho_ten": "Con hop le"},
            ],
            "diagram": {
                "assignments": {"child_2": "2"},
                "engineState": {
                    "nodes": [
                        {
                            "id": "mother",
                            "kind": "person",
                            "role": "Mẹ",
                            "relationType": "parent",
                            "bucket": 0,
                            "allowsShare": True,
                            "removable": False,
                        },
                        {
                            "id": "child_2",
                            "kind": "person",
                            "role": "Con",
                            "relationType": "child",
                            "personId": "2",
                            "parentSlotId": "owner",
                            "sourceId": "owner",
                            "familyGroupId": "ownerSpouse",
                            "bucket": 2,
                            "allowsShare": True,
                            "removable": True,
                        },
                    ],
                },
                "updatedAt": "2026-06-22T21:00:00.000Z",
            },
        })

        class _FakeQuery:
            def __init__(self, *, first_item=None, all_items=None):
                self._first_item = first_item
                self._all_items = all_items or []

            def filter(self, *_args, **_kwargs):
                return self

            def first(self):
                return self._first_item

            def all(self):
                return self._all_items

        class _FakeDb:
            def __init__(self, stored_case, customer_rows):
                self.stored_case = stored_case
                self.customer_rows = customer_rows
                self.committed = False

            def query(self, model):
                if model is InheritanceCase:
                    return _FakeQuery(first_item=self.stored_case)
                if model is Customer:
                    return _FakeQuery(all_items=self.customer_rows)
                raise AssertionError(f"Unexpected model query: {model}")

            def commit(self):
                self.committed = True

        fake_db = _FakeDb(case, customers)

        with patch("routers.cases._replace_case_participants", lambda *_args, **_kwargs: None):
            result = update_diagram(
                cid=99,
                case_state_json=submitted_case_state,
                diagram_payload="",
                engine_state_json="",
                db=fake_db,
            )

        saved_nodes = json.loads(result["case_state_json"])["diagram"]["engineState"]["nodes"]
        self.assertTrue(fake_db.committed)
        self.assertEqual(saved_nodes[0]["id"], "mother")
        self.assertEqual(saved_nodes[0]["bucket"], 0)
        self.assertTrue(saved_nodes[0]["allowsShare"])
        self.assertFalse(saved_nodes[0]["removable"])
        self.assertEqual(saved_nodes[1]["id"], "child_2")
        self.assertEqual(saved_nodes[1]["bucket"], 2)
        self.assertTrue(saved_nodes[1]["allowsShare"])
        self.assertTrue(saved_nodes[1]["removable"])

    def test_update_diagram_preserves_empty_child_slot_with_owner_parent_link(self):
        case = SimpleNamespace(
            id=100,
            is_locked=False,
            nguoi_chet_id=1,
            case_state_json=json.dumps({
                "schemaVersion": 1,
                "stage": [
                    {"id": "1", "ho_ten": "Nguoi chet"},
                    {"id": "2", "ho_ten": "Con hop le"},
                ],
                "diagram": {"assignments": {}, "engineState": {"nodes": []}},
            }),
            engine_state_json=None,
        )
        customers = [_customer(1, "Nguoi chet"), _customer(2, "Con hop le")]
        submitted_case_state = json.dumps({
            "schemaVersion": 1,
            "stage": [
                {"id": "1", "ho_ten": "Nguoi chet"},
                {"id": "2", "ho_ten": "Con hop le"},
            ],
            "diagram": {
                "assignments": {"child_2": "2"},
                "engineState": {
                    "nodes": [
                        {
                            "id": "owner",
                            "kind": "person",
                            "role": "Owner",
                            "relationType": "owner",
                            "personId": "1",
                            "bucket": 1,
                            "allowsShare": True,
                            "removable": False,
                        },
                        {
                            "id": "child_empty",
                            "kind": "person",
                            "role": "Con",
                            "relationType": "child",
                            "parentSlotId": "owner",
                            "sourceId": "owner",
                            "familyGroupId": "ownerSpouse",
                            "bucket": 2,
                            "allowsShare": True,
                            "removable": True,
                        },
                        {
                            "id": "child_2",
                            "kind": "person",
                            "role": "Con",
                            "relationType": "child",
                            "personId": "2",
                            "parentSlotId": "owner",
                            "sourceId": "owner",
                            "familyGroupId": "ownerSpouse",
                            "bucket": 2,
                            "allowsShare": True,
                            "removable": True,
                        },
                    ],
                },
                "updatedAt": "2026-06-22T22:00:00.000Z",
            },
        })

        class _FakeQuery:
            def __init__(self, *, first_item=None, all_items=None):
                self._first_item = first_item
                self._all_items = all_items or []

            def filter(self, *_args, **_kwargs):
                return self

            def first(self):
                return self._first_item

            def all(self):
                return self._all_items

        class _FakeDb:
            def __init__(self, stored_case, customer_rows):
                self.stored_case = stored_case
                self.customer_rows = customer_rows
                self.committed = False

            def query(self, model):
                if model is InheritanceCase:
                    return _FakeQuery(first_item=self.stored_case)
                if model is Customer:
                    return _FakeQuery(all_items=self.customer_rows)
                raise AssertionError(f"Unexpected model query: {model}")

            def commit(self):
                self.committed = True

        fake_db = _FakeDb(case, customers)

        with patch("routers.cases._replace_case_participants", lambda *_args, **_kwargs: None):
            result = update_diagram(
                cid=100,
                case_state_json=submitted_case_state,
                diagram_payload="",
                engine_state_json="",
                db=fake_db,
            )

        saved_case_state = json.loads(result["case_state_json"])
        saved_nodes = saved_case_state["diagram"]["engineState"]["nodes"]
        saved_assignments = saved_case_state["diagram"]["assignments"]
        self.assertTrue(fake_db.committed)
        self.assertEqual(
            [node["id"] for node in saved_nodes],
            ["owner", "child_empty", "child_2"],
        )
        self.assertEqual(saved_nodes[1]["parentSlotId"], "owner")
        self.assertEqual(saved_nodes[1]["sourceId"], "owner")
        self.assertNotIn("child_empty", saved_assignments)
        self.assertEqual(saved_assignments["child_2"], "2")

    def test_update_diagram_preserves_empty_sibling_slot_with_live_parent_person(self):
        case = SimpleNamespace(
            id=101,
            is_locked=False,
            nguoi_chet_id=1,
            case_state_json=json.dumps({
                "schemaVersion": 1,
                "stage": [
                    {"id": "1", "ho_ten": "Nguoi chet"},
                    {"id": "3", "ho_ten": "Cha ruot"},
                ],
                "diagram": {"assignments": {}, "engineState": {"nodes": []}},
            }),
            engine_state_json=None,
        )
        customers = [_customer(1, "Nguoi chet"), _customer(3, "Cha ruot")]
        submitted_case_state = json.dumps({
            "schemaVersion": 1,
            "stage": [
                {"id": "1", "ho_ten": "Nguoi chet"},
                {"id": "3", "ho_ten": "Cha ruot"},
            ],
            "diagram": {
                "assignments": {"father": "3"},
                "engineState": {
                    "nodes": [
                        {
                            "id": "owner",
                            "kind": "person",
                            "role": "Owner",
                            "relationType": "owner",
                            "personId": "1",
                            "bucket": 1,
                            "allowsShare": True,
                            "removable": False,
                        },
                        {
                            "id": "father",
                            "kind": "person",
                            "role": "Cha",
                            "relationType": "parent",
                            "personId": "3",
                            "bucket": 0,
                            "allowsShare": True,
                            "removable": False,
                        },
                        {
                            "id": "sibling_empty",
                            "kind": "person",
                            "role": "Anh/Chị/Em",
                            "relationType": "sibling",
                            "parentSlotId": "father",
                            "parentPersonId": "3",
                            "sourceId": "father",
                            "familyGroupId": "birthParents",
                            "bucket": 1,
                            "allowsShare": True,
                            "removable": True,
                        },
                    ],
                },
                "updatedAt": "2026-06-22T23:00:00.000Z",
            },
        })

        class _FakeQuery:
            def __init__(self, *, first_item=None, all_items=None):
                self._first_item = first_item
                self._all_items = all_items or []

            def filter(self, *_args, **_kwargs):
                return self

            def first(self):
                return self._first_item

            def all(self):
                return self._all_items

        class _FakeDb:
            def __init__(self, stored_case, customer_rows):
                self.stored_case = stored_case
                self.customer_rows = customer_rows
                self.committed = False

            def query(self, model):
                if model is InheritanceCase:
                    return _FakeQuery(first_item=self.stored_case)
                if model is Customer:
                    return _FakeQuery(all_items=self.customer_rows)
                raise AssertionError(f"Unexpected model query: {model}")

            def commit(self):
                self.committed = True

        fake_db = _FakeDb(case, customers)

        with patch("routers.cases._replace_case_participants", lambda *_args, **_kwargs: None):
            result = update_diagram(
                cid=101,
                case_state_json=submitted_case_state,
                diagram_payload="",
                engine_state_json="",
                db=fake_db,
            )

        saved_case_state = json.loads(result["case_state_json"])
        saved_nodes = saved_case_state["diagram"]["engineState"]["nodes"]
        saved_assignments = saved_case_state["diagram"]["assignments"]
        saved_node_ids = [node["id"] for node in saved_nodes]
        self.assertTrue(fake_db.committed)
        self.assertIn("father", saved_node_ids)
        self.assertIn("sibling_empty", saved_node_ids)
        sibling_node = next(node for node in saved_nodes if node["id"] == "sibling_empty")
        self.assertEqual(sibling_node["parentSlotId"], "father")
        self.assertEqual(sibling_node["parentPersonId"], "3")
        self.assertEqual(sibling_node["sourceId"], "father")
        self.assertNotIn("sibling_empty", saved_assignments)
        self.assertEqual(saved_assignments["father"], "3")

    def test_update_diagram_preserves_empty_grandchild_slot_with_live_parent_branch(self):
        case = SimpleNamespace(
            id=102,
            is_locked=False,
            nguoi_chet_id=1,
            case_state_json=json.dumps({
                "schemaVersion": 1,
                "stage": [
                    {"id": "1", "ho_ten": "Nguoi chet"},
                    {"id": "2", "ho_ten": "Con ruot"},
                ],
                "diagram": {"assignments": {}, "engineState": {"nodes": []}},
            }),
            engine_state_json=None,
        )
        customers = [_customer(1, "Nguoi chet"), _customer(2, "Con ruot")]
        submitted_case_state = json.dumps({
            "schemaVersion": 1,
            "stage": [
                {"id": "1", "ho_ten": "Nguoi chet"},
                {"id": "2", "ho_ten": "Con ruot"},
            ],
            "diagram": {
                "assignments": {"child_anchor": "2"},
                "engineState": {
                    "nodes": [
                        {
                            "id": "owner",
                            "kind": "person",
                            "role": "Owner",
                            "relationType": "owner",
                            "personId": "1",
                            "bucket": 1,
                            "allowsShare": True,
                            "removable": False,
                        },
                        {
                            "id": "child_anchor",
                            "kind": "person",
                            "role": "Con",
                            "relationType": "child",
                            "personId": "2",
                            "parentSlotId": "owner",
                            "parentPersonId": "1",
                            "sourceId": "owner",
                            "bucket": 1,
                            "allowsShare": True,
                            "removable": True,
                        },
                        {
                            "id": "grandchild_empty",
                            "kind": "person",
                            "role": "Cháu",
                            "relationType": "grandchild",
                            "parentSlotId": "child_anchor",
                            "parentPersonId": "2",
                            "sourceId": "child_anchor",
                            "familyGroupId": "branch-2",
                            "bucket": 4,
                            "allowsShare": True,
                            "removable": True,
                        },
                    ],
                },
                "updatedAt": "2026-06-22T23:30:00.000Z",
            },
        })

        class _FakeQuery:
            def __init__(self, *, first_item=None, all_items=None):
                self._first_item = first_item
                self._all_items = all_items or []

            def filter(self, *_args, **_kwargs):
                return self

            def first(self):
                return self._first_item

            def all(self):
                return self._all_items

        class _FakeDb:
            def __init__(self, stored_case, customer_rows):
                self.stored_case = stored_case
                self.customer_rows = customer_rows
                self.committed = False

            def query(self, model):
                if model is InheritanceCase:
                    return _FakeQuery(first_item=self.stored_case)
                if model is Customer:
                    return _FakeQuery(all_items=self.customer_rows)
                raise AssertionError(f"Unexpected model query: {model}")

            def commit(self):
                self.committed = True

        fake_db = _FakeDb(case, customers)

        with patch("routers.cases._replace_case_participants", lambda *_args, **_kwargs: None):
            result = update_diagram(
                cid=102,
                case_state_json=submitted_case_state,
                diagram_payload="",
                engine_state_json="",
                db=fake_db,
            )

        saved_case_state = json.loads(result["case_state_json"])
        saved_nodes = saved_case_state["diagram"]["engineState"]["nodes"]
        saved_assignments = saved_case_state["diagram"]["assignments"]
        saved_node_ids = [node["id"] for node in saved_nodes]
        self.assertTrue(fake_db.committed)
        self.assertIn("child_anchor", saved_node_ids)
        self.assertIn("grandchild_empty", saved_node_ids)
        grandchild_node = next(node for node in saved_nodes if node["id"] == "grandchild_empty")
        self.assertEqual(grandchild_node["parentSlotId"], "child_anchor")
        self.assertEqual(grandchild_node["parentPersonId"], "2")
        self.assertEqual(grandchild_node["sourceId"], "child_anchor")
        self.assertEqual(grandchild_node["bucket"], 4)
        self.assertNotIn("grandchild_empty", saved_assignments)
        self.assertEqual(saved_assignments["child_anchor"], "2")

    def test_update_diagram_preserves_empty_branch_spouse_slot_with_live_parent_branch(self):
        case = SimpleNamespace(
            id=103,
            is_locked=False,
            nguoi_chet_id=1,
            case_state_json=json.dumps({
                "schemaVersion": 1,
                "stage": [
                    {"id": "1", "ho_ten": "Nguoi chet"},
                    {"id": "2", "ho_ten": "Con ruot"},
                ],
                "diagram": {"assignments": {}, "engineState": {"nodes": []}},
            }),
            engine_state_json=None,
        )
        customers = [_customer(1, "Nguoi chet"), _customer(2, "Con ruot")]
        submitted_case_state = json.dumps({
            "schemaVersion": 1,
            "stage": [
                {"id": "1", "ho_ten": "Nguoi chet"},
                {"id": "2", "ho_ten": "Con ruot"},
            ],
            "diagram": {
                "assignments": {"child_anchor": "2"},
                "engineState": {
                    "nodes": [
                        {
                            "id": "owner",
                            "kind": "person",
                            "role": "Owner",
                            "relationType": "owner",
                            "personId": "1",
                            "bucket": 1,
                            "allowsShare": True,
                            "removable": False,
                        },
                        {
                            "id": "child_anchor",
                            "kind": "person",
                            "role": "Con",
                            "relationType": "child",
                            "personId": "2",
                            "parentSlotId": "owner",
                            "parentPersonId": "1",
                            "sourceId": "owner",
                            "bucket": 1,
                            "allowsShare": True,
                            "removable": True,
                        },
                        {
                            "id": "branch_spouse_empty",
                            "kind": "person",
                            "role": "Con_dau_re",
                            "relationType": "branchSpouse",
                            "parentSlotId": "child_anchor",
                            "parentPersonId": "2",
                            "sourceId": "child_anchor",
                            "familyGroupId": "branch-2",
                            "bucket": 4,
                            "allowsShare": True,
                            "removable": True,
                        },
                    ],
                },
                "updatedAt": "2026-06-23T00:00:00.000Z",
            },
        })

        class _FakeQuery:
            def __init__(self, *, first_item=None, all_items=None):
                self._first_item = first_item
                self._all_items = all_items or []

            def filter(self, *_args, **_kwargs):
                return self

            def first(self):
                return self._first_item

            def all(self):
                return self._all_items

        class _FakeDb:
            def __init__(self, stored_case, customer_rows):
                self.stored_case = stored_case
                self.customer_rows = customer_rows
                self.committed = False

            def query(self, model):
                if model is InheritanceCase:
                    return _FakeQuery(first_item=self.stored_case)
                if model is Customer:
                    return _FakeQuery(all_items=self.customer_rows)
                raise AssertionError(f"Unexpected model query: {model}")

            def commit(self):
                self.committed = True

        fake_db = _FakeDb(case, customers)

        with patch("routers.cases._replace_case_participants", lambda *_args, **_kwargs: None):
            result = update_diagram(
                cid=103,
                case_state_json=submitted_case_state,
                diagram_payload="",
                engine_state_json="",
                db=fake_db,
            )

        saved_case_state = json.loads(result["case_state_json"])
        saved_nodes = saved_case_state["diagram"]["engineState"]["nodes"]
        saved_assignments = saved_case_state["diagram"]["assignments"]
        saved_node_ids = [node["id"] for node in saved_nodes]
        self.assertTrue(fake_db.committed)
        self.assertIn("child_anchor", saved_node_ids)
        self.assertIn("branch_spouse_empty", saved_node_ids)
        branch_spouse_node = next(node for node in saved_nodes if node["id"] == "branch_spouse_empty")
        self.assertEqual(branch_spouse_node["parentSlotId"], "child_anchor")
        self.assertEqual(branch_spouse_node["parentPersonId"], "2")
        self.assertEqual(branch_spouse_node["sourceId"], "child_anchor")
        self.assertEqual(branch_spouse_node["bucket"], 4)
        self.assertNotIn("branch_spouse_empty", saved_assignments)
        self.assertEqual(saved_assignments["child_anchor"], "2")

    def test_update_diagram_preserves_empty_spouse_parent_slot_without_assignment(self):
        case = SimpleNamespace(
            id=104,
            is_locked=False,
            nguoi_chet_id=1,
            case_state_json=json.dumps({
                "schemaVersion": 1,
                "stage": [
                    {"id": "1", "ho_ten": "Nguoi chet"},
                    {"id": "5", "ho_ten": "Vo chong"},
                ],
                "diagram": {"assignments": {}, "engineState": {"nodes": []}},
            }),
            engine_state_json=None,
        )
        customers = [_customer(1, "Nguoi chet"), _customer(5, "Vo chong")]
        submitted_case_state = json.dumps({
            "schemaVersion": 1,
            "stage": [
                {"id": "1", "ho_ten": "Nguoi chet"},
                {"id": "5", "ho_ten": "Vo chong"},
            ],
            "diagram": {
                "assignments": {"spouse": "5"},
                "engineState": {
                    "nodes": [
                        {
                            "id": "owner",
                            "kind": "person",
                            "role": "Owner",
                            "relationType": "owner",
                            "personId": "1",
                            "bucket": 1,
                            "allowsShare": True,
                            "removable": False,
                        },
                        {
                            "id": "spouse",
                            "kind": "person",
                            "role": "Vợ/Chồng",
                            "relationType": "spouse",
                            "personId": "5",
                            "bucket": 1,
                            "allowsShare": True,
                            "removable": False,
                        },
                        {
                            "id": "spouse_father",
                            "kind": "person",
                            "role": "Cha_vc",
                            "relationType": "spouseParent",
                            "sourceId": "spouse",
                            "familyGroupId": "spouseParents",
                            "bucket": 0,
                            "allowsShare": True,
                            "removable": False,
                        },
                    ],
                },
                "updatedAt": "2026-06-23T00:30:00.000Z",
            },
        })

        class _FakeQuery:
            def __init__(self, *, first_item=None, all_items=None):
                self._first_item = first_item
                self._all_items = all_items or []

            def filter(self, *_args, **_kwargs):
                return self

            def first(self):
                return self._first_item

            def all(self):
                return self._all_items

        class _FakeDb:
            def __init__(self, stored_case, customer_rows):
                self.stored_case = stored_case
                self.customer_rows = customer_rows
                self.committed = False

            def query(self, model):
                if model is InheritanceCase:
                    return _FakeQuery(first_item=self.stored_case)
                if model is Customer:
                    return _FakeQuery(all_items=self.customer_rows)
                raise AssertionError(f"Unexpected model query: {model}")

            def commit(self):
                self.committed = True

        fake_db = _FakeDb(case, customers)

        with patch("routers.cases._replace_case_participants", lambda *_args, **_kwargs: None):
            result = update_diagram(
                cid=104,
                case_state_json=submitted_case_state,
                diagram_payload="",
                engine_state_json="",
                db=fake_db,
            )

        saved_case_state = json.loads(result["case_state_json"])
        saved_nodes = saved_case_state["diagram"]["engineState"]["nodes"]
        saved_assignments = saved_case_state["diagram"]["assignments"]
        saved_node_ids = [node["id"] for node in saved_nodes]
        self.assertTrue(fake_db.committed)
        self.assertIn("spouse", saved_node_ids)
        self.assertIn("spouse_father", saved_node_ids)
        spouse_parent_node = next(node for node in saved_nodes if node["id"] == "spouse_father")
        self.assertEqual(spouse_parent_node["relationType"], "spouseParent")
        self.assertEqual(spouse_parent_node["sourceId"], "spouse")
        self.assertEqual(spouse_parent_node["familyGroupId"], "spouseParents")
        self.assertEqual(spouse_parent_node["bucket"], 0)
        self.assertFalse(spouse_parent_node["removable"])
        self.assertNotIn("spouse_father", saved_assignments)
        self.assertEqual(saved_assignments["spouse"], "5")

    def test_update_diagram_preserves_empty_spouse_slot_without_assignment(self):
        case = SimpleNamespace(
            id=105,
            is_locked=False,
            nguoi_chet_id=1,
            case_state_json=json.dumps({
                "schemaVersion": 1,
                "stage": [
                    {"id": "1", "ho_ten": "Nguoi chet"},
                ],
                "diagram": {"assignments": {}, "engineState": {"nodes": []}},
            }),
            engine_state_json=None,
        )
        customers = [_customer(1, "Nguoi chet")]
        submitted_case_state = json.dumps({
            "schemaVersion": 1,
            "stage": [
                {"id": "1", "ho_ten": "Nguoi chet"},
            ],
            "diagram": {
                "assignments": {},
                "engineState": {
                    "nodes": [
                        {
                            "id": "owner",
                            "kind": "person",
                            "role": "Owner",
                            "relationType": "owner",
                            "personId": "1",
                            "bucket": 1,
                            "allowsShare": True,
                            "removable": False,
                        },
                        {
                            "id": "spouse",
                            "kind": "person",
                            "role": "Vợ/Chồng",
                            "relationType": "spouse",
                            "bucket": 1,
                            "allowsShare": True,
                            "removable": False,
                        },
                    ],
                },
                "updatedAt": "2026-06-23T01:00:00.000Z",
            },
        })

        class _FakeQuery:
            def __init__(self, *, first_item=None, all_items=None):
                self._first_item = first_item
                self._all_items = all_items or []

            def filter(self, *_args, **_kwargs):
                return self

            def first(self):
                return self._first_item

            def all(self):
                return self._all_items

        class _FakeDb:
            def __init__(self, stored_case, customer_rows):
                self.stored_case = stored_case
                self.customer_rows = customer_rows
                self.committed = False

            def query(self, model):
                if model is InheritanceCase:
                    return _FakeQuery(first_item=self.stored_case)
                if model is Customer:
                    return _FakeQuery(all_items=self.customer_rows)
                raise AssertionError(f"Unexpected model query: {model}")

            def commit(self):
                self.committed = True

        fake_db = _FakeDb(case, customers)

        with patch("routers.cases._replace_case_participants", lambda *_args, **_kwargs: None):
            result = update_diagram(
                cid=105,
                case_state_json=submitted_case_state,
                diagram_payload="",
                engine_state_json="",
                db=fake_db,
            )

        saved_case_state = json.loads(result["case_state_json"])
        saved_nodes = saved_case_state["diagram"]["engineState"]["nodes"]
        saved_assignments = saved_case_state["diagram"]["assignments"]
        saved_node_ids = [node["id"] for node in saved_nodes]
        self.assertTrue(fake_db.committed)
        self.assertIn("owner", saved_node_ids)
        self.assertIn("spouse", saved_node_ids)
        spouse_node = next(node for node in saved_nodes if node["id"] == "spouse")
        self.assertEqual(spouse_node["relationType"], "spouse")
        self.assertEqual(spouse_node["bucket"], 1)
        self.assertFalse(spouse_node["removable"])
        self.assertNotIn("spouse", saved_assignments)
        self.assertEqual(saved_assignments, {"owner": "1"})

    def test_derive_case_state_from_legacy_participants(self):
        customer = _customer(12, "Legacy Person")
        customer.gioi_tinh = "Nam"
        customer.ngay_sinh = date(1980, 5, 4)
        customer.ngay_chet = date(2020, 6, 7)
        customer.so_giay_to = "012345678901"
        customer.ngay_cap = date(2021, 8, 9)
        customer.dia_chi = "Legacy address"

        payload = json.loads(_derive_case_state_json_from_participants([_participant(customer)]))

        self.assertEqual(payload["schemaVersion"], 1)
        self.assertEqual(payload["diagram"], {})
        self.assertEqual(payload["stage"][0]["id"], "12")
        self.assertEqual(payload["stage"][0]["ho_ten"], "Legacy Person")
        self.assertEqual(payload["stage"][0]["ngay_sinh"], "04/05/1980")
        self.assertEqual(payload["stage"][0]["ngay_chet"], "07/06/2020")
        self.assertEqual(payload["stage"][0]["so_giay_to"], "012345678901")
        self.assertEqual(payload["stage"][0]["ngay_cap"], "09/08/2021")
        self.assertEqual(payload["stage"][0]["dia_chi"], "Legacy address")

    def test_derive_case_state_from_legacy_participants_deduplicates_customer_ids(self):
        customer = _customer(12, "Legacy Person")

        payload = json.loads(_derive_case_state_json_from_participants([
            _participant(customer),
            _participant(customer),
        ]))

        self.assertEqual([row["id"] for row in payload["stage"]], ["12"])


class DiagramPayloadParserTests(unittest.TestCase):
    @staticmethod
    def _v2_case_state(*, receive=True, fake_result=None):
        diagram = {
            "engineInput": {
                "version": 2,
                "nodes": [
                    {
                        "id": "owner",
                        "personId": "1",
                        "relationType": "person",
                        "roleLabel": "Chủ đất",
                        "parentSlotIds": [],
                        "spouseSlotId": None,
                        "isLandOwner": True,
                        "willReceive": False,
                        "hidden": False,
                        "deleted": False,
                    },
                    {
                        "id": "child",
                        "personId": "2",
                        "relationType": "child",
                        "roleLabel": "Con",
                        "parentSlotIds": ["owner"],
                        "spouseSlotId": None,
                        "isLandOwner": False,
                        "willReceive": receive,
                        "hidden": False,
                        "deleted": False,
                    },
                ],
            },
        }
        if fake_result is not None:
            diagram["engineResult"] = fake_result
        return json.dumps({
            "schemaVersion": 2,
            "stage": [{"id": "1"}, {"id": "2"}],
            "diagram": diagram,
        })

    def test_v2_case_state_recomputes_result_and_projects_backend_percentage(self):
        owner = _customer(1, "Owner")
        owner.ngay_chet = date(2020, 1, 1)
        child = _customer(2, "Child")

        resolved = _resolve_v2_case_state(
            self._v2_case_state(fake_result={"allocations": {"2": {"finalShare": "0"}}}),
            customers_by_id={"1": owner, "2": child},
            deceased_customer_id="1",
        )

        self.assertIsNotNone(resolved)
        normalized, participants, participant_ids, result = resolved
        saved = json.loads(normalized)
        self.assertEqual(saved["version"], 2)
        self.assertEqual(saved["schemaVersion"], 2)
        self.assertTrue(saved["updatedAt"].endswith("Z"))
        self.assertEqual(result["allocations"]["2"]["finalShare"], "1")
        self.assertEqual(saved["diagram"]["engineResult"], result)
        self.assertEqual(participant_ids, {2})
        self.assertEqual(participants[0].ty_le, 100.0)
        self.assertEqual(participants[0].parent_customer_id, 1)

    def test_v2_case_state_drops_legacy_diagram_mirrors_on_save(self):
        owner = _customer(1, "Owner")
        owner.ngay_chet = date(2020, 1, 1)
        child = _customer(2, "Child")
        payload = json.loads(self._v2_case_state())
        payload["diagram"].update({
            "assignments": {"child": "2"},
            "engineState": {
                "nodes": [{"id": "child", "personId": "2"}],
                "allocations": {"2": {"finalShare": "999"}},
                "trace": [{"from": "1", "to": "2"}],
            },
        })

        normalized, _participants, _participant_ids, _result = _resolve_v2_case_state(
            json.dumps(payload),
            customers_by_id={"1": owner, "2": child},
            deceased_customer_id="1",
        )

        saved_diagram = json.loads(normalized)["diagram"]
        self.assertEqual(set(saved_diagram), {"engineInput", "engineResult"})


    def test_v2_participant_projection_uses_exact_engine_share_instead_of_hardcoded_value(self):
        owner = _customer(1, "Owner")
        owner.ngay_chet = date(2020, 1, 1)
        first_child = _customer(2, "First child")
        second_child = _customer(3, "Second child")
        payload = json.loads(self._v2_case_state())
        payload["stage"].append({"id": "3"})
        payload["diagram"]["engineInput"]["nodes"].append({
            "id": "child_2",
            "personId": "3",
            "relationType": "child",
            "roleLabel": "Con",
            "parentSlotIds": ["owner"],
            "spouseSlotId": None,
            "isLandOwner": False,
            "willReceive": True,
            "hidden": False,
            "deleted": False,
        })

        resolved = _resolve_v2_case_state(
            json.dumps(payload),
            customers_by_id={"1": owner, "2": first_child, "3": second_child},
            deceased_customer_id="1",
        )

        self.assertIsNotNone(resolved)
        _normalized, participants, participant_ids, result = resolved
        shares = {participant.customer_id: participant.ty_le for participant in participants}
        self.assertEqual(participant_ids, {2, 3})
        self.assertEqual(result["allocations"]["2"]["finalShare"], "1/2")
        self.assertEqual(result["allocations"]["3"]["finalShare"], "1/2")
        self.assertEqual(shares, {2: 50.0, 3: 50.0})

    def test_v2_case_state_invalid_or_incomplete_never_falls_back_to_legacy(self):
        owner = _customer(1, "Owner")
        owner.ngay_chet = date(2020, 1, 1)
        child = _customer(2, "Child")

        with self.assertRaises(DiagramPayloadValidationError) as exc:
            _resolve_v2_case_state(
                self._v2_case_state(receive=False),
                customers_by_id={"1": owner, "2": child},
                deceased_customer_id="1",
            )

        self.assertIn("chưa có người nhận", str(exc.exception))

    def test_v2_marker_without_engine_input_is_rejected_instead_of_falling_back(self):
        raw = json.dumps({
            "version": 2,
            "schemaVersion": 2,
            "stage": [{"id": "1"}],
            "diagram": {"engineResult": {"status": "complete"}},
        })

        with self.assertRaises(DiagramPayloadValidationError) as exc:
            _resolve_v2_case_state(raw, customers_by_id={"1": _customer(1, "Owner")}, deceased_customer_id="1")

        self.assertIn("thiếu engineInput", str(exc.exception))

    def test_v2_stage_update_preserves_authoritative_diagram_result(self):
        owner = _customer(1, "Owner")
        owner.ngay_chet = date(2020, 1, 1)
        child = _customer(2, "Child")
        existing, _participants, _ids, result = _resolve_v2_case_state(
            self._v2_case_state(),
            customers_by_id={"1": owner, "2": child},
            deceased_customer_id="1",
        )
        submitted = json.loads(existing)
        submitted["stage"][1]["ho_ten"] = "Child edited"
        submitted["diagram"]["engineResult"] = {"status": "complete", "allocations": {"2": {"finalShare": "0"}}}

        merged = json.loads(_merge_case_state_stage(existing, json.dumps(submitted)))

        self.assertEqual(merged["stage"][1]["ho_ten"], "Child edited")
        self.assertEqual(merged["diagram"]["engineResult"], result)

    def test_calculate_diagram_uses_database_people_without_committing(self):
        owner = _customer(1, "Owner")
        owner.ngay_chet = date(2020, 1, 1)
        child = _customer(2, "Child")

        class Query:
            def all(self):
                return [owner, child]

        class ReadOnlyDb:
            def query(self, model):
                self.queried_model = model
                return Query()

        db = ReadOnlyDb()
        engine_input = json.loads(self._v2_case_state())["diagram"]["engineInput"]
        result = calculate_diagram({
            "engineInput": engine_input,
            "allocations": {"2": {"finalShare": "999/1", "displayPercent": "99900.00"}},
        }, db=db)

        self.assertEqual(result["status"], "complete")
        self.assertEqual(result["allocations"]["2"]["finalShare"], "1")
        self.assertEqual(result["allocations"]["2"]["displayPercent"], "100.00")
        self.assertFalse(hasattr(db, "committed"))

    def test_normalize_case_state_rejects_v2_person_outside_stage(self):
        payload = json.loads(self._v2_case_state())
        payload["stage"] = [{"id": "1"}]

        with self.assertRaises(DiagramPayloadValidationError) as exc:
            _normalize_case_state_json(json.dumps(payload))

        self.assertIn("engineInput", str(exc.exception))

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

    def test_normalize_diagram_payload_drops_legacy_flow_from_list(self):
        payload = _payload([
            {
                "id": "child_1",
                "kind": "person",
                "role": "Con",
                "relationType": "child",
                "personId": "2",
                "flowFrom": ["owner", "spouse_mother", "", None, 5],
            }
        ])

        normalized = _normalize_diagram_payload(payload)

        self.assertNotIn("flowFrom", normalized["nodes"][0])

    def test_normalize_diagram_payload_drops_legacy_edges_list(self):
        payload = json.dumps({
            "version": 2,
            "updatedAt": "2026-05-11T10:00:00.000Z",
            "nodes": [
                {
                    "id": "owner",
                    "kind": "person",
                    "role": "Owner",
                    "relationType": "owner",
                    "personId": "1",
                },
                {
                    "id": "child_1",
                    "kind": "person",
                    "role": "Con",
                    "relationType": "child",
                    "personId": "2",
                },
            ],
            "edges": [
                {
                    "id": "edge-1",
                    "source": " owner ",
                    "target": "child_1",
                    "kind": "kinship",
                    "label": "Quan he",
                    "markerEnd": {"type": "arrowclosed"},
                    "style": {"strokeWidth": 2},
                },
            ],
        })

        normalized = _normalize_diagram_payload(payload)

        self.assertNotIn("edges", normalized)

    def test_normalize_diagram_payload_keeps_render_metadata_but_drops_legacy_output(self):
        payload = json.dumps({
            "version": 2,
            "updatedAt": "2026-05-11T10:00:00.000Z",
            "nodes": [
                {
                    "id": "child_1",
                    "kind": "person",
                    "role": "Con",
                    "relationType": "child",
                    "personId": "2",
                },
            ],
            "allocations": {"2": {"displayPercent": "50.00"}},
            "warnings": [{"code": "demo_warning"}],
            "trace": [{"type": "flow", "from": "1", "to": "2"}],
            "viewport": {"x": 120.5, "y": -32.25, "zoom": 0.85},
            "layoutMeta": {
                "laneOffsets": {"children": 240},
                "collapsedBranches": ["child_1"],
            },
        })

        normalized = _normalize_diagram_payload(payload)

        self.assertNotIn("allocations", normalized)
        self.assertNotIn("warnings", normalized)
        self.assertNotIn("trace", normalized)
        self.assertEqual(normalized["viewport"]["zoom"], 0.85)
        self.assertEqual(normalized["layoutMeta"]["laneOffsets"]["children"], 240)
        self.assertEqual(normalized["layoutMeta"]["collapsedBranches"][0], "child_1")

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

    def test_parse_case_diagram_payload_reads_legacy_decision_without_persisting_it(self):
        customers = {
            "1": _customer(1, "Owner"),
            "2": _customer(2, "Accept"),
            "3": _customer(3, "Refuse"),
            "4": _customer(4, "Unset"),
        }
        payload = _payload([
            {"id": "owner", "kind": "person", "role": "Owner", "relationType": "owner", "personId": "1"},
            {"id": "child_1", "kind": "person", "role": "Con", "relationType": "child", "personId": "2", "parentPersonId": "1", "inheritanceDecision": "accept"},
            {"id": "child_2", "kind": "person", "role": "Con", "relationType": "child", "personId": "3", "parentPersonId": "1", "inheritanceDecision": "refuse"},
            {"id": "child_3", "kind": "person", "role": "Con", "relationType": "child", "personId": "4", "parentPersonId": "1", "inheritanceDecision": "unset"},
        ])

        participants, participant_ids, engine_state = _parse_case_diagram_payload(payload, customers, "1")

        self.assertEqual(participant_ids, {2, 3, 4})
        self.assertTrue(participants[0].co_nhan_tai_san)
        self.assertFalse(participants[1].co_nhan_tai_san)
        self.assertFalse(participants[2].co_nhan_tai_san)
        normalized = json.loads(engine_state)
        self.assertEqual(len(normalized["nodes"]), 4)
        self.assertNotIn("inheritanceDecision", normalized["nodes"][1])
        self.assertTrue(normalized["nodes"][1]["willReceive"])
        self.assertFalse(normalized["nodes"][2]["willReceive"])
        self.assertFalse(normalized["nodes"][3]["willReceive"])

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


class AtomicPersistenceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.engine = create_engine(f"sqlite:///{Path(self.tmp.name) / 'atomic.db'}")
        database.Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine)

    def tearDown(self):
        self.engine.dispose()
        self.tmp.cleanup()

    @staticmethod
    def _case_state() -> str:
        return DiagramPayloadParserTests._v2_case_state()

    @staticmethod
    def _seed_people_and_property(db):
        owner = _customer(1, "Owner")
        owner.ngay_chet = date(2020, 1, 1)
        db.add_all([owner, _customer(2, "New child"), _customer(3, "Old child"), _property(10)])
        db.commit()

    @staticmethod
    def _fail_after_participant_replacement(db, case_id, participants):
        from routers.cases import _replace_case_participants

        _replace_case_participants(db, case_id, participants)
        db.flush()
        raise RuntimeError("forced participant replacement failure")

    def test_create_rolls_back_case_when_participant_replacement_fails(self):
        db = self.Session()
        self._seed_people_and_property(db)

        with (
            patch("routers.cases._replace_case_participants", self._fail_after_participant_replacement),
            patch("routers.cases._render_case_form", return_value=SimpleNamespace(status_code=422)),
        ):
            response = create(
                request=SimpleNamespace(),
                nguoi_chet_id="1",
                tai_san_id="10",
                property_ids=["10"],
                participant_id=None,
                participant_role=None,
                participant_share=None,
                participant_receive=None,
                participant_parent_id=None,
                diagram_payload="",
                engine_state_json="",
                case_state_json=self._case_state(),
                db=db,
            )

        self.assertEqual(response.status_code, 422)
        self.assertEqual(db.query(InheritanceCase).count(), 0)
        self.assertEqual(db.query(InheritanceParticipant).count(), 0)
        db.close()

    def test_edit_rolls_back_case_and_participants_when_replacement_fails(self):
        db = self.Session()
        self._seed_people_and_property(db)
        case = InheritanceCase(
            nguoi_chet_id=1,
            tai_san_id=10,
            ngay_lap_ho_so=date(2026, 1, 1),
            noi_niem_yet="old value",
        )
        db.add(case)
        db.flush()
        db.add(InheritanceParticipant(
            ho_so_id=case.id,
            customer_id=3,
            vai_tro="Con",
            hang_thua_ke=1,
            ty_le=100.0,
            co_nhan_tai_san=True,
        ))
        db.commit()
        case_id = case.id

        with (
            patch("routers.cases._replace_case_participants", self._fail_after_participant_replacement),
            patch("routers.cases._render_case_form", return_value=SimpleNamespace(status_code=422)),
        ):
            response = edit(
                cid=case_id,
                request=SimpleNamespace(),
                nguoi_chet_id="1",
                tai_san_id="10",
                property_ids=["10"],
                noi_niem_yet="new value",
                participant_id=None,
                participant_role=None,
                participant_share=None,
                participant_receive=None,
                participant_parent_id=None,
                diagram_payload="",
                engine_state_json="",
                case_state_json=self._case_state(),
                db=db,
            )

        db.expire_all()
        saved_case = db.query(InheritanceCase).filter(InheritanceCase.id == case_id).one()
        saved_participants = db.query(InheritanceParticipant).filter(
            InheritanceParticipant.ho_so_id == case_id
        ).all()
        self.assertEqual(response.status_code, 422)
        self.assertEqual(saved_case.noi_niem_yet, "old value")
        self.assertEqual([item.customer_id for item in saved_participants], [3])
        db.close()


if __name__ == "__main__":
    unittest.main()
