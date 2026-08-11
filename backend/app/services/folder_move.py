"""
Folder Move Service — handles moving a folder to a different location on the
SMB/UNC share and keeping the database in sync.

CRITICAL ORDERING (source of truth = filesystem):
    Web Request -> Validate -> Target parent exists? -> Duplicate check ->
    Move SMB Folder -> SUCCESS -> Update DB -> Create Event -> Notify Web
    FAIL -> Return Error (database untouched)
"""

import datetime
import logging
import os
import shutil
from typing import Optional

from sqlalchemy.orm import Session

from app.config import settings
from app.models.folder import Folder, FolderStatus
from app.models.folder_event import FolderEvent, FolderEventType
from app.websocket.manager import ws_manager

logger = logging.getLogger(__name__)

_INVALID_CHARS = set('<>:"|?*')
_CONTROL_CHARS = set(chr(i) for i in range(32))
_RESERVED_NAMES = {
    "CON", "PRN", "AUX", "NUL",
    *(f"COM{i}" for i in range(1, 10)),
    *(f"LPT{i}" for i in range(1, 10)),
}


class MoveError(Exception):
    """Raised when a folder move fails."""

    def __init__(self, error_code: str, message: str, status_code: int = 400):
        self.error_code = error_code
        self.message = message
        self.status_code = status_code
        super().__init__(message)


def _validate_path_segment(segment: str) -> str:
    """Validate a single path segment (folder name component)."""
    if not segment or not segment.strip():
        raise MoveError("INVALID_NAME", "Path segment cannot be empty.")

    stripped = segment.strip()
    bad_chars = _INVALID_CHARS & set(stripped)
    if bad_chars:
        raise MoveError(
            "INVALID_NAME",
            f"Path segment contains invalid characters: {' '.join(sorted(bad_chars))}",
        )
    if _CONTROL_CHARS & set(stripped):
        raise MoveError("INVALID_NAME", "Path segment contains control characters.")
    if len(stripped) > 255:
        raise MoveError("INVALID_NAME", "Path segment exceeds 255 characters.")
    if stripped.endswith(".") or stripped.endswith(" "):
        raise MoveError("INVALID_NAME", "Path segment cannot end with a dot or space.")
    stem = stripped.split(".")[0].upper()
    if stem in _RESERVED_NAMES:
        raise MoveError("INVALID_NAME", f'"{stem}" is a reserved Windows name.')
    return stripped


def _validate_relative_path(rel_path: str, smb_root: str) -> str:
    """
    Validate a proposed *relative path* for a folder move.

    Rules:
      * Must not be empty.
      * No absolute paths (no leading slash or drive letter).
      * No backreference segments (``..``) escaping the SMB root.
      * Each segment must pass Windows naming rules.
      * Parent directory must exist on disk.
    """
    if not rel_path or not rel_path.strip():
        raise MoveError("INVALID_PATH", "Relative path cannot be empty.")

    rel_path = rel_path.strip().replace("\\", "/").rstrip("/")
    if not rel_path:
        raise MoveError("INVALID_PATH", "Relative path cannot be empty.")

    if rel_path.startswith("/") or rel_path.startswith("\\"):
        raise MoveError("INVALID_PATH", "Relative path must not be absolute.")
    if len(rel_path) >= 2 and rel_path[1] == ":":
        raise MoveError("INVALID_PATH", "Relative path must not contain a drive letter.")

    segments = [s for s in rel_path.split("/") if s not in ("", ".")]
    if any(s == ".." for s in segments):
        raise MoveError("INVALID_PATH", "Relative path cannot contain '..'.")
    if not segments:
        raise MoveError("INVALID_PATH", "Relative path cannot be empty.")

    for seg in segments[:-1]:
        _validate_path_segment(seg)
    _validate_path_segment(segments[-1])

    normalized = "/".join(segments)
    return normalized


