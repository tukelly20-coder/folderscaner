"""
REST API endpoints for document folder scanning.
"""

import datetime
import mimetypes
import os
import subprocess
import threading
import time
from urllib.parse import quote

from fastapi import APIRouter, Depends, Query
from fastapi import HTTPException
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.database.database import get_db
from app.models.folder import Folder
from app.models.user_smb_root import UserSmbRoot
from app.schemas.document_scan import DocumentScanResponse
from app.services.document_scanner import DocumentScanner
from app.services.project_sync import sync_folder_to_main_project

router = APIRouter(prefix="/api/documents", tags=["documents"])

PLAN_FILE_EXCLUDES = {
    "__pycache__",
    "node_modules",
    ".git",
    ".svn",
    "thumbs.db",
}

PLAN_FILE_EXCLUDED_EXTENSIONS = {
    ".py",
    ".pyc",
    ".pyo",
}

EXPLORER_OPEN_DEBOUNCE_SECONDS = 3.0
_EXPLORER_OPEN_LOCK = threading.Lock()
_LAST_EXPLORER_OPEN: dict[str, float] = {}


def _is_plan_file_excluded(name: str) -> bool:
    lowered = name.lower()
    return lowered in PLAN_FILE_EXCLUDES or os.path.splitext(lowered)[1] in PLAN_FILE_EXCLUDED_EXTENSIONS


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


def _refresh_folder_metadata(folder: Folder, db: Session) -> dict:
    """Refresh document-derived metadata before Propack displays this folder."""
    result = {"cache_updated": False, "project_sync": None}
    try:
        scanner = DocumentScanner(folder.scan_root or None)
        result["cache_updated"] = scanner.update_folder_cache(folder, force=True)
        result["project_sync"] = sync_folder_to_main_project(folder)
        db.commit()
    except Exception as exc:
        db.rollback()
        result["error"] = str(exc)
    return result


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
    return f"/scanner-api/documents/folders/{folder_id}/{route}{query}"


def _should_skip_recent_explorer_open(path: str) -> bool:
    key = os.path.normcase(os.path.abspath(path))
    now = time.monotonic()
    with _EXPLORER_OPEN_LOCK:
        last_opened_at = _LAST_EXPLORER_OPEN.get(key, 0)
        if now - last_opened_at < EXPLORER_OPEN_DEBOUNCE_SECONDS:
            return True
        _LAST_EXPLORER_OPEN[key] = now
    return False


