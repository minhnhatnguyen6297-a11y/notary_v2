import json
import sqlite3
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import database
from database import Base
from models import Property
from routers.properties import _normalize_land_rows


ROOT = Path(__file__).resolve().parents[1]


def test_two_properties_can_share_serial_and_keep_independent_land_rows():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    try:
        first_land = _normalize_land_rows(
            '[{"loai_dat":"ONT","dien_tich":"120","thoi_han":"Lâu dài"}]'
        )
        second_land = _normalize_land_rows(
            '[{"loai_dat":"CLN","dien_tich":"350.5","thoi_han":"Đến 2050"}]'
        )
        first = Property(
            so_serial="CS 123456",
            so_thua_dat="10",
            dia_chi="Xã Minh Tân",
            land_rows_json=first_land["json"],
            loai_dat=first_land["description"],
            dien_tich=first_land["total_area"],
        )
        second = Property(
            so_serial="CS 123456",
            so_thua_dat="11",
            dia_chi="Xã Minh Tân",
            land_rows_json=second_land["json"],
            loai_dat=second_land["description"],
            dien_tich=second_land["total_area"],
        )
        session.add_all([first, second])
        session.commit()

        assert first.id != second.id
        assert json.loads(first.land_rows_json)[0]["loai_dat"] == "ONT"
        assert json.loads(second.land_rows_json)[0]["loai_dat"] == "CLN"
        assert first.dien_tich == 120
        assert second.dien_tich == 350.5
    finally:
        session.close()
        engine.dispose()


def test_properties_migration_removes_old_unique_serial_and_preserves_ids(tmp_path, monkeypatch):
    db_path = tmp_path / "old-notary.db"
    with sqlite3.connect(db_path) as connection:
        connection.executescript(
            """
            CREATE TABLE properties (
                id INTEGER NOT NULL PRIMARY KEY,
                so_serial VARCHAR(100) NOT NULL UNIQUE,
                so_vao_so VARCHAR(100),
                so_thua_dat VARCHAR(100),
                so_to_ban_do VARCHAR(100),
                dia_chi TEXT NOT NULL,
                loai_dat VARCHAR(100),
                hinh_thuc_su_dung VARCHAR(100),
                thoi_han VARCHAR(100),
                nguon_goc TEXT,
                ngay_cap DATE,
                co_quan_cap VARCHAR(200),
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            );
            INSERT INTO properties (
                id, so_serial, so_thua_dat, dia_chi
            ) VALUES (41, 'CS 654321', '20', 'Xã An Bình');
            """
        )

    monkeypatch.setattr(database, "DB_PATH", db_path)
    database.migrate_properties_schema()

    with sqlite3.connect(db_path) as connection:
        original = connection.execute(
            "SELECT id, so_serial, so_thua_dat FROM properties WHERE id=41"
        ).fetchone()
        connection.execute(
            "INSERT INTO properties (so_serial, so_thua_dat, dia_chi) VALUES (?, ?, ?)",
            ("CS 654321", "21", "Xã An Bình"),
        )
        duplicate_count = connection.execute(
            "SELECT COUNT(*) FROM properties WHERE so_serial='CS 654321'"
        ).fetchone()[0]

    assert original == (41, "CS 654321", "20")
    assert duplicate_count == 2


def test_property_templates_use_vertical_fields_and_asset_columns():
    list_template = (ROOT / "frontend/templates/properties/list.html").read_text(encoding="utf-8")
    form_template = (ROOT / "frontend/templates/properties/form.html").read_text(encoding="utf-8")

    assert 'class="asset-column"' in list_template
    assert "data-property-id" in list_template
    assert "data-asset-form" in list_template
    assert 'id="add-asset-column"' in list_template
    assert "data-land-rows" in list_template
    assert "người nhận" not in list_template.lower()
    assert "nguoi_nhan" not in list_template.lower()

    assert 'class="property-form-field"' in form_template
    assert "col-md-" not in form_template
    assert "data-land-rows" in form_template
