"""
Document Scanner — scans a root path for A0 folders and extracts customer names
from 03 subfolders, and scans document files for drawing codes.
"""

import logging
import os
import re
from typing import Optional

from app.config import settings
from app.services.folder_scanner import _normalize_path, _relative_path
from app.schemas.document_scan import DocumentScanResult

logger = logging.getLogger(__name__)

A0_PATTERN = re.compile(r"^P[^-]{3}-\d{4}-[^-]{3}-A.+$")
CUSTOMER_PREFIX = "03 客户资料_Dữ liệu khách hàng_"
SALESPERSON_PATTERN = re.compile(r"^业务员[：:]\s*(.+)$")
DOCUMENT_EXTENSIONS = {".txt", ".xlsx", ".xls", ".pdf"}
DRAWING_CODE_PATTERN = re.compile(r"(?:^|[\s\-_])(P[A-Za-z0-9\-]{17})(?=[\s\-_]|$)", re.IGNORECASE)


def _is_a0(name: str) -> bool:
    return bool(A0_PATTERN.match(name))


def _extract_customer_name(subfolder_name: str) -> tuple[Optional[str], Optional[str]]:
    raw = subfolder_name[len(CUSTOMER_PREFIX):]
    if "_" in raw:
        return raw.split("_")[-1].strip(), subfolder_name
    elif raw:
        return raw.strip(), subfolder_name
    return None, subfolder_name


def _is_drawing_code(code: str) -> bool:
    return len(code) == 18 and len(code) >= 2 and code[-2] == "A"


def _extract_drawing_codes_from_text(text: str) -> list[str]:
    matches = DRAWING_CODE_PATTERN.findall(text)
    return list({m for m in matches if _is_drawing_code(m)})


def _scan_files_for_drawing_codes(folder_path: str) -> list[str]:
    codes: list[str] = []
    for root, _, files in os.walk(folder_path):
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
                        content = f.read()
                    codes.extend(_extract_drawing_codes_from_text(content))
                except Exception as exc:
                    logger.warning("Cannot read text file %s: %s", full_path, exc)
    return list(dict.fromkeys(codes))


def _extract_salesperson_from_customer_folder(customer_folder_path: str) -> Optional[str]:
    for root, _, files in os.walk(customer_folder_path):
        for file in files:
            name_without_ext = os.path.splitext(file)[0]
            match = SALESPERSON_PATTERN.match(name_without_ext)
            if match:
                return match.group(1).strip()
    return None


class DocumentScanner:
    """Stateless filesystem inspector for A0 folders and customer names."""

    def __init__(self, smb_root: str | None = None):
        self.smb_root = smb_root or settings.SMB_ROOT

    def scan(self) -> list[DocumentScanResult]:
        root = self.smb_root

        results: list[DocumentScanResult] = []

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

            if not _is_a0(entry.name):
                continue

            a0_rel = _relative_path(root, entry.path)
            customer_name: Optional[str] = None
            customer_subfolder_name: Optional[str] = None
            salesperson_name: Optional[str] = None
            found = False

            try:
                sub_entries = os.scandir(entry.path)
            except Exception as exc:
                logger.warning("Cannot scan A0 folder %s: %s", entry.path, exc)
                results.append(
                    DocumentScanResult(
                        a0_folder_path=a0_rel,
                        a0_folder_name=entry.name,
                        customer_name=None,
                        customer_subfolder_name=None,
                        salesperson_name=None,
                        found=False,
                    )
                )
                continue

            for sub in sub_entries:
                if sub.is_dir() and sub.name.startswith(CUSTOMER_PREFIX):
                    customer_name, customer_subfolder_name = _extract_customer_name(
                        sub.name
                    )
                    found = bool(customer_name)
                    salesperson_name = _extract_salesperson_from_customer_folder(
                        sub.path
                    )
                    break

            drawing_codes = _scan_files_for_drawing_codes(entry.path)

            results.append(
                DocumentScanResult(
                    a0_folder_path=a0_rel,
                    a0_folder_name=entry.name,
                    customer_name=customer_name,
                    customer_subfolder_name=customer_subfolder_name,
                    salesperson_name=salesperson_name,
                    found=found,
                    drawing_codes=drawing_codes,
                )
            )

        return results
