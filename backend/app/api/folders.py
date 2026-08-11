"""
REST API endpoints for folder CRUD operations.
"""

import datetime
import io
import logging
import mimetypes
import os
import re
from typing import List
from urllib.parse import quote

import pandas as pd
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse, StreamingResponse
from sqlalchemy.orm import Session

from app.config import normalize_smb_root
from app.database.database import get_db
from app.models.folder import Folder, FolderStatus
from app.schemas.folder import FolderRead, FolderUpdate, FolderMove
from app.services.folder_move import FolderMoveService, MoveError
from app.services.folder_rename import FolderRenameService, RenameError

router = APIRouter(prefix="/api/folders", tags=["folders"])
logger = logging.getLogger(__name__)
PROJECT_FOLDER_PATTERN = re.compile(
    r"^[A-Z][A-Z0-9]{0,7}-\d{2}(0[1-9]|1[0-2])-\d{3}(?:$|[-_\s])",
    re.IGNORECASE,
)
YEAR_FOLDER_PATTERN = re.compile(r"^\d{4}$")
MONTH_FOLDER_PATTERN = re.compile(
    r"^(?:(?:0?[1-9]|1[0-2])\s*(?:月|thang|tháng|month)?|(?:thang|tháng|month)\s*(?:0?[1-9]|1[0-2]))$",
    re.IGNORECASE,
)
MAX_PROJECT_SEARCH_DEPTH = 4

PLAN_FILE_EXCLUDES = {
    "__pycache__",
    "node_modules",
    ".git",
    ".svn",
    "thumbs.db",
}


def _normalize_compare_path(value: str) -> str:
    normalized = normalize_smb_root(value).replace("\\", "/")
    if len(normalized) == 3 and normalized[1:] == ":/":
        return normalized
    return normalized.rstrip("/")


def _is_drive_root(root: str) -> bool:
    normalized = _normalize_compare_path(root)
    return len(normalized) == 3 and normalized[1:] == ":/"


def _parent_compare_path(value: str) -> str:
    parent = os.path.dirname(value.replace("\\", "/"))
    if len(parent) == 3 and parent[1:] == ":/":
        return parent
    return parent.rstrip("/")


def _relative_parts(root: str, full_path: str) -> list[str]:
    root_cmp = _normalize_compare_path(root)
    full = (full_path or "").replace("\\", "/")
    prefix = root_cmp if root_cmp.endswith("/") else f"{root_cmp}/"
    if not full.startswith(prefix):
        return []
    rel = full[len(prefix):].strip("/")
    return [part for part in rel.split("/") if part]


def _is_project_folder(name: str) -> bool:
    return bool(PROJECT_FOLDER_PATTERN.match((name or "").strip()))


def _is_year_folder(name: str) -> bool:
    return bool(YEAR_FOLDER_PATTERN.match((name or "").strip()))


def _is_month_folder(name: str) -> bool:
    return bool(MONTH_FOLDER_PATTERN.match((name or "").strip()))


def _is_scoped_project_path(root: str, full_path: str, name: str) -> bool:
    if _is_drive_root(root):
        return _parent_compare_path(full_path or "") == _normalize_compare_path(root) and _is_project_folder(name)

    parts = _relative_parts(root, full_path)
    if not parts or len(parts) > MAX_PROJECT_SEARCH_DEPTH:
        return False
    if not _is_project_folder(name):
        return False

    containers = parts[:-1]
    return all(_is_year_folder(part) or _is_month_folder(part) for part in containers)


def _classify_plan_file(path: str, is_dir: bool = False) -> str:
    if is_dir:
        return "folder"
    ext = os.path.splitext(path)[1].lower()
    if ext == ".pdf":
        return "pdf"
    if ext in {".xls", ".xlsx", ".xlsm", ".csv"}:
        return "bom"
    if ext in {".dwg", ".dxf"}:
        return "drawing"
    if ext in {".step", ".stp", ".igs", ".iges", ".sldprt", ".sldasm"}:
        return "cad"
    return "file"


def _safe_rel_path(value: str | None) -> str:
    rel = (value or "").replace("\\", "/").strip("/")
    if not rel:
        return ""
    normalized = os.path.normpath(rel).replace("\\", "/")
    if normalized == ".":
        return ""
    if normalized.startswith("../") or normalized == ".." or os.path.isabs(normalized):
        raise HTTPException(status_code=400, detail="Invalid relative path")
    return normalized


def _folder_or_404(folder_id: int, db: Session) -> Folder:
    folder = db.query(Folder).filter(Folder.id == folder_id).first()
    if not folder:
        raise HTTPException(status_code=404, detail="Folder not found")
    return folder


def _path_under_folder(folder: Folder, rel: str | None = None) -> tuple[str, str]:
    root = os.path.abspath(folder.absolute_path)
    safe_rel = _safe_rel_path(rel)
    target = os.path.abspath(os.path.join(root, safe_rel)) if safe_rel else root
    if target != root and not target.startswith(root + os.sep):
        raise HTTPException(status_code=400, detail="Invalid relative path")
    return target, safe_rel


