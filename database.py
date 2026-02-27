from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

# Dùng SQLite — file notary.db tự tạo trong thư mục dự án
DATABASE_URL = "sqlite:///./notary.db"

engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db():
    """Cung cấp kết nối DB cho mỗi request, tự đóng sau khi xong."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
