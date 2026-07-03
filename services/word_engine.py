from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any


HIDDEN_BUILTIN_TEMPLATE_NAMES = {
    "system_placeholder_reference.docx",
    "system_template_chuan_v1.docx",
}


ROLE_LABELS = {
    "chu_dat": "chủ đất",
    "vo_chong": "vợ/chồng",
    "cha": "cha",
    "me": "mẹ",
    "cha_vo_chong": "cha vợ/chồng",
    "me_vo_chong": "mẹ vợ/chồng",
    "con": "con",
    "anh_chi_em": "anh/chị/em",
    "chau": "cháu",
    "vo_chong_nhanh": "vợ/chồng nhánh",
}


class WordExportValidationError(Exception):
    """Lỗi nghiệp vụ khi dữ liệu không đủ để xuất Word đúng."""


@dataclass
class WordPerson:
    id: Any = None
    ho_ten: str = ""
    gioi_tinh: str = ""
    ngay_sinh: Any = None
    ngay_chet: Any = None
    so_giay_to: str = ""
    loai_giay_to: str = ""
    ngay_cap: Any = None
    noi_cap: str = ""
    dia_chi: str = ""
    loai_dia_chi: str = ""
    role: str = ""
    inheritance_decision: str = "unset"
    is_land_owner: bool = False
    is_hidden: bool = False
    is_deleted: bool = False

    @property
    def is_deceased(self) -> bool:
        return bool(self.ngay_chet)

    @property
    def is_alive(self) -> bool:
        return not self.is_deceased

    @property
    def gender_normalized(self) -> str:
        raw = _normalize_token(self.gioi_tinh)
        if raw in {"nam", "nam"}:
            return "nam"
        if raw in {"nu", "nữ", "nu"}:
            return "nữ"
        return ""

    @property
    def address_label(self) -> str:
        return _safe_text(self.loai_dia_chi) or "Địa chỉ"


def _fmt_date(d: Any) -> str:
    if not d:
        return ""
    if isinstance(d, str):
        return d
    return d.strftime("%d/%m/%Y")


def _fmt_birth_or_year(d: Any) -> str:
    if not d:
        return ""
    if isinstance(d, str):
        return d
    if getattr(d, "day", None) == 1 and getattr(d, "month", None) == 1:
        return str(d.year)
    return _fmt_date(d)


def _safe_text(v: Any) -> str:
    if v is None:
        return ""
    return str(v).strip()


def _so_thanh_chu(so: float) -> str:
    try:
        so = float(so)
    except (TypeError, ValueError):
        return ""

    don_vi = ["không", "một", "hai", "ba", "bốn", "năm", "sáu", "bảy", "tám", "chín"]

    def _doc_ba_chu_so(n: int) -> str:
        tram = n // 100
        chuc = (n % 100) // 10
        dv = n % 10
        result = ""
        if tram:
            result += don_vi[tram] + " trăm"
            if chuc == 0 and dv:
                result += " linh " + don_vi[dv]
            elif chuc:
                result += " " + (don_vi[chuc] + " mươi" if chuc > 1 else "mườ")
                if dv == 1 and chuc > 1:
                    result += " mốt"
                elif dv == 5 and chuc > 0:
                    result += " lăm"
                elif dv:
                    result += " " + don_vi[dv]
        elif chuc:
            result += don_vi[chuc] + " mươi" if chuc > 1 else "mườ"
            if dv == 1 and chuc > 1:
                result += " mốt"
            elif dv == 5 and chuc > 0:
                result += " lăm"
            elif dv:
                result += " " + don_vi[dv]
        elif dv:
            result += don_vi[dv]
        return result.strip()

    phan_nguyen = int(so)
    phan_le_str = ""
    if so != phan_nguyen:
        le = round(so - phan_nguyen, 6)
        dec_s = f"{le:.6f}".split(".")[1].rstrip("0")
        if dec_s:
            phan_le_str = " phẩy " + " ".join(don_vi[int(d)] for d in dec_s)

    if phan_nguyen == 0:
        return ("không" + phan_le_str).strip()

    parts = []
    n = phan_nguyen
    ty = n // 1_000_000_000
    n %= 1_000_000_000
    tr = n // 1_000_000
    n %= 1_000_000
    ng = n // 1_000
    n %= 1_000

    if ty:
        parts.append(_doc_ba_chu_so(ty) + " tỷ")
    if tr:
        parts.append(_doc_ba_chu_so(tr) + " triệu")
    if ng:
        parts.append(_doc_ba_chu_so(ng) + " nghìn")
    if n:
        parts.append(_doc_ba_chu_so(n))

    return (" ".join(parts) + phan_le_str).strip()


def _normalize_token(s: str) -> str:
    s = (s or "").strip().lower()
    s = s.replace("đ", "d")
    s = unicodedata.normalize("NFKD", s)
    s = "".join(ch for ch in s if not unicodedata.combining(ch))
    s = re.sub(r"\s+", " ", s)
    return s


def _role_key(role: str) -> str:
    normalized = _normalize_token(role)
    normalized = normalized.replace("/", " ").replace("_", " ")
    normalized = re.sub(r"\s+", " ", normalized).strip()
    if normalized in {"owner", "chu dat"}:
        return "chu_dat"
    if normalized in {"vo chong"}:
        return "vo_chong"
    if normalized == "cha":
        return "cha"
    if normalized in {"me", "me"}:
        return "me"
    if normalized in {"cha vc", "cha vo chong"}:
        return "cha_vo_chong"
    if normalized in {"me vc", "me vo chong"}:
        return "me_vo_chong"
    if normalized == "con":
        return "con"
    if normalized in {"anh chi em"}:
        return "anh_chi_em"
    if normalized in {"chau"}:
        return "chau"
    if normalized in {"con dau re", "vo chong nhanh"}:
        return "vo_chong_nhanh"
    return normalized.replace(" ", "_")


