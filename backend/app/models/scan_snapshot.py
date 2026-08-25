import datetime

from sqlalchemy import Column, DateTime, Integer, String, UniqueConstraint

from app.database.database import Base


class ScanSnapshot(Base):
    __tablename__ = "scan_snapshots"
    __table_args__ = (
        UniqueConstraint("scan_root", "relative_path", name="uq_scan_snapshot_root_path"),
    )

    id = Column(Integer, primary_key=True, index=True)
    scan_root = Column(String, nullable=False, index=True)
    relative_path = Column(String, nullable=False, index=True)
    signature = Column(String, nullable=False)
    last_scanned_at = Column(DateTime, nullable=False, default=datetime.datetime.utcnow)
    created_at = Column(DateTime, nullable=False, default=datetime.datetime.utcnow)
    updated_at = Column(
        DateTime,
        nullable=False,
        default=datetime.datetime.utcnow,
        onupdate=datetime.datetime.utcnow,
    )
