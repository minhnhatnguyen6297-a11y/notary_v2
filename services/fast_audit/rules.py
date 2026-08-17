from __future__ import annotations

import re


NOTARY_ANCHORS = [
    "lời chứng của công chứng viên",
    "lời chứng",
    "lờ chứng",
]

_NOTARY_ANCHOR_RES = [
    re.compile(r"\s+".join(re.escape(part) for part in anchor.split()), re.IGNORECASE)
    for anchor in NOTARY_ANCHORS
]

DOC_TYPE_PATTERNS = [
    ("trich_luc_khai_tu", [
        r"trích\s+lục\s+khai\s+tử",
        r"giấy\s+báo\s+tử",
        r"khai\s+tử",
    ]),
    ("can_cuoc", [
        r"căn\s+cước\s+công\s+dân",
        r"căn\s+cước",
        r"chứng\s+minh\s+nhân\s+dân",
        r"cmnd",
        r"cccd",
    ]),
    ("giay_chung_nhan", [
        r"giấy\s+chứng\s+nhận",
        r"quyền\s+sử\s+dụng\s+đất",
        r"sổ\s+đỏ",
        r"sổ\s+hồng",
    ]),
    ("van_ban_tu_choi", [
        r"văn\s+bản\s+từ\s+chối\s+nhận\s+di\s+sản",
        r"từ\s+chối\s+nhận\s+di\s+sản",
        r"từ\s+chối\s+di\s+sản",
    ]),
    ("bien_ban_hop_gia_dinh", [
        r"biên\s+bản\s+họp\s+gia\s+đình",
        r"họp\s+gia\s+đình",
        r"thỏa\s+thuận\s+phân\s+chia",
    ]),
    ("so_do_thua_ke", [
        r"sơ\s+đồ\s+thừa\s+kế",
        r"sơ\s+đồ\s+gia\s+đình",
    ]),
    ("don_xac_nhan", [
        r"đơn\s+xác\s+nhận",
        r"xác\s+nhận",
    ]),
]

WORD_TEMPLATE_HINTS = [
    ("van_ban_tu_choi", [
        r"từ\s+chối\s+nhận\s+di\s+sản",
        r"từ\s+chối\s+di\s+sản",
    ]),
    ("bien_ban_hop_gia_dinh", [
        r"biên\s+bản\s+họp\s+gia\s+đình",
        r"thỏa\s+thuận\s+phân\s+chia",
    ]),
    ("so_do_thua_ke", [
        r"sơ\s+đồ\s+thừa\s+kế",
    ]),
    ("don_xac_nhan", [
        r"đơn\s+xác\s+nhận",
    ]),
    ("pcds", [
        r"khai\s+nhận\s+di\s+sản",
        r"thỏa\s+thuận\s+phân\s+chia",
    ]),
]

ID_CARD_RE = re.compile(r"\b\d{9,12}\b")
DATE_RE = re.compile(r"\b\d{1,2}[/-]\d{1,2}[/-]\d{2,4}\b")
PLOT_RE = re.compile(r"(?:thửa\s+đất\s+số|thửa\s+số|số\s+thửa)[:\s]*([0-9.,/\-]+)", re.IGNORECASE)
MAP_SHEET_RE = re.compile(r"(?:tờ\s+bản\s+đồ\s+số|tờ\s+số|số\s+tờ)[:\s]*([0-9.,/\-]+)", re.IGNORECASE)
AREA_RE = re.compile(
    r"(?:diện\s+tích|dt)[:\s]*([0-9.,/\-]+)\s*(?:m2|m²|m\^2| mét vuông| m2)?",
    re.IGNORECASE,
)
DOC_NO_RE = re.compile(r"(?:số\s+văn\s+bản|số\s+):\s*([0-9A-Z./\-]+)", re.IGNORECASE)


def normalize_for_rules(text: str) -> str:
    text = (text or "").lower()
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def classify_doc_type(text: str) -> str | None:
    norm = normalize_for_rules(text)
    for doc_type, patterns in DOC_TYPE_PATTERNS:
        for pat in patterns:
            if re.search(pat, norm):
                return doc_type
    return None


def is_notary_page(text: str) -> bool:
    norm = normalize_for_rules(text)
    return any(anchor in norm for anchor in NOTARY_ANCHORS)


def cut_at_notary_anchor(text: str) -> tuple[str, bool]:
    """Return (text_before_anchor, anchor_found)."""
    matches = [match for pattern in _NOTARY_ANCHOR_RES if (match := pattern.search(text or ""))]
    if not matches:
        return text, False
    return text[:min(match.start() for match in matches)].strip(), True


def detect_word_template_type(file_name: str, title_text: str, body_text: str) -> str:
    combined = f"{file_name} {title_text} {body_text[:2000]}".lower()
    for template_type, patterns in WORD_TEMPLATE_HINTS:
        for pat in patterns:
            if re.search(pat, combined):
                return template_type
    return "generic"


def has_placeholders(text: str) -> bool:
    return bool(re.search(r"\[[^\[\]]+\]", text))


def extract_dates(text: str) -> list[str]:
    return DATE_RE.findall(text)


def extract_id_numbers(text: str) -> list[str]:
    return ID_CARD_RE.findall(text)
