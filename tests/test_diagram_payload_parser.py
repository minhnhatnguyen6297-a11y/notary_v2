import json
import inspect
import sqlite3
import tempfile
import unittest
from datetime import date
from pathlib import Path

import database
from fastapi import FastAPI
from fastapi.testclient import TestClient
from models import Customer, InheritanceCase, InheritanceParticipant, Property
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from routers import cases as cases_router
from routers.cases import (
    DiagramPayloadValidationError,
    _derive_case_state_json_from_participants,
    _normalize_case_state_json,
    _normalize_diagram_payload,
    _parse_case_diagram_payload,
    _prune_case_state_diagram,
    _prune_engine_state,
    _resolve_posted_participants,
    _validate_case_refs,
    create,
    edit,
    update_stage,
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
    def test_legacy_stage_fallback_includes_deceased_owner(self):
        owner = _customer(1, "Owner")
        child = _customer(2, "Child")
        state = json.loads(_derive_case_state_json_from_participants(
            [type("Participant", (), {"customer": child})()], owner
        ))

        self.assertEqual([row["id"] for row in state["stage"]], ["1", "2"])

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

    def test_normalize_case_state_json_requires_ids_but_keeps_duplicate_stage_rows(self):
        with self.assertRaises(DiagramPayloadValidationError):
            _normalize_case_state_json(json.dumps({"schemaVersion": 1, "stage": [{"ho_ten": "missing"}], "diagram": {}}))
        payload = json.loads(_normalize_case_state_json(json.dumps({
            "schemaVersion": 1, "stage": [{"id": "1"}, {"id": "1"}], "diagram": {}
        })))
        self.assertEqual([row["id"] for row in payload["stage"]], ["1", "1"])

    def test_update_stage_persists_normalized_snapshot(self):
        case = type("Case", (), {"is_locked": False, "case_state_json": None, "engine_state_json": ""})()

        class Query:
            def filter(self, *_args): return self
            def first(self): return case
            def delete(self, **_kwargs): pass
        class Db:
            committed = False
            def query(self, *_args): return Query()
            def commit(self): self.committed = True
        db = Db()
        result = update_stage(1, json.dumps({"schemaVersion": 1, "stage": [{"id": "1"}], "diagram": {}}), db)

        self.assertTrue(db.committed)
        self.assertEqual(result["case_state_json"], case.case_state_json)

    def test_update_stage_does_not_mutate_legacy_participants(self):
        case = type("Case", (), {"is_locked": False, "case_state_json": None, "engine_state_json": ""})()

        class Query:
            def filter(self, *_args): return self
            def first(self): return case
        class Db:
            def __init__(self): self.queries = []
            def query(self, model):
                self.queries.append(model)
                return Query()
            def commit(self): pass
        db = Db()

        update_stage(1, json.dumps({"schemaVersion": 1, "stage": [{"id": "1"}], "diagram": {}}), db)

        self.assertEqual(db.queries, [InheritanceCase])
        self.assertNotIn(InheritanceParticipant, db.queries)

    def test_stage_update_api_persists_state_without_deleting_legacy_participant(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            engine = create_engine(f"sqlite:///{Path(tmp_dir) / 'stage-update.db'}")
            session_factory = sessionmaker(bind=engine)
            database.Base.metadata.create_all(engine)
            try:
                with session_factory() as db:
                    owner = Customer(ho_ten="Owner")
                    child = Customer(ho_ten="Legacy Child")
                    property_ = Property(so_serial="STAGE-1", dia_chi="Test address")
                    db.add_all([owner, child, property_])
                    db.flush()
                    case = InheritanceCase(
                        nguoi_chet_id=owner.id,
                        tai_san_id=property_.id,
                        ngay_lap_ho_so=date.today(),
                    )
                    db.add(case)
                    db.flush()
                    db.add(InheritanceParticipant(
                        ho_so_id=case.id,
                        customer_id=child.id,
                        vai_tro="Con",
                    ))
                    db.commit()
                    case_id = case.id
                    owner_id = owner.id
                    participant_id = child.id

                app = FastAPI()
                app.include_router(cases_router.router, prefix="/cases")

                def get_test_db():
                    db = session_factory()
                    try:
                        yield db
                    finally:
                        db.close()

                app.dependency_overrides[cases_router.get_db] = get_test_db
                with TestClient(app) as client:
                    response = client.post(
                        f"/cases/{case_id}/stage-update",
                        data={"case_state_json": json.dumps({
                            "schemaVersion": 1,
                            "stage": [{"id": str(owner_id)}],
                            "diagram": {},
                        })},
                    )

                self.assertEqual(response.status_code, 200)
                with session_factory() as db:
                    self.assertEqual(db.get(InheritanceCase, case_id).case_state_json, response.json()["case_state_json"])
                    self.assertIsNotNone(db.query(InheritanceParticipant).filter_by(
                        ho_so_id=case_id, customer_id=participant_id
                    ).first())
            finally:
                engine.dispose()

    def test_create_and_edit_blank_diagram_filter_legacy_people_against_empty_stage(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            engine = create_engine(f"sqlite:///{Path(tmp_dir) / 'empty-stage.db'}")
            session_factory = sessionmaker(bind=engine)
            database.Base.metadata.create_all(engine)
            try:
                with session_factory() as db:
                    owner = Customer(ho_ten="Owner", ngay_chet=date.today())
                    child = Customer(ho_ten="Legacy Child")
                    property_ = Property(so_serial="EMPTY-1", dia_chi="Test address")
                    db.add_all([owner, child, property_])
                    db.commit()
                    owner_id, child_id, property_id = owner.id, child.id, property_.id

                app = FastAPI()
                app.include_router(cases_router.router, prefix="/cases")

                def get_test_db():
                    db = session_factory()
                    try:
                        yield db
                    finally:
                        db.close()

                def form_data():
                    engine_state = {
                        "nodes": [{"id": "legacy", "kind": "person", "personId": str(child_id)}],
                        "allocations": {str(child_id): {"displayPercent": "100"}},
                        "trace": [{"personId": str(child_id)}],
                        "warnings": [{"code": "stale"}],
                    }
                    return {
                        "nguoi_chet_id": str(owner_id),
                        "tai_san_id": str(property_id),
                        "case_state_json": json.dumps({"schemaVersion": 1, "stage": [], "diagram": {}}),
                        "diagram_payload": "",
                        "engine_state_json": json.dumps(engine_state),
                        "participant_id": str(child_id),
                        "participant_role": "Con",
                        "participant_parent_id": str(owner_id),
                    }

                app.dependency_overrides[cases_router.get_db] = get_test_db
                with TestClient(app) as client:
                    response = client.post("/cases/create", data=form_data(), follow_redirects=False)
                    self.assertEqual(response.status_code, 302)
                    with session_factory() as db:
                        case = db.query(InheritanceCase).one()
                        case_id = case.id
                        self.assertEqual(case.participants, [])
                        persisted_engine = json.loads(case.engine_state_json)
                        self.assertEqual(persisted_engine["nodes"], [])
                        self.assertEqual(persisted_engine["allocations"], {})
                        self.assertEqual(persisted_engine["trace"], [])
                        self.assertEqual(persisted_engine["warnings"], [])

                    response = client.post(
                        f"/cases/{case_id}/edit", data=form_data(), follow_redirects=False,
                    )
                    self.assertEqual(response.status_code, 302)

                with session_factory() as db:
                    case = db.get(InheritanceCase, case_id)
                    self.assertEqual(case.participants, [])
                    self.assertEqual(json.loads(case.engine_state_json)["nodes"], [])
            finally:
                engine.dispose()

    def test_update_stage_prunes_removed_people_from_case_and_engine_diagram_state(self):
        case = type("Case", (), {
            "is_locked": False,
            "case_state_json": None,
            "engine_state_json": json.dumps({
                "nodes": [{"id": "owner", "personId": "1"}, {"id": "child", "personId": "2", "parentSlotId": "owner"}],
                "edges": [{"source": "owner", "target": "child"}],
                "receiverIds": ["1", "2"],
            }),
        })()

        class Query:
            def filter(self, *_args): return self
            def first(self): return case
            def delete(self, **_kwargs): pass
        class Db:
            def query(self, *_args): return Query()
            def commit(self): pass
            def rollback(self): pass

        result = update_stage(1, json.dumps({
            "schemaVersion": 1,
            "stage": [{"id": "1"}],
            "diagram": {"assignments": {"owner": "1", "child": "2"}, "engineState": json.loads(case.engine_state_json)},
        }), Db())

        payload = json.loads(result["case_state_json"])
        self.assertEqual(payload["diagram"]["assignments"], {"owner": "1"})
        self.assertEqual([node["personId"] for node in payload["diagram"]["engineState"]["nodes"]], ["1"])
        self.assertEqual(json.loads(case.engine_state_json)["receiverIds"], ["1"])

    def test_stage_pruning_preserves_structure_and_clears_recursive_orphans(self):
        payload = _prune_case_state_diagram({
            "stage": [{"id": "1"}, {"id": "3"}],
            "diagram": {
                "assignments": {
                    "owner": "1", "removed": "1", "structure": "3",
                    "ghost": "3", "nested": "2", "missing": "1",
                },
                "engineState": {
                    "nodes": [
                        {"id": "owner", "kind": "person", "personId": "1"},
                        {"id": "removed", "kind": "person", "personId": "2", "person": {"id": "2"}},
                        {
                            "id": "survivor", "kind": "person", "personId": "3",
                            "parentPersonId": "2", "parentSlotId": "removed", "sourceId": "removed",
                        },
                        {
                            "id": "structure", "kind": "structural", "personId": "2", "person": {"id": "2"},
                            "parentPersonId": "2", "parentSlotId": "owner", "sourceId": "removed",
                        },
                        {
                            "id": "ghost", "kind": "ghost", "parentPersonId": "2",
                            "parentSlotId": "structure", "sourceId": "structure",
                        },
                        {"id": "nested", "kind": "ghost", "parentSlotId": "ghost", "sourceId": "ghost"},
                    ],
                    "edges": [
                        {"id": "removed-edge", "source": "owner", "target": "removed"},
                        {"id": "survivor-edge", "source": "owner", "target": "survivor"},
                        {"id": "ghost-edge", "source": "structure", "target": "ghost"},
                        {"id": "nested-edge", "source": "ghost", "target": "nested"},
                        {"id": "incomplete-edge", "source": "owner"},
                    ],
                    "assetOwnerIds": ["1", "2"],
                    "receiverIds": ["2", "3"],
                    "participantIds": ["1", "2", "3"],
                    "allocations": {"2": {"displayPercent": "40"}, "3": {"displayPercent": "60"}},
                    "trace": [{"personId": "2"}, {"personId": "3"}],
                    "warnings": [{"code": "stale-result"}],
                },
            },
        })
        pruned = payload["diagram"]["engineState"]

        nodes = {node["id"]: node for node in pruned["nodes"]}
        self.assertEqual(set(nodes), {"owner", "survivor", "structure", "ghost", "nested"})
        self.assertIsNone(nodes["structure"]["personId"])
        self.assertIsNone(nodes["structure"]["person"])
        self.assertIsNone(nodes["structure"]["parentPersonId"])
        self.assertEqual(nodes["structure"]["parentSlotId"], "owner")
        self.assertIsNone(nodes["structure"]["sourceId"])
        self.assertIsNone(nodes["ghost"]["parentPersonId"])
        self.assertEqual(nodes["ghost"]["parentSlotId"], "structure")
        self.assertEqual(nodes["nested"]["parentSlotId"], "ghost")
        self.assertIsNone(nodes["survivor"]["parentPersonId"])
        self.assertIsNone(nodes["survivor"]["parentSlotId"])
        self.assertEqual([edge["id"] for edge in pruned["edges"]], ["survivor-edge", "ghost-edge", "nested-edge"])
        self.assertEqual(pruned["assetOwnerIds"], ["1"])
        self.assertEqual(pruned["receiverIds"], ["3"])
        self.assertEqual(pruned["participantIds"], ["1", "3"])
        self.assertEqual(pruned["allocations"], {})
        self.assertEqual(pruned["trace"], [])
        self.assertEqual(pruned["warnings"], [])
        self.assertEqual(payload["diagram"]["assignments"], {"owner": "1", "structure": "3", "ghost": "3"})

    def test_create_and_edit_use_pruned_case_state_engine_over_conflicting_channels(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            engine = create_engine(f"sqlite:///{Path(tmp_dir) / 'full-form.db'}")
            session_factory = sessionmaker(bind=engine)
            database.Base.metadata.create_all(engine)
            try:
                with session_factory() as db:
                    owner = Customer(ho_ten="Owner", ngay_chet=date.today())
                    first = Customer(ho_ten="First")
                    second = Customer(ho_ten="Second")
                    removed = Customer(ho_ten="Removed")
                    property_ = Property(so_serial="FORM-1", dia_chi="Test address")
                    db.add_all([owner, first, second, removed, property_])
                    db.commit()
                    owner_id, first_id, second_id = owner.id, first.id, second.id
                    removed_id, property_id = removed.id, property_.id

                app = FastAPI()
                app.include_router(cases_router.router, prefix="/cases")

                def get_test_db():
                    db = session_factory()
                    try:
                        yield db
                    finally:
                        db.close()

                def form_data(committed_person_id, raw_person_id):
                    committed_nodes = [
                        {"id": "owner", "kind": "person", "role": "Owner", "personId": str(owner_id)},
                        {
                            "id": "kept", "kind": "person", "role": "Con", "personId": str(committed_person_id),
                            "parentPersonId": str(owner_id),
                        },
                        {
                            "id": "stale", "kind": "person", "role": "Con", "personId": str(removed_id),
                            "parentPersonId": str(owner_id),
                        },
                        {
                            "id": "ghost", "kind": "ghost", "personId": str(removed_id),
                            "parentSlotId": "owner", "parentPersonId": str(removed_id),
                        },
                    ]
                    committed_engine = {
                        "version": 2,
                        "updatedAt": "2026-08-14T00:00:00Z",
                        "nodes": committed_nodes,
                        "receiverIds": [str(committed_person_id), str(removed_id)],
                    }
                    raw_engine = {
                        "version": 2,
                        "updatedAt": "2026-08-14T00:00:01Z",
                        "nodes": [
                            {"id": "owner", "kind": "person", "role": "Owner", "personId": str(owner_id)},
                            {"id": "raw-only", "kind": "person", "role": "Con", "personId": str(raw_person_id)},
                        ],
                    }
                    case_state = {
                        "schemaVersion": 1,
                        "stage": [
                            {"id": str(owner_id)}, {"id": str(committed_person_id)}, {"id": str(raw_person_id)},
                        ],
                        "diagram": {
                            "assignments": {"kept": str(committed_person_id), "stale": str(removed_id)},
                            "engineState": committed_engine,
                        },
                    }
                    return {
                        "nguoi_chet_id": str(owner_id),
                        "tai_san_id": str(property_id),
                        "case_state_json": json.dumps(case_state),
                        "diagram_payload": json.dumps(raw_engine),
                        "engine_state_json": json.dumps(raw_engine),
                    }

                app.dependency_overrides[cases_router.get_db] = get_test_db
                with TestClient(app) as client:
                    response = client.post(
                        "/cases/create", data=form_data(first_id, second_id), follow_redirects=False,
                    )
                    self.assertEqual(response.status_code, 302)

                    with session_factory() as db:
                        case = db.query(InheritanceCase).one()
                        case_id = case.id
                        self.assertEqual([p.customer_id for p in case.participants], [first_id])
                        case_nodes = {node["id"]: node for node in json.loads(case.case_state_json)["diagram"]["engineState"]["nodes"]}
                        self.assertNotIn("stale", case_nodes)
                        self.assertIsNone(case_nodes["ghost"]["personId"])
                        self.assertIsNone(case_nodes["ghost"]["parentPersonId"])
                        self.assertNotIn("raw-only", {node["id"] for node in json.loads(case.engine_state_json)["nodes"]})

                    response = client.post(
                        f"/cases/{case_id}/edit", data=form_data(second_id, first_id), follow_redirects=False,
                    )
                    self.assertEqual(response.status_code, 302)

                with session_factory() as db:
                    case = db.get(InheritanceCase, case_id)
                    self.assertEqual([p.customer_id for p in case.participants], [second_id])
                    engine_nodes = {node["id"]: node for node in json.loads(case.engine_state_json)["nodes"]}
                    self.assertNotIn("stale", engine_nodes)
                    self.assertNotIn("raw-only", engine_nodes)
                    self.assertEqual(engine_nodes["kept"]["personId"], str(second_id))
                    self.assertIsNone(engine_nodes["ghost"]["personId"])
            finally:
                engine.dispose()


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

    def test_parse_case_diagram_payload_ignores_ghost_with_person_id(self):
        customers = {"1": _customer(1, "Owner"), "2": _customer(2, "Ghost"), "3": _customer(3, "Child")}
        payload = _payload([
            {"id": "owner", "kind": "person", "role": "Owner", "personId": "1"},
            {"id": "ghost", "kind": "ghost", "role": "Con", "personId": "2"},
            {"id": "child", "kind": "person", "role": "Con", "personId": "3", "parentPersonId": "1"},
        ])

        participants, participant_ids, _ = _parse_case_diagram_payload(payload, customers, "1")

        self.assertEqual(participant_ids, {3})
        self.assertEqual([participant.customer_id for participant in participants], [3])

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

    def test_resolve_legacy_inputs_filters_stage_and_clears_stale_parent(self):
        customers = [_customer(1, "Dead"), _customer(2, "Kept"), _customer(3, "Removed")]

        participants, participant_ids, engine_state, _ = _resolve_posted_participants(
            all_customers=customers,
            deceased_customer_id="1",
            diagram_payload="",
            participant_id=["2", "3"],
            participant_role=["Con", "Con"],
            participant_share=["0", "0"],
            participant_receive=["1", "1"],
            participant_parent_id=["3", "1"],
            engine_state_json=json.dumps({
                "nodes": [
                    {"id": "owner", "personId": "1"},
                    {"id": "kept", "personId": "2", "parentPersonId": "3"},
                    {"id": "removed", "personId": "3"},
                ],
                "allocations": {"2": {"displayPercent": "50"}, "3": {"displayPercent": "50"}},
            }),
            stage_ids={"1", "2"},
        )

        self.assertEqual(participant_ids, {2})
        self.assertEqual([participant.customer_id for participant in participants], [2])
        self.assertIsNone(participants[0].parent_customer_id)
        self.assertEqual([node["personId"] for node in json.loads(engine_state)["nodes"]], ["1", "2"])
        self.assertEqual(json.loads(engine_state)["allocations"], {})


if __name__ == "__main__":
    unittest.main()
