"""
Folder Scanner — polls the SMB/UNC share, detects Created / Deleted / Renamed / Modified
changes, updates the database, logs events, and pushes WebSocket notifications.
"""

import asyncio
import datetime
import logging
import os
import re
from typing import Dict, List, Optional, Tuple

from sqlalchemy.orm import Session

from app.config import normalize_smb_root, settings
from app.models.folder import Folder, FolderStatus
from app.models.folder_event import FolderEvent, FolderEventType
from app.models.scan_snapshot import ScanSnapshot
from app.services.project_sync import sync_folder_to_main_project
from app.websocket.manager import ws_manager

logger = logging.getLogger(__name__)
PROJECT_FOLDER_PATTERN = re.compile(
    r"^[A-Z][A-Z0-9]{0,7}-\d{2}(0[1-9]|1[0-2])-\d{3}(?:$|[-_\s])",
    re.IGNORECASE,
)
PROJECT_IDENTITY_PATTERN = re.compile(
    r"^([A-Z][A-Z0-9]{0,7}-\d{2}(?:0[1-9]|1[0-2])-\d{3})(?:$|[-_\s])",
    re.IGNORECASE,
)
YEAR_FOLDER_PATTERN = re.compile(r"^\d{4}$")
MONTH_FOLDER_PATTERN = re.compile(
    r"^(?:(?:0?[1-9]|1[0-2])\s*(?:月|thang|tháng|month)?|(?:thang|tháng|month)\s*(?:0?[1-9]|1[0-2]))$",
    re.IGNORECASE,
)
MAX_PROJECT_SEARCH_DEPTH = 4


def _normalize_path(p: str) -> str:
    """Normalise a filesystem path to use forward slashes for DB storage."""
    return str(p).replace("\\", "/")


def _relative_path(root: str, full: str) -> str:
    """Compute the path relative to *root* (both normalised)."""
    rel = os.path.relpath(full, root)
    return _normalize_path(rel)


def _same_parent(path: str, parent: str) -> bool:
    """Return True when *path* is a direct child of *parent*."""
    normalized_path = _normalize_path(path)
    normalized_parent = _normalize_path(parent)
    path_parent = _normalize_path(os.path.dirname(normalized_path))
    return path_parent.rstrip("/") == normalized_parent.rstrip("/")


def _is_drive_root(root: str) -> bool:
    normalized = _normalize_path(normalize_smb_root(root))
    return len(normalized) == 3 and normalized[1:] == ":/"


def _compare_root(root: str) -> str:
    normalized = _normalize_path(normalize_smb_root(root))
    if len(normalized) == 3 and normalized[1:] == ":/":
        return normalized
    return normalized.rstrip("/")


def _relative_parts(root: str, full_path: str) -> list[str]:
    root_cmp = _compare_root(root)
    full = _normalize_path(full_path)
    prefix = root_cmp if root_cmp.endswith("/") else f"{root_cmp}/"
    if not full.startswith(prefix):
        return []
    rel = full[len(prefix):].strip("/")
    return [part for part in rel.split("/") if part]


def _parse_excludes(raw: str) -> list:
    """Parse a comma-separated string of folder names into a list."""
    return [item.strip() for item in raw.split(",") if item.strip()]


def _is_project_folder(name: str) -> bool:
    return bool(PROJECT_FOLDER_PATTERN.match(name.strip()))


def _project_identity(name: str) -> str:
    match = PROJECT_IDENTITY_PATTERN.match((name or "").strip())
    return match.group(1).upper() if match else ""


def _is_year_folder(name: str) -> bool:
    return bool(YEAR_FOLDER_PATTERN.match(name.strip()))


def _is_month_folder(name: str) -> bool:
    return bool(MONTH_FOLDER_PATTERN.match(name.strip()))


def _is_scoped_project_path(root: str, full_path: str) -> bool:
    if _is_drive_root(root):
        return _same_parent(full_path, root)

    parts = _relative_parts(root, full_path)
    if not parts or len(parts) > MAX_PROJECT_SEARCH_DEPTH:
        return False
    if not _is_project_folder(parts[-1]):
        return False

    containers = parts[:-1]
    return all(_is_year_folder(part) or _is_month_folder(part) for part in containers)


