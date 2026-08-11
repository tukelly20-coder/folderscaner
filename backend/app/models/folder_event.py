import datetime
import enum

from sqlalchemy import Column, DateTime, Enum, ForeignKey, Integer, String
from sqlalchemy.orm import relationship

from app.database.database import Base


class FolderEventType(str, enum.Enum):
    CREATED = "created"
    DELETED = "deleted"
    MODIFIED = "modified"
    RENAMED = "renamed"
    MOVED = "moved"


class FolderEvent(Base):
    __tablename__ = "folder_events"

    id = Column(Integer, primary_key=True, index=True)
    folder_id = Column(
        Integer,
        ForeignKey("folders.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    event_type = Column(Enum(FolderEventType), nullable=False, index=True)
    old_name = Column(String, nullable=True)
    new_name = Column(String, nullable=True)
    old_path = Column(String, nullable=True)
    new_path = Column(String, nullable=True)
    detected_at = Column(
        DateTime, nullable=False, default=datetime.datetime.utcnow
    )
    source = Column(String, nullable=True)

    folder = relationship("Folder", back_populates="events")
