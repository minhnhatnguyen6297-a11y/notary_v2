import sqlite3
from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

# Dùng SQLite — file notary.db tự tạo trong thư mục dự án
DATABASE_URL = "sqlite:///./notary.db"

engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def migrate_customers_nullable():
    """Chuyển các cột customers (trừ ho_ten) sang nullable nếu chưa có."""
    con = sqlite3.connect("notary.db")
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
    con = sqlite3.connect("notary.db")
    cur = con.cursor()
    _ensure_table_columns(cur, "inheritance_cases", {
        "noi_niem_yet": "VARCHAR(200)",
    })
    _ensure_table_columns(cur, "inheritance_participants", {
        "parent_customer_id": "INTEGER",
    })
    con.commit()
    con.close()


def migrate_properties_schema():
    """Them cac cot moi cho bang properties tren DB cu."""
    con = sqlite3.connect("notary.db")
    cur = con.cursor()
    _ensure_table_columns(cur, "properties", {
        "dien_tich": "FLOAT",
        "loai_so": "VARCHAR(200)",
        "land_rows_json": "TEXT",
    })
    con.commit()
    con.close()


def get_db():
    """Cung cấp kết nối DB cho mỗi request, tự đóng sau khi xong."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
