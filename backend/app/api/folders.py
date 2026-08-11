"""
REST API endpoints for folder CRUD operations.
"""

import datetime
import io
import logging
from typing import List

import pandas as pd
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.database.database import get_db
from app.models.folder import Folder, FolderStatus
from app.schemas.folder import FolderRead, FolderUpdate, FolderMove
from app.services.folder_move import FolderMoveService, MoveError
from app.services.folder_rename import FolderRenameService, RenameError

router = APIRouter(prefix="/api/folders", tags=["folders"])
logger = logging.getLogger(__name__)


@router.get("/", response_model=List[FolderRead])
def list_folders(
    skip: int = 0,
    limit: int = 100,
    status_filter: str | None = None,
    db: Session = Depends(get_db),
):
    """GET /api/folders — List all folders (optionally filtered by status)."""
    query = db.query(Folder).order_by(Folder.id.desc())
    if status_filter:
        try:
            status = FolderStatus(status_filter)
            query = query.filter(Folder.status == status)
        except ValueError:
            pass
    return query.offset(skip).limit(limit).all()


@router.get("/{folder_id}", response_model=FolderRead)
def get_folder(
    folder_id: int,
    db: Session = Depends(get_db),
):
    """GET /api/folders/{id} — Get single folder."""
    folder = db.query(Folder).filter(Folder.id == folder_id).first()
    if not folder:
        raise HTTPException(status_code=404, detail="Folder not found")
    return folder


@router.put("/{folder_id}", response_model=FolderRead)
def update_folder(
    folder_id: int,
    payload: FolderUpdate,
    db: Session = Depends(get_db),
):
    """
    PUT /api/folders/{id} — Update folder (rename via name field).

    CRITICAL ORDERING (architecture spec section 14):
      Validate -> Check duplicate -> Rename SMB Folder -> SUCCESS -> Update DB
    """
    if payload.name is None and payload.status is None:
        raise HTTPException(
            status_code=400,
            detail="At least one of name or status must be provided.",
        )

    if payload.name is not None:
        svc = FolderRenameService(db)
        try:
            updated = svc.rename_folder(folder_id, payload.name)
            return updated
        except RenameError as exc:
            raise HTTPException(
                status_code=exc.status_code,
                detail={
                    "error": exc.error_code,
                    "message": exc.message,
                },
            )

    folder = db.query(Folder).filter(Folder.id == folder_id).first()
    if not folder:
        raise HTTPException(status_code=404, detail="Folder not found")

    if payload.status is not None:
        folder.status = payload.status
        folder.updated_at = datetime.datetime.utcnow()
        db.commit()
        db.refresh(folder)
    elif payload.name is not None:
        folder.name = payload.name
        folder.updated_at = datetime.datetime.utcnow()
        db.commit()
        db.refresh(folder)

    return folder


@router.post("/{folder_id}/move", response_model=FolderRead)
def move_folder(
    folder_id: int,
    payload: FolderMove,
    db: Session = Depends(get_db),
):
    """
    POST /api/folders/{id}/move — Move a folder to a new location on the SMB share.

    The body contains :attr:`payload.new_relative_path` (the target location
    relative to ``SMB_ROOT``) and an optional :attr:`payload.new_name` to
    rename the leaf folder during the move.  The filesystem (SMB) is the source
    of truth; the database is only updated after a successful move on disk.
    """
    svc = FolderMoveService(db)
    try:
        return svc.move_folder(folder_id, payload.new_relative_path, payload.new_name)
    except MoveError as exc:
        raise HTTPException(
            status_code=exc.status_code,
            detail={
                "error": exc.error_code,
                "message": exc.message,
            },
        )


@router.delete("/{folder_id}", response_model=FolderRead)
def delete_folder(
    folder_id: int,
    db: Session = Depends(get_db),
):
    """
    DELETE /api/folders/{id} — Soft-delete folder (sets status=DELETED).

    Uses os.rename to move the folder to a _deleted_ subfolder on disk
    so the filesystem stays consistent.  If the rename on disk fails,
    the DB record is NOT soft-deleted.
    """
    folder = db.query(Folder).filter(Folder.id == folder_id).first()
    if not folder:
        raise HTTPException(status_code=404, detail="Folder not found")

    if folder.status == FolderStatus.DELETED:
        raise HTTPException(status_code=400, detail="Folder is already deleted")

    import os
    import shutil

    deleted_marker = "_deleted"
    parent_dir = os.path.dirname(folder.absolute_path)
    deleted_dir = os.path.join(parent_dir, deleted_marker)
    target_path = os.path.join(deleted_dir, folder.name)

    try:
        os.makedirs(deleted_dir, exist_ok=True)
        shutil.move(folder.absolute_path, target_path)
    except OSError as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Cannot move folder on disk: {exc}",
        )

    from app.models.folder_event import FolderEvent, FolderEventType

    old_name = folder.name
    old_path = folder.absolute_path
    folder.status = FolderStatus.DELETED
    folder.name = folder.name
    folder.absolute_path = target_path.replace("\\", "/")
    folder.updated_at = datetime.datetime.utcnow()

    event = FolderEvent(
        folder_id=folder.id,
        event_type=FolderEventType.DELETED,
        old_name=old_name,
        old_path=old_path,
        new_path=folder.absolute_path,
        source="API",
    )
    db.add(event)
    db.commit()
    db.refresh(folder)
    return folder


@router.get("/export/excel")
def export_folders_excel(
    db: Session = Depends(get_db),
):
    """GET /api/folders/export/excel — Export all folders to XLSX."""
    folders = db.query(Folder).order_by(Folder.id.desc()).all()

    df = pd.DataFrame(
        [
            {
                "ID": f.id,
                "Folder Name": f.name,
                "Relative Path": f.relative_path,
                "Absolute Path": f.absolute_path,
                "Parent ID": f.parent_id,
                "Status": f.status.value,
                "First Seen": f.first_seen,
                "Last Seen": f.last_seen,
                "Created At": f.created_at,
                "Updated At": f.updated_at,
            }
            for f in folders
        ]
    )

    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        df.to_excel(writer, sheet_name="Folders", index=False)
    buffer.seek(0)

    return StreamingResponse(
        buffer,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=folders_export.xlsx"},
    )