def _display_document_type(raw: str) -> str:
    raw = _safe_text(raw)
    if raw == "thoa_thuan":
        return "Thỏa thuận phân chia di sản"
    if raw == "khai_nhan":
        return "Văn bản khai nhận di sản thừa kế"
    return raw


def _format_share(value: Any) -> str:
    try:
        number = float(value or 0)
    except (TypeError, ValueError):
        return ""
    if number.is_integer():
        return str(int(number))
    return f"{number:g}"


def _receive_status(participant: Any) -> str:
    if participant is None:
        return ""
    return "Nhận di sản" if bool(getattr(participant, "co_nhan_tai_san", False)) else "Từ chối nhận di sản"


def _add_person_placeholders(
    mapping: dict[str, str],
    label: str,
    customer: Any,
    participant: Any = None,
) -> None:
    prefix = label.strip()
    mapping[f"[Họ tên {prefix}]"] = _safe_text(getattr(customer, "ho_ten", ""))
    mapping[f"[Giới tính {prefix}]"] = _safe_text(getattr(customer, "gioi_tinh", ""))
    mapping[f"[Ngày sinh {prefix}]"] = _fmt_date(getattr(customer, "ngay_sinh", None))
    mapping[f"[Năm sinh {prefix}]"] = _fmt_birth_or_year(getattr(customer, "ngay_sinh", None))
    mapping[f"[Ngày chết {prefix}]"] = _fmt_date(getattr(customer, "ngay_chet", None))
    mapping[f"[Năm chết {prefix}]"] = _fmt_date(getattr(customer, "ngay_chet", None))
    mapping[f"[Số giấy tờ {prefix}]"] = _safe_text(getattr(customer, "so_giay_to", ""))
    mapping[f"[Loại giấy tờ {prefix}]"] = _safe_text(getattr(customer, "loai_giay_to", ""))
    mapping[f"[Ngày cấp {prefix}]"] = _fmt_date(getattr(customer, "ngay_cap", None))
    mapping[f"[Nơi cấp {prefix}]"] = _safe_text(getattr(customer, "noi_cap", ""))
    mapping[f"[Địa chỉ {prefix}]"] = _safe_text(getattr(customer, "dia_chi", ""))
    mapping[f"[Nhãn địa chỉ {prefix}]"] = _safe_text(getattr(customer, "loai_dia_chi", ""))
    mapping[f"[Vai trò {prefix}]"] = _safe_text(getattr(participant, "vai_tro", "")) if participant else ""
    mapping[f"[Hàng thừa kế {prefix}]"] = _safe_text(getattr(participant, "hang_thua_ke", "")) if participant else ""
    mapping[f"[Trạng thái nhận/từ chối {prefix}]"] = _receive_status(participant)
    mapping[f"[Tỷ lệ nhận {prefix}]"] = _format_share(getattr(participant, "ty_le", "")) if participant else ""


def _empty_person_placeholders(mapping: dict[str, str], label: str) -> None:
    _add_person_placeholders(mapping, label, None, None)


def _add_indexed_people(mapping: dict[str, str], label: str, people: list[tuple[Any, Any]], limit: int = 20) -> None:
    for index in range(1, limit + 1):
        if index <= len(people):
            customer, participant = people[index - 1]
            _add_person_placeholders(mapping, f"{label} {index}", customer, participant)
        else:
            _empty_person_placeholders(mapping, f"{label} {index}")


def _pick_core_people(case: Any) -> tuple[Any, Any, Any, list[Any]]:
    owner = getattr(case, "nguoi_chet", None)
    spouse = None
    for p in getattr(case, "participants", []) or []:
        if _role_key(getattr(p, "vai_tro", "")) == "vo_chong":
            spouse = getattr(p, "customer", None)
            break

    pair = [c for c in [owner, spouse] if c is not None]
    nam = [c for c in pair if _normalize_token(getattr(c, "gioi_tinh", "")) == "nam"]
    nu = [c for c in pair if _normalize_token(getattr(c, "gioi_tinh", "")) in {"nu", "nữ"}]

    if len(nam) == 1 and len(nu) == 1:
        person1 = nam[0]
        person2 = nu[0]
    elif len(pair) == 2:
        person1 = pair[0]
        person2 = pair[1]
    elif len(pair) == 1:
        person1 = pair[0]
        person2 = None
    else:
        person1 = None
        person2 = None

    excluded_ids = {getattr(c, "id", None) for c in [person1, person2] if c is not None}
    receivers = [
        p for p in getattr(case, "participants", []) or []
        if getattr(p, "co_nhan_tai_san", False) and getattr(p, "customer_id", None) not in excluded_ids
    ]
    receivers = sorted(receivers, key=lambda p: (-(getattr(p, "ty_le", 0) or 0), getattr(p, "customer_id", 0) or 0))
    non_receivers = [
        p for p in getattr(case, "participants", []) or []
        if not getattr(p, "co_nhan_tai_san", False) and getattr(p, "customer_id", None) not in excluded_ids
    ]
    non_receivers = sorted(non_receivers, key=lambda p: getattr(p, "customer_id", 0) or 0)

    person3 = getattr(receivers[0], "customer", None) if receivers else None
    people_4_plus = [p.customer for p in receivers[1:]] + [p.customer for p in non_receivers]
    return person1, person2, person3, people_4_plus


def _parse_land_rows(raw: str) -> list[dict[str, Any]]:
    if not raw:
        return []
    try:
        rows = json.loads(raw)
    except Exception:
        return []
    if not isinstance(rows, list):
        return []
    return [row for row in rows if isinstance(row, dict)]


def _person_pairs(participants: list[Any]) -> list[tuple[Any, Any]]:
    return [(getattr(p, "customer", None), p) for p in participants if getattr(p, "customer", None) is not None]