class FolderMoveService:
    """Service for moving folders to a new location on the SMB share."""

    def __init__(self, db: Session):
        self.db = db

    def move_folder(
        self,
        folder_id: int,
        new_relative_path: str,
        new_name: Optional[str] = None,
    ) -> Folder:
        """
        Move *folder_id* to *new_relative_path* on the filesystem.

        Optionally rename the leaf folder via *new_name*.  When *new_name*
        is omitted the existing folder name is preserved.

        The filesystem (SMB) is the source of truth.  The database is only
        updated after a successful move on disk.
        """
        # 1. Fetch folder
        folder = (
            self.db.query(Folder)
            .filter(Folder.id == folder_id)
            .first()
        )
        if not folder:
            raise MoveError(
                "FOLDER_NOT_FOUND",
                f"Folder with id {folder_id} not found.",
                status_code=404,
            )

        # 2. Cannot move deleted folders
        if folder.status == FolderStatus.DELETED:
            raise MoveError(
                "FOLDER_DELETED",
                "Cannot move a deleted folder.",
                status_code=400,
            )

        # 3. Determine the leaf name
        leaf_name = new_name.strip() if new_name else folder.name
        leaf_name = _validate_path_segment(leaf_name)

        # 4. Validate the target relative path
        validated_rel = _validate_relative_path(new_relative_path, settings.SMB_ROOT)

        # 5. Build the absolute target path (parent_dir / leaf_name)
        smb_root = settings.SMB_ROOT.rstrip("/\\")
        target_abs = os.path.join(smb_root, *validated_rel.split("/"))
        # If the user provided a new name, the leaf must equal that name.
        # If they did not, the existing name is the leaf → validated_rel's last
        # segment should equal folder.name.
        if os.path.basename(target_abs) != leaf_name:
            # The last segment of the relative path is the folder name.
            target_abs = os.path.join(os.path.dirname(target_abs), leaf_name)
            validated_rel = os.path.relpath(target_abs, smb_root).replace("\\", "/")

        # 6. Concurrent modification check — source must still exist
        source_abs = folder.absolute_path.replace("/", "\\")
        if not os.path.exists(source_abs):
            raise MoveError(
                "FOLDER_NOT_FOUND_ON_DISK",
                "Folder was deleted or moved on the filesystem since last scan. "
                "Please refresh and try again.",
                status_code=409,
            )

        # 7. Target parent must exist on disk
        target_parent = os.path.dirname(target_abs)
        if not os.path.isdir(target_parent):
            raise MoveError(
                "TARGET_PARENT_MISSING",
                f"Target parent directory does not exist on disk: {target_parent}",
                status_code=400,
            )

        # 8. Duplicate check — target must not already exist
        if os.path.exists(target_abs):
            raise MoveError(
                "FOLDER_ALREADY_EXISTS",
                f'A folder already exists at the target location: {target_abs}',
                status_code=400,
            )

        # 9. Perform the actual filesystem move
        try:
            os.makedirs(target_parent, exist_ok=True)
            shutil.move(source_abs, target_abs)
        except (OSError, shutil.Error) as exc:
            logger.exception("Move failed for %s -> %s", source_abs, target_abs)
            raise MoveError(
                "MOVE_FAILED",
                f"Failed to move folder on filesystem: {exc}",
                status_code=500,
            )

        # 10. ONLY on success: update database
        old_name = folder.name
        old_path = folder.absolute_path

        folder.name = leaf_name
        folder.relative_path = validated_rel
        folder.absolute_path = target_abs.replace("\\", "/")
        folder.parent_id = self._resolve_parent(validated_rel)
        folder.updated_at = datetime.datetime.utcnow()

        event = FolderEvent(
            folder_id=folder.id,
            event_type=FolderEventType.MOVED,
            old_name=old_name,
            new_name=leaf_name,
            old_path=old_path,
            new_path=folder.absolute_path,
            source="WEB",
        )
        self.db.add(event)
        self.db.commit()
        self.db.refresh(folder)

        ws_data = {
            "event": "folder_moved",
            "folder_id": folder.id,
            "name": folder.name,
            "old_name": old_name,
            "relative_path": folder.relative_path,
            "absolute_path": folder.absolute_path,
            "status": folder.status.value,
        }
        ws_manager.broadcast_background(ws_data)

        return folder

    def _resolve_parent(self, rel_path: str) -> Optional[int]:
        """Return the DB id of the parent folder, if it exists."""
        parent_rel = os.path.dirname(rel_path)
        if not parent_rel or parent_rel == "":
            return None
        parent = (
            self.db.query(Folder)
            .filter(Folder.relative_path == parent_rel)
            .first()
        )
        return parent.id if parent else None
