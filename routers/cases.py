from fastapi import APIRouter, Depends, Request, Form, HTTPException, UploadFile, File
from fastapi.responses import RedirectResponse, StreamingResponse, JSONResponse, PlainTextResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from typing import Optional, List, Union, Any
from datetime import date, datetime
import io
import json
from pathlib import Path
from uuid import uuid4
from types import SimpleNamespace

from database import get_db
from models import InheritanceCase, Customer, Property, InheritanceParticipant, InheritanceCaseProperty, WordTemplate
from services.word_engine import (
    WordExportValidationError,
    build_template_mapping,
    find_unresolved_placeholders,
    list_public_builtin_templates,
    replace_in_doc,
)
from services.inheritance_engine import run_inheritance_case

router = APIRouter()
templates = Jinja2Templates(directory="frontend/templates")
WORD_TEMPLATE_UPLOAD_DIR = Path("word_templates/custom")
def _hang_for_role(role: str) -> int:
    role = (role or "").strip()
    if role in ("Cha", "Mẹ", "Cha_vc", "Me_vc", "Vợ/Chồng", "Con", "Cháu", "Con_dau_re"):
        return 1
    if role in ("Ông/Bà", "Anh/Chị/Em"):
        return 2
    return 1


def _to_list(v):
    if v is None:
        return []
    if isinstance(v, list):
        return v
    return [v]


def _normalize_property_ids(primary_property_id: str, raw_property_ids: Optional[Union[List[str], str]]) -> list[int]:
    values: list[str] = []
    for item in _to_list(raw_property_ids):
        if item is None:
            continue
        text = str(item).strip()
        if not text:
            continue
        if text.startswith("[") and text.endswith("]"):
            try:
                parsed = json.loads(text)
                for v in parsed if isinstance(parsed, list) else []:
                    values.append(str(v).strip())
                continue
            except Exception:
                pass
        values.extend([x.strip() for x in text.split(",") if x and x.strip()])

    if primary_property_id:
        values.append(primary_property_id)
    out: list[int] = []
    seen: set[int] = set()
    for v in values:
        if not str(v).isdigit():
            continue
        pid = int(v)
        if pid in seen:
            continue
        seen.add(pid)
        out.append(pid)
    if primary_property_id and primary_property_id.isdigit():
        primary = int(primary_property_id)
        if primary in out:
            out = [primary] + [x for x in out if x != primary]
    return out


def _sync_case_property_links(db: Session, case_id: int, property_ids: list[int], primary_property_id: int) -> None:
    db.query(InheritanceCaseProperty).filter(InheritanceCaseProperty.case_id == case_id).delete()
    for pid in property_ids:
        db.add(
            InheritanceCaseProperty(
                case_id=case_id,
                property_id=pid,
                is_primary=(pid == primary_property_id),
            )
        )


class DiagramPayloadValidationError(Exception):
    def __init__(self, errors: list[str]):
        super().__init__("; ".join(errors))
        self.errors = errors


def _clean_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _clean_nullable_text(value: Any) -> Optional[str]:
    text = _clean_text(value)
    return text or None


