import uuid
from sqlalchemy import Column, Integer, String, Date, Boolean, Float, ForeignKey, Text, DateTime, JSON
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from database import Base


class Customer(Base):
    """Bảng lưu thông tin người (sống hoặc đã chết)."""
    __tablename__ = "customers"

    id           = Column(Integer, primary_key=True, index=True)
    ho_ten       = Column(String(200), nullable=False)
    gioi_tinh    = Column(String(10),  nullable=True)           # Nam / Nữ
    ngay_sinh    = Column(Date,        nullable=True)
    ngay_chet    = Column(Date,        nullable=True)            # NULL = còn sống
    so_giay_to   = Column(String(50),  nullable=True,  unique=True)
    ngay_cap     = Column(Date,        nullable=True)
    dia_chi      = Column(Text,        nullable=True)
    created_at   = Column(DateTime,    server_default=func.now())

    # Quan hệ
    participations   = relationship(
        "InheritanceParticipant",
        back_populates="customer",
        cascade="all, delete-orphan",
        foreign_keys="InheritanceParticipant.customer_id",
    )
    inheritance_cases = relationship("InheritanceCase", back_populates="nguoi_chet", foreign_keys="InheritanceCase.nguoi_chet_id")

    @property
    def con_song(self):
        return self.ngay_chet is None

    @property
    def _moc_cccd_moi(self):
        """01/07/2024 — ngưỡng phân biệt CCCD cũ/mới."""
        from datetime import date
        return self.ngay_cap and self.ngay_cap >= date(2024, 10, 1)

    @property
    def loai_giay_to(self):
        """Căn cước công dân (trước 01/10/2024) hoặc Căn cước (từ 01/10/2024)."""
        return "Căn cước" if self._moc_cccd_moi else "Căn cước công dân"

    @property
    def noi_cap(self):
        """Bộ Công an (từ 01/10/2024) hoặc Cục CSQLHC về TTXH (trước đó)."""
        return "Bộ Công an" if self._moc_cccd_moi else "Cục cảnh sát quản lý hành chính về trật tự xã hội"

    @property
    def loai_dia_chi(self):
        """'Cư trú tại' (từ 01/10/2024) hoặc 'Thường trú tại' (trước đó)."""
        return "Cư trú tại" if self._moc_cccd_moi else "Thường trú tại"


class Property(Base):
    """Bảng lưu thông tin Giấy chứng nhận quyền sử dụng đất (sổ đỏ)."""
    __tablename__ = "properties"

    id                = Column(Integer, primary_key=True, index=True)
    so_serial         = Column(String(100), nullable=False, unique=True)
    so_vao_so         = Column(String(100), nullable=True)
    so_thua_dat       = Column(String(100), nullable=True)
    so_to_ban_do      = Column(String(100), nullable=True)
    dia_chi           = Column(Text,        nullable=False)
    loai_dat          = Column(String(100), nullable=True)
    dien_tich         = Column(Float,        nullable=True)
    loai_so           = Column(String(200), nullable=True)   # Loại GCN (3 loại)
    land_rows_json    = Column(Text,        nullable=True)   # JSON: [{loai_dat, dien_tich, thoi_han}]
    hinh_thuc_su_dung = Column(String(100), nullable=True)
    thoi_han          = Column(String(100), nullable=True)
    nguon_goc         = Column(Text,        nullable=True)
    ngay_cap          = Column(Date,        nullable=True)
    co_quan_cap       = Column(String(200), nullable=True)
    created_at        = Column(DateTime,    server_default=func.now())

    # Quan hệ
    inheritance_cases = relationship("InheritanceCase", back_populates="tai_san")
    case_links = relationship("InheritanceCaseProperty", back_populates="property", cascade="all, delete-orphan")


