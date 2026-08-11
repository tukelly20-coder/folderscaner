"""
Folder Scanner — polls the SMB/UNC share, detects Created / Deleted / Renamed / Modified
changes, updates the database, logs events, and pushes WebSocket notifications.
"""

import asyncio
import datetime
import logging
import os
from typing import Dict, List, Optional, Tuple

from sqlalchemy.orm import Session

from app.config import settings
from app.models.folder import Folder, FolderStatus
from app.models.folder_event import FolderEvent, FolderEventType
from app.websocket.manager import ws_manager

logger = logging.getLogger(__name__)


def _normalize_path(p: str) -> str:
    """Normalise a filesystem path to use forward slashes for DB storage."""
    return str(p).replace("\\", "/")


def _relative_path(root: str, full: str) -> str:
    """Compute the path relative to *root* (both normalised)."""
    rel = os.path.relpath(full, root)
    return _normalize_path(rel)


def _parse_excludes(raw: str) -> list:
    """Parse a comma-separated string of folder names into a list."""
    return [item.strip() for item in raw.split(",") if item.strip()]


class FolderScanner:
    """Scans *SMB_ROOT* periodically and syncs state into the database."""

    def __init__(self, db: Session, smb_root: Optional[str] = None, excludes: Optional[list] = None):
        self.db = db
        self.smb_root = (smb_root or settings.SMB_ROOT).rstrip("/\\")
        raw_excludes = excludes or _parse_excludes(settings.SMB_EXCLUDES)
        self.excludes = {e.strip() for e in raw_excludes if e.strip()}
        self._running = False

    # ---- public API ----

    def scan_once(self) -> Dict:
        """Perform a single scan cycle and return a summary dict."""
        logger.info("Starting scan of %s", self.smb_root)
        summary = {
            "created": 0,
            "deleted": 0,
            "renamed": 0,
            "modified": 0,
            "errors": [],
        }

        try:
            fs_folders = self._read_filesystem()
        except Exception as exc:
            logger.exception("Filesystem read error")
            summary["errors"].append(str(exc))
            return summary

        db_map = self._load_db_map()

        try:
            # 1. Detect deletions and renames (db entries not in filesystem)
            for db_path, db_folder in list(db_map.items()):
                if db_folder.status == FolderStatus.DELETED:
                    continue
                if db_path not in fs_folders:
                    candidate = self._find_rename_target(db_folder, fs_folders)
                    if candidate:
                        self._handle_rename(db_folder, candidate, summary)
                    else:
                        self._handle_delete(db_folder, summary)

            # 2. Detect creations and modifications (filesystem entries)
            for fs_path, fs_info in fs_folders.items():
                if fs_path not in db_map:
                    self._handle_create(fs_path, fs_info, summary)
                else:
                    db_folder = db_map[fs_path]
                    self._handle_maybe_modify(db_folder, fs_info, summary)

            self.db.commit()
        except Exception as exc:
            logger.exception("Scan error")
            self.db.rollback()
            summary["errors"].append(str(exc))

        logger.info(
            "Scan complete: %d created, %d deleted, %d renamed, %d modified",
            summary["created"],
            summary["deleted"],
            summary["renamed"],
            summary["modified"],
        )
        return summary

    async def scan_loop(self, interval: Optional[int] = None):
        """Async loop that calls scan_once() every *interval* seconds."""
        interval = interval or settings.SCAN_INTERVAL
        self._running = True
        while self._running:
            self.excludes = set(
                e.strip() for e in _parse_excludes(settings.SMB_EXCLUDES) if e.strip()
            )
            await asyncio.to_thread(self.scan_once)
            await asyncio.sleep(interval)

    def stop(self):
        self._running = False

    # ---- filesystem I/O ----

    def _read_filesystem(self) -> Dict[str, dict]:
        """
        Walk *smb_root* and return {relative_path: info_dict}.

        Uses os.scandir so it works with mounted UNC paths on Windows
        and with smbprotocol when credentials are supplied.
        """
        result: Dict[str, dict] = {}
        root = self.smb_root

        try:
            entries = os.scandir(root)
        except Exception as exc:
            logger.error("Cannot scan %s: %s", root, exc)
            raise

        for entry in entries:
            try:
                stat = entry.stat()
            except OSError:
                continue
            if not entry.is_dir():
                continue
            if entry.name in self.excludes:
                logger.info("Skipping excluded folder: %s", entry.path)
                continue
            rel = _relative_path(root, entry.path)
            full = _normalize_path(entry.path)
            result[rel] = {
                "name": entry.name,
                "relative_path": rel,
                "absolute_path": full,
                "mtime": datetime.datetime.utcfromtimestamp(stat.st_mtime),
                "size": stat.st_size,
                "is_dir": True,
            }

        return result

    # ---- database helpers ----

    def _load_db_map(self) -> Dict[str, Folder]:
        """Return {relative_path: Folder} for all folders (active and deleted)."""
        folders = self.db.query(Folder).all()
        return {f.relative_path: f for f in folders}

    # ---- change handlers ----

    def _find_rename_target(
        self, db_folder: Folder, fs_folders: Dict[str, dict]
    ) -> Optional[Tuple[str, dict]]:
        """
        Heuristic: if the DB entry's relative_path no longer exists on disk,
        but a single folder in the same parent directory exists,
        treat it as a rename.
        """
        db_parent = os.path.dirname(db_folder.relative_path)

        candidates = []
        for fs_rel, fs_info in fs_folders.items():
            if os.path.dirname(fs_rel) != db_parent:
                continue
            candidates.append((fs_rel, fs_info))

        if len(candidates) == 1:
            return candidates[0]
        return None

    def _handle_create(
        self, rel_path: str, info: dict, summary: Dict
    ) -> None:
        """Handle a newly discovered folder."""
        folder = Folder(
            name=info["name"],
            relative_path=rel_path,
            absolute_path=info["absolute_path"],
            parent_id=self._resolve_parent(rel_path),
            status=FolderStatus.ACTIVE,
            first_seen=datetime.datetime.utcnow(),
            last_seen=datetime.datetime.utcnow(),
        )
        self.db.add(folder)
        self.db.flush()
        self._log_event(
            folder.id,
            FolderEventType.CREATED,
            new_name=info["name"],
            new_path=info["absolute_path"],
            source="SCANNER",
        )
        summary["created"] += 1
        self._notify("folder_created", folder)

    def _handle_delete(self, folder: Folder, summary: Dict) -> None:
        """Soft-delete a folder that no longer exists on disk."""
        folder.status = FolderStatus.DELETED
        folder.updated_at = datetime.datetime.utcnow()
        self._log_event(
            folder.id,
            FolderEventType.DELETED,
            old_name=folder.name,
            old_path=folder.absolute_path,
            source="SCANNER",
        )
        summary["deleted"] += 1
        self._notify("folder_deleted", folder)

    def _handle_rename(
        self,
        folder: Folder,
        target: Tuple[str, dict],
        summary: Dict,
    ) -> None:
        """Update folder name/path after a rename on disk."""
        target_rel, target_info = target
        old_name = folder.name
        old_path = folder.absolute_path

        folder.name = target_info["name"]
        folder.relative_path = target_rel
        folder.absolute_path = target_info["absolute_path"]
        folder.parent_id = self._resolve_parent(target_rel)
        folder.updated_at = datetime.datetime.utcnow()

        self._log_event(
            folder.id,
            FolderEventType.RENAMED,
            old_name=old_name,
            new_name=folder.name,
            old_path=old_path,
            new_path=folder.absolute_path,
            source="SCANNER",
        )
        summary["renamed"] += 1
        self._notify("folder_renamed", folder)

    def _handle_maybe_modify(
        self, folder: Folder, info: dict, summary: Dict
    ) -> None:
        """Check if an existing folder was modified on disk."""
        if folder.status == FolderStatus.DELETED:
            folder.status = FolderStatus.ACTIVE
            folder.name = info["name"]
            folder.absolute_path = info["absolute_path"]
            folder.updated_at = datetime.datetime.utcnow()
            self.db.add(folder)
            self._log_event(
                folder.id,
                FolderEventType.CREATED,
                new_name=info["name"],
                new_path=info["absolute_path"],
                source="SCANNER",
            )
            summary["created"] += 1
            self._notify("folder_created", folder)
            return

        old_name = folder.name
        old_path = folder.absolute_path

        changed = False
        if folder.name != info["name"]:
            folder.name = info["name"]
            changed = True

        if folder.absolute_path != info["absolute_path"]:
            folder.absolute_path = info["absolute_path"]
            changed = True

        if changed:
            folder.updated_at = datetime.datetime.utcnow()
            self._log_event(
                folder.id,
                FolderEventType.MODIFIED,
                old_name=old_name,
                new_name=folder.name,
                old_path=old_path,
                new_path=folder.absolute_path,
                source="SCANNER",
            )
            summary["modified"] += 1
            self._notify("folder_modified", folder)

    def _resolve_parent(self, rel_path: str) -> Optional[int]:
        """Return the DB id of the parent folder, if it exists."""
        parent_rel = os.path.dirname(rel_path)
        if not parent_rel:
            return None
        parent = (
            self.db.query(Folder)
            .filter(Folder.relative_path == parent_rel)
            .first()
        )
        return parent.id if parent else None

    # ---- event + notification helpers ----

    def _log_event(
        self,
        folder_id: int,
        event_type: FolderEventType,
        old_name: Optional[str] = None,
        new_name: Optional[str] = None,
        old_path: Optional[str] = None,
        new_path: Optional[str] = None,
        source: str = "SCANNER",
    ) -> FolderEvent:
        evt = FolderEvent(
            folder_id=folder_id,
            event_type=event_type,
            old_name=old_name,
            new_name=new_name,
            old_path=old_path,
            new_path=new_path,
            source=source,
        )
        self.db.add(evt)
        return evt

    @staticmethod
    def _notify(event_type: str, folder: Folder) -> None:
        """Push a WebSocket notification to all connected clients.

        Safe to call from any thread (the broadcast is scheduled on the
        main event loop via ``run_coroutine_threadsafe``).
        """
        data = {
            "event": event_type,
            "folder_id": folder.id,
            "name": folder.name,
            "relative_path": folder.relative_path,
            "absolute_path": folder.absolute_path,
            "status": folder.status.value,
        }
        ws_manager.broadcast_background(data)
