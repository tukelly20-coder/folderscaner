from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, ConfigDict

from app.schemas.event import FolderEventRead


class FolderStatus(str, Enum):
    ACTIVE = "active"
    DELETED = "deleted"
    PENDING = "pending"


class FolderBase(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    name: str
    relative_path: str
    absolute_path: str
    parent_id: Optional[int] = None
    status: FolderStatus = FolderStatus.ACTIVE


class FolderCreate(FolderBase):
    pass


class FolderUpdate(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    name: Optional[str] = None
    relative_path: Optional[str] = None
    absolute_path: Optional[str] = None
    parent_id: Optional[int] = None
    status: Optional[FolderStatus] = None


class FolderMove(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    new_relative_path: str
    new_name: Optional[str] = None


class FolderRead(FolderBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    first_seen: datetime
    last_seen: datetime
    created_at: datetime
    updated_at: datetime
    children: List["FolderRead"] = []
    events: List[FolderEventRead] = []


FolderRead.model_rebuild()


class FolderListResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    relative_path: str
    absolute_path: str
    parent_id: Optional[int]
    status: FolderStatus
    first_seen: datetime
    last_seen: datetime
    created_at: datetime
    updated_at: datetime
