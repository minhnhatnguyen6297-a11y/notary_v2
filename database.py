import sqlite3
from pathlib import Path
from sqlalchemy import create_engine, event
from sqlalchemy.orm import declarative_base, sessionmaker

# Dùng SQLite — file notary.db tự tạo trong thư mục dự án
BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "notary.db"
DATABASE_URL = f"sqlite:///{DB_PATH.as_posix()}"

def _enable_sqlite_foreign_keys(dbapi_connection, _connection_record):
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


def enable_sqlite_foreign_keys(sqlalchemy_engine):
    event.listen(sqlalchemy_engine, "connect", _enable_sqlite_foreign_keys)


engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
enable_sqlite_foreign_keys(engine)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def assert_foreign_key_check():
    con = sqlite3.connect(DB_PATH)
    try:
        violation = con.execute("PRAGMA foreign_key_check").fetchone()
    finally:
        con.close()
    if violation:
        raise RuntimeError("SQLite foreign key check failed")


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
    con.close()


def migrate_zalo_schema():
    """Them cot va bang Zalo theo huong cong them, khong dien giai du lieu cu."""
    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()
    _ensure_table_columns(cur, "zalo_connector_accounts", {
        "qr_generated_at": "DATETIME",
        "qr_expires_at": "DATETIME",
        "intake_consented_at": "DATETIME",
        "policy_version": "INTEGER NOT NULL DEFAULT 0",
        "policy_acked_version": "INTEGER NOT NULL DEFAULT 0",
        "source_sync_request_version": "INTEGER NOT NULL DEFAULT 0",
        "source_sync_acked_version": "INTEGER NOT NULL DEFAULT 0",
        "gap_started_at": "DATETIME",
        "text_storage_full": "BOOLEAN NOT NULL DEFAULT 0",
    })
    _ensure_table_columns(cur, "zalo_sources", {
        "source_type": "VARCHAR(20)",
        "enabled_explicit": "BOOLEAN",
        "acked_enabled": "BOOLEAN",
        "policy_version": "INTEGER NOT NULL DEFAULT 0",
        "policy_acked_version": "INTEGER NOT NULL DEFAULT 0",
        "last_activity_at": "DATETIME",
    })
    cur.executescript("""
        CREATE TABLE IF NOT EXISTS zalo_message_texts (
            id VARCHAR(36) PRIMARY KEY,
            connector_account_id VARCHAR(36) NOT NULL,
            source_id VARCHAR(36) NOT NULL,
            conversation_id VARCHAR(200) NOT NULL,
            msg_id VARCHAR(200) NOT NULL,
            sender_id VARCHAR(200) NOT NULL,
            sent_at DATETIME NOT NULL,
            received_at DATETIME NOT NULL,
            raw_text TEXT NOT NULL,
            payload_digest VARCHAR(64) NOT NULL,
            created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(connector_account_id) REFERENCES zalo_connector_accounts(id),
            FOREIGN KEY(source_id) REFERENCES zalo_sources(id),
            CONSTRAINT uq_zalo_message_text UNIQUE (connector_account_id, conversation_id, msg_id)
        );
        CREATE INDEX IF NOT EXISTS ix_zalo_message_texts_connector_account_id
        ON zalo_message_texts(connector_account_id);
        CREATE INDEX IF NOT EXISTS ix_zalo_message_texts_source_id
        ON zalo_message_texts(source_id);
        CREATE TABLE IF NOT EXISTS zalo_data_sync_runs (
            id VARCHAR(36) PRIMARY KEY,
            connector_account_id VARCHAR(36) NOT NULL,
            status VARCHAR(30) NOT NULL,
            cutoff_at DATETIME NOT NULL,
            deadline_at DATETIME NOT NULL,
            source_ids_json JSON NOT NULL DEFAULT '[]',
            counters_json JSON NOT NULL DEFAULT '{}',
            error_message TEXT,
            started_at DATETIME NOT NULL,
            completed_at DATETIME,
            FOREIGN KEY(connector_account_id) REFERENCES zalo_connector_accounts(id)
        );
        CREATE INDEX IF NOT EXISTS ix_zalo_data_sync_runs_connector_account_id
        ON zalo_data_sync_runs(connector_account_id);
        CREATE UNIQUE INDEX IF NOT EXISTS uq_zalo_data_sync_running_account
        ON zalo_data_sync_runs(connector_account_id) WHERE status = 'running';
    """)
    con.commit()
    con.close()
    assert_foreign_key_check()


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