def _coerce_bool(value: Any, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    text = str(value).strip().lower()
    if text in {"1", "true", "yes", "on"}:
        return True
    if text in {"0", "false", "no", "off"}:
        return False
    return default


def _coerce_int(value: Any, default: int = 0) -> int:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if value is None:
        return default
    text = str(value).strip()
    if not text:
        return default
    try:
        return int(text)
    except (TypeError, ValueError):
        return default


def _normalize_role(role: str, relation_type: str) -> str:
    role_text = _clean_text(role)
    if role_text:
        return role_text
    relation = _clean_text(relation_type).lower()
    defaults = {
        "owner": "Owner",
        "spouse": "Vợ/Chồng",
        "child": "Con",
        "sibling": "Anh/Chị/Em",
        "grandchild": "Cháu",
        "branchspouse": "Con_dau_re",
    }
    return defaults.get(relation, "Khac")


def _normalize_diagram_payload(raw_payload: str) -> dict[str, Any]:
    try:
        payload = json.loads(raw_payload or "{}")
    except Exception as exc:
        raise DiagramPayloadValidationError([f"diagram_payload không phải JSON hợp lệ: {exc}"])
    if not isinstance(payload, dict):
        raise DiagramPayloadValidationError(["diagram_payload phải là object JSON."])

    payload_root = payload
    if isinstance(payload.get("engineState"), dict) and payload["engineState"].get("nodes") is not None:
        payload_root = payload["engineState"]

    version = payload_root.get("version", payload.get("version"))
    updated_at = _clean_text(payload_root.get("updatedAt", payload.get("updatedAt")))
    nodes_raw = payload_root.get("nodes")
    render_state = {
        key: payload_root[key]
        for key in ("viewport", "layoutMeta")
        if key in payload_root
    }

    errors: list[str] = []
    if version != 2:
        errors.append("diagram_payload.version phải bằng 2.")
    if not updated_at:
        errors.append("diagram_payload.updatedAt là bắt buộc.")
    if not isinstance(nodes_raw, list):
        errors.append("diagram_payload.nodes phải là danh sách.")
    if errors:
        raise DiagramPayloadValidationError(errors)

    normalized_nodes: list[dict[str, Any]] = []
    seen_node_ids: set[str] = set()
    for idx, raw_node in enumerate(nodes_raw):
        if not isinstance(raw_node, dict):
            errors.append(f"Node #{idx + 1} không hợp lệ.")
            continue
        node_id = _clean_text(raw_node.get("id"))
        if not node_id:
            errors.append(f"Node #{idx + 1} thiếu id.")
            continue
        if node_id in seen_node_ids:
            errors.append(f"Node id trùng: {node_id}.")
            continue
        seen_node_ids.add(node_id)
        person_id = _clean_nullable_text(raw_node.get("personId") or (raw_node.get("person") or {}).get("id"))
        relation_type = _clean_text(raw_node.get("relationType"))
        legacy_decision = _clean_text(raw_node.get("inheritanceDecision"))
        normalized_nodes.append({
            "id": node_id,
            "kind": _clean_text(raw_node.get("kind")) or "person",
            "label": _clean_text(raw_node.get("label")),
            "role": _normalize_role(raw_node.get("role"), relation_type),
            "relationType": relation_type,
            "bucket": _coerce_int(raw_node.get("bucket"), 0),
            "allowsShare": _coerce_bool(raw_node.get("allowsShare"), True),
            "removable": _coerce_bool(raw_node.get("removable"), True),
            "personId": person_id,
            "parentPersonId": _clean_nullable_text(raw_node.get("parentPersonId") or raw_node.get("parentId")),
            "parentSlotId": _clean_nullable_text(raw_node.get("parentSlotId")),
            "familyGroupId": _clean_nullable_text(raw_node.get("familyGroupId")),
            "sourceId": _clean_nullable_text(raw_node.get("sourceId")),
            "willReceive": _coerce_bool(raw_node.get("willReceive"), legacy_decision == "accept"),
            "hidden": _coerce_bool(raw_node.get("hidden"), False),
            "deleted": _coerce_bool(raw_node.get("deleted"), False),
            "isLandOwner": _coerce_bool(raw_node.get("isLandOwner"), False),
        })

    if errors:
        raise DiagramPayloadValidationError(errors)

    return {
        "version": 2,
        "updatedAt": updated_at,
        "nodes": normalized_nodes,
        **render_state,
    }


def _extract_diagram_participants(
    diagram_state: dict[str, Any],
    customers_by_id: dict[str, Customer],
    deceased_customer_id: str,
) -> tuple[list[SimpleNamespace], set[int]]:
    errors: list[str] = []
    active_person_ids: set[str] = set()
    seen_participant_ids: set[str] = set()
    participants: list[SimpleNamespace] = []

    for node in diagram_state["nodes"]:
        person_id = _clean_text(node.get("personId"))
        if not person_id or node.get("kind") == "ghost" or node.get("hidden") or node.get("deleted"):
            continue
        active_person_ids.add(person_id)

    for node in diagram_state["nodes"]:
        person_id = _clean_text(node.get("personId"))
        if not person_id or node.get("kind") == "ghost" or node.get("hidden") or node.get("deleted"):
            continue
        if person_id not in customers_by_id:
            errors.append(f"Người tham gia #{person_id} không tồn tại trong danh bạ.")
            continue
        role = _clean_text(node.get("role")) or "Khac"
        if role == "Owner":
            if person_id != deceased_customer_id:
                errors.append("Node Owner phải trùng với người chết của hồ sơ.")
            continue
        if person_id == deceased_customer_id:
            errors.append("Người chết không được lưu trong danh sách participant.")
            continue
        if person_id in seen_participant_ids:
            errors.append(f"Người tham gia bị trùng trong sơ đồ: #{person_id}.")
            continue
        parent_person_id = _clean_nullable_text(node.get("parentPersonId"))
        if parent_person_id and parent_person_id not in active_person_ids:
            errors.append(f"parentPersonId không hợp lệ cho participant #{person_id}.")
            continue
        seen_participant_ids.add(person_id)
        customer = customers_by_id[person_id]
        participants.append(SimpleNamespace(
            customer_id=customer.id,
            customer=customer,
            vai_tro=role,
            ty_le=0.0,
            co_nhan_tai_san=_coerce_bool(node.get("willReceive"), False),
            parent_customer_id=int(parent_person_id) if parent_person_id and parent_person_id.isdigit() else None,
        ))

    if errors:
        raise DiagramPayloadValidationError(errors)
    return participants, {p.customer_id for p in participants}


def _parse_case_diagram_payload(
    raw_payload: str,
    customers_by_id: dict[str, Customer],
    deceased_customer_id: str,
) -> tuple[list[SimpleNamespace], set[int], str]:
    diagram_state = _normalize_diagram_payload(raw_payload)
    participants, participant_ids = _extract_diagram_participants(
        diagram_state,
        customers_by_id=customers_by_id,
        deceased_customer_id=deceased_customer_id,
    )
    return participants, participant_ids, json.dumps(diagram_state, ensure_ascii=False)


def _build_temp_participants(
    all_customers: List[Customer],
    participant_id: Optional[Union[List[str], str]],
    participant_role: Optional[Union[List[str], str]],
    participant_share: Optional[Union[List[str], str]],
    participant_receive: Optional[Union[List[str], str]],
    participant_parent_id: Optional[Union[List[str], str]] = None,
):
    id_list = _to_list(participant_id)
    role_list = _to_list(participant_role)
    share_list = _to_list(participant_share)
    receive_list = _to_list(participant_receive)
    parent_list = _to_list(participant_parent_id)
    customers_by_id = {str(c.id): c for c in all_customers}
    participants = []

    for idx, cid in enumerate(id_list):
        cid_str = str(cid or "").strip()
        if not cid_str:
            continue
        customer = customers_by_id.get(cid_str)
        if not customer:
            continue
        role = (role_list[idx] if idx < len(role_list) else "") or "Khac"
        share_raw = share_list[idx] if idx < len(share_list) else "0"
        receive_raw = receive_list[idx] if idx < len(receive_list) else "1"
        parent_raw = parent_list[idx] if idx < len(parent_list) else ""
        try:
            share_val = float(share_raw)
        except Exception:
            share_val = 0.0
        co_nhan = str(receive_raw).lower() in ("1", "true", "on", "yes")

        parent_cid = None
        if parent_raw and str(parent_raw).isdigit():
            parent_cid = int(parent_raw)

        participants.append(SimpleNamespace(
            customer_id=customer.id,
            customer=customer,
            vai_tro=role,
            ty_le=share_val,
            co_nhan_tai_san=co_nhan,
            parent_customer_id=parent_cid
        ))
    participant_ids = {p.customer_id for p in participants}
    return participants, participant_ids


def _render_case_form(
    request: Request,
    *,
    obj: Optional[InheritanceCase],
    deceased: list[Customer],
    properties: list[Property],
    errors: list[str],
    field_errors: dict[str, str],
    form: dict[str, Any],
    all_customers: list[Customer],
    participants: list[SimpleNamespace],
    participant_ids: set[int],
    case_property_ids: list[int],
):
    return templates.TemplateResponse("cases/form.html", {
        "request": request,
        "obj": obj,
        "deceased": deceased,
        "properties": properties,
        "errors": errors,
        "field_errors": field_errors,
        "form": form,
        "all_customers": all_customers,
        "participants": participants,
        "participant_ids": participant_ids,
        "case_property_ids": case_property_ids,
    })


def _derive_case_state_json_from_participants(participants: list[Any]) -> str:
    stage: list[dict[str, str]] = []
    seen_ids: set[str] = set()
    for participant in participants or []:
        customer = getattr(participant, "customer", None)
        if not customer:
            continue
        customer_id = _clean_text(getattr(customer, "id", ""))
        if not customer_id or customer_id in seen_ids:
            continue
        seen_ids.add(customer_id)
        stage.append({
            "id": customer_id,
            "ho_ten": _clean_text(getattr(customer, "ho_ten", "")),
            "gioi_tinh": _clean_text(getattr(customer, "gioi_tinh", "")),
            "ngay_sinh": _fmt_date(getattr(customer, "ngay_sinh", None)),
            "ngay_chet": _fmt_date(getattr(customer, "ngay_chet", None)),
            "so_giay_to": _clean_text(getattr(customer, "so_giay_to", "")),
            "ngay_cap": _fmt_date(getattr(customer, "ngay_cap", None)),
            "noi_cap": _clean_text(getattr(customer, "noi_cap", "")),
            "dia_chi": _clean_text(getattr(customer, "dia_chi", "")),
            "place_of_origin": _clean_text(getattr(customer, "place_of_origin", "")),
        })
    return _normalize_case_state_json(json.dumps({
        "schemaVersion": 1,
        "stage": stage,
        "diagram": {},
    }, ensure_ascii=False))


def _validate_case_refs(
    *,
    nguoi_chet_id: str,
    tai_san_id: str,
    selected_property_ids: list[int],
    customers_by_id: dict[str, Customer],
    properties_by_id: dict[int, Property],
    field_errors: dict[str, str],
    errors: list[str],
) -> None:
    if not nguoi_chet_id:
        field_errors["nguoi_chet_id"] = "Bắt buộc"
    elif nguoi_chet_id not in customers_by_id:
        field_errors["nguoi_chet_id"] = "Người chết không tồn tại"
    if not tai_san_id:
        field_errors["tai_san_id"] = "Bắt buộc"
    elif not tai_san_id.isdigit() or int(tai_san_id) not in properties_by_id:
        field_errors["tai_san_id"] = "Tài sản không tồn tại"

    invalid_property_ids = [pid for pid in selected_property_ids if pid not in properties_by_id]
    if invalid_property_ids:
        errors.append(f"Danh sách tài sản có id không tồn tại: {', '.join(map(str, invalid_property_ids))}.")


def _resolve_posted_participants(
    *,
    all_customers: list[Customer],
    deceased_customer_id: str,
    diagram_payload: str,
    participant_id: Optional[Union[List[str], str]],
    participant_role: Optional[Union[List[str], str]],
    participant_share: Optional[Union[List[str], str]],
    participant_receive: Optional[Union[List[str], str]],
    participant_parent_id: Optional[Union[List[str], str]],
    engine_state_json: str,
) -> tuple[list[SimpleNamespace], set[int], Optional[str], str]:
    customers_by_id = {str(c.id): c for c in all_customers}
    raw_payload = _clean_text(diagram_payload)
    if raw_payload:
        participants, participant_ids, normalized_engine_state = _parse_case_diagram_payload(
            raw_payload,
            customers_by_id=customers_by_id,
            deceased_customer_id=deceased_customer_id,
        )
        return participants, participant_ids, normalized_engine_state, normalized_engine_state

    posted_participants, posted_participant_ids = _build_temp_participants(
        all_customers,
        participant_id,
        participant_role,
        participant_share,
        participant_receive,
        participant_parent_id,
    )
    normalized_engine_state = _clean_text(engine_state_json) or None
    return posted_participants, posted_participant_ids, normalized_engine_state, raw_payload


def _replace_case_participants(db: Session, case_id: int, participants: list[SimpleNamespace]) -> None:
    db.query(InheritanceParticipant).filter(InheritanceParticipant.ho_so_id == case_id).delete()
    for participant in participants:
        db.add(
            InheritanceParticipant(
                ho_so_id=case_id,
                customer_id=int(participant.customer_id),
                vai_tro=participant.vai_tro or "Khac",
                hang_thua_ke=_hang_for_role(participant.vai_tro or "Khac"),
                ty_le=float(getattr(participant, "ty_le", 0.0) or 0.0),
                co_nhan_tai_san=bool(getattr(participant, "co_nhan_tai_san", True)),
                parent_customer_id=getattr(participant, "parent_customer_id", None),
            )
        )


def _v2_participant_projection(
    engine_input: dict[str, Any],
    engine_result: dict[str, Any],
    customers_by_id: dict[str, Customer],
    deceased_customer_id: str,
) -> tuple[list[SimpleNamespace], set[int]]:
    active_nodes = {
        _clean_text(node.get("id")): node
        for node in engine_input.get("nodes", [])
        if isinstance(node, dict)
        and _clean_text(node.get("id"))
        and _clean_text(node.get("personId"))
        and not node.get("hidden")
        and not node.get("deleted")
    }
    person_by_slot = {
        slot_id: _clean_text(node.get("personId"))
        for slot_id, node in active_nodes.items()
    }
    allocations = engine_result.get("allocations", {})
    participants: list[SimpleNamespace] = []

    for slot_id, node in active_nodes.items():
        person_id = person_by_slot[slot_id]
        if person_id == deceased_customer_id:
            continue
        customer = customers_by_id.get(person_id)
        if customer is None:
            continue
        parent_customer_id = None
        for parent_slot_id in node.get("parentSlotIds") or []:
            parent_person_id = person_by_slot.get(_clean_text(parent_slot_id))
            if parent_person_id and parent_person_id.isdigit():
                parent_customer_id = int(parent_person_id)
                break
        role = _clean_text(node.get("roleLabel"))
        if not role:
            role = "Chủ đất" if node.get("isLandOwner") else _normalize_role("", node.get("relationType"))
        display_percent = _clean_text((allocations.get(person_id) or {}).get("displayPercent")) or "0"
        participants.append(SimpleNamespace(
            customer_id=customer.id,
            customer=customer,
            vai_tro=role,
            ty_le=float(display_percent),
            co_nhan_tai_san=node.get("willReceive") is True,
            parent_customer_id=parent_customer_id,
        ))

    return participants, {participant.customer_id for participant in participants}


def _resolve_v2_case_state(
    raw_case_state: str,
    *,
    customers_by_id: dict[str, Customer],
    deceased_customer_id: str,
) -> Optional[tuple[str, list[SimpleNamespace], set[int], dict[str, Any]]]:
    normalized_case_state = _normalize_case_state_json(raw_case_state)
    if not normalized_case_state:
        return None
    payload = json.loads(normalized_case_state)
    diagram = payload.get("diagram") if isinstance(payload.get("diagram"), dict) else {}
    if "engineInput" not in diagram:
        if payload.get("version") == 2 or payload.get("schemaVersion") == 2:
            raise DiagramPayloadValidationError(["Diagram V2 thiếu engineInput."])
        return None
    engine_input = diagram.get("engineInput")
    if not isinstance(engine_input, dict):
        raise DiagramPayloadValidationError(["case_state_json.diagram.engineInput phải là object JSON."])

    stage_ids = {
        _clean_text(item.get("id"))
        for item in payload.get("stage", [])
        if isinstance(item, dict) and _clean_text(item.get("id"))
    }
    referenced_ids = {
        _clean_text(node.get("personId"))
        for node in engine_input.get("nodes", [])
        if isinstance(node, dict)
        and _clean_text(node.get("personId"))
        and not node.get("hidden")
        and not node.get("deleted")
    }
    outside_stage = sorted(referenced_ids - stage_ids)
    if outside_stage:
        raise DiagramPayloadValidationError([
            f"Diagram V2 có người không thuộc Stage: {', '.join(outside_stage)}."
        ])

    engine_result = run_inheritance_case(engine_input, customers_by_id)
    if engine_result.get("status") in {"invalid", "incomplete", "unsupported"}:
        messages = [
            _clean_text(item.get("message")) or _clean_text(item.get("code"))
            for item in engine_result.get("errors", [])
            if isinstance(item, dict)
        ]
        messages.extend(
            f"Di sản của người #{item.get('sourcePersonId')} chưa có người nhận hợp lệ."
            for item in engine_result.get("unresolvedEstates", [])
            if isinstance(item, dict)
        )
        raise DiagramPayloadValidationError(messages or ["Kết quả thừa kế chưa hoàn tất."])

    participants, participant_ids = _v2_participant_projection(
        engine_input,
        engine_result,
        customers_by_id,
        deceased_customer_id,
    )
    payload["version"] = 2
    payload["schemaVersion"] = 2
    payload["updatedAt"] = datetime.utcnow().isoformat() + "Z"
    payload["diagram"] = {
        "engineInput": engine_input,
        "engineResult": engine_result,
    }
    normalized = _normalize_case_state_json(json.dumps(payload, ensure_ascii=False))
    return normalized, participants, participant_ids, engine_result


@router.post("/diagram/calculate")
def calculate_diagram(payload: dict[str, Any], db: Session = Depends(get_db)):
    engine_input = payload.get("engineInput") if isinstance(payload.get("engineInput"), dict) else payload
    customers_by_id = {str(customer.id): customer for customer in db.query(Customer).all()}
    return run_inheritance_case(engine_input, customers_by_id)


@router.get("/")
def list_cases(request: Request, db: Session = Depends(get_db), q: str = ""):
    cases = db.query(InheritanceCase).order_by(InheritanceCase.id.desc()).all()
    if q:
        cases = [c for c in cases if q.lower() in c.nguoi_chet.ho_ten.lower()]
    return templates.TemplateResponse("cases/list.html", {"request": request, "cases": cases, "q": q})



@router.get("/create")
def create_form(request: Request, db: Session = Depends(get_db)):
    all_customers = db.query(Customer).order_by(Customer.ho_ten).all()
    # Người chết = có ngày chết
    deceased = [c for c in all_customers if c.ngay_chet is not None]
    properties = db.query(Property).order_by(Property.id.desc()).all()
    from datetime import date as _date
    form = {
        "nguoi_chet_id": "", "tai_san_id": "", "ngay_lap_ho_so": _date.today().isoformat(),
        "loai_van_ban": "khai_nhan", "ghi_chu": "", "engine_state_json": "", "diagram_payload": "", "case_state_json": ""
    }
    return _render_case_form(
        request,
        obj=None,
        deceased=deceased,
        properties=properties,
        errors=[],
        field_errors={},
        form=form,
        all_customers=all_customers,
        participants=[],
        participant_ids=set(),
        case_property_ids=[],
    )


@router.post("/create")
def create(
    request: Request,
    nguoi_chet_id: Optional[str] = Form(None),
    tai_san_id: Optional[str] = Form(None),
    property_ids: Optional[Union[List[str], str]] = Form(None),
    participant_id: Optional[Union[List[str], str]] = Form(None),
    participant_role: Optional[Union[List[str], str]] = Form(None),
    participant_share: Optional[Union[List[str], str]] = Form(None),
    participant_receive: Optional[Union[List[str], str]] = Form(None),
    participant_parent_id: Optional[Union[List[str], str]] = Form(None),
    diagram_payload: Optional[str] = Form(None),
    engine_state_json: Optional[str] = Form(None),
    case_state_json: Optional[str] = Form(None),
    db: Session = Depends(get_db)
):
    from datetime import date as _date
    form = {
        "nguoi_chet_id": (nguoi_chet_id or "").strip(),
        "tai_san_id": (tai_san_id or "").strip(),
        "diagram_payload": (diagram_payload or "").strip(),
        "engine_state_json": (engine_state_json or "").strip(),
        "case_state_json": (case_state_json or "").strip(),
    }
    selected_property_ids = _normalize_property_ids(form["tai_san_id"], property_ids)
    errors = []
    field_errors = {}
    all_customers = db.query(Customer).order_by(Customer.ho_ten).all()
    customers_by_id = {str(c.id): c for c in all_customers}
    deceased = [c for c in all_customers if c.ngay_chet is not None]
    properties = db.query(Property).order_by(Property.id.desc()).all()
    properties_by_id = {p.id: p for p in properties}
    _validate_case_refs(
        nguoi_chet_id=form["nguoi_chet_id"],
        tai_san_id=form["tai_san_id"],
        selected_property_ids=selected_property_ids,
        customers_by_id=customers_by_id,
        properties_by_id=properties_by_id,
        field_errors=field_errors,
        errors=errors,
    )
    using_v2 = False
    try:
        form["case_state_json"] = _normalize_case_state_json(form["case_state_json"])
        v2_state = _resolve_v2_case_state(
            form["case_state_json"],
            customers_by_id=customers_by_id,
            deceased_customer_id=form["nguoi_chet_id"],
        )
        if v2_state is not None:
            using_v2 = True
            form["case_state_json"], posted_participants, posted_participant_ids, _engine_result = v2_state
        else:
            posted_participants, posted_participant_ids, normalized_engine_state, normalized_payload = _resolve_posted_participants(
                all_customers=all_customers,
                deceased_customer_id=form["nguoi_chet_id"],
                diagram_payload=form["diagram_payload"],
                participant_id=participant_id,
                participant_role=participant_role,
                participant_share=participant_share,
                participant_receive=participant_receive,
                participant_parent_id=participant_parent_id,
                engine_state_json=form["engine_state_json"],
            )
            form["engine_state_json"] = normalized_engine_state or ""
            form["diagram_payload"] = normalized_payload or ""
    except DiagramPayloadValidationError as exc:
        errors.extend(exc.errors)
        if form["diagram_payload"]:
            try:
                normalized_state = _normalize_diagram_payload(form["diagram_payload"])
                form["engine_state_json"] = json.dumps(normalized_state, ensure_ascii=False)
            except DiagramPayloadValidationError:
                pass
        posted_participants, posted_participant_ids = [], set()

    if field_errors or errors:
        return _render_case_form(
            request,
            obj=None,
            deceased=deceased,
            properties=properties,
            errors=errors,
            field_errors=field_errors,
            form=form,
            all_customers=all_customers,
            participants=posted_participants,
            participant_ids=posted_participant_ids,
            case_property_ids=selected_property_ids,
        )

    try:
        case = InheritanceCase(
            nguoi_chet_id=int(form["nguoi_chet_id"]),
            tai_san_id=int(form["tai_san_id"]),
            ngay_lap_ho_so=_date.today(),
            loai_van_ban="khai_nhan",
            ghi_chu=None,
            engine_state_json=None if using_v2 else (form["engine_state_json"] or None),
            case_state_json=form["case_state_json"] or None,
        )
        db.add(case)
        db.flush()
        if selected_property_ids:
            _sync_case_property_links(db, case.id, selected_property_ids, int(form["tai_san_id"]))
        _replace_case_participants(db, case.id, posted_participants)
        db.commit()
        return RedirectResponse(f"/cases/{case.id}/edit", status_code=302)
    except Exception as e:
        db.rollback()
        errors.append(f"Lỗi tạo hồ sơ: {e}")
        return _render_case_form(
            request,
            obj=None,
            deceased=deceased,
            properties=properties,
            errors=errors,
            field_errors=field_errors,
            form=form,
            all_customers=all_customers,
            participants=posted_participants,
            participant_ids=posted_participant_ids,
            case_property_ids=selected_property_ids,
        )


@router.get("/{cid}")
def detail(cid: int, request: Request, db: Session = Depends(get_db)):
    case = db.query(InheritanceCase).filter(InheritanceCase.id == cid).first()
    if not case:
        raise HTTPException(404)
    all_customers = db.query(Customer).order_by(Customer.ho_ten).all()
    participant_ids = {p.customer_id for p in case.participants}
    available = [c for c in all_customers if c.id not in participant_ids and c.id != case.nguoi_chet_id]
    return templates.TemplateResponse("cases/detail.html", {
        "request": request, "case": case, "available": available,
        "vai_tro_options": ["Vợ/Chồng", "Con", "Cha/Mẹ", "Anh/Chị/Em"]
    })


@router.get("/{cid}/edit")
def edit_form(cid: int, request: Request, db: Session = Depends(get_db)):
    case = db.query(InheritanceCase).filter(InheritanceCase.id == cid).first()
    if not case:
        raise HTTPException(404)
    if case.is_locked:
        return RedirectResponse(f"/cases/{cid}", status_code=302)
    all_customers = db.query(Customer).order_by(Customer.ho_ten).all()
    deceased = [c for c in all_customers if c.ngay_chet is not None]
    properties = db.query(Property).order_by(Property.id.desc()).all()
    participants = case.participants
    participant_ids = {p.customer_id for p in participants}
    case_property_ids = [int(link.property_id) for link in sorted(case.property_links, key=lambda x: (not x.is_primary, x.id))]
    if not case_property_ids and case.tai_san_id:
        case_property_ids = [int(case.tai_san_id)]
    form = {
        "nguoi_chet_id": str(case.nguoi_chet_id) if case.nguoi_chet_id else "",
        "tai_san_id": str(case.tai_san_id) if case.tai_san_id else "",
        "ngay_lap_ho_so": case.ngay_lap_ho_so.isoformat() if case.ngay_lap_ho_so else "",
        "loai_van_ban": case.loai_van_ban or "khai_nhan",
        "noi_niem_yet": case.noi_niem_yet or "",
        "ghi_chu": case.ghi_chu or "",
        "engine_state_json": case.engine_state_json or "",
        "diagram_payload": case.engine_state_json or "",
        "case_state_json": case.case_state_json or _derive_case_state_json_from_participants(participants),
    }
    return _render_case_form(
        request,
        obj=case,
        deceased=deceased,
        properties=properties,
        errors=[],
        field_errors={},
        form=form,
        all_customers=all_customers,
        participants=participants,
        participant_ids=participant_ids,
        case_property_ids=case_property_ids,
    )


@router.post("/{cid}/edit")
def edit(
    cid: int, request: Request,
    nguoi_chet_id: Optional[str] = Form(None), tai_san_id: Optional[str] = Form(None),
    property_ids: Optional[Union[List[str], str]] = Form(None),
    noi_niem_yet: Optional[str] = Form(None),
    participant_id: Optional[Union[List[str], str]] = Form(None),
    participant_role: Optional[Union[List[str], str]] = Form(None),
    participant_share: Optional[Union[List[str], str]] = Form(None),
    participant_receive: Optional[Union[List[str], str]] = Form(None),
    participant_parent_id: Optional[Union[List[str], str]] = Form(None),
    diagram_payload: Optional[str] = Form(None),
    engine_state_json: Optional[str] = Form(None),
    case_state_json: Optional[str] = Form(None),
    db: Session = Depends(get_db)
):
    case = db.query(InheritanceCase).filter(InheritanceCase.id == cid).first()
    if not case or case.is_locked:
        raise HTTPException(400)
    form = {
        "nguoi_chet_id": (nguoi_chet_id or "").strip(),
        "tai_san_id": (tai_san_id or "").strip(),
        "noi_niem_yet": (noi_niem_yet or "").strip(),
        "diagram_payload": (diagram_payload or "").strip(),
        "engine_state_json": (engine_state_json or "").strip(),
        "case_state_json": (case_state_json or "").strip(),
    }
    selected_property_ids = _normalize_property_ids(form["tai_san_id"], property_ids)
    errors = []
    field_errors = {}
    all_customers = db.query(Customer).order_by(Customer.ho_ten).all()
    customers_by_id = {str(c.id): c for c in all_customers}
    deceased = [c for c in all_customers if c.ngay_chet is not None]
    properties = db.query(Property).order_by(Property.id.desc()).all()
    properties_by_id = {p.id: p for p in properties}
    _validate_case_refs(
        nguoi_chet_id=form["nguoi_chet_id"],
        tai_san_id=form["tai_san_id"],
        selected_property_ids=selected_property_ids,
        customers_by_id=customers_by_id,
        properties_by_id=properties_by_id,
        field_errors=field_errors,
        errors=errors,
    )
    using_v2 = False
    try:
        form["case_state_json"] = _normalize_case_state_json(form["case_state_json"])
        v2_state = _resolve_v2_case_state(
            form["case_state_json"],
            customers_by_id=customers_by_id,
            deceased_customer_id=form["nguoi_chet_id"],
        )
        if v2_state is not None:
            using_v2 = True
            form["case_state_json"], posted_participants, posted_participant_ids, _engine_result = v2_state
        else:
            posted_participants, posted_participant_ids, normalized_engine_state, normalized_payload = _resolve_posted_participants(
                all_customers=all_customers,
                deceased_customer_id=form["nguoi_chet_id"],
                diagram_payload=form["diagram_payload"],
                participant_id=participant_id,
                participant_role=participant_role,
                participant_share=participant_share,
                participant_receive=participant_receive,
                participant_parent_id=participant_parent_id,
                engine_state_json=form["engine_state_json"],
            )
            form["engine_state_json"] = normalized_engine_state or ""
            form["diagram_payload"] = normalized_payload or ""
    except DiagramPayloadValidationError as exc:
        errors.extend(exc.errors)
        if form["diagram_payload"]:
            try:
                normalized_state = _normalize_diagram_payload(form["diagram_payload"])
                form["engine_state_json"] = json.dumps(normalized_state, ensure_ascii=False)
            except DiagramPayloadValidationError:
                pass
        posted_participants, posted_participant_ids = [], set()
    if field_errors or errors:
        return _render_case_form(
            request,
            obj=case,
            deceased=deceased,
            properties=properties,
            errors=errors,
            field_errors=field_errors,
            form=form,
            all_customers=all_customers,
            participants=posted_participants,
            participant_ids=posted_participant_ids,
            case_property_ids=selected_property_ids,
        )

    try:
        case.nguoi_chet_id = int(form["nguoi_chet_id"])
        case.tai_san_id = int(form["tai_san_id"])
        case.noi_niem_yet = form["noi_niem_yet"] or None
        if not using_v2:
            case.engine_state_json = form["engine_state_json"] or None
        case.case_state_json = form["case_state_json"] or None
        if selected_property_ids:
            _sync_case_property_links(db, case.id, selected_property_ids, int(form["tai_san_id"]))
        _replace_case_participants(db, case.id, posted_participants)
        db.commit()
        return RedirectResponse(f"/cases/{cid}/edit", status_code=302)
    except Exception as e:
        db.rollback()
        errors.append(f"Lỗi cập nhật hồ sơ: {e}")
        return _render_case_form(
            request,
            obj=case,
            deceased=deceased,
            properties=properties,
            errors=errors,
            field_errors=field_errors,
            form=form,
            all_customers=all_customers,
            participants=posted_participants,
            participant_ids=posted_participant_ids,
            case_property_ids=selected_property_ids,
        )


@router.post("/{cid}/stage-update")
def update_stage(cid: int, case_state_json: str = Form(...), db: Session = Depends(get_db)):
    case = db.query(InheritanceCase).filter(InheritanceCase.id == cid).first()
    if not case or case.is_locked:
        raise HTTPException(400)
    try:
        normalized = _merge_case_state_stage(case.case_state_json or "", case_state_json)
    except DiagramPayloadValidationError as exc:
        return JSONResponse(
            {"ok": False, "error": "; ".join(exc.errors), "errors": exc.errors},
            status_code=400,
        )
    case.case_state_json = normalized or None
    db.commit()
    return {"ok": True, "case_state_json": normalized}


@router.post("/{cid}/diagram-update")
def update_diagram(
    cid: int,
    case_state_json: str = Form(...),
    diagram_payload: Optional[str] = Form(None),
    engine_state_json: Optional[str] = Form(None),
    db: Session = Depends(get_db),
):
    case = db.query(InheritanceCase).filter(InheritanceCase.id == cid).first()
    if not case or case.is_locked:
        raise HTTPException(400)

    try:
        normalized_case_state = _merge_case_state_diagram(case.case_state_json or "", case_state_json)
        customers_by_id = {str(customer.id): customer for customer in db.query(Customer).all()}
        v2_state = _resolve_v2_case_state(
            normalized_case_state,
            customers_by_id=customers_by_id,
            deceased_customer_id=str(case.nguoi_chet_id or ""),
        )
        if v2_state is not None:
            normalized_case_state, participants, _participant_ids, engine_result = v2_state
            case.case_state_json = normalized_case_state
            _replace_case_participants(db, case.id, participants)
            db.commit()
            return {
                "ok": True,
                "case_state_json": normalized_case_state,
                "engine_result": engine_result,
            }

        case_state_payload = _case_state_payload(normalized_case_state)
        allowed_stage_ids = {
            _clean_text((person or {}).get("id"))
            for person in case_state_payload.get("stage", [])
            if isinstance(person, dict) and _clean_text((person or {}).get("id"))
        }
        case_diagram = case_state_payload.get("diagram") if isinstance(case_state_payload.get("diagram"), dict) else {}
        case_engine_state = case_diagram.get("engineState") if isinstance(case_diagram.get("engineState"), dict) else None
        case_updated_at = _clean_text(case_diagram.get("updatedAt")) or datetime.utcnow().isoformat() + "Z"
        raw_payload = ""
        if case_engine_state is not None and case_engine_state.get("nodes") is not None:
            raw_payload = json.dumps({
                "version": 2,
                "updatedAt": case_updated_at,
                "engineState": case_engine_state,
            }, ensure_ascii=False)
        else:
            raw_payload = _clean_text(diagram_payload)
        participants: list[SimpleNamespace] = []
        normalized_engine_state = _clean_text(engine_state_json) or None
        normalized_payload = raw_payload

        if raw_payload:
            normalized_state = _normalize_diagram_payload(raw_payload)
            filtered_nodes = [
                node for node in normalized_state["nodes"]
                if (
                    (
                        not _clean_text(node.get("personId"))
                        or _clean_text(node.get("personId")) in allowed_stage_ids
                    )
                    and not (node.get("kind") == "ghost" and _clean_text(node.get("personId")))
                )
            ]
            priority_slot_ids = {"owner", "spouse", "father", "mother", "spouse_father", "spouse_mother"}
            while True:
                filtered_nodes = sorted(
                    filtered_nodes,
                    key=lambda node: (
                        0 if _clean_text(node.get("id")) in priority_slot_ids else
                        1 if _clean_text(node.get("relationType")) == "child" and _clean_text(node.get("parentSlotId")) == "owner" else
                        2 if _clean_text(node.get("relationType")) == "child" else
                        3 if _clean_text(node.get("relationType")) in {"parent", "spouseParent", "spouse", "sibling"} else
                        4 if _clean_text(node.get("relationType")) in {"branchSpouse", "grandchild"} else
                        5,
                        0 if _clean_text(node.get("parentSlotId")) == "owner" else 1,
                    ),
                )
                active_person_ids = {
                    _clean_text(node.get("personId"))
                    for node in filtered_nodes
                    if _clean_text(node.get("personId")) and not node.get("hidden") and not node.get("deleted")
                }
                node_ids = {node.get("id") for node in filtered_nodes if node.get("id")}
                pruned_nodes: list[dict[str, Any]] = []
                seen_active_people: set[str] = set()
                kept_active_people: dict[str, dict[str, Any]] = {}
                changed = False
                for node in filtered_nodes:
                    person_id = _clean_text(node.get("personId"))
                    parent_person_id = _clean_text(node.get("parentPersonId"))
                    parent_slot_id = _clean_text(node.get("parentSlotId"))
                    source_id = _clean_text(node.get("sourceId"))
                    is_active_person = bool(person_id) and not node.get("hidden") and not node.get("deleted")
                    if is_active_person and person_id in seen_active_people:
                        changed = True
                        continue
                    if parent_person_id and parent_person_id not in active_person_ids:
                        changed = True
                        continue
                    if parent_slot_id and parent_slot_id != "owner" and parent_slot_id not in node_ids:
                        changed = True
                        continue
                    if source_id and source_id != "owner" and source_id not in node_ids:
                        changed = True
                        continue
                    if is_active_person:
                        seen_active_people.add(person_id)
                        kept_active_people[person_id] = node
                    pruned_nodes.append(node)
                filtered_nodes = pruned_nodes
                if not changed:
                    break
            raw_payload = json.dumps({
                **normalized_state,
                "nodes": filtered_nodes,
            }, ensure_ascii=False)
            participants, _participant_ids, normalized_engine_state = _parse_case_diagram_payload(
                raw_payload,
                customers_by_id=customers_by_id,
                deceased_customer_id=str(case.nguoi_chet_id or ""),
            )
            normalized_payload = normalized_engine_state
            parsed_engine_state = json.loads(normalized_engine_state)
            pruned_assignments: dict[str, str] = {}
            for node in parsed_engine_state.get("nodes", []):
                slot_id = _clean_text(node.get("id"))
                person_id = _clean_text(node.get("personId"))
                if slot_id and person_id and not node.get("hidden") and not node.get("deleted"):
                    pruned_assignments[slot_id] = person_id
            normalized_case_state = _normalize_case_state_json(json.dumps({
                **case_state_payload,
                "diagram": {
                    **case_diagram,
                    "assignments": pruned_assignments,
                    "engineState": parsed_engine_state,
                    "updatedAt": parsed_engine_state.get("updatedAt") or case_updated_at,
                },
            }, ensure_ascii=False))

        case.case_state_json = normalized_case_state or None
        case.engine_state_json = normalized_engine_state or None
        _replace_case_participants(db, case.id, participants)
        db.commit()
        return {
            "ok": True,
            "case_state_json": normalized_case_state,
            "engine_state_json": normalized_engine_state or "",
            "diagram_payload": normalized_payload or "",
        }
    except DiagramPayloadValidationError as exc:
        return JSONResponse(
            {"ok": False, "error": "; ".join(exc.errors), "errors": exc.errors},
            status_code=400,
        )
    except Exception as exc:
        db.rollback()
        return JSONResponse(
            {"ok": False, "error": f"diagram_update_failed: {exc}"},
            status_code=500,
        )


@router.post("/{cid}/lock")
def lock(cid: int, db: Session = Depends(get_db)):
    case = db.query(InheritanceCase).filter(InheritanceCase.id == cid).first()
    if case:
        case.trang_thai = "locked"
        db.commit()
    return RedirectResponse(f"/cases/{cid}", status_code=302)


@router.post("/{cid}/unlock")
def unlock(cid: int, db: Session = Depends(get_db)):
    case = db.query(InheritanceCase).filter(InheritanceCase.id == cid).first()
    if case:
        case.trang_thai = "draft"
        db.commit()
    return RedirectResponse(f"/cases/{cid}", status_code=302)


@router.post("/{cid}/delete")
def delete(cid: int, db: Session = Depends(get_db)):
    case = db.query(InheritanceCase).filter(InheritanceCase.id == cid).first()
    if case and not case.is_locked:
        db.delete(case)
        db.commit()
    return RedirectResponse("/cases", status_code=302)


def _get_selected_word_template_path(db: Session) -> Optional[Path]:
    active = (
        db.query(WordTemplate)
        .filter(WordTemplate.is_active)
        .order_by(WordTemplate.id.desc())
        .first()
    )
    if active and active.duong_dan_file:
        p = Path(active.duong_dan_file)
        if p.exists():
            return p

    # Ưu tiên template PCDS V2 mới.
    default_v2 = Path("word_templates/1. PCDS .docx")
    if default_v2.exists():
        return default_v2

    template_candidates = [
        Path(r"\\maychu\D\Minh\HỒ SƠ UBND CÁC XÃ\2. Mẫu thừa kế\xã_PCDS -.docx"),
        Path("word_templates/xa_PCDS_template.docx"),
    ]
    existing_templates = [p for p in template_candidates if p.exists()]
    if not existing_templates:
        return None
    return max(existing_templates, key=lambda p: p.stat().st_mtime)


@router.get("/templates/list-json")
def list_templates_json(db: Session = Depends(get_db)):
    """API trả về danh sách template Word dạng JSON cho modal xuất văn bản."""
    items = db.query(WordTemplate).order_by(WordTemplate.id.desc()).all()
    builtin = list_public_builtin_templates(Path("word_templates"))
    return {
        "templates": [
            {"id": t.id, "ten_mau": t.ten_mau, "ten_file_goc": t.ten_file_goc, "is_active": t.is_active, "builtin": False}
            for t in items
        ] + builtin
    }


@router.get("/templates/placeholders")
def word_template_placeholders():
    catalog_path = Path("word_templates/placeholder_mapping.md")
    if not catalog_path.exists():
        raise HTTPException(status_code=404, detail="Khong tim thay catalog placeholder.")
    return PlainTextResponse(catalog_path.read_text(encoding="utf-8"), media_type="text/plain; charset=utf-8")


@router.get("/templates/manage")
def word_templates_page(request: Request, db: Session = Depends(get_db), ok: str = "", err: str = ""):
    items = db.query(WordTemplate).order_by(WordTemplate.id.desc()).all()
    return templates.TemplateResponse("cases/templates.html", {
        "request": request,
        "items": items,
        "ok": ok,
        "err": err,
    })


@router.post("/templates/manage/upload")
async def upload_word_template(
    ten_mau: str = Form(...),
    file_mau: UploadFile = File(...),
    dat_mac_dinh: Optional[str] = Form(None),
    db: Session = Depends(get_db)
):
    ten_mau = (ten_mau or "").strip()
    if not ten_mau:
        return RedirectResponse("/cases/templates/manage?err=Vui+long+nhap+ten+mau", status_code=302)
    if not file_mau or not file_mau.filename:
        return RedirectResponse("/cases/templates/manage?err=Vui+long+chon+file", status_code=302)
    if not file_mau.filename.lower().endswith(".docx"):
        return RedirectResponse("/cases/templates/manage?err=Chi+ho+tro+file+.docx", status_code=302)

    WORD_TEMPLATE_UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    saved_name = f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid4().hex[:8]}.docx"
    saved_path = WORD_TEMPLATE_UPLOAD_DIR / saved_name
    content = await file_mau.read()
    saved_path.write_bytes(content)

    set_active = str(dat_mac_dinh).lower() in ("1", "true", "on", "yes")
    if set_active:
        db.query(WordTemplate).update({WordTemplate.is_active: False})

    item = WordTemplate(
        ten_mau=ten_mau,
        ten_file_goc=file_mau.filename,
        duong_dan_file=str(saved_path),
        is_active=set_active,
    )
    db.add(item)
    db.commit()
    return RedirectResponse("/cases/templates/manage?ok=Tai+mau+thanh+cong", status_code=302)


