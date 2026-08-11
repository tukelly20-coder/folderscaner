"""
Document Scanner - extracts customer, salesperson, and drawing-code metadata
from A0 project folders. Results can be cached on Folder rows so opening the
web table does not need a deep SMB/VPN scan.
"""

import datetime
import json
import logging
import os
import re
from typing import Optional

from sqlalchemy.orm import Session

from app.config import normalize_smb_root, settings
from app.models.folder import Folder, FolderStatus
from app.schemas.document_scan import DocumentScanResult
from app.services.folder_scanner import _normalize_path, _relative_path

logger = logging.getLogger(__name__)

A0_PATTERN = re.compile(r"^P[^-]{3}-\d{4}-[^-]{3}-A.+$")
CUSTOMER_PREFIX = "03 客户资料_Dữ liệu khách hàng_"
SALESPERSON_PATTERN = re.compile(r"^业务员[：:]\s*(.+)$")
DOCUMENT_EXTENSIONS = {".txt", ".xlsx", ".xls", ".pdf"}
DRAWING_CODE_PATTERN = re.compile(
    r"(?:^|[\s\-_])(P[A-Za-z0-9\-]{17})(?=[\s\-_]|$)",
    re.IGNORECASE,
)
DOCUMENT_SCAN_EXCLUDES = {
    "_deleted",
    "backup",
    "backups",
    "old",
    "temp",
    "tmp",
    "node_modules",
    "__pycache__",
}


def _is_a0(name: str) -> bool:
    return bool(A0_PATTERN.match(name))


def _extract_customer_name(subfolder_name: str) -> tuple[Optional[str], Optional[str]]:
    raw = subfolder_name[len(CUSTOMER_PREFIX) :]
    if "_" in raw:
        return raw.split("_")[-1].strip(), subfolder_name
    if raw:
        return raw.strip(), subfolder_name
    return None, subfolder_name


def _is_drawing_code(code: str) -> bool:
    return len(code) == 18 and len(code) >= 2 and code[-2].upper() == "A"


def _extract_drawing_codes_from_text(text: str) -> list[str]:
    matches = DRAWING_CODE_PATTERN.findall(text)
    return list({m.upper() for m in matches if _is_drawing_code(m)})


def _scan_files_for_drawing_codes(folder_path: str) -> list[str]:
    codes: list[str] = []
    for root, dirs, files in os.walk(folder_path):
        dirs[:] = [d for d in dirs if d not in DOCUMENT_SCAN_EXCLUDES]
        for file in files:
            ext = os.path.splitext(file)[1].lower()
            if ext not in DOCUMENT_EXTENSIONS:
                continue

            name_without_ext = os.path.splitext(file)[0]
            codes.extend(_extract_drawing_codes_from_text(name_without_ext))

            if ext == ".txt":
                full_path = os.path.join(root, file)
                try:
                    with open(full_path, "r", encoding="utf-8", errors="ignore") as f:
                        codes.extend(_extract_drawing_codes_from_text(f.read()))
                except Exception as exc:
                    logger.warning("Cannot read text file %s: %s", full_path, exc)

    return list(dict.fromkeys(codes))


def _get_document_metadata_mtime(
    folder_path: str,
    fallback: datetime.datetime | None = None,
) -> datetime.datetime | None:
    latest = fallback
    try:
        root_stat = os.stat(folder_path)
        latest = max(
            latest or datetime.datetime.min,
            datetime.datetime.utcfromtimestamp(root_stat.st_mtime),
        )
    except OSError:
        return latest

    for root, dirs, files in os.walk(folder_path):
        dirs[:] = [d for d in dirs if d not in DOCUMENT_SCAN_EXCLUDES]
        for name in files:
            ext = os.path.splitext(name)[1].lower()
            if ext not in DOCUMENT_EXTENSIONS:
                continue
            path = os.path.join(root, name)
            try:
                file_mtime = datetime.datetime.utcfromtimestamp(os.stat(path).st_mtime)
            except OSError:
                continue
            if latest is None or file_mtime > latest:
                latest = file_mtime

    return latest


def _extract_salesperson_from_customer_folder(customer_folder_path: str) -> Optional[str]:
    for root, dirs, files in os.walk(customer_folder_path):
        dirs[:] = [d for d in dirs if d not in DOCUMENT_SCAN_EXCLUDES]
        for file in files:
            name_without_ext = os.path.splitext(file)[0]
            match = SALESPERSON_PATTERN.match(name_without_ext)
            if match:
                return match.group(1).strip()
    return None


