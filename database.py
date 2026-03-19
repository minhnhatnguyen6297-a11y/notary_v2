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


def get_db():
    """Cung cấp kết nối DB cho mỗi request, tự đóng sau khi xong."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
