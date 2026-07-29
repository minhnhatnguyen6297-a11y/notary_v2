from datetime import date
from pathlib import Path
from types import SimpleNamespace

import pytest
from docx import Document

from services.word_engine import (
    WordExportValidationError,
    build_word_context,
    build_template_mapping,
    find_unresolved_placeholders,
    list_public_builtin_templates,
    replace_in_doc,
)


def _person(
    cid,
    name,
    *,
    gender="Nam",
    born=None,
    dead=None,
    doc_no="",
    issued=None,
    address="",
):
    return SimpleNamespace(
        id=cid,
        ho_ten=name,
        gioi_tinh=gender,
        ngay_sinh=born,
        ngay_chet=dead,
        so_giay_to=doc_no,
        ngay_cap=issued,
        dia_chi=address,
        loai_giay_to="Căn cước công dân",
        noi_cap="Cục cảnh sát quản lý hành chính về trật tự xã hội",
        loai_dia_chi="Thường trú tại",
    )


def _participant(person, role, *, receive=True, share=0, inheritance_order=1):
    return SimpleNamespace(
        customer=person,
        customer_id=person.id,
        vai_tro=role,
        co_nhan_tai_san=receive,
        ty_le=share,
        hang_thua_ke=inheritance_order,
        parent_customer_id=None,
    )


def _prop(**kwargs):
    defaults = dict(
        so_serial="BM 1451111",
        so_vao_so="CS123",
        so_thua_dat="45",
        so_to_ban_do="12",
        dia_chi="Thửa đất tại xã Minh Tân",
        loai_dat="Đất ở tại nông thôn",
        dien_tich=120.5,
        loai_so="Giấy chứng nhận quyền sử dụng đất",
        land_rows_json='[{"loai_dat":"ONT","dien_tich":"80","thoi_han":"Lâu dài"}]',
        hinh_thuc_su_dung="Sử dụng riêng",
        thoi_han="Lâu dài",
        nguon_goc="Nhà nước công nhận quyền sử dụng đất",
        ngay_cap=date(2020, 7, 8),
        co_quan_cap="UBND huyện Ý Yên",
    )
    defaults.update(kwargs)
    return SimpleNamespace(**defaults)


def _case_state(*people, nodes=None):
    stage = []
    for p in people:
        stage.append({
            "id": str(p.id),
            "ho_ten": p.ho_ten,
            "gioi_tinh": p.gioi_tinh,
            "ngay_sinh": p.ngay_sinh.isoformat() if p.ngay_sinh else None,
            "ngay_chet": p.ngay_chet.isoformat() if p.ngay_chet else None,
            "so_giay_to": p.so_giay_to,
            "ngay_cap": p.ngay_cap.isoformat() if p.ngay_cap else None,
            "noi_cap": p.noi_cap,
            "dia_chi": p.dia_chi,
            "loai_dia_chi": p.loai_dia_chi,
        })
    payload = {"schemaVersion": 1, "stage": stage, "diagram": {}}
    if nodes:
        payload["diagram"] = {"engineState": {"nodes": nodes}}
    import json
    return json.dumps(payload, ensure_ascii=False)


def _case_state_v2(*people, nodes, allocations):
    import json

    payload = json.loads(_case_state(*people))
    payload["version"] = 2
    payload["diagram"] = {
        "engineInput": {"version": 2, "nodes": nodes},
        "engineResult": {
            "status": "complete",
            "allocations": allocations,
        },
    }
    return json.dumps(payload, ensure_ascii=False)


def _node(person_id, *, role="Khac", will_receive=False, is_land_owner=False, legacy_decision=None):
    node = {
        "id": f"node_{person_id}",
        "personId": str(person_id),
        "role": role,
        "isLandOwner": is_land_owner,
        "hidden": False,
        "deleted": False,
    }
    if will_receive is not None:
        node["willReceive"] = will_receive
    if legacy_decision is not None:
        node["inheritanceDecision"] = legacy_decision
    return node


