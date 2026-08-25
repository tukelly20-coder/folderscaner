from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class UserSmbRootUpdate(BaseModel):
    user_key: str
    smb_root: str = ""


class UserSmbRootRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    user_key: str
    smb_root: str
    active: bool
    created_at: datetime
    updated_at: datetime