def _data_line(customer: Any, participant: Any = None) -> str:
    name = _safe_text(getattr(customer, "ho_ten", ""))
    parts = [name]
    born = _fmt_birth_or_year(getattr(customer, "ngay_sinh", None))
    doc_no = _safe_text(getattr(customer, "so_giay_to", ""))
    role = _safe_text(getattr(participant, "vai_tro", "")) if participant else ""
    share = _format_share(getattr(participant, "ty_le", "")) if participant else ""
    status = _receive_status(participant)
    if born:
        parts.append(f"sinh {born}")
    if doc_no:
        parts.append(f"số giấy tờ {doc_no}")
    if role:
        parts.append(f"vai trò {role}")
    if status:
        parts.append(status.lower())
    if share:
        parts.append(f"tỷ lệ {share}%")
    return " - ".join(part for part in parts if part)


def _data_list(items: list[tuple[Any, Any]]) -> str:
    return "\n".join(f"{index}. {_data_line(customer, participant)}" for index, (customer, participant) in enumerate(items, start=1))


def _build_grouped_people(case: Any) -> dict[str, list[tuple[Any, Any]]]:
    owner = getattr(case, "nguoi_chet", None)
    owner_id = getattr(owner, "id", None)
    role_groups: dict[str, list[tuple[Any, Any]]] = {key: [] for key in ROLE_LABELS}
    if owner is not None:
        role_groups["chu_dat"].append((owner, None))

    for participant in getattr(case, "participants", []) or []:
        customer = getattr(participant, "customer", None)
        if customer is None:
            continue
        key = _role_key(getattr(participant, "vai_tro", ""))
        if key in role_groups:
            role_groups[key].append((customer, participant))

    spouse_ids = {getattr(customer, "id", None) for customer, _ in role_groups["vo_chong"]}
    excluded = {owner_id, *spouse_ids}
    participants = list(getattr(case, "participants", []) or [])
    role_groups["nguoi_nhan"] = _person_pairs([
        p for p in participants
        if getattr(p, "co_nhan_tai_san", False) and getattr(p, "customer_id", None) not in excluded
    ])
    role_groups["nguoi_tu_choi"] = _person_pairs([
        p for p in participants
        if not getattr(p, "co_nhan_tai_san", False) and getattr(p, "customer_id", None) not in excluded
    ])
    role_groups["nguoi_thua_ke"] = ([(owner, None)] if owner is not None else []) + _person_pairs(participants)
    return role_groups


# ---------------------------------------------------------------------------
# Word export V2: case_state_json-aware helpers
# ---------------------------------------------------------------------------


def _load_case_state(case: Any) -> dict[str, Any]:
    raw = _safe_text(getattr(case, "case_state_json", ""))
    if not raw:
        return {}
    try:
        payload = json.loads(raw)
    except Exception:
        return {}
    if not isinstance(payload, dict):
        return {}
    return payload


def _word_person_from_stage(stage_person: dict[str, Any]) -> WordPerson:
    return WordPerson(
        id=_safe_text(stage_person.get("id")),
        ho_ten=_safe_text(stage_person.get("ho_ten")),
        gioi_tinh=_safe_text(stage_person.get("gioi_tinh")),
        ngay_sinh=stage_person.get("ngay_sinh") or None,
        ngay_chet=stage_person.get("ngay_chet") or None,
        so_giay_to=_safe_text(stage_person.get("so_giay_to")),
        loai_giay_to=_safe_text(stage_person.get("loai_giay_to")),
        ngay_cap=stage_person.get("ngay_cap") or None,
        noi_cap=_safe_text(stage_person.get("noi_cap")),
        dia_chi=_safe_text(stage_person.get("dia_chi")),
        loai_dia_chi=_safe_text(stage_person.get("loai_dia_chi", stage_person.get("place_of_origin"))),
    )


def _word_person_from_customer(customer: Any) -> WordPerson:
    return WordPerson(
        id=getattr(customer, "id", None),
        ho_ten=_safe_text(getattr(customer, "ho_ten", "")),
        gioi_tinh=_safe_text(getattr(customer, "gioi_tinh", "")),
        ngay_sinh=getattr(customer, "ngay_sinh", None),
        ngay_chet=getattr(customer, "ngay_chet", None),
        so_giay_to=_safe_text(getattr(customer, "so_giay_to", "")),
        loai_giay_to=_safe_text(getattr(customer, "loai_giay_to", "")),
        ngay_cap=getattr(customer, "ngay_cap", None),
        noi_cap=_safe_text(getattr(customer, "noi_cap", "")),
        dia_chi=_safe_text(getattr(customer, "dia_chi", "")),
        loai_dia_chi=_safe_text(getattr(customer, "loai_dia_chi", "")),
    )


def _apply_diagram_nodes(persons: list[WordPerson], nodes: list[dict[str, Any]]) -> list[WordPerson]:
    if not nodes:
        return persons
    by_id = {str(p.id): p for p in persons if p.id is not None}
    for node in nodes:
        if not isinstance(node, dict):
            continue
        person_id = _safe_text(node.get("personId") or (node.get("person") or {}).get("id"))
        if not person_id or person_id not in by_id:
            continue
        p = by_id[person_id]
        p.role = _safe_text(node.get("role")) or p.role
        p.inheritance_decision = _safe_text(node.get("inheritanceDecision")) or p.inheritance_decision
        p.is_land_owner = bool(node.get("isLandOwner", False))
        p.is_hidden = bool(node.get("hidden", False))
        p.is_deleted = bool(node.get("deleted", False))
    return persons


