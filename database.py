import sqlite3
from pathlib import Path
from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

# Dùng SQLite — file notary.db tự tạo trong thư mục dự án
BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "notary.db"
DATABASE_URL = f"sqlite:///{DB_PATH.as_posix()}"

engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def migrate_customers_nullable():
    """Chuyển các cột customers (trừ ho_ten) sang nullable nếu chưa có."""
    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()
    cur.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='customers'")
    row = cur.fetchone()
    if row and "NOT NULL" in row[0]:
        cur.executescript("""
            PRAGMA foreign_keys=off;
            BEGIN;
            CREATE TABLE customers_new (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                ho_ten      VARCHAR(200) NOT NULL,
                gioi_tinh   VARCHAR(10),
                ngay_sinh   DATE,
                ngay_chet   DATE,
                so_giay_to  VARCHAR(50) UNIQUE,
                ngay_cap    DATE,
                dia_chi     TEXT,
                created_at  DATETIME DEFAULT (CURRENT_TIMESTAMP)
            );
            INSERT INTO customers_new SELECT id,ho_ten,gioi_tinh,ngay_sinh,ngay_chet,so_giay_to,ngay_cap,dia_chi,created_at FROM customers;
            DROP TABLE customers;
            ALTER TABLE customers_new RENAME TO customers;
            COMMIT;
            PRAGMA foreign_keys=on;
        """)
    con.close()


def _ensure_table_columns(cur, table_name: str, expected_columns: dict[str, str]):
    cur.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
        (table_name,),
    )
    if cur.fetchone() is None:
        return

    cur.execute(f"PRAGMA table_info({table_name})")
    existing_columns = {row[1] for row in cur.fetchall()}
    for column_name, column_sql in expected_columns.items():
        if column_name not in existing_columns:
            cur.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_sql}")


def migrate_inheritance_cases_schema():
    """Them cac cot moi cho cac bang thua ke tren DB cu."""
    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()
    _ensure_table_columns(cur, "inheritance_cases", {
        "noi_niem_yet": "VARCHAR(200)",
        "engine_state_json": "TEXT",
        "case_state_json": "TEXT",
    })
    _ensure_table_columns(cur, "inheritance_participants", {
        "parent_customer_id": "INTEGER",
    })
    con.commit()
    con.close()


def migrate_properties_schema():
    """Them cac cot moi cho bang properties tren DB cu."""
    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()
    _ensure_table_columns(cur, "properties", {
        "dien_tich": "FLOAT",
        "loai_so": "VARCHAR(200)",
        "land_rows_json": "TEXT",
    })
    con.commit()

    cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='properties'")
    if cur.fetchone() is not None:
        cur.execute("PRAGMA index_list(properties)")
        unique_serial = False
        for index_row in cur.fetchall():
            if not index_row[2]:
                continue
            cur.execute(f"PRAGMA index_info('{index_row[1]}')")
            if [column[2] for column in cur.fetchall()] == ["so_serial"]:
                unique_serial = True
                break

        if unique_serial:
            con.execute("PRAGMA foreign_keys=OFF")
            try:
                cur.executescript(
                    """
                    BEGIN;
                    CREATE TABLE properties_new (
                        id INTEGER NOT NULL,
                        so_serial VARCHAR(100) NOT NULL,
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
                        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                        dien_tich FLOAT,
                        loai_so VARCHAR(200),
                        land_rows_json TEXT,
                        PRIMARY KEY (id)
                    );
                    INSERT INTO properties_new (
                        id, so_serial, so_vao_so, so_thua_dat, so_to_ban_do,
                        dia_chi, loai_dat, hinh_thuc_su_dung, thoi_han,
                        nguon_goc, ngay_cap, co_quan_cap, created_at,
                        dien_tich, loai_so, land_rows_json
                    )
                    SELECT
                        id, so_serial, so_vao_so, so_thua_dat, so_to_ban_do,
                        dia_chi, loai_dat, hinh_thuc_su_dung, thoi_han,
                        nguon_goc, ngay_cap, co_quan_cap, created_at,
                        dien_tich, loai_so, land_rows_json
                    FROM properties;
                    DROP TABLE properties;
                    ALTER TABLE properties_new RENAME TO properties;
                    CREATE INDEX ix_properties_id ON properties(id);
                    COMMIT;
                    """
                )
            except Exception:
                con.rollback()
                raise
            finally:
                con.execute("PRAGMA foreign_keys=ON")

    con.close()


def migrate_inheritance_case_properties_schema():
    """Tao bang lien ket nhieu tai san cho ho so neu chua co."""
    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()
    cur.executescript(
        """
        CREATE TABLE IF NOT EXISTS inheritance_case_properties (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            case_id INTEGER NOT NULL,
            property_id INTEGER NOT NULL,
            is_primary BOOLEAN NOT NULL DEFAULT 0,
            created_at DATETIME DEFAULT (CURRENT_TIMESTAMP),
            updated_at DATETIME DEFAULT (CURRENT_TIMESTAMP),
            FOREIGN KEY(case_id) REFERENCES inheritance_cases(id),
            FOREIGN KEY(property_id) REFERENCES properties(id)
        );
        CREATE UNIQUE INDEX IF NOT EXISTS ix_case_property_unique
        ON inheritance_case_properties(case_id, property_id);
        CREATE INDEX IF NOT EXISTS ix_case_property_case
        ON inheritance_case_properties(case_id);
        CREATE INDEX IF NOT EXISTS ix_case_property_property
        ON inheritance_case_properties(property_id);
        """
    )
    con.commit()
    con.close()


def get_db():
    """Cung cấp kết nối DB cho mỗi request, tự đóng sau khi xong."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
