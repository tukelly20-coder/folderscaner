"""
REST API endpoints for scanner control.
"""

from typing import List

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.config import settings
from app.database.database import get_db
from app.services.folder_scanner import FolderScanner, _parse_excludes

router = APIRouter(prefix="/api/scanner", tags=["scanner"])


class ExcludesUpdate(BaseModel):
    excludes: List[str]


@router.get("/status")
def scanner_status():
    """GET /api/scanner/status — Get scanner configuration and running state."""
    return {
        "scan_interval": settings.SCAN_INTERVAL,
        "smb_root": settings.SMB_ROOT,
        "excludes": _parse_excludes(settings.SMB_EXCLUDES),
        "running": True,
    }


@router.post("/scan")
def trigger_scan(
    db: Session = Depends(get_db),
):
    """POST /api/scanner/scan — Trigger a manual scan of the filesystem."""
    scanner = FolderScanner(db=db)
    summary = scanner.scan_once()
    return {"success": True, "results": summary}


@router.post("/excludes")
def update_excludes(
    payload: ExcludesUpdate,
    db: Session = Depends(get_db),
):
    """POST /api/scanner/excludes — Update the folder exclusion list and trigger a new scan."""
    settings.SMB_EXCLUDES = ",".join(payload.excludes)
    scanner = FolderScanner(db=db, excludes=payload.excludes)
    summary = scanner.scan_once()
    return {"success": True, "excludes": payload.excludes, "results": summary}