def _build_word_persons(case: Any) -> list[WordPerson]:
    state = _load_case_state(case)
    has_state = bool(state)
    stage = state.get("stage", []) if has_state else []
    diagram = state.get("diagram", {}) if has_state and isinstance(state.get("diagram"), dict) else {}
    engine_state = diagram.get("engineState", {}) if isinstance(diagram.get("engineState"), dict) else {}
    nodes = engine_state.get("nodes", []) if isinstance(engine_state.get("nodes"), list) else []

    persons: list[WordPerson] = []
    owner = getattr(case, "nguoi_chet", None)

    if has_state and isinstance(stage, list):
        for item in stage:
            if isinstance(item, dict):
                persons.append(_word_person_from_stage(item))

    # Đảm bảo ngườ chết của hồ sơ luôn có mặt trong danh sách để xử lý chủ đất.
    if owner is not None:
        owner_id = str(getattr(owner, "id", ""))
        existing = next((p for p in persons if str(p.id) == owner_id), None)
        if existing is None:
            owner_wp = _word_person_from_customer(owner)
            owner_wp.is_land_owner = True
            persons.append(owner_wp)
        else:
            existing.is_land_owner = True

    if has_state:
        persons = _apply_diagram_nodes(persons, nodes)

    # Fallback về participants cũ khi không có case_state_json hợp lệ.
    if not has_state:
        for participant in getattr(case, "participants", []) or []:
            customer = getattr(participant, "customer", None)
            if customer is None:
                continue
            wp = _word_person_from_customer(customer)
            wp.role = _safe_text(getattr(participant, "vai_tro", ""))
            wp.inheritance_decision = "accept" if bool(getattr(participant, "co_nhan_tai_san", False)) else "refuse"
            persons.append(wp)

    return persons


def _active_persons(persons: list[WordPerson]) -> list[WordPerson]:
    return [p for p in persons if not p.is_hidden and not p.is_deleted]


def _landowners(persons: list[WordPerson]) -> list[WordPerson]:
    return [p for p in _active_persons(persons) if p.is_land_owner]


def _deceased_landowners(persons: list[WordPerson]) -> list[WordPerson]:
    return [p for p in _landowners(persons) if p.is_deceased]


def _receivers(persons: list[WordPerson]) -> list[WordPerson]:
    return [p for p in _active_persons(persons) if p.inheritance_decision == "accept" and p.is_alive]


def _unset_people(persons: list[WordPerson]) -> list[WordPerson]:
    return [p for p in _active_persons(persons) if p.inheritance_decision == "unset" and p.is_alive]


def _refused_people(persons: list[WordPerson]) -> list[WordPerson]:
    return [p for p in _active_persons(persons) if p.inheritance_decision == "refuse" and p.is_alive]


def _children(persons: list[WordPerson]) -> list[WordPerson]:
    return [p for p in _active_persons(persons) if _role_key(p.role) == "con" and p.is_alive]


def _spouses_of(persons: list[WordPerson], target: WordPerson) -> list[WordPerson]:
    return [p for p in _active_persons(persons) if _role_key(p.role) == "vo_chong" and p.id != target.id]


def _title_for_person(person: WordPerson) -> str:
    if person.gender_normalized == "nam":
        return "ông"
    if person.gender_normalized == "nữ":
        return "bà"
    return "ông/bà"


def _format_name_list(people: list[WordPerson]) -> str:
    if not people:
        return ""
    parts = [f"{_title_for_person(p)} {p.ho_ten}".strip() for p in people if p.ho_ten]
    if len(parts) == 1:
        return parts[0]
    if len(parts) == 2:
        return f"{parts[0]} và {parts[1]}"
    return ", ".join(parts[:-1]) + f" và {parts[-1]}"


def _format_simple_name_list(people: list[WordPerson]) -> str:
    if not people:
        return ""
    names = [p.ho_ten for p in people if p.ho_ten]
    if len(names) == 1:
        return names[0]
    if len(names) == 2:
        return f"{names[0]} và {names[1]}"
    return ", ".join(names[:-1]) + f" và {names[-1]}"


def _deceased_landowner_clauses(people: list[WordPerson]) -> str:
    lines = []
    for p in people:
        title = _title_for_person(p)
        born = _fmt_birth_or_year(p.ngay_sinh)
        died = _fmt_date(p.ngay_chet)
        doc_no = _safe_text(p.so_giay_to)
        issued = _fmt_date(p.ngay_cap)
        address = _safe_text(p.dia_chi)
        line = f"{title} {p.ho_ten}"
        if born:
            line += f"; Sinh năm: {born}"
        line += f"; chết ngày {died} theo Trích lục khai tử (Bản sao) số {doc_no} do Ủy ban nhân dân xã [Nơi niêm yết], tỉnh Ninh Bình ký ngày {issued}. Nơi chết: {address}."
        lines.append(line)
    return "\n".join(lines)


def _family_relation_clauses(deceased_landowners: list[WordPerson], persons: list[WordPerson]) -> str:
    paragraphs = []
    for owner in deceased_landowners:
        title = _title_for_person(owner)
        spouses = _spouses_of(persons, owner)
        if spouses:
            spouse = spouses[0]
            spouse_title = _title_for_person(spouse)
            paragraphs.append(f"{title} {owner.ho_ten} có vợ/chồng là {spouse_title} {spouse.ho_ten}.")
        children = _children(persons)
        if children:
            child_lines = []
            for child in children:
                if child.inheritance_decision == "refuse":
                    child_lines.append(
                        f"{child.ho_ten} đã từ chối di sản theo Văn bản từ chối nhận di sản số ......................... ."
                    )
                else:
                    child_lines.append(child.ho_ten)
            child_text = "; ".join(child_lines)
            paragraphs.append(f"{title} {owner.ho_ten} có {len(children)} ngườ con là: {child_text}.")
    return "\n".join(paragraphs)


def _get_property_list(case: Any) -> list[Any]:
    links = getattr(case, "property_links", None)
    if links:
        ordered = sorted(links, key=lambda x: (not bool(getattr(x, "is_primary", False)), getattr(x, "id", 0)))
        props = [getattr(link, "property", None) for link in ordered]
        props = [p for p in props if p is not None]
        if props:
            return props
    ts = getattr(case, "tai_san", None)
    if ts is not None:
        return [ts]
    return []