class InheritanceCase(Base):
    """Bảng lưu Hồ sơ thừa kế — trung tâm của hệ thống."""
    __tablename__ = "inheritance_cases"

    id               = Column(Integer, primary_key=True, index=True)
    nguoi_chet_id    = Column(Integer, ForeignKey("customers.id"), nullable=False)
    tai_san_id       = Column(Integer, ForeignKey("properties.id"), nullable=False)
    ngay_lap_ho_so   = Column(Date,    nullable=False)
    loai_van_ban     = Column(String(50), default="khai_nhan")   # khai_nhan / thoa_thuan
    trang_thai       = Column(String(20), default="draft")       # draft / locked
    noi_niem_yet     = Column(String(200), nullable=True)        # Tên xã/thị trấn nơi lập văn bản
    ghi_chu          = Column(Text,    nullable=True)
    engine_state_json = Column(Text,   nullable=True)            # JSON state cua engine/sơ đồ thừa kế mới
    created_at       = Column(DateTime, server_default=func.now())

    # Quan hệ
    nguoi_chet   = relationship("Customer", back_populates="inheritance_cases", foreign_keys=[nguoi_chet_id])
    tai_san      = relationship("Property", back_populates="inheritance_cases")
    property_links = relationship("InheritanceCaseProperty", back_populates="case", cascade="all, delete-orphan")
    participants = relationship("InheritanceParticipant", back_populates="ho_so", cascade="all, delete-orphan")

    @property
    def is_locked(self):
        return self.trang_thai == "locked"

    @property
    def tong_ty_le(self):
        return sum(p.ty_le or 0 for p in self.participants if p.co_nhan_tai_san)


class InheritanceCaseProperty(Base):
    """Lien ket nhieu tai san cho mot ho so."""
    __tablename__ = "inheritance_case_properties"

    id = Column(Integer, primary_key=True, index=True)
    case_id = Column(Integer, ForeignKey("inheritance_cases.id"), nullable=False)
    property_id = Column(Integer, ForeignKey("properties.id"), nullable=False)
    is_primary = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    case = relationship("InheritanceCase", back_populates="property_links")
    property = relationship("Property", back_populates="case_links")


class InheritanceParticipant(Base):
    """Bảng lưu những người tham gia hồ sơ thừa kế."""
    __tablename__ = "inheritance_participants"

    id               = Column(Integer, primary_key=True, index=True)
    ho_so_id         = Column(Integer, ForeignKey("inheritance_cases.id"),  nullable=False)
    customer_id      = Column(Integer, ForeignKey("customers.id"),          nullable=False)
    vai_tro          = Column(String(50),  nullable=False)   # Vợ/Chồng, Con, Cha/Mẹ, Anh/Chị/Em
    hang_thua_ke     = Column(Integer,     default=1)        # Hàng thừa kế 1, 2, 3
    co_nhan_tai_san  = Column(Boolean,     default=True)     # True = nhận, False = từ chối
    ty_le            = Column(Float,       default=0.0)      # Tỷ lệ % sở hữu sau phân chia
    ghi_chu          = Column(Text,        nullable=True)
    parent_customer_id = Column(Integer, ForeignKey("customers.id"), nullable=True)

    # Quan hệ
    ho_so    = relationship("InheritanceCase", back_populates="participants")
    customer = relationship("Customer",        foreign_keys=[customer_id], back_populates="participations")
    parent_customer = relationship("Customer", foreign_keys=[parent_customer_id])


class WordTemplate(Base):
    """Luu cac file mau Word do nguoi dung tai len de xuat van ban."""
    __tablename__ = "word_templates"

    id = Column(Integer, primary_key=True, index=True)
    ten_mau = Column(String(200), nullable=False)
    ten_file_goc = Column(String(255), nullable=False)
    duong_dan_file = Column(String(500), nullable=False)
    is_active = Column(Boolean, default=False)
    created_at = Column(DateTime, server_default=func.now())


class OCRJob(Base):
    """Tram kiem soat tien do OCR."""
    __tablename__ = "ocr_jobs"

    id = Column(String(36), primary_key=True, index=True, default=lambda: str(uuid.uuid4()))
    status = Column(String(20), nullable=False, default="queued")
    temp_file_path = Column(Text, nullable=True)
    result_json = Column(JSON, nullable=True)
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


class ExtractedDocument(Base):
    """Kho luu tru du lieu da boc tach sau khi user xac nhan."""
    __tablename__ = "extracted_documents"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, nullable=True)
    document_type = Column(String(50), nullable=False)
    raw_text = Column(Text, nullable=True)
    parsed_data = Column(JSON, nullable=True)
    created_at = Column(DateTime, server_default=func.now())