class FolderScanner:
    """Scans *SMB_ROOT* periodically and syncs state into the database."""

    def __init__(
        self,
        db: Session,
        smb_root: Optional[str] = None,
        excludes: Optional[list] = None,
        force_document_cache: bool = False,
        force_full_scan: bool = False,
    ):
        self.db = db
        self.smb_root = normalize_smb_root(smb_root or settings.SMB_ROOT)
        raw_excludes = excludes or _parse_excludes(settings.SMB_EXCLUDES)
        self.excludes = {e.strip() for e in raw_excludes if e.strip()}
        self.force_document_cache = force_document_cache
        self.force_full_scan = force_full_scan
        self._running = False
        self._scanned_project_parents: set[str] = set()
        self._snapshot_map: dict[str, ScanSnapshot] = {}
        self._scan_stats = {"scanned_containers": 0, "skipped_containers": 0}

    # ---- public API ----

    def scan_once(self) -> Dict:
        """Perform a single scan cycle and return a summary dict."""
        logger.info("Starting scan of %s", self.smb_root)
        summary = {
            "created": 0,
            "deleted": 0,
            "renamed": 0,
            "modified": 0,
            "document_cache_updated": 0,
            "project_sync_updated": 0,
            "project_sync_skipped": 0,
            "full_scan": self.force_full_scan,
            "scanned_containers": 0,
            "skipped_containers": 0,
            "errors": [],
        }

        try:
            fs_folders = self._read_filesystem()
            summary.update(self._scan_stats)
        except Exception as exc:
            logger.exception("Filesystem read error")
            summary["errors"].append(str(exc))
            return summary

        db_map = self._load_db_map(fs_folders)

        try:
            # 1. Detect deletions and renames in containers scanned this round.
            for db_path, db_folder in list(db_map.items()):
                if db_folder.status == FolderStatus.DELETED:
                    continue
                if db_path not in fs_folders and self._should_reconcile_db_path(db_path):
                    candidate = self._find_rename_target(db_folder, fs_folders)
                    if candidate and (
                        candidate[0] not in db_map
                        or getattr(db_map.get(candidate[0]), "id", None) == db_folder.id
                    ):
                        self._handle_rename(db_folder, candidate, summary)
                        db_map.pop(db_path, None)
                        db_map[candidate[0]] = db_folder
                        self._refresh_document_cache(db_folder, candidate[1], summary)
                        self._sync_main_project(db_folder, summary)
                    else:
                        self._handle_delete(db_folder, summary)

            # 2. Detect creations and modifications (filesystem entries)
            for fs_path, fs_info in fs_folders.items():
                if fs_path not in db_map:
                    folder = self._handle_create(fs_path, fs_info, summary)
                    self._refresh_document_cache(folder, fs_info, summary)
                    self._sync_main_project(folder, summary)
                else:
                    db_folder = db_map[fs_path]
                    self._handle_maybe_modify(db_folder, fs_info, summary)
                    self._refresh_document_cache(db_folder, fs_info, summary)
                    self._sync_main_project(db_folder, summary)

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

    def _should_reconcile_db_path(self, db_path: str) -> bool:
        if self.force_full_scan:
            return True
        parent = _normalize_path(os.path.dirname(db_path))
        return parent in self._scanned_project_parents

    # ---- filesystem I/O ----

    def _read_filesystem(self) -> Dict[str, dict]:
        """
        Walk *smb_root* and return {relative_path: info_dict}.

        Uses os.scandir so it works with mounted UNC paths on Windows
        and with smbprotocol when credentials are supplied.
        """
        result: Dict[str, dict] = {}
        root = self.smb_root
        self._scanned_project_parents = set()
        self._snapshot_map = self._load_snapshot_map()
        self._scan_stats = {"scanned_containers": 0, "skipped_containers": 0}

        def add_project_entry(entry) -> None:
            try:
                stat = entry.stat()
            except OSError:
                return
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

        def container_relative_path(path: str) -> str:
            if _compare_root(path) == _compare_root(root):
                return ""
            return _relative_path(root, path)

        def container_signature(entries: list) -> str:
            parts: list[str] = []
            for entry in entries:
                if entry.name in self.excludes:
                    continue
                try:
                    stat = entry.stat()
                except OSError:
                    continue
                if (
                    _is_project_folder(entry.name)
                    or _is_year_folder(entry.name)
                    or _is_month_folder(entry.name)
                ):
                    parts.append(f"{entry.name}:{stat.st_mtime_ns}:{stat.st_size}")
            return "|".join(sorted(parts))

        def snapshot_matches(rel_path: str, signature: str) -> bool:
            snapshot = self._snapshot_map.get(rel_path)
            return bool(snapshot and snapshot.signature == signature)

        def upsert_snapshot(rel_path: str, signature: str) -> None:
            now = datetime.datetime.utcnow()
            snapshot = self._snapshot_map.get(rel_path)
            if snapshot:
                snapshot.signature = signature
                snapshot.last_scanned_at = now
                snapshot.updated_at = now
                return

            snapshot = ScanSnapshot(
                scan_root=_normalize_path(root),
                relative_path=rel_path,
                signature=signature,
                last_scanned_at=now,
            )
            self.db.add(snapshot)
            self._snapshot_map[rel_path] = snapshot

        def should_enter_container(name: str, depth: int) -> bool:
            if depth >= MAX_PROJECT_SEARCH_DEPTH - 1:
                return False
            if _is_drive_root(root):
                return False
            if depth == 0:
                return _is_year_folder(name) or _is_month_folder(name)
            return _is_year_folder(name) or _is_month_folder(name)

        def scan_container(path: str, depth: int) -> None:
            try:
                with os.scandir(path) as entries:
                    dir_entries = [entry for entry in entries if entry.is_dir()]
                    rel_path = container_relative_path(path)
                    signature = container_signature(dir_entries)
                    enterable_entries = [
                        entry
                        for entry in dir_entries
                        if entry.name not in self.excludes
                        and should_enter_container(entry.name, depth)
                    ]
                    container_unchanged = (
                        not self.force_full_scan
                        and rel_path
                        and snapshot_matches(rel_path, signature)
                    )
                    if container_unchanged and not enterable_entries:
                        self._scan_stats["skipped_containers"] += 1
                        logger.info("Skipping unchanged scan container: %s", path)
                        return

                    if container_unchanged:
                        self._scan_stats["skipped_containers"] += 1
                    else:
                        upsert_snapshot(rel_path, signature)
                        self._scanned_project_parents.add(rel_path)
                        self._scan_stats["scanned_containers"] += 1

                    for entry in dir_entries:
                        if entry.name in self.excludes:
                            logger.info("Skipping excluded folder: %s", entry.path)
                            continue
                        if _is_project_folder(entry.name):
                            if not container_unchanged:
                                add_project_entry(entry)
                            continue
                        if should_enter_container(entry.name, depth):
                            scan_container(entry.path, depth + 1)
                        else:
                            logger.info("Skipping non-project folder: %s", entry.path)
            except OSError as exc:
                if depth == 0:
                    raise
                logger.warning("Cannot scan folder %s: %s", path, exc)

        try:
            scan_container(root, 0)
        except Exception as exc:
            logger.error("Cannot scan %s: %s", root, exc)
            raise

        return result

    def _load_snapshot_map(self) -> dict[str, ScanSnapshot]:
        root_key = _normalize_path(self.smb_root)
        rows = (
            self.db.query(ScanSnapshot)
            .filter(ScanSnapshot.scan_root == root_key)
            .all()
        )
        return {row.relative_path or "": row for row in rows}

    # ---- database helpers ----

    def _load_db_map(self, fs_folders: Dict[str, dict]) -> Dict[str, Folder]:
        """Return {relative_path: Folder} for folders matching this scan.

        Each configured SMB root is an independent scope. Different users can
        have the same relative layout under different root folders.
        """
        root_prefix = f"{_normalize_path(self.smb_root).rstrip('/')}/%"
        folders = (
            self.db.query(Folder)
            .filter(Folder.absolute_path.like(root_prefix))
            .all()
        )
        folders = [
            folder
            for folder in folders
            if _is_scoped_project_path(self.smb_root, folder.absolute_path or "")
        ]
        mapped: Dict[str, Folder] = {}
        for folder in folders:
            if folder.absolute_path:
                mapped[_relative_path(self.smb_root, folder.absolute_path)] = folder
        return mapped

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
        db_identity = _project_identity(db_folder.name)

        candidates = []
        for fs_rel, fs_info in fs_folders.items():
            if os.path.dirname(fs_rel) != db_parent:
                continue
            candidates.append((fs_rel, fs_info))

        if db_identity:
            identity_matches = [
                candidate
                for candidate in candidates
                if _project_identity(candidate[1].get("name", "")) == db_identity
            ]
            if len(identity_matches) == 1:
                return identity_matches[0]

        if len(candidates) == 1:
            return candidates[0]
        return None

    def _handle_create(
        self, rel_path: str, info: dict, summary: Dict
    ) -> Folder:
        """Handle a newly discovered folder."""
        folder = Folder(
            name=info["name"],
            relative_path=rel_path,
            absolute_path=info["absolute_path"],
            scan_root=_normalize_path(self.smb_root),
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
        return folder

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
        folder.scan_root = _normalize_path(self.smb_root)
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
        folder.last_seen = datetime.datetime.utcnow()
        if folder.status == FolderStatus.DELETED:
            folder.status = FolderStatus.ACTIVE
            folder.name = info["name"]
            folder.relative_path = info["relative_path"]
            folder.absolute_path = info["absolute_path"]
            folder.scan_root = _normalize_path(self.smb_root)
            folder.parent_id = self._resolve_parent(info["relative_path"])
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

        if getattr(folder, "scan_root", None) != _normalize_path(self.smb_root):
            folder.scan_root = _normalize_path(self.smb_root)
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

    def _refresh_document_cache(self, folder: Folder, info: dict, summary: Dict) -> None:
        """Refresh expensive document metadata only when folder mtime changed."""
        try:
            from app.services.document_scanner import DocumentScanner

            if DocumentScanner(self.smb_root).update_folder_cache(
                folder,
                info.get("mtime"),
                force=self.force_document_cache,
            ):
                summary["document_cache_updated"] += 1
        except Exception as exc:
            logger.warning(
                "Document cache refresh failed for %s: %s",
                getattr(folder, "relative_path", ""),
                exc,
            )

    @staticmethod
    def _sync_main_project(folder: Folder, summary: Dict) -> None:
        result = sync_folder_to_main_project(folder)
        if result.get("success") and result.get("updated"):
            summary["project_sync_updated"] += 1
            return

        summary["project_sync_skipped"] += 1
        if result.get("reason") == "sync_error":
            summary["errors"].append(result.get("error") or "Project sync failed")

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