def _property_description(properties: list[Any]) -> str:
    if not properties:
        return ""
    paragraphs = []
    for idx, prop in enumerate(properties, start=1):
        loai_so = _safe_text(getattr(prop, "loai_so", "")) or "Giấy chứng nhận quyền sử dụng đất"
        serial = _safe_text(getattr(prop, "so_serial", ""))
        so_vao_so = _safe_text(getattr(prop, "so_vao_so", ""))
        so_thua = _safe_text(getattr(prop, "so_thua_dat", ""))
        so_to = _safe_text(getattr(prop, "so_to_ban_do", ""))
        dia_chi = _safe_text(getattr(prop, "dia_chi", ""))
        co_quan_cap = _safe_text(getattr(prop, "co_quan_cap", ""))
        ngay_cap = _fmt_date(getattr(prop, "ngay_cap", None))

        header = f"{idx}. Quyền sử dụng đất tại: {dia_chi} theo {loai_so} số: {serial}; Số vào sổ cấp GCN: {so_vao_so} do {co_quan_cap} cấp ngày {ngay_cap}."
        paragraphs.append(header)

        detail = f"Thửa đất số: {so_thua}, tờ bản đồ số: {so_to}."
        paragraphs.append(detail)

        land_rows = _parse_land_rows(_safe_text(getattr(prop, "land_rows_json", "")))
        if not land_rows:
            land_rows = [{
                "loai_dat": _safe_text(getattr(prop, "loai_dat", "")),
                "dien_tich": _safe_text(getattr(prop, "dien_tich", "")),
                "thoi_han": _safe_text(getattr(prop, "thoi_han", "")),
            }]

        total_area = 0.0
        for row in land_rows:
            try:
                total_area += float(row.get("dien_tich") or 0)
            except (TypeError, ValueError):
                pass
        area_str = f"{total_area:g}" if total_area else _safe_text(getattr(prop, "dien_tich", ""))
        paragraphs.append(f"Diện tích: {area_str} m2")
        paragraphs.append(f"Hình thức sử dụng: {_safe_text(getattr(prop, 'hinh_thuc_su_dung', ''))}")

        land_type_lines = []
        for m_idx, row in enumerate(land_rows, start=1):
            loai_dat = _safe_text(row.get("loai_dat", ""))
            dien_tich = _safe_text(row.get("dien_tich", ""))
            thoi_han = _safe_text(row.get("thoi_han", ""))
            if not loai_dat and not dien_tich:
                continue
            land_type_lines.append(f"{idx}.{m_idx}. {loai_dat}: {dien_tich} m2 ({thoi_han})")
        if land_type_lines:
            paragraphs.append("\n".join(land_type_lines))

        paragraphs.append(f"Thờ hạn sử dụng: {_safe_text(getattr(prop, 'thoi_han', ''))}")
        paragraphs.append(f"Nguồn gốc sử dụng đất: {_safe_text(getattr(prop, 'nguon_goc', ''))}.")
    return "\n".join(paragraphs)


def _division_clause(
    deceased_landowners: list[WordPerson],
    receivers: list[WordPerson],
    unset_people: list[WordPerson],
    refused_people: list[WordPerson],
    persons: list[WordPerson],
) -> str:
    if not receivers:
        raise WordExportValidationError("Không có ngườ nhận di sản (accept) để xuất văn bản phân chia.")

    deceased_names = _format_name_list(deceased_landowners)
    receiver_names = _format_name_list(receivers)
    unset_names = _format_name_list(unset_people)
    simple_receiver_names = _format_simple_name_list(receivers)

    # Ngườ nhận + ngườ chưa chọn (không bao gồm chủ đất còn sống chưa chọn ở đây nếu họ là chủ đất)
    opening_group = _format_name_list(receivers + [p for p in unset_people if not p.is_land_owner])

    paragraphs = []
    paragraphs.append(
        f"Chúng tôi gồm: {opening_group} là những ngườ thừa kế theo pháp luật của {deceased_names}. "
        "Bằng văn bản này chúng tôi thống nhất phân chia như sau:"
    )

    if unset_names:
        paragraphs.append(
            f"Chúng tôi - {unset_names} tự nguyện tặng cho toàn bộ quyền hưởng di sản thừa kế của mình "
            f"được thụ hưởng từ {deceased_names} cho {receiver_names}."
        )

    living_landowner_unset = [p for p in unset_people if p.is_land_owner]
    if living_landowner_unset:
        donor_names = _format_name_list(living_landowner_unset)
        paragraphs.append(
            f"Đồng thở, tôi/chúng tôi - {donor_names} tự nguyện tặng cho phần quyền sử dụng đất "
            f"thuộc quyền sử dụng của mình cho {receiver_names}."
        )

    paragraphs.append(
        f"{simple_receiver_names} đồng ý nhận phần di sản và phần quyền sử dụng đất được tặng cho "
        "theo nội dung thỏa thuận phân chia di sản thừa kế ở trên."
    )

    return "\n".join(paragraphs)


def _heir_note(person: WordPerson) -> str:
    if person.inheritance_decision == "refuse":
        return "Đã từ chối nhận di sản"
    if person.inheritance_decision == "unset":
        return "Chưa chọn/Thỏa thuận tặng cho"
    if person.inheritance_decision == "accept":
        return "Nhận tài sản"
    return ""


def _role_note(person: WordPerson) -> str:
    role = _role_key(person.role)
    if role == "vo_chong":
        if person.gender_normalized == "nam":
            return "Là chồng"
        return "Là vợ"
    if role == "con":
        return "Là con"
    return ""


def _combined_heir_note(person: WordPerson) -> str:
    parts = [p for p in [_role_note(person), _heir_note(person)] if p]
    return "; ".join(parts)