def _open_folder_in_explorer(path: str) -> None:
    if not os.path.isdir(path):
        raise HTTPException(status_code=404, detail="Folder not found")
    if os.name != "nt":
        raise HTTPException(status_code=400, detail="Opening Windows Explorer is only supported on Windows")
    if _should_skip_recent_explorer_open(path):
        return

    script = """
$Target = $args[0]
$ErrorActionPreference = 'Stop'
$shell = New-Object -ComObject Shell.Application
$windows = @($shell.Windows() | Where-Object {
    try { [System.IO.Path]::GetFileName($_.FullName).ToLowerInvariant() -eq 'explorer.exe' } catch { $false }
})
if ($windows.Count -gt 0) {
    $windows[0].Navigate2($Target)
    $windows[0].Visible = $true
} else {
    Start-Process explorer.exe -ArgumentList $Target
}
"""
    try:
        completed = subprocess.run(
            ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", script, path],
            timeout=5,
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        if completed.returncode != 0:
            subprocess.Popen(["explorer", path])
    except OSError:
        try:
            subprocess.Popen(["explorer", path])
        except OSError as exc:
            raise HTTPException(status_code=500, detail=f"Cannot open Windows Explorer: {exc}")
    except subprocess.TimeoutExpired:
        subprocess.Popen(["explorer", path])


def _count_visible_children(path: str) -> int:
    try:
        with os.scandir(path) as scan:
            return sum(1 for entry in scan if not _is_plan_file_excluded(entry.name))
    except OSError:
        return 0


def _list_plan_folder_entries(folder: Folder, rel: str = "", limit: int = 300) -> list[dict]:
    target, safe_rel = _path_under_folder(folder, rel)
    if not os.path.isdir(target):
        raise HTTPException(status_code=404, detail=f"SMB folder not found: {folder.absolute_path}")

    entries: list[dict] = []
    try:
        with os.scandir(target) as scan:
            for entry in scan:
                if _is_plan_file_excluded(entry.name):
                    continue

                try:
                    is_dir = entry.is_dir()
                    stat = entry.stat()
                except OSError:
                    continue

                child_rel = "/".join(part for part in [safe_rel, entry.name] if part)
                entries.append({
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
                    "open_url": _api_url(folder.id, "open", child_rel) if is_dir else "",
                })
    except OSError as exc:
        raise HTTPException(status_code=500, detail=f"Cannot read SMB folder: {exc}")

    entries.sort(key=lambda item: (not item["is_dir"], item["name"].lower()))
    return entries[:limit]


def _list_plan_pdf_entries(folder: Folder, limit: int = 300) -> list[dict]:
    root = os.path.abspath(folder.absolute_path)
    if not os.path.isdir(root):
        return []

    entries: list[dict] = []
    try:
        for current_root, dirs, files in os.walk(root):
            dirs[:] = [name for name in dirs if not _is_plan_file_excluded(name)]
            for name in files:
                if len(entries) >= limit:
                    break
                if _is_plan_file_excluded(name) or os.path.splitext(name)[1].lower() != ".pdf":
                    continue

                path = os.path.join(current_root, name)
                try:
                    stat = os.stat(path)
                except OSError:
                    continue

                rel = os.path.relpath(path, root).replace("\\", "/")
                rel_folder = os.path.dirname(rel).replace("\\", "/")
                entries.append({
                    "name": name,
                    "type": "pdf",
                    "folder_name": os.path.basename(current_root),
                    "relative_folder": rel_folder,
                    "exists": True,
                    "is_dir": False,
                    "size": stat.st_size,
                    "modified_at": datetime.datetime.utcfromtimestamp(stat.st_mtime).isoformat() + "Z",
                    "view_url": _api_url(folder.id, "file", rel),
                    "download_url": _api_url(folder.id, "file", rel, download=True),
                    "list_url": "",
                    "open_url": "",
                })
            if len(entries) >= limit:
                break
    except OSError:
        return entries

    entries.sort(key=lambda item: (
        item.get("relative_folder", "").lower(),
        item.get("name", "").lower(),
    ))
    return entries


@router.post("/scan", response_model=DocumentScanResponse)
def scan_documents(
    root: str | None = Query(default=None),
    user_key: str | None = Query(default=None),
    force: bool = Query(default=False),
    db: Session = Depends(get_db),
):
    """Incrementally scan A0 folders and update cached document metadata."""
    _ = root
    if not user_key:
        raise HTTPException(status_code=400, detail="Missing user_key")

    cleaned_user = user_key.strip()[:255]
    saved = (
        db.query(UserSmbRoot)
        .filter(UserSmbRoot.user_key == cleaned_user, UserSmbRoot.active == True)
        .first()
    )
    scan_root = saved.smb_root if saved else ""
    if not scan_root:
        raise HTTPException(status_code=400, detail="Missing SMB root for this user")

    scanner = DocumentScanner(smb_root=scan_root)
    results = scanner.scan(db=db, force=force)
    return DocumentScanResponse(
        root=scan_root,
        total_scanned=len(results),
        results=results,
    )


@router.get("/folders/{folder_id}")
def list_plan_documents(
    folder_id: int,
    db: Session = Depends(get_db),
):
    """List files directly from the SMB folder for a plan code."""
    folder = _folder_or_404(folder_id, db)
    metadata_refresh = _refresh_folder_metadata(folder, db)
    entries = _list_plan_folder_entries(folder)
    pdf_documents = _list_plan_pdf_entries(folder)
    documents = [entry for entry in entries if not entry["is_dir"]]
    folders = [
        {
            "name": entry["name"],
            "exists": entry["exists"],
            "file_count": entry["size"],
            "list_url": entry["list_url"],
            "open_url": entry["open_url"],
        }
        for entry in entries
        if entry["is_dir"]
    ]
    return {
        "success": True,
        "code": folder.name[:16],
        "message": f"Tim thay {len(documents)} file va {len(folders)} thu muc trong SMB",
        "documents": documents,
        "pdf_documents": pdf_documents,
        "pdf_count": len(pdf_documents),
        "folders": folders,
        "erp_info": None,
        "smb_path": folder.absolute_path,
        "open_url": _api_url(folder.id, "open"),
        "metadata_refresh": metadata_refresh,
    }


@router.get("/folders/{folder_id}/folder")
def list_plan_document_subfolder(
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
        "open_url": _api_url(folder.id, "open", safe_rel),
    }


@router.post("/folders/{folder_id}/open")
def open_plan_document_folder(
    folder_id: int,
    rel: str = Query(default=""),
    db: Session = Depends(get_db),
):
    """Open a plan folder or subfolder in Windows Explorer on the scanner host."""
    folder = _folder_or_404(folder_id, db)
    target, safe_rel = _path_under_folder(folder, rel)
    _open_folder_in_explorer(target)
    return {
        "success": True,
        "folder_name": os.path.basename(safe_rel) if safe_rel else folder.name,
        "path": target,
    }


@router.get("/folders/{folder_id}/file")
def get_plan_document_file(
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

    return FileResponse(
        target,
        media_type=mimetypes.guess_type(target)[0] or "application/octet-stream",
        filename=os.path.basename(target),
        content_disposition_type="attachment" if download else "inline",
    )
