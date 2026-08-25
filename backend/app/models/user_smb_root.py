import datetime

from sqlalchemy import Boolean, Column, DateTime, Integer, String

from app.database.database import Base


class UserSmbRoot(Base):
    __tablename__ = "user_smb_roots"

    id = Column(Integer, primary_key=True, index=True)
    user_key = Column(String, nullable=False, unique=True, index=True)
    smb_root = Column(String, nullable=False, index=True)
    active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime, nullable=False, default=datetime.datetime.utcnow)
    updated_at = Column(
        DateTime,
        nullable=False,
        default=datetime.datetime.utcnow,
        onupdate=datetime.datetime.utcnow,
    )