def _add_block_placeholders(mapping: dict[str, str], case: Any, persons: list[WordPerson]) -> None:
    active = _active_persons(persons)
    deceased_landowners = _deceased_landowners(active)
    receivers = _receivers(active)
    unset_people = _unset_people(active)
    refused_people = _refused_people(active)

    if not deceased_landowners:
        raise WordExportValidationError("Không xác định được chủ đất đã chết để xuất văn bản.")

    # Cụm ngườ để lại di sản
    mapping["[Cụm ngườ để lại di sản]"] = _format_name_list(deceased_landowners)

    # Danh sách ngườ nhận và chưa chọn (mở đầu)
    opening_group = receivers + [p for p in unset_people if not p.is_land_owner]
    mapping["[Danh sách ngườ nhận và chưa chọn]"] = _format_name_list(opening_group)

    # Đoạn ngườ chết là chủ đất
    mapping["[Đoạn ngườ chết là chủ đất]"] = _deceased_landowner_clauses(deceased_landowners)

    # Đoạn quan hệ gia đình
    mapping["[Đoạn quan hệ gia đình]"] = _family_relation_clauses(deceased_landowners, active)

    # Đoạn mô tả di sản
    properties = _get_property_list(case)
    mapping["[Đoạn mô tả di sản]"] = _property_description(properties)

    # Đoạn phân chia di sản
    mapping["[Đoạn phân chia di sản]"] = _division_clause(
        deceased_landowners, receivers, unset_people, refused_people, active
    )

    # Danh sách ngườ ký
    signers = receivers + [p for p in unset_people if not p.is_land_owner]
    mapping["[Danh sách ngườ ký]"] = _format_simple_name_list(signers)

    # Danh sách hàng thừa kế
    heir_rows = [p for p in active if _role_key(p.role) != "chu_dat"]
    mapping["[Danh sách hàng thừa kế]"] = _format_simple_name_list(heir_rows)

    # Bảng hàng thừa kế 20 dòng
    if len(heir_rows) > 20:
        raise WordExportValidationError(
            f"Danh sách hàng thừa kế vượt quá 20 ngườ (hiện có {len(heir_rows)})."
        )
    for idx in range(1, 21):
        if idx <= len(heir_rows):
            p = heir_rows[idx - 1]
            mapping[f"[Họ tên hàng thừa kế {idx}]"] = p.ho_ten
            mapping[f"[Năm sinh hàng thừa kế {idx}]"] = _fmt_birth_or_year(p.ngay_sinh)
            mapping[f"[Địa chỉ hàng thừa kế {idx}]"] = p.dia_chi
            mapping[f"[Ghi chú hàng thừa kế {idx}]"] = _combined_heir_note(p)
        else:
            mapping[f"[Họ tên hàng thừa kế {idx}]"] = ""
            mapping[f"[Năm sinh hàng thừa kế {idx}]"] = ""
            mapping[f"[Địa chỉ hàng thừa kế {idx}]"] = ""
            mapping[f"[Ghi chú hàng thừa kế {idx}]"] = ""

    # Bảng ngườ ký 20 dòng
    if len(signers) > 20:
        raise WordExportValidationError(
            f"Danh sách ngườ ký vượt quá 20 ngườ (hiện có {len(signers)})."
        )
    for idx in range(1, 21):
        if idx <= len(signers):
            mapping[f"[Họ tên ngườ ký {idx}]"] = signers[idx - 1].ho_ten
        else:
            mapping[f"[Họ tên ngườ ký {idx}]"] = ""


