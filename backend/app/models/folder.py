import datetime
import enum

from sqlalchemy import Column, DateTime, Enum, ForeignKey, Integer, String
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
    relative_path = Column(String, nullable=False, unique=True, index=True)
    absolute_path = Column(String, nullable=False, unique=True, index=True)
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