@router.post("/templates/manage/{tid}/activate")
def activate_word_template(tid: int, db: Session = Depends(get_db)):
    item = db.query(WordTemplate).filter(WordTemplate.id == tid).first()
    if not item:
        return RedirectResponse("/cases/templates/manage?err=Khong+tim+thay+mau", status_code=302)
    db.query(WordTemplate).update({WordTemplate.is_active: False})
    item.is_active = True
    db.commit()
    return RedirectResponse("/cases/templates/manage?ok=Da+chon+mau+mac+dinh", status_code=302)


@router.post("/templates/manage/{tid}/delete")
def delete_word_template(tid: int, db: Session = Depends(get_db)):
    item = db.query(WordTemplate).filter(WordTemplate.id == tid).first()
    if not item:
        return RedirectResponse("/cases/templates/manage?err=Khong+tim+thay+mau", status_code=302)

    was_active = bool(item.is_active)
    file_path = Path(item.duong_dan_file or "")
    db.delete(item)
    db.commit()

    if file_path.exists():
        try:
            file_path.unlink()
        except Exception:
            pass

    if was_active:
        latest = db.query(WordTemplate).order_by(WordTemplate.id.desc()).first()
        if latest:
            latest.is_active = True
            db.commit()

    return RedirectResponse("/cases/templates/manage?ok=Da+xoa+mau", status_code=302)