def _add_property_placeholders(mapping: dict[str, str], case: Any) -> None:
    properties = _get_property_list(case)
    if len(properties) > 5:
        raise WordExportValidationError(
            f"Vượt quá 5 tài sản (hiện có {len(properties)}). Vui lòng giảm số lượng tài sản trước khi xuất Word."
        )

    for idx in range(1, 6):
        if idx <= len(properties):
            prop = properties[idx - 1]
            land_rows = _parse_land_rows(_safe_text(getattr(prop, "land_rows_json", "")))
            if not land_rows:
                land_rows = [{
                    "loai_dat": _safe_text(getattr(prop, "loai_dat", "")),
                    "dien_tich": _safe_text(getattr(prop, "dien_tich", "")),
                    "thoi_han": _safe_text(getattr(prop, "thoi_han", "")),
                }]
            total_area = 0.0
            for row in land_rows:
                try:
                    total_area += float(row.get("dien_tich") or 0)
                except (TypeError, ValueError):
                    pass
            area_str = f"{total_area:g}" if total_area else _safe_text(getattr(prop, "dien_tich", ""))

            mapping[f"[Địa chỉ tài sản {idx}]"] = _safe_text(getattr(prop, "dia_chi", ""))
            mapping[f"[Loại sổ tài sản {idx}]"] = _safe_text(getattr(prop, "loai_so", "")) or "Giấy chứng nhận quyền sử dụng đất"
            mapping[f"[Serial tài sản {idx}]"] = _safe_text(getattr(prop, "so_serial", ""))
            mapping[f"[Số vào sổ tài sản {idx}]"] = _safe_text(getattr(prop, "so_vao_so", ""))
            mapping[f"[Số thửa tài sản {idx}]"] = _safe_text(getattr(prop, "so_thua_dat", ""))
            mapping[f"[Số tờ tài sản {idx}]"] = _safe_text(getattr(prop, "so_to_ban_do", ""))
            mapping[f"[Diện tích tài sản {idx}]"] = area_str

            for m_idx in range(1, 11):
                if m_idx <= len(land_rows):
                    row = land_rows[m_idx - 1]
                    mapping[f"[Loại đất tài sản {idx}.{m_idx}]"] = _safe_text(row.get("loai_dat", ""))
                    mapping[f"[Diện tích loại đất tài sản {idx}.{m_idx}]"] = _safe_text(row.get("dien_tích", row.get("dien_tich", "")))
                    mapping[f"[Thờ hạn loại đất tài sản {idx}.{m_idx}]"] = _safe_text(row.get("thoi_han", ""))
                else:
                    mapping[f"[Loại đất tài sản {idx}.{m_idx}]"] = ""
                    mapping[f"[Diện tích loại đất tài sản {idx}.{m_idx}]"] = ""
                    mapping[f"[Thờ hạn loại đất tài sản {idx}.{m_idx}]"] = ""
        else:
            mapping[f"[Địa chỉ tài sản {idx}]"] = ""
            mapping[f"[Loại sổ tài sản {idx}]"] = ""
            mapping[f"[Serial tài sản {idx}]"] = ""
            mapping[f"[Số vào sổ tài sản {idx}]"] = ""
            mapping[f"[Số thửa tài sản {idx}]"] = ""
            mapping[f"[Số tờ tài sản {idx}]"] = ""
            mapping[f"[Diện tích tài sản {idx}]"] = ""
            for m_idx in range(1, 11):
                mapping[f"[Loại đất tài sản {idx}.{m_idx}]"] = ""
                mapping[f"[Diện tích loại đất tài sản {idx}.{m_idx}]"] = ""
                mapping[f"[Thờ hạn loại đất tài sản {idx}.{m_idx}]"] = ""


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def build_template_mapping(case: Any, today: date | None = None) -> dict[str, str]:
    ts = getattr(case, "tai_san", None)
    today = today or date.today()
    person1, person2, person3, people_4_plus = _pick_core_people(case)

    people_slots = [None] * 21
    people_slots[1] = person1
    people_slots[2] = person2
    people_slots[3] = person3
    for idx, c in enumerate(people_4_plus[:17], start=4):
        people_slots[idx] = c

    noi_niem_yet = _safe_text(getattr(case, "noi_niem_yet", "")) or _safe_text(getattr(ts, "dia_chi", ""))
    land_rows = _parse_land_rows(_safe_text(getattr(ts, "land_rows_json", "")))
    if land_rows:
        total = 0.0
        for row in land_rows:
            try:
                total += float(row.get("dien_tich") or 0)
            except (TypeError, ValueError):
                pass
        dien_tich_so = total if total > 0 else getattr(ts, "dien_tich", None)
    else:
        dien_tich_so = getattr(ts, "dien_tich", None)
    dien_tich_str = f"{dien_tich_so:g}" if dien_tich_so else ""
    dien_tich_chu = _so_thanh_chu(dien_tich_so).capitalize() if dien_tich_so else ""
    loai_so_val = _safe_text(getattr(ts, "loai_so", "")) or "Giấy chứng nhận quyền sử dụng đất"
    loai_van_ban = _display_document_type(getattr(case, "loai_van_ban", ""))

    mapping: dict[str, str] = {
        "[Tên file]": f"ho_so_thua_ke_{getattr(case, 'id', '')}",
        "[Loại văn bản]": loai_van_ban,
        "[Ngày lập hồ sơ]": _fmt_date(getattr(case, "ngay_lap_ho_so", None)),
        "[Nơi niêm yết]": noi_niem_yet,
        "[Ghi chú]": _safe_text(getattr(case, "ghi_chu", "")),
        "[Niêm Yết]": noi_niem_yet,
        "[NIÊM YẾT]": noi_niem_yet.upper() if noi_niem_yet else "",
        "[Loại sổ]": loai_so_val,
        "[Địa chỉ đất]": _safe_text(getattr(ts, "dia_chi", "")),
        "[Số serial]": _safe_text(getattr(ts, "so_serial", "")),
        "[Serial]": _safe_text(getattr(ts, "so_serial", "")),
        "[Số vào sổ]": _safe_text(getattr(ts, "so_vao_so", "")),
        "[Số thửa]": _safe_text(getattr(ts, "so_thua_dat", "")),
        "[Số tờ]": _safe_text(getattr(ts, "so_to_ban_do", "")),
        "[Số tờ bản đồ]": _safe_text(getattr(ts, "so_to_ban_do", "")),
        "[Diện tích]": dien_tich_str,
        "[Diện tích chữ]": dien_tich_chu,
        "[Hình thức sử dụng]": _safe_text(getattr(ts, "hinh_thuc_su_dung", "")),
        "[Loại đất]": _safe_text(getattr(ts, "loai_dat", "")),
        "[Thờ hạn]": _safe_text(getattr(ts, "thoi_han", "")),
        "[Nguồn gốc]": _safe_text(getattr(ts, "nguon_goc", "")),
        "[Ngày cấp sổ]": _fmt_date(getattr(ts, "ngay_cap", None)),
        "[Cơ quan cấp sổ]": _safe_text(getattr(ts, "co_quan_cap", "")),
        "[Ngày]": str(today.day),
        "[Tháng]": f"{today.month:02d}",
        "[Ngày chữ]": _so_thanh_chu(today.day),
        "[Tháng chữ]": _so_thanh_chu(today.month),
        "[Ngườ ủy quyền]": "",
        "[Ngườ ủy quyền2]": "",
        "[Số công chứng]": "",
        "[ONT]": "",
        "[CLN]": "",
        "[NTS]": "",
        "[LUC]": "",
        "[Giá chuyển nhượng]": "",
        "[SĐT]": "",
    }

    for i in range(1, 21):
        c = people_slots[i]
        mapping[f"[Tên {i}]"] = _safe_text(getattr(c, "ho_ten", "") if c else "")
        mapping[f"[Năm sinh {i}]"] = _fmt_birth_or_year(getattr(c, "ngay_sinh", None) if c else None)
        mapping[f"[CCCD {i}]"] = _safe_text(getattr(c, "so_giay_to", "") if c else "")
        mapping[f"[Ngày cấp {i}]"] = _fmt_date(getattr(c, "ngay_cap", None) if c else None)
        mapping[f"[Địa chỉ {i}]"] = _safe_text(getattr(c, "dia_chi", "") if c else "")
        mapping[f"[Loại CC {i}]"] = _safe_text(getattr(c, "loai_giay_to", "") if c else "")
        mapping[f"[Nơi cấp CC {i}]"] = _safe_text(getattr(c, "noi_cap", "") if c else "")
        mapping[f"[Thường trú {i}]"] = _safe_text(getattr(c, "loai_dia_chi", "") if c else "")
        mapping[f"[Năm chết {i}]"] = _fmt_date(getattr(c, "ngay_chet", None) if c else None)
    mapping["[Năm chết]"] = mapping.get("[Năm chết 1]", "")

    for i, row in enumerate(land_rows[:10], start=1):
        mapping[f"[Loại đất {i}]"] = _safe_text(row.get("loai_dat", ""))
        mapping[f"[Diện tích {i}]"] = _safe_text(row.get("dien_tich", ""))
        mapping[f"[Thờ hạn {i}]"] = _safe_text(row.get("thoi_han", ""))
    for i in range(len(land_rows) + 1, 11):
        mapping[f"[Loại đất {i}]"] = ""
        mapping[f"[Diện tích {i}]"] = ""
        mapping[f"[Thờ hạn {i}]"] = ""
    if not mapping.get("[Thờ hạn 1]") and getattr(ts, "thoi_han", None):
        mapping["[Thờ hạn 1]"] = _safe_text(getattr(ts, "thoi_han", ""))

    groups = _build_grouped_people(case)
    for role_key, label in ROLE_LABELS.items():
        first = groups.get(role_key, [])[:1]
        if first:
            _add_person_placeholders(mapping, label, first[0][0], first[0][1])
        else:
            _empty_person_placeholders(mapping, label)
        _add_indexed_people(mapping, label, groups.get(role_key, []))
    _add_indexed_people(mapping, "ngườ nhận", groups["nguoi_nhan"])
    _add_indexed_people(mapping, "ngườ từ chối", groups["nguoi_tu_choi"])
    _add_indexed_people(mapping, "ngườ thừa kế", groups["nguoi_thua_ke"])

    mapping["[Danh sách ngườ nhận]"] = _data_list(groups["nguoi_nhan"])
    mapping["[Danh sách ngườ từ chối]"] = _data_list(groups["nguoi_tu_choi"])
    mapping["[Danh sách ngườ thừa kế]"] = _data_list(groups["nguoi_thua_ke"])
    mapping["[Đoạn mô tả quan hệ]"] = _data_list(groups["nguoi_thua_ke"])

    # -----------------------------------------------------------------------
    # Word export V2 placeholders based on case_state_json
    # -----------------------------------------------------------------------
    persons = _build_word_persons(case)
    _add_block_placeholders(mapping, case, persons)
    _add_property_placeholders(mapping, case)

    # Đoạn phân chia di sản V1 (legacy) chỉ dùng khi V2 chưa populate.
    if not mapping.get("[Đoạn phân chia di sản]"):
        mapping["[Đoạn phân chia di sản]"] = (
            f"{loai_van_ban}: {mapping['[Danh sách ngườ nhận]']}"
            if mapping["[Danh sách ngườ nhận]"]
            else loai_van_ban
        )

    return mapping