def _api_url(folder_id: int, route: str, rel: str = "", download: bool = False) -> str:
    query = f"?rel={quote(rel, safe='')}" if rel else ""
    if download:
        query = f"{query}&download=1" if query else "?download=1"
    return f"/scanner-api/folders/{folder_id}/documents/{route}{query}"


def _count_visible_children(path: str) -> int:
    try:
        with os.scandir(path) as scan:
            return sum(1 for entry in scan if entry.name.lower() not in PLAN_FILE_EXCLUDES)
    except OSError:
        return 0


def _list_plan_folder_entries(folder: Folder, rel: str = "", limit: int = 300) -> list[dict]:
    target, safe_rel = _path_under_folder(folder, rel)
    if not os.path.isdir(target):
        raise HTTPException(status_code=404, detail="SMB folder not found")

    entries: list[dict] = []
    try:
        with os.scandir(target) as scan:
            for entry in scan:
                if entry.name.lower() in PLAN_FILE_EXCLUDES:
                    continue

                try:
                    is_dir = entry.is_dir()
                    stat = entry.stat()
                except OSError:
                    continue

                child_rel = "/".join(part for part in [safe_rel, entry.name] if part)
                item = {
                    "name": entry.name,
                    "type": _classify_plan_file(entry.path, is_dir),
                    "folder_name": os.path.basename(target),
                    "exists": True,
                    "is_dir": is_dir,
                    "size": _count_visible_children(entry.path) if is_dir else stat.st_size,
                    "modified_at": datetime.datetime.utcfromtimestamp(stat.st_mtime).isoformat() + "Z",
                    "view_url": "" if is_dir else _api_url(folder.id, "file", child_rel),
                    "download_url": "" if is_dir else _api_url(folder.id, "file", child_rel, download=True),
                    "list_url": _api_url(folder.id, "folder", child_rel) if is_dir else "",
                }
                entries.append(item)
    except OSError as exc:
        raise HTTPException(status_code=500, detail=f"Cannot read SMB folder: {exc}")

    entries.sort(key=lambda item: (not item["is_dir"], item["name"].lower()))
    return entries[:limit]


@router.get("/", response_model=List[FolderRead])
def list_folders(
    skip: int = 0,
    limit: int = 100,
    status_filter: str | None = None,
    root: str | None = None,
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
    if root:
        normalized_root = _normalize_compare_path(root)
        folders = query.all()
        scoped = [
            folder
            for folder in folders
            if _is_scoped_project_path(
                normalized_root,
                folder.absolute_path or "",
                folder.name or "",
            )
        ]
        return scoped[skip : skip + limit]

    return query.offset(skip).limit(limit).all()


@router.get("/{folder_id}/documents")
def list_folder_documents(
    folder_id: int,
    db: Session = Depends(get_db),
):
    """List files directly from the SMB folder for a plan code."""
    folder = _folder_or_404(folder_id, db)
    entries = _list_plan_folder_entries(folder)
    documents = [entry for entry in entries if not entry["is_dir"]]
    folders = [
        {
            "name": entry["name"],
            "exists": entry["exists"],
            "file_count": entry["size"],
            "list_url": entry["list_url"],
        }
        for entry in entries
        if entry["is_dir"]
    ]
    return {
        "success": True,
        "code": folder.name[:16],
        "message": f"Tim thay {len(documents)} file va {len(folders)} thu muc trong SMB",
        "documents": documents,
        "folders": folders,
        "erp_info": None,
        "smb_path": folder.absolute_path,
    }


@router.get("/{folder_id}/documents/folder")
def list_folder_document_subfolder(
    folder_id: int,
    rel: str = Query(default=""),
    db: Session = Depends(get_db),
):
    """List a subfolder under the plan SMB folder."""
    folder = _folder_or_404(folder_id, db)
    entries = _list_plan_folder_entries(folder, rel)
    _, safe_rel = _path_under_folder(folder, rel)
    return {
        "folder_name": os.path.basename(safe_rel) if safe_rel else folder.name,
        "entries": entries,
        "total": len(entries),
        "truncated": False,
    }


@router.get("/{folder_id}/documents/file")
def get_folder_document_file(
    folder_id: int,
    rel: str = Query(default=""),
    download: bool = Query(default=False),
    db: Session = Depends(get_db),
):
    """Open or download a file under the plan SMB folder."""
    folder = _folder_or_404(folder_id, db)
    target, _ = _path_under_folder(folder, rel)
    if not os.path.isfile(target):
        raise HTTPException(status_code=404, detail="File not found")

    headers = {}
    if download:
        headers["Content-Disposition"] = f'attachment; filename="{os.path.basename(target)}"'
    return FileResponse(
        target,
        media_type=mimetypes.guess_type(target)[0] or "application/octet-stream",
        headers=headers,
    )


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
