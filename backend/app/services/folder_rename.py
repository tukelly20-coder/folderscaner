"""
Folder Rename Service — handles Web -> SMB rename requests.

CRITICAL ORDERING (per architecture spec):
  Web Request -> Validate -> Check duplicate -> Rename SMB Folder ->
  SUCCESS -> Update Database -> Create Event -> Notify Web
  FAIL  -> Return Error (database untouched)

The filesystem (SMB) is the source of truth.  The database is ONLY
updated after a successful rename on disk.
"""

import datetime
import logging
import os
from typing import Optional

from sqlalchemy.orm import Session

from app.config import settings
from app.models.folder import Folder, FolderStatus
from app.models.folder_event import FolderEvent, FolderEventType
from app.websocket.manager import ws_manager

logger = logging.getLogger(__name__)

# Characters that are invalid in Windows folder names
_INVALID_CHARS = set('<>:"/\\|?*')
_CONTROL_CHARS = set(chr(i) for i in range(32))

# Names reserved by Windows
_RESERVED_NAMES = {
    "CON", "PRN", "AUX", "NUL",
    *(f"COM{i}" for i in range(1, 10)),
    *(f"LPT{i}" for i in range(1, 10)),
}


class RenameError(Exception):
    """Raised when a folder rename fails."""
    def __init__(self, error_code: str, message: str, status_code: int = 400):
        self.error_code = error_code
        self.message = message
        self.status_code = status_code
        super().__init__(message)


def validate_folder_name(name: str) -> str:
    """
    Validate a folder name according to Windows naming rules.

    Raises:
        RenameError: if the name is invalid.
    """
    if not name or not name.strip():
        raise RenameError(
            "INVALID_NAME",
            "Folder name cannot be empty.",
        )

    stripped = name.strip()

    # Check for invalid characters
    bad_chars = _INVALID_CHARS & set(stripped)
    if bad_chars:
        raise RenameError(
            "INVALID_NAME",
            f"Folder name contains invalid characters: {' '.join(sorted(bad_chars))}",
        )

    # Check for control characters
    if _CONTROL_CHARS & set(stripped):
        raise RenameError(
            "INVALID_NAME",
            "Folder name contains control characters.",
        )

    # Check length
    if len(stripped) > 255:
        raise RenameError(
            "INVALID_NAME",
            "Folder name exceeds 255 characters.",
        )

    # Check trailing dots / spaces (Windows disallows these)
    if stripped.endswith(".") or stripped.endswith(" "):
        raise RenameError(
            "INVALID_NAME",
            "Folder name cannot end with a space or dot.",
        )

    # Check reserved names
    stem = stripped.split(".")[0].upper()
    if stem in _RESERVED_NAMES:
        raise RenameError(
            "INVALID_NAME",
            f'"{stem}" is a reserved Windows name and cannot be used.',
        )

    return stripped


def _compute_relative(root: str, full_path: str) -> str:
    """Compute the path relative to *root*, normalised to forward slashes."""
    rel = os.path.relpath(full_path, root)
    return str(rel).replace("\\", "/")


class FolderRenameService:
    """Service for renaming folders on the SMB share."""

    def __init__(self, db: Session):
        self.db = db

    def rename_folder(
        self,
        folder_id: int,
        new_name: str,
    ) -> Folder:
        """
        Rename a folder on the filesystem (SMB share) and update the database.

        Steps (per architecture spec section 14):
        1. Fetch folder from DB by ID
        2. Validate the new name
        3. Check the target doesn't already exist (duplicate check)
        4. Check concurrent modification (folder still on disk)
        5. Perform os.rename() on SMB filesystem
        6. ONLY on success: update database, create event, notify web
        7. On failure: return error, database untouched
        """
        # 1. Fetch folder
        folder = (
            self.db.query(Folder)
            .filter(Folder.id == folder_id)
            .first()
        )
        if not folder:
            raise RenameError(
                "FOLDER_NOT_FOUND",
                f"Folder with id {folder_id} not found.",
                status_code=404,
            )

        # 2. Check not deleted
        if folder.status == FolderStatus.DELETED:
            raise RenameError(
                "FOLDER_DELETED",
                "Cannot rename a deleted folder.",
                status_code=400,
            )

        # 3. Validate new name
        validated = validate_folder_name(new_name)

        old_name = folder.name
        old_path = folder.absolute_path

        # 4. Check duplicate — target name should not already exist
        sibling_path = os.path.join(
            os.path.dirname(folder.absolute_path), validated
        )
        if os.path.exists(sibling_path):
            raise RenameError(
                "FOLDER_ALREADY_EXISTS",
                f'Folder "{validated}" already exists.',
                status_code=400,
            )

        # 5. Concurrent modification check
        if not os.path.exists(folder.absolute_path):
            raise RenameError(
                "FOLDER_NOT_FOUND_ON_DISK",
                "Folder was deleted or moved on the filesystem since last scan. "
                "Please refresh and try again.",
                status_code=409,
            )

        new_path = sibling_path

        # 6. Perform the actual filesystem rename
        try:
            os.rename(folder.absolute_path, new_path)
        except OSError as exc:
            logger.exception("Rename failed for %s -> %s", old_path, new_path)
            raise RenameError(
                "RENAME_FAILED",
                f"Failed to rename folder on filesystem: {exc}",
                status_code=500,
            )

        # 7. ONLY on success: update database
        folder.name = validated
        folder.relative_path = _compute_relative(settings.SMB_ROOT, new_path)
        folder.absolute_path = new_path.replace("\\", "/")
        folder.updated_at = datetime.datetime.utcnow()

        event = FolderEvent(
            folder_id=folder.id,
            event_type=FolderEventType.RENAMED,
            old_name=old_name,
            new_name=validated,
            old_path=old_path,
            new_path=folder.absolute_path,
            source="WEB",
        )
        self.db.add(event)
        self.db.commit()
        self.db.refresh(folder)

        ws_data = {
            "event": "folder_renamed",
            "folder_id": folder.id,
            "name": folder.name,
            "old_name": old_name,
            "relative_path": folder.relative_path,
            "absolute_path": folder.absolute_path,
            "status": folder.status.value,
        }
        ws_manager.broadcast_background(ws_data)

        return folder