def _make_case(owner, participants=None, *, properties=None, case_state=None):
    if properties is None:
        properties = []
    primary = properties[0] if properties else _prop()
    return SimpleNamespace(
        id=99,
        nguoi_chet=owner,
        tai_san=primary,
        property_links=[
            SimpleNamespace(property=p, is_primary=(p is primary), id=i)
            for i, p in enumerate(properties)
        ] if properties else [],
        ngay_lap_ho_so=date(2026, 7, 3),
        loai_van_ban="thoa_thuan",
        noi_niem_yet="UBND xã Minh Tân",
        ghi_chu="Ghi chú nội bộ",
        participants=participants or [],
        case_state_json=case_state,
    )


def test_build_template_mapping_exposes_standard_vietnamese_placeholders_and_legacy_aliases():
    owner = _person(1, "Nguyễn Văn Chủ", gender="Nam", born=date(1950, 1, 1), dead=date(2024, 2, 3), doc_no="001050000001")
    receiver = _person(2, "Nguyễn Văn Con", gender="Nam", born=date(1980, 8, 9), doc_no="001080000003")
    prop = _prop()
    case = _make_case(
        owner,
        participants=[_participant(receiver, "Con")],
        properties=[prop],
    )
    mapping = build_template_mapping(case, today=date(2026, 7, 3))

    assert mapping["[Họ tên chủ đất]"] == "Nguyễn Văn Chủ"
    assert mapping["[Chủ đất chết 1 - Họ tên]"] == "Nguyễn Văn Chủ"
    assert mapping["[Người nhận 1 - Họ tên]"] == "Nguyễn Văn Con"
    assert mapping["[Số serial]"] == "BM 1451111"
    assert mapping["[Ngày lập hồ sơ]"] == "03/07/2026"
    assert mapping["[Tên 1]"] == "Nguyễn Văn Chủ"
    assert mapping["[Năm chết]"] == "03/02/2024"
    assert "[ho_ten_1_chu_dat]" not in mapping


def test_build_template_mapping_resolves_role_and_data_only_snippets():
    owner = _person(1, "Nguyễn Văn Chủ", gender="Nam", born=date(1950, 1, 1), dead=date(2024, 2, 3), doc_no="001050000001")
    spouse = _person(2, "Trần Thị Vợ", gender="Nữ", born=date(1955, 4, 5), doc_no="001055000002")
    child = _person(3, "Nguyễn Văn Con", gender="Nam", born=date(1980, 8, 9), doc_no="001080000003")
    case = _make_case(
        owner,
        participants=[_participant(spouse, "Vợ/Chồng"), _participant(child, "Con")],
        properties=[_prop()],
    )
    mapping = build_template_mapping(case, today=date(2026, 7, 3))

    assert mapping["[Họ tên vợ/chồng]"] == "Trần Thị Vợ"
    assert "Nguyễn Văn Con" in mapping["[Danh sách người thừa kế]"]


def test_replace_in_doc_replaces_split_runs_tables_headers_and_footers():
    doc = Document()
    para = doc.add_paragraph()
    para.add_run("[Họ tên")
    para.add_run(" chủ đất]")
    table = doc.add_table(rows=1, cols=1)
    table.cell(0, 0).text = "[Số serial]"
    doc.sections[0].header.paragraphs[0].text = "[Địa chỉ đất]"
    doc.sections[0].footer.paragraphs[0].text = "[Tên 1]"

    replace_in_doc(
        doc,
        {
            "[Họ tên chủ đất]": "Nguyễn Văn Chủ",
            "[Số serial]": "BM 1451111",
            "[Địa chỉ đất]": "Thửa đất tại xã Minh Tân",
            "[Tên 1]": "Nguyễn Văn Chủ",
        },
    )

    assert doc.paragraphs[0].text == "Nguyễn Văn Chủ"
    assert table.cell(0, 0).text == "BM 1451111"
    assert doc.sections[0].header.paragraphs[0].text == "Thửa đất tại xã Minh Tân"
    assert doc.sections[0].footer.paragraphs[0].text == "Nguyễn Văn Chủ"


def test_find_unresolved_placeholders_reports_only_unknown_tokens():
    doc = Document()
    doc.add_paragraph("[Đã map] [Chưa map]")

    replace_in_doc(doc, {"[Đã map]": "x"})

    assert find_unresolved_placeholders(doc) == ["[Chưa map]"]


def test_list_public_builtin_templates_hides_reference_and_snake_case_templates(tmp_path):
    (tmp_path / "xa_PCDS_template.docx").write_bytes(b"doc")
    (tmp_path / "system_placeholder_reference.docx").write_bytes(b"doc")
    (tmp_path / "system_template_chuan_v1.docx").write_bytes(b"doc")
    (tmp_path / "~$ PCDS .docx").write_bytes(b"doc")

    items = list_public_builtin_templates(tmp_path)

    assert [item["id"] for item in items] == ["builtin:xa_PCDS_template.docx"]


def test_placeholder_catalog_documents_vietnamese_contract_without_snake_case_public_contract():
    catalog = Path("word_templates/placeholder_mapping.md").read_text(encoding="utf-8")

    assert "[Người N - Họ tên]" in catalog
    assert "[Người nhận N - Họ tên]" in catalog
    assert "[Dòng người từ chối N]" in catalog
    assert "người chưa chọn" not in catalog.lower()
    assert "[ho_ten_1_chu_dat]" not in catalog


# ---------------------------------------------------------------------------
# Word export V2 tests
# ---------------------------------------------------------------------------


def test_one_deceased_landowner_spouse_alive_not_landowner():
    owner = _person(1, "Nguyễn Văn A", gender="Nam", born=date(1950, 1, 1), dead=date(2024, 2, 3), doc_no="001")
    spouse = _person(2, "Trần Thị B", gender="Nữ", born=date(1955, 4, 5), doc_no="002")
    child = _person(3, "Nguyễn Văn C", gender="Nam", born=date(1980, 8, 9), doc_no="003")
    case = _make_case(
        owner,
        properties=[_prop()],
        case_state=_case_state(
            owner, spouse, child,
            nodes=[
                _node(1, role="Owner", is_land_owner=True),
                _node(2, role="Vợ/Chồng"),
                _node(3, role="Con", will_receive=True),
            ],
        ),
    )
    mapping = build_template_mapping(case)
    assert mapping["[Cụm chủ đất chết]"] == "ông Nguyễn Văn A"
    assert mapping["[Người nhận 1 - Họ tên]"] == "Nguyễn Văn C"
    assert mapping["[Người từ chối 1 - Họ tên]"] == ""
    assert mapping["[Người 2 - Trạng thái]"] == "Người không nhận"


def test_word_context_reads_v2_engine_input_and_exact_engine_result_shares():
    owner = _person(1, "X", dead=date(2024, 2, 3))
    receiver = _person(2, "M")
    case = _make_case(
        owner,
        properties=[_prop()],
        case_state=_case_state_v2(
            owner,
            receiver,
            nodes=[
                _node(1, role="Owner", is_land_owner=True),
                _node(2, role="Con", will_receive=True),
            ],
            allocations={
                "1": {"finalShare": "0"},
                "2": {"finalShare": "1/3"},
            },
        ),
    )

    context = build_word_context(case)
    mapping = build_template_mapping(case)

    assert [person.ho_ten for person in context.receivers] == ["M"]
    assert context.receivers[0].share == "1/3"
    assert mapping["[Người nhận 1 - Tỷ lệ]"] == "1/3"


def test_two_deceased_landowners_both_in_estate_cluster():
    owner1 = _person(1, "Nguyễn Văn A", gender="Nam", born=date(1950, 1, 1), dead=date(2024, 2, 3), doc_no="001")
    owner2 = _person(2, "Trần Thị B", gender="Nữ", born=date(1952, 3, 4), dead=date(2024, 5, 6), doc_no="002")
    child = _person(3, "Nguyễn Văn C", gender="Nam", born=date(1980, 8, 9), doc_no="003")
    case = _make_case(
        owner1,
        properties=[_prop()],
        case_state=_case_state(
            owner1, owner2, child,
            nodes=[
                _node(1, role="Owner", is_land_owner=True),
                _node(2, role="Vợ/Chồng", is_land_owner=True),
                _node(3, role="Con", will_receive=True),
            ],
        ),
    )
    mapping = build_template_mapping(case)
    assert mapping["[Chủ đất chết 1 - Họ tên]"] == "Nguyễn Văn A"
    assert mapping["[Chủ đất chết 2 - Họ tên]"] == "Trần Thị B"
    assert mapping["[Nối chủ đất chết 2]"] == " và "


def test_living_landowner_nonreceiver_keeps_base_without_implicit_gift():
    owner1 = _person(1, "Nguyễn Văn A", gender="Nam", born=date(1950, 1, 1), dead=date(2024, 2, 3), doc_no="001")
    owner2 = _person(2, "Trần Thị B", gender="Nữ", born=date(1952, 3, 4), doc_no="002")
    child = _person(3, "Nguyễn Văn C", gender="Nam", born=date(1980, 8, 9), doc_no="003")
    case = _make_case(
        owner1,
        properties=[_prop()],
        case_state=_case_state(
            owner1, owner2, child,
            nodes=[
                _node(1, role="Owner", is_land_owner=True),
                _node(2, role="Vợ/Chồng", is_land_owner=True),
                _node(3, role="Con", will_receive=True),
            ],
        ),
    )
    mapping = build_template_mapping(case)
    assert mapping["[Cụm chủ đất chết]"] == "ông Nguyễn Văn A"
    assert mapping["[Chủ đất sống 1 - Họ tên]"] == "Trần Thị B"
    assert mapping["[Người từ chối 1 - Họ tên]"] == ""
    assert "Trần Thị B" not in mapping["[Đoạn phân chia di sản]"]
    assert "tặng cho" not in mapping["[Đoạn phân chia di sản]"]
    assert mapping["[Dòng chủ đất sống tặng cho 1]"] == ""


def test_nonreceiver_does_not_create_a_legal_refusal_statement():
    owner = _person(1, "Nguyễn Văn A", gender="Nam", born=date(1950, 1, 1), dead=date(2024, 2, 3), doc_no="001")
    child_accept = _person(2, "Nguyễn Văn B", gender="Nam", born=date(1980, 8, 9), doc_no="002")
    child_refuse = _person(3, "Nguyễn Thị C", gender="Nữ", born=date(1982, 10, 11), doc_no="003")
    case = _make_case(
        owner,
        properties=[_prop()],
        case_state=_case_state(
            owner, child_accept, child_refuse,
            nodes=[
                _node(1, role="Owner", is_land_owner=True),
                _node(2, role="Con", will_receive=True),
                _node(3, role="Con"),
            ],
        ),
    )
    mapping = build_template_mapping(case)
    assert mapping["[Người từ chối 1 - Họ tên]"] == ""
    assert mapping["[Dòng người từ chối 1]"] == ""
    assert "Nguyễn Thị C" in mapping["[Đoạn quan hệ gia đình]"]
    assert "từ chối di sản" not in mapping["[Đoạn quan hệ gia đình]"]


def test_nonreceiver_is_not_in_division_clause_or_legal_refusal_group():
    owner = _person(1, "Nguyễn Văn A", gender="Nam", born=date(1950, 1, 1), dead=date(2024, 2, 3), doc_no="001")
    unset = _person(2, "Trần Thị B", gender="Nữ", born=date(1955, 4, 5), doc_no="002")
    receiver = _person(3, "Nguyễn Văn C", gender="Nam", born=date(1980, 8, 9), doc_no="003")
    case = _make_case(
        owner,
        properties=[_prop()],
        case_state=_case_state(
            owner, unset, receiver,
            nodes=[
                _node(1, role="Owner", is_land_owner=True),
                _node(2, role="Vợ/Chồng"),
                _node(3, role="Con", will_receive=True),
            ],
        ),
    )
    mapping = build_template_mapping(case)
    assert mapping["[Người từ chối 1 - Họ tên]"] == ""
    assert "Trần Thị B" not in mapping["[Đoạn phân chia di sản]"]
    assert "chưa chọn" not in mapping["[Đoạn phân chia di sản]"].lower()


def test_multiple_receivers_listed_in_accept_paragraph():
    owner = _person(1, "Nguyễn Văn A", gender="Nam", born=date(1950, 1, 1), dead=date(2024, 2, 3), doc_no="001")
    r1 = _person(2, "Nguyễn Văn B", gender="Nam", born=date(1980, 8, 9), doc_no="002")
    r2 = _person(3, "Nguyễn Thị C", gender="Nữ", born=date(1982, 10, 11), doc_no="003")
    case = _make_case(
        owner,
        properties=[_prop()],
        case_state=_case_state(
            owner, r1, r2,
            nodes=[
                _node(1, role="Owner", is_land_owner=True),
                _node(2, role="Con", will_receive=True),
                _node(3, role="Con", will_receive=True),
            ],
        ),
    )
    mapping = build_template_mapping(case)
    assert "Nguyễn Văn B" in mapping["[Đoạn phân chia di sản]"]
    assert "Nguyễn Thị C" in mapping["[Đoạn phân chia di sản]"]
    assert "đồng ý nhận phần di sản" in mapping["[Đoạn phân chia di sản]"]


def test_word_context_keeps_legal_refusal_empty_and_allows_owner_receiver_overlap():
    owner_dead = _person(1, "Nguyễn Văn A", dead=date(2024, 2, 3))
    owner_alive = _person(2, "Trần Thị B", gender="Nữ")
    receiver = _person(3, "Nguyễn Văn C")
    refused = _person(4, "Nguyễn Thị D", gender="Nữ")
    case = _make_case(
        owner_dead,
        properties=[_prop()],
        case_state=_case_state(
            owner_dead,
            owner_alive,
            receiver,
            refused,
            nodes=[
                _node(1, role="Owner", is_land_owner=True),
                _node(2, role="Vợ/Chồng", is_land_owner=True, will_receive=True),
                _node(3, role="Con", will_receive=True),
                _node(4, role="Con"),
            ],
        ),
    )

    context = build_word_context(case)

    assert [person.ho_ten for person in context.landowners] == ["Nguyễn Văn A", "Trần Thị B"]
    assert [person.ho_ten for person in context.receivers] == ["Trần Thị B", "Nguyễn Văn C"]
    assert context.legal_refusal_people == []


def test_legacy_accept_is_read_only_when_will_receive_is_missing():
    owner = _person(1, "Nguyễn Văn A", dead=date(2024, 2, 3))
    receiver = _person(2, "Nguyễn Văn B")
    case = _make_case(
        owner,
        properties=[_prop()],
        case_state=_case_state(
            owner,
            receiver,
            nodes=[
                _node(1, role="Owner", is_land_owner=True),
                _node(2, role="Con", will_receive=None, legacy_decision="accept"),
            ],
        ),
    )

    mapping = build_template_mapping(case)

    assert mapping["[Người nhận 1 - Họ tên]"] == "Nguyễn Văn B"


def test_empty_numbered_slots_clear_the_whole_tier_two_block():
    owner = _person(1, "Nguyễn Văn A", dead=date(2024, 2, 3))
    receiver = _person(2, "Nguyễn Văn B")
    case = _make_case(
        owner,
        properties=[_prop()],
        case_state=_case_state(
            owner,
            receiver,
            nodes=[
                _node(1, role="Owner", is_land_owner=True),
                _node(2, role="Con", will_receive=True),
            ],
        ),
    )

    mapping = build_template_mapping(case)

    assert mapping["[Người nhận 2 - Họ tên]"] == ""
    assert mapping["[Dòng người nhận 2]"] == ""
    assert mapping["[Nối chủ đất chết 2]"] == ""
    assert mapping["[Chủ đất chết 2 - Họ tên]"] == ""
    assert mapping["[Dòng tài sản 2]"] == ""


def test_five_properties_numbering():
    owner = _person(1, "Nguyễn Văn A", gender="Nam", born=date(1950, 1, 1), dead=date(2024, 2, 3), doc_no="001")
    receiver = _person(2, "Nguyễn Văn B", gender="Nam", born=date(1980, 8, 9), doc_no="002")
    props = [
        _prop(dia_chi="Đất 1", so_serial="S1", land_rows_json='[{"loai_dat":"ONT","dien_tich":"80"},{"loai_dat":"CLN","dien_tich":"20"}]'),
        _prop(dia_chi="Đất 2", so_serial="S2", land_rows_json='[{"loai_dat":"NTS","dien_tich":"50"}]'),
        _prop(dia_chi="Đất 3", so_serial="S3"),
        _prop(dia_chi="Đất 4", so_serial="S4"),
        _prop(dia_chi="Đất 5", so_serial="S5"),
    ]
    case = _make_case(
        owner,
        properties=props,
        case_state=_case_state(
            owner, receiver,
            nodes=[
                _node(1, role="Owner", is_land_owner=True),
                _node(2, role="Con", will_receive=True),
            ],
        ),
    )
    mapping = build_template_mapping(case)
    desc = mapping["[Đoạn mô tả di sản]"]
    assert desc.startswith("Các quyền sử dụng đất như sau:\n1. Quyền sử dụng đất tại: Đất 1")
    assert "1. Quyền sử dụng đất tại: Đất 1" in desc
    assert "1.1. ONT: 80" in desc
    assert "1.2. CLN: 20" in desc
    assert "2.1. NTS: 50" in desc
    assert mapping["[Serial tài sản 5]"] == "S5"
    assert mapping["[Tài sản 5 - Serial]"] == "S5"
    assert mapping["[Dòng tài sản 5]"].startswith("5. Quyền sử dụng đất tại: Đất 5")


def test_multiple_properties_use_primary_first_then_stable_link_order():
    owner = _person(1, "Nguyễn Văn A", gender="Nam", dead=date(2024, 2, 3))
    receiver = _person(2, "Nguyễn Văn B", gender="Nam")
    primary = _prop(dia_chi="Tài sản chính", so_serial="PRIMARY")
    linked_first = _prop(dia_chi="Tài sản liên kết trước", so_serial="LINK-1")
    linked_second = _prop(dia_chi="Tài sản liên kết sau", so_serial="LINK-2")
    case = _make_case(
        owner,
        properties=[primary, linked_first, linked_second],
        case_state=_case_state(
            owner,
            receiver,
            nodes=[
                _node(1, role="Owner", is_land_owner=True),
                _node(2, role="Con", will_receive=True),
            ],
        ),
    )
    case.property_links = [
        SimpleNamespace(property=linked_second, is_primary=False, id=30),
        SimpleNamespace(property=primary, is_primary=True, id=20),
        SimpleNamespace(property=linked_first, is_primary=False, id=10),
    ]

    context = build_word_context(case)
    mapping = build_template_mapping(case)

    assert context.assets == [primary, linked_first, linked_second]
    assert mapping["[Tài sản 1 - Serial]"] == "PRIMARY"
    assert mapping["[Tài sản 2 - Serial]"] == "LINK-1"
    assert mapping["[Tài sản 3 - Serial]"] == "LINK-2"


def test_real_pcds_template_resolves_two_properties_into_one_document():
    owner = _person(1, "Nguyễn Văn A", gender="Nam", dead=date(2024, 2, 3))
    receiver = _person(2, "Nguyễn Văn B", gender="Nam")
    case = _make_case(
        owner,
        properties=[
            _prop(dia_chi="Thửa đất thứ nhất", so_serial="S1"),
            _prop(dia_chi="Thửa đất thứ hai", so_serial="S2"),
        ],
        case_state=_case_state(
            owner,
            receiver,
            nodes=[
                _node(1, role="Owner", is_land_owner=True),
                _node(2, role="Con", will_receive=True),
            ],
        ),
    )
    doc = Document("word_templates/1. PCDS .docx")

    replace_in_doc(doc, build_template_mapping(case))

    assert find_unresolved_placeholders(doc) == []
    full_text = "\n".join(
        [paragraph.text for paragraph in doc.paragraphs]
        + [cell.text for table in doc.tables for row in table.rows for cell in row.cells]
    )
    assert "Các quyền sử dụng đất như sau:" in full_text
    assert "1. Quyền sử dụng đất tại: Thửa đất thứ nhất" in full_text
    assert "2. Quyền sử dụng đất tại: Thửa đất thứ hai" in full_text


def test_more_than_five_properties_raises():
    owner = _person(1, "Nguyễn Văn A", gender="Nam", dead=date(2024, 2, 3))
    receiver = _person(2, "Nguyễn Văn B", gender="Nam")
    props = [_prop(dia_chi=f"Đất {i}", so_serial=f"S{i}") for i in range(1, 7)]
    case = _make_case(
        owner,
        properties=props,
        case_state=_case_state(
            owner, receiver,
            nodes=[
                _node(1, role="Owner", is_land_owner=True),
                _node(2, role="Con", will_receive=True),
            ],
        ),
    )
    with pytest.raises(WordExportValidationError, match="5 tài sản"):
        build_template_mapping(case)


def test_more_than_twenty_heirs_raises():
    owner = _person(1, "Nguyễn Văn A", gender="Nam", dead=date(2024, 2, 3))
    people = [owner]
    nodes = [_node(1, role="Owner", is_land_owner=True)]
    for i in range(2, 24):
        p = _person(i, f"Ngườ {i}", gender="Nam")
        people.append(p)
        nodes.append(_node(i, role="Con", will_receive=True))
    case = _make_case(
        owner,
        properties=[_prop()],
        case_state=_case_state(*people, nodes=nodes),
    )
    with pytest.raises(WordExportValidationError, match="20 người"):
        build_template_mapping(case)


def test_pcds_template_no_old_critical_placeholders():
    doc = Document("word_templates/1. PCDS .docx")
    all_texts = []
    for p in doc.paragraphs:
        all_texts.append(p.text)
    for t in doc.tables:
        for row in t.rows:
            for cell in row.cells:
                all_texts.append(cell.text)
    full = "\n".join(all_texts)
    import re
    placeholders = set(re.findall(r"\[[^\[\]]+\]", full))
    old_critical = {
        "[Tên 1]", "[Tên 2]", "[Tên 3]", "[ONT]", "[CLN]", "[NTS]",
        "[Cụm ngườ để lại di sản]",
        "[Danh sách ngườ nhận và chưa chọn]",
        "[Danh sách ngườ ký]",
    }
    assert not (old_critical & placeholders), f"Old placeholders remain: {old_critical & placeholders}"
    assert "[Chủ đất chết 1 - Xưng hô]" in placeholders
    assert "[Chủ đất chết 2 - Họ tên]" in placeholders
    assert "[Dòng người 20]" in placeholders
    assert "[Dòng người từ chối 20]" in placeholders
    assert "[Đoạn phân chia di sản]" in placeholders
