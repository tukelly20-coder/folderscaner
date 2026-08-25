import datetime
import enum
import json

from sqlalchemy import Column, DateTime, Enum, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship

from app.database.database import Base


class FolderStatus(str, enum.Enum):
    ACTIVE = "active"
    DELETED = "deleted"
    PENDING = "pending"


class Folder(Base):
    __tablename__ = "folders"

    id = Column(Integer, primary_key=True, index=True)
    parent_id = Column(
        Integer,
        ForeignKey("folders.id"),
        index=True,
        nullable=True,
    )
    name = Column(String, nullable=False)
    relative_path = Column(String, nullable=False, index=True)
    absolute_path = Column(String, nullable=False, unique=True, index=True)
    scan_root = Column(String, nullable=True, index=True)
    status = Column(
        Enum(FolderStatus),
        nullable=False,
        default=FolderStatus.ACTIVE,
    )
    first_seen = Column(DateTime, nullable=False, default=datetime.datetime.utcnow)
    last_seen = Column(DateTime, nullable=False, default=datetime.datetime.utcnow)
    created_at = Column(DateTime, nullable=False, default=datetime.datetime.utcnow)
    updated_at = Column(
        DateTime,
        nullable=False,
        default=datetime.datetime.utcnow,
        onupdate=datetime.datetime.utcnow,
    )
    source_mtime = Column(DateTime, nullable=True)
    document_signature = Column(String, nullable=True)
    document_scanned_at = Column(DateTime, nullable=True)
    customer_name = Column(String, nullable=True)
    customer_subfolder_name = Column(String, nullable=True)
    salesperson_name = Column(String, nullable=True)
    drawing_codes_json = Column(Text, nullable=True)

    parent = relationship(
        "Folder",
        remote_side=[id],
        backref="children",
    )
    events = relationship(
        "FolderEvent",
        back_populates="folder",
        cascade="all, delete-orphan",
    )

    @property
    def drawing_codes(self) -> list[str]:
        if not self.drawing_codes_json:
            return []
        try:
            parsed = json.loads(self.drawing_codes_json)
            return parsed if isinstance(parsed, list) else []
        except json.JSONDecodeError:
            return []
