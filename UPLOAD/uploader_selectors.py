from __future__ import annotations

DEFAULT_STATUS_TEXT = "Đã công chứng"
DEFAULT_GHI_CHU = ""
DEFAULT_PHI_CONG_CHUNG = ""
DEFAULT_THU_LAO = ""

LOGIN_SELECTORS = {
    "username": [
        {"type": "css", "value": "input[name='username']"},
        {"type": "css", "value": "input[type='text']"},
    ],
    "password": [
        {"type": "css", "value": "input[name='password']"},
        {"type": "css", "value": "input[type='password']"},
    ],
    "submit": [
        {"type": "role", "role": "button", "name": "Đăng nhập"},
        {"type": "text", "value": "Đăng nhập"},
    ],
}

FORM_FIELD_ORDER = [
    "ten_hop_dong",
    "ngay_cong_chung",
    "so_cong_chung",
    "tinh_trang",
    "nhom_hop_dong",
    "loai_tai_san",
    "cong_chung_vien",
    "thu_ky",
    "nguoi_yeu_cau",
    "duong_su",
    "tai_san",
    "file_hop_dong",
    "ghi_chu",
    "phi_cong_chung",
    "thu_lao_cong_chung",
]

FORM_SELECTORS = {
    "ten_hop_dong": {
        "kind": "text",
        "label": "Tên hợp đồng",
        "strategies": [],
        "verify": True,
    },
    "ngay_cong_chung": {
        "kind": "text",
        "label": "Ngày công chứng",
        "strategies": [],
    },
    "so_cong_chung": {
        "kind": "text",
        "label": "Số công chứng",
        "strategies": [],
        "verify": True,
    },
    "tinh_trang": {
        "kind": "dropdown",
        "label": "Tình trạng",
        "strategies": [],
    },
    "nhom_hop_dong": {
        "kind": "dropdown",
        "label": "Nhóm hợp đồng",
        "strategies": [],
        "verify": True,
    },
    "loai_tai_san": {
        "kind": "dropdown",
        "label": "Loại tài sản",
        "strategies": [],
        "verify": True,
    },
    "cong_chung_vien": {
        "kind": "dropdown",
        "label": "Công chứng viên",
        "strategies": [],
    },
    "thu_ky": {
        "kind": "dropdown",
        "label": "Thư ký",
        "strategies": [],
    },
    "nguoi_yeu_cau": {
        "kind": "editor",
        "label": "Thông tin người yêu cầu công chứng",
        "strategies": [],
    },
    "duong_su": {
        "kind": "editor",
        "label": "Đương sự",
        "strategies": [],
    },
    "tai_san": {
        "kind": "editor",
        "label": "Tài sản",
        "strategies": [],
    },
    "file_hop_dong": {
        "kind": "file",
        "label": "Văn bản hợp đồng",
        "strategies": [
            {"type": "css", "value": "input[type='file']"},
        ],
        "verify_upload": True,
    },
    "ghi_chu": {
        "kind": "text",
        "label": "Ghi chú",
        "strategies": [],
    },
    "phi_cong_chung": {
        "kind": "text",
        "label": "Phí công chứng",
        "strategies": [],
    },
    "thu_lao_cong_chung": {
        "kind": "text",
        "label": "Thù lao công chứng",
        "strategies": [],
    },
}

SAVE_BUTTON_SELECTORS = [
    {"type": "role", "role": "button", "name": "Lưu hợp đồng"},
    {"type": "text", "value": "Lưu hợp đồng"},
]

UPLOAD_SUCCESS_MARKERS = [
    {"type": "text_dynamic"},
]

VERIFY_FIELDS = ["ten_hop_dong", "so_cong_chung", "nhom_hop_dong", "loai_tai_san", "file_hop_dong"]