# ── JSON API cho modal Quản lý mẫu (không rời trang) ──────────────────────────

@router.post("/templates/api/upload")
async def api_upload_template(
    ten_mau: str = Form(...),
    file_mau: UploadFile = File(...),
    dat_mac_dinh: Optional[str] = Form(None),
    db: Session = Depends(get_db)
):
    ten_mau = (ten_mau or "").strip()
    if not ten_mau:
        return JSONResponse({"ok": False, "err": "Vui lòng nhập tên mẫu"}, status_code=400)
    if not file_mau or not file_mau.filename:
        return JSONResponse({"ok": False, "err": "Vui lòng chọn file"}, status_code=400)
    if not file_mau.filename.lower().endswith(".docx"):
        return JSONResponse({"ok": False, "err": "Chỉ hỗ trợ file .docx"}, status_code=400)

    WORD_TEMPLATE_UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    saved_name = f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid4().hex[:8]}.docx"
    saved_path = WORD_TEMPLATE_UPLOAD_DIR / saved_name
    content = await file_mau.read()
    saved_path.write_bytes(content)

    set_active = str(dat_mac_dinh).lower() in ("1", "true", "on", "yes")
    if set_active:
        db.query(WordTemplate).update({WordTemplate.is_active: False})

    item = WordTemplate(
        ten_mau=ten_mau,
        ten_file_goc=file_mau.filename,
        duong_dan_file=str(saved_path),
        is_active=set_active,
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    return JSONResponse({"ok": True, "id": item.id, "ten_mau": item.ten_mau, "is_active": item.is_active})


@router.post("/templates/api/{tid}/activate")
def api_activate_template(tid: int, db: Session = Depends(get_db)):
    item = db.query(WordTemplate).filter(WordTemplate.id == tid).first()
    if not item:
        return JSONResponse({"ok": False, "err": "Không tìm thấy mẫu"}, status_code=404)
    db.query(WordTemplate).update({WordTemplate.is_active: False})
    item.is_active = True
    db.commit()
    return JSONResponse({"ok": True})


@router.post("/templates/api/{tid}/delete")
def api_delete_template(tid: int, db: Session = Depends(get_db)):
    item = db.query(WordTemplate).filter(WordTemplate.id == tid).first()
    if not item:
        return JSONResponse({"ok": False, "err": "Không tìm thấy mẫu"}, status_code=404)
    was_active = bool(item.is_active)
    file_path = Path(item.duong_dan_file or "")
    db.delete(item)
    db.commit()
    if file_path.exists():
        try:
            file_path.unlink()
        except Exception:
            pass
    if was_active:
        latest = db.query(WordTemplate).order_by(WordTemplate.id.desc()).first()
        if latest:
            latest.is_active = True
            db.commit()
    return JSONResponse({"ok": True})


def _fmt_date(d: Optional[date]) -> str:
    if not d:
        return ""
    return d.strftime("%d/%m/%Y")


def _normalize_case_state_json(raw_payload: str) -> str:
    raw_text = _clean_text(raw_payload)
    if not raw_text:
        return ""
    try:
        payload = json.loads(raw_text)
    except Exception as exc:
        raise DiagramPayloadValidationError([f"case_state_json không phải JSON hợp lệ: {exc}"])
    if not isinstance(payload, dict):
        raise DiagramPayloadValidationError(["case_state_json phải là object JSON."])
    stage = payload.get("stage", [])
    diagram = payload.get("diagram", {})
    if not isinstance(stage, list):
        raise DiagramPayloadValidationError(["case_state_json.stage phải là danh sách."])
    if not isinstance(diagram, dict):
        raise DiagramPayloadValidationError(["case_state_json.diagram phải là object JSON."])
    errors = []
    stage_ids = set()
    for index, item in enumerate(stage, start=1):
        if not isinstance(item, dict):
            errors.append(f"case_state_json.stage[{index}] phải là object JSON.")
            continue
        person_id = _clean_text(item.get("id"))
        if not person_id:
            errors.append(f"case_state_json.stage[{index}] thiếu id.")
            continue
        if person_id in stage_ids:
            errors.append(f"case_state_json.stage id trung: {person_id}")
        stage_ids.add(person_id)
    assignments = diagram.get("assignments", {})
    if assignments and not isinstance(assignments, dict):
        errors.append("case_state_json.diagram.assignments phải là object JSON.")
    if isinstance(assignments, dict):
        for slot_id, person_id in assignments.items():
            normalized_id = _clean_text(person_id)
            if normalized_id and normalized_id not in stage_ids:
                errors.append(f"case_state_json.diagram.assignments.{slot_id} reference {normalized_id} khong co trong stage.")
    engine_state = diagram.get("engineState") or {}
    nodes = engine_state.get("nodes", []) if isinstance(engine_state, dict) else []
    if isinstance(nodes, list):
        for node in nodes:
            if not isinstance(node, dict):
                continue
            nested_person = node.get("person") if isinstance(node.get("person"), dict) else {}
            person_id = _clean_text(node.get("personId") or nested_person.get("id"))
            if person_id and person_id not in stage_ids:
                errors.append(f"case_state_json.diagram.engineState node reference {person_id} khong co trong stage.")
    engine_input = diagram.get("engineInput")
    if engine_input is not None and not isinstance(engine_input, dict):
        errors.append("case_state_json.diagram.engineInput phải là object JSON.")
    engine_input_nodes = engine_input.get("nodes", []) if isinstance(engine_input, dict) else []
    if isinstance(engine_input, dict) and not isinstance(engine_input_nodes, list):
        errors.append("case_state_json.diagram.engineInput.nodes phải là danh sách.")
    if isinstance(engine_input_nodes, list):
        for node in engine_input_nodes:
            if not isinstance(node, dict):
                continue
            person_id = _clean_text(node.get("personId"))
            if person_id and person_id not in stage_ids:
                errors.append(f"case_state_json.diagram.engineInput node reference {person_id} khong co trong stage.")
    if errors:
        raise DiagramPayloadValidationError(errors)
    if isinstance(engine_state, dict):
        # Legacy browser output is never authoritative. Keep only migration
        # input and optional render metadata until the case is saved as V2.
        for key in ("edges", "allocations", "warnings", "trace"):
            engine_state.pop(key, None)
    return json.dumps(payload, ensure_ascii=False)


def _case_state_payload(raw_payload: str) -> dict[str, Any]:
    normalized = _normalize_case_state_json(raw_payload)
    if not normalized:
        return {"schemaVersion": 1, "stage": [], "diagram": {}}
    payload = json.loads(normalized)
    if not isinstance(payload, dict):
        return {"schemaVersion": 1, "stage": [], "diagram": {}}
    return payload


def _merge_case_state_diagram(existing_raw: str, submitted_raw: str) -> str:
    submitted = _case_state_payload(submitted_raw)
    existing_stage: list[Any] = []
    if _clean_text(existing_raw):
        try:
            existing = _case_state_payload(existing_raw)
            if isinstance(existing.get("stage"), list):
                existing_stage = existing["stage"]
        except DiagramPayloadValidationError:
            existing_stage = []

    merged = {
        **submitted,
        "schemaVersion": submitted.get("schemaVersion") or 1,
        "stage": existing_stage if existing_stage else submitted.get("stage", []),
        "diagram": submitted.get("diagram") if isinstance(submitted.get("diagram"), dict) else {},
    }
    return _normalize_case_state_json(json.dumps(merged, ensure_ascii=False))


def _merge_case_state_stage(existing_raw: str, submitted_raw: str) -> str:
    submitted = _case_state_payload(submitted_raw)
    if not _clean_text(existing_raw):
        return _normalize_case_state_json(json.dumps(submitted, ensure_ascii=False))
    existing = _case_state_payload(existing_raw)
    if existing.get("version") != 2 and existing.get("schemaVersion") != 2:
        return _normalize_case_state_json(json.dumps(submitted, ensure_ascii=False))
    merged = {
        **existing,
        "stage": submitted.get("stage", []),
        "diagram": existing.get("diagram", {}),
    }
    return _normalize_case_state_json(json.dumps(merged, ensure_ascii=False))


@router.get("/{cid}/export-word")
def export_word_from_template(cid: int, db: Session = Depends(get_db), template_id: Optional[str] = None):
    """Export inheritance case using the selected Word template."""
    try:
        from docx import Document
    except Exception:
        raise HTTPException(status_code=500, detail="Thieu thu vien python-docx. Vui long cai requirements.")

    case = db.query(InheritanceCase).filter(InheritanceCase.id == cid).first()
    if not case:
        raise HTTPException(404)

    # Resolve template path from template_id param
    template_path = None
    if template_id:
        if str(template_id).startswith("builtin:"):
            fname = str(template_id)[len("builtin:"):]
            p = Path("word_templates") / fname
            if p.exists():
                template_path = p
        else:
            try:
                tid = int(template_id)
                t = db.query(WordTemplate).filter(WordTemplate.id == tid).first()
                if t and t.duong_dan_file:
                    p = Path(t.duong_dan_file)
                    if p.exists():
                        template_path = p
            except (ValueError, TypeError):
                pass

    if not template_path:
        template_path = _get_selected_word_template_path(db)
    if not template_path:
        raise HTTPException(status_code=500, detail="Khong tim thay file template Word.")

    try:
        doc = Document(str(template_path))
    except Exception as ex:
        raise HTTPException(status_code=500, detail=f"Khong mo duoc template: {ex}")

    try:
        mapping = build_template_mapping(case)
    except WordExportValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    replace_in_doc(doc, mapping)
    unresolved = find_unresolved_placeholders(doc)
    if unresolved:
        raise HTTPException(
            status_code=400,
            detail="Template còn placeholder chưa được hỗ trợ: " + ", ".join(unresolved),
        )

    buf = io.BytesIO()
    doc.save(buf)
    buf.seek(0)

    filename = f"ho_so_thua_ke_{cid}.docx"
    return StreamingResponse(
        buf,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )
