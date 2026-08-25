"""
REST API endpoints for scanner control.
"""

from typing import List, Optional

import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.config import normalize_smb_root, settings
from app.database.database import get_db
from app.models.user_smb_root import UserSmbRoot
from app.schemas.user_smb_root import UserSmbRootRead, UserSmbRootUpdate
from app.services.folder_scanner import FolderScanner, _parse_excludes
from app.services.sync_service import scanner_scheduler

router = APIRouter(prefix="/api/scanner", tags=["scanner"])


class ExcludesUpdate(BaseModel):
    excludes: List[str]


def _clean_user_key(value: str) -> str:
    cleaned = (value or "").strip()
    if not cleaned:
        raise HTTPException(status_code=400, detail="Missing user_key")
    return cleaned[:255]


def _empty_scan_summary() -> dict:
    return {
        "created": 0,
        "deleted": 0,
        "renamed": 0,
        "modified": 0,
        "document_cache_updated": 0,
        "project_sync_updated": 0,
        "project_sync_skipped": 0,
        "errors": [],
    }


def _active_user_roots(db: Session) -> list[str]:
    rows = (
        db.query(UserSmbRoot)
        .filter(UserSmbRoot.active == True, UserSmbRoot.smb_root != "")
        .all()
    )

    roots: list[str] = []
    seen: set[str] = set()
    for row in rows:
        normalized = normalize_smb_root(row.smb_root)
        key = normalized.replace("\\", "/").lower()
        if normalized and key not in seen:
            seen.add(key)
            roots.append(normalized)
    return roots


def _merge_scan_summary(total: dict, next_summary: dict) -> dict:
    for key, value in next_summary.items():
        if isinstance(value, int):
            total[key] = int(total.get(key, 0)) + value
        elif key == "errors":
            total.setdefault("errors", []).extend(value or [])
    return total


@router.get("/status")
def scanner_status():
    """GET /api/scanner/status — Get scanner configuration and running state."""
    scheduler_status = scanner_scheduler.status()
    return {
        "scan_interval": settings.SCAN_INTERVAL,
        "scanner_mode": scheduler_status["mode"],
        "scanner": scheduler_status,
        "smb_root": settings.SMB_ROOT,
        "excludes": _parse_excludes(settings.SMB_EXCLUDES),
        "running": scanner_scheduler.running,
    }


@router.get("/user-root", response_model=UserSmbRootRead | None)
def get_user_smb_root(
    user_key: str = Query(...),
    db: Session = Depends(get_db),
):
    """Return the persisted SMB root for one web user."""
    cleaned_user = _clean_user_key(user_key)
    return (
        db.query(UserSmbRoot)
        .filter(UserSmbRoot.user_key == cleaned_user, UserSmbRoot.active == True)
        .first()
    )


@router.put("/user-root", response_model=UserSmbRootRead | None)
def save_user_smb_root(
    payload: UserSmbRootUpdate,
    db: Session = Depends(get_db),
):
    """Persist one user's SMB root so the background scanner can scan it."""
    cleaned_user = _clean_user_key(payload.user_key)
    cleaned_root = normalize_smb_root(payload.smb_root)
    existing = db.query(UserSmbRoot).filter(UserSmbRoot.user_key == cleaned_user).first()

    if not cleaned_root:
        if existing:
            existing.smb_root = ""
            existing.active = False
            existing.updated_at = datetime.datetime.utcnow()
            db.commit()
            scanner_scheduler.request_reconcile()
        return None

    if existing:
        existing.smb_root = cleaned_root
        existing.active = True
        existing.updated_at = datetime.datetime.utcnow()
        db.commit()
        db.refresh(existing)
        scanner_scheduler.request_reconcile()
        return existing

    created = UserSmbRoot(user_key=cleaned_user, smb_root=cleaned_root, active=True)
    db.add(created)
    db.commit()
    db.refresh(created)
    scanner_scheduler.request_reconcile()
    return created


@router.post("/scan")
def trigger_scan(
    root: Optional[str] = Query(default=None),
    user_key: Optional[str] = Query(default=None),
    force_documents: bool = Query(default=True),
    db: Session = Depends(get_db),
):
    """POST /api/scanner/scan — Trigger a manual scan of the filesystem."""
    _ = root
    if not user_key:
        raise HTTPException(status_code=400, detail="Missing user_key")

    cleaned_user = _clean_user_key(user_key)
    saved = (
        db.query(UserSmbRoot)
        .filter(UserSmbRoot.user_key == cleaned_user, UserSmbRoot.active == True)
        .first()
    )
    scan_root = saved.smb_root if saved else ""
    if not scan_root:
        raise HTTPException(status_code=400, detail="Missing SMB root for this user")

    scanner = FolderScanner(
        db=db,
        smb_root=scan_root,
        force_document_cache=force_documents,
        force_full_scan=True,
    )
    summary = scanner.scan_once()
    return {"success": True, "results": summary}


@router.post("/excludes")
def update_excludes(
    payload: ExcludesUpdate,
    db: Session = Depends(get_db),
):
    """POST /api/scanner/excludes — Update the folder exclusion list and trigger a new scan."""
    settings.SMB_EXCLUDES = ",".join(payload.excludes)
    summary = _empty_scan_summary()
    for root in _active_user_roots(db):
        scanner = FolderScanner(
            db=db,
            smb_root=root,
            excludes=payload.excludes,
            force_document_cache=True,
            force_full_scan=True,
        )
        _merge_scan_summary(summary, scanner.scan_once())
    return {"success": True, "excludes": payload.excludes, "results": summary}