class DocumentScanner:
    """Filesystem inspector for A0 folders and cached document metadata."""

    def __init__(self, smb_root: str | None = None):
        self.smb_root = normalize_smb_root(smb_root or settings.SMB_ROOT)

    def scan_folder_path(self, folder_path: str, folder_name: str | None = None) -> DocumentScanResult:
        root = self.smb_root
        folder_name = folder_name or os.path.basename(folder_path)
        a0_rel = _relative_path(root, folder_path)
        customer_name: Optional[str] = None
        customer_subfolder_name: Optional[str] = None
        salesperson_name: Optional[str] = None
        found = False

        try:
            with os.scandir(folder_path) as sub_entries:
                for sub in sub_entries:
                    if sub.is_dir() and sub.name.startswith(CUSTOMER_PREFIX):
                        customer_name, customer_subfolder_name = _extract_customer_name(sub.name)
                        found = bool(customer_name)
                        salesperson_name = _extract_salesperson_from_customer_folder(sub.path)
                        break
        except Exception as exc:
            logger.warning("Cannot scan A0 folder %s: %s", folder_path, exc)
            return DocumentScanResult(
                a0_folder_path=a0_rel,
                a0_folder_name=folder_name,
                customer_name=None,
                customer_subfolder_name=None,
                salesperson_name=None,
                found=False,
                drawing_codes=[],
            )

        drawing_codes = _scan_files_for_drawing_codes(folder_path)

        return DocumentScanResult(
            a0_folder_path=a0_rel,
            a0_folder_name=folder_name,
            customer_name=customer_name,
            customer_subfolder_name=customer_subfolder_name,
            salesperson_name=salesperson_name,
            found=found,
            drawing_codes=drawing_codes,
        )

    def update_folder_cache(
        self,
        folder: Folder,
        source_mtime: datetime.datetime | None = None,
        force: bool = False,
    ) -> bool:
        if folder.status != FolderStatus.ACTIVE or not _is_a0(folder.name):
            return False

        if source_mtime is None:
            try:
                stat = os.stat(folder.absolute_path)
                source_mtime = datetime.datetime.utcfromtimestamp(stat.st_mtime)
            except OSError:
                return False
        source_mtime = _get_document_metadata_mtime(folder.absolute_path, source_mtime)

        if not force and folder.source_mtime and folder.source_mtime >= source_mtime:
            return False

        result = self.scan_folder_path(folder.absolute_path, folder.name)
        folder.customer_name = result.customer_name
        folder.customer_subfolder_name = result.customer_subfolder_name
        folder.salesperson_name = result.salesperson_name
        folder.drawing_codes_json = json.dumps(result.drawing_codes, ensure_ascii=False)
        folder.source_mtime = source_mtime
        folder.document_scanned_at = datetime.datetime.utcnow()
        return True

    def update_changed_folder_caches(self, db: Session, force: bool = False) -> int:
        updated = 0
        folders = db.query(Folder).filter(Folder.status == FolderStatus.ACTIVE).all()
        for folder in folders:
            if self.update_folder_cache(folder, force=force):
                updated += 1
        if updated:
            db.commit()
        return updated

    def scan(self, db: Session | None = None, force: bool = False) -> list[DocumentScanResult]:
        root = self.smb_root
        results: list[DocumentScanResult] = []

        db_folders = {}
        if db is not None:
            db_folders = {
                folder.relative_path: folder
                for folder in db.query(Folder).filter(Folder.status == FolderStatus.ACTIVE).all()
            }

        try:
            with os.scandir(root) as entries:
                for entry in entries:
                    try:
                        stat = entry.stat()
                    except OSError:
                        continue

                    if not entry.is_dir() or not _is_a0(entry.name):
                        continue

                    rel_path = _relative_path(root, entry.path)
                    source_mtime = _get_document_metadata_mtime(
                        entry.path,
                        datetime.datetime.utcfromtimestamp(stat.st_mtime),
                    )
                    folder = db_folders.get(rel_path)

                    if (
                        db is not None
                        and folder is not None
                        and not force
                        and folder.source_mtime
                        and folder.source_mtime >= source_mtime
                    ):
                        results.append(
                            DocumentScanResult(
                                a0_folder_path=folder.relative_path,
                                a0_folder_name=folder.name,
                                customer_name=folder.customer_name,
                                customer_subfolder_name=folder.customer_subfolder_name,
                                salesperson_name=folder.salesperson_name,
                                found=bool(folder.customer_name),
                                drawing_codes=folder.drawing_codes,
                            )
                        )
                        continue

                    result = self.scan_folder_path(entry.path, entry.name)
                    results.append(result)

                    if db is not None and folder is not None:
                        folder.customer_name = result.customer_name
                        folder.customer_subfolder_name = result.customer_subfolder_name
                        folder.salesperson_name = result.salesperson_name
                        folder.drawing_codes_json = json.dumps(result.drawing_codes, ensure_ascii=False)
                        folder.source_mtime = source_mtime
                        folder.document_scanned_at = datetime.datetime.utcnow()
        except Exception as exc:
            logger.error("Cannot scan %s: %s", root, exc)
            raise

        if db is not None:
            db.commit()

        return results
