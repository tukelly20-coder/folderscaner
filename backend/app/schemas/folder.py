from __future__ import annotations

from datetime import datetime
from enum import Enum
import json
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

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
    customer_name: Optional[str] = None
    customer_subfolder_name: Optional[str] = None
    salesperson_name: Optional[str] = None
    drawing_codes: List[str] = Field(default_factory=list)


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
    source_mtime: Optional[datetime] = None
    document_scanned_at: Optional[datetime] = None
    children: List["FolderRead"] = []
    events: List[FolderEventRead] = []

    @field_validator("drawing_codes", mode="before")
    @classmethod
    def parse_drawing_codes(cls, value):
        if value is None:
            return []
        if isinstance(value, list):
            return value
        if isinstance(value, str):
            try:
                parsed = json.loads(value)
                return parsed if isinstance(parsed, list) else []
            except json.JSONDecodeError:
                return [item.strip() for item in value.split(",") if item.strip()]
        return []


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
    source_mtime: Optional[datetime] = None
    document_scanned_at: Optional[datetime] = None
    customer_name: Optional[str] = None
    customer_subfolder_name: Optional[str] = None
    salesperson_name: Optional[str] = None
    drawing_codes: List[str] = Field(default_factory=list)
