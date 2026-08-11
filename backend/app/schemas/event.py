from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, ConfigDict


class FolderEventType(str, Enum):
    CREATED = "created"
    DELETED = "deleted"
    MODIFIED = "modified"
    RENAMED = "renamed"
    MOVED = "moved"


class FolderEventBase(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    event_type: FolderEventType
    old_name: Optional[str] = None
    new_name: Optional[str] = None
    old_path: Optional[str] = None
    new_path: Optional[str] = None
    source: Optional[str] = None


class FolderEventCreate(FolderEventBase):
    folder_id: int


class FolderEventRead(FolderEventBase):
    id: int
    folder_id: int
    detected_at: datetime