def _build_normalized_mapping(mapping: dict[str, str]) -> dict[str, str]:
    normalized = {}
    for k, v in mapping.items():
        if not (k.startswith("[") and k.endswith("]")):
            continue
        normalized[_normalize_token(k[1:-1])] = v
    return normalized


def _replace_text_placeholders(text: str, mapping: dict[str, str], normalized_mapping: dict[str, str]) -> str:
    new_text = text
    for k, v in mapping.items():
        if k in new_text:
            new_text = new_text.replace(k, v)

    def _token_repl(match):
        token = match.group(1)
        direct = mapping.get(f"[{token}]")
        if direct is not None:
            return direct
        norm = _normalize_token(token)
        if norm in normalized_mapping:
            return normalized_mapping[norm]
        return match.group(0)

    return re.sub(r"\[([^\[\]]+)\]", _token_repl, new_text)


def _replace_in_paragraph(paragraph: Any, mapping: dict[str, str], normalized_mapping: dict[str, str]) -> None:
    if not paragraph.runs:
        return
    text = "".join(r.text for r in paragraph.runs)
    if "[" not in text or "]" not in text:
        return

    for run in paragraph.runs:
        if "[" in run.text and "]" in run.text:
            new_text = _replace_text_placeholders(run.text, mapping, normalized_mapping)
            if new_text != run.text:
                run.text = new_text

    text = "".join(r.text for r in paragraph.runs)
    if "[" not in text or "]" not in text:
        return

    new_text = _replace_text_placeholders(text, mapping, normalized_mapping)
    if new_text != text:
        paragraph.runs[0].text = new_text
        for run in paragraph.runs[1:]:
            run.clear()


def replace_in_doc(doc: Any, mapping: dict[str, str]) -> None:
    normalized_mapping = _build_normalized_mapping(mapping)
    for paragraph in doc.paragraphs:
        _replace_in_paragraph(paragraph, mapping, normalized_mapping)
    for table in doc.tables:
        for row in table.rows:
            for cell in row.cells:
                for paragraph in cell.paragraphs:
                    _replace_in_paragraph(paragraph, mapping, normalized_mapping)
    for section in doc.sections:
        for paragraph in section.header.paragraphs:
            _replace_in_paragraph(paragraph, mapping, normalized_mapping)
        for paragraph in section.footer.paragraphs:
            _replace_in_paragraph(paragraph, mapping, normalized_mapping)


def list_public_builtin_templates(root: str | Path = "word_templates") -> list[dict[str, Any]]:
    root_path = Path(root)
    items = []
    for path in sorted(root_path.glob("*.docx"), key=lambda p: p.name.lower()):
        if path.name in HIDDEN_BUILTIN_TEMPLATE_NAMES:
            continue
        if path.name.startswith("~$"):
            continue
        items.append({"id": f"builtin:{path.name}", "ten_mau": path.stem, "is_active": False, "builtin": True})
    return items
