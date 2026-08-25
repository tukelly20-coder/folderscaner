"""
Document Scanner - extracts customer, salesperson, and drawing-code metadata
from A0 project folders. Results can be cached on Folder rows so opening the
web table does not need a deep SMB/VPN scan.
"""

import datetime
import hashlib
import json
import logging
import os
import re
import sqlite3
from typing import Optional

from sqlalchemy.orm import Session

from app.config import normalize_smb_root, settings
from app.models.folder import Folder, FolderStatus
from app.schemas.document_scan import DocumentScanResult
from app.services.folder_scanner import _normalize_path, _relative_path

logger = logging.getLogger(__name__)

A0_PATTERN = re.compile(r"^P[^-]{3}-\d{4}-[^-]{3}-A.+$")
CUSTOMER_PREFIX = "03 客户资料_Dữ liệu khách hàng_"
CUSTOMER_FOLDER_KEYWORDS = (
    "客户资料",
    "客戶資料",
    "Dữ liệu khách hàng",
    "Du lieu khach hang",
    "khách hàng",
    "khach hang",
)
SALESPERSON_PATTERN = re.compile(
    r"^(?:业务员|業務員|业务|業務|sales(?:person)?|nhân viên kinh doanh|nhan vien kinh doanh)\s*[：:：-]\s*(.+)$",
    re.IGNORECASE,
)
DOCUMENT_EXTENSIONS = {".txt", ".xlsx", ".xls", ".pdf"}
DRAWING_CODE_PATTERN = re.compile(
    r"(?<![A-Z0-9])((?:P(?!SJT)[A-Z]{3}\d{3}|PSJT\d{3})-\d{4}-\d{2}-[A-Z]\d)(?![A-Z0-9])",
    re.IGNORECASE,
)
PROJECT_CODE_PATTERN = re.compile(
    r"^([A-Z][A-Z0-9]{0,7}-\d{2}(?:0[1-9]|1[0-2])-\d{3}(?:-[A-Z0-9]+)?)",
    re.IGNORECASE,
)
ROOT_DRAWING_CODE_PATTERN = re.compile(
    r"^P(?!SJT)[A-Z]{3}\d{3}-0000-00-[A-Z]0$",
    re.IGNORECASE,
)
SJT_DRAWING_CODE_PATTERN = re.compile(
    r"^PSJT\d{3}-\d{4}-00-[A-Z]0$",
    re.IGNORECASE,
)
FOLDER_CATEGORY_KEYWORDS = {
    "SJT": ("SJT", "软件图", "散件图", "导条皮带", "皮带", "护罩", "设备门", "设备们"),
    "WLJ": ("WLJ", "物料架", "货架", "千层车", "料车"),
    "ZZC": ("ZZC", "周转车"),
    "GZT": ("GZT", "工作台", "桌"),
    "WCP": ("WCP", "无尘棚"),
    "LSX": ("LSX", "流水线", "皮带线", "PVC", "输送线"),
    "ZWJ": ("ZWJ", "转弯机", "顶升移栽", "移栽机"),
    "GZL": ("GZL", "改造"),
    "BSX": ("BSX", "倍速线"),
    "WLL": ("WLL", "围栏", "护栏"),
    "GTX": ("GTX", "滚筒线"),
    "ZHT": ("ZHT", "展会图", "平面"),
    "LHX": ("LHX", "老化线"),
}
CODE_PREFIX_CATEGORIES = {
    "PWLJ": "WLJ",
    "PZZC": "ZZC",
    "PGZT": "GZT",
    "PWCP": "WCP",
    "PLSX": "LSX",
    "PZWJ": "ZWJ",
    "PGZL": "GZL",
    "PSJT": "SJT",
    "PBSX": "BSX",
    "PWLL": "WLL",
    "PGTX": "GTX",
    "PZHT": "ZHT",
    "PLHX": "LHX",
}
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
DOCUMENT_SCAN_VERSION = "drawing-code-v2"


def _is_a0(name: str) -> bool:
    return bool(A0_PATTERN.match(name))


def _is_customer_folder_name(name: str) -> bool:
    normalized = (name or "").casefold()
    return any(keyword.casefold() in normalized for keyword in CUSTOMER_FOLDER_KEYWORDS)


def _extract_customer_name(subfolder_name: str) -> tuple[Optional[str], Optional[str]]:
    raw = (subfolder_name or "").strip()
    if raw.startswith(CUSTOMER_PREFIX):
        suffix = raw[len(CUSTOMER_PREFIX) :].strip()
        if suffix:
            return suffix.split("_")[-1].strip(), subfolder_name

    parts = [part.strip() for part in re.split(r"[_\-]+", raw) if part.strip()]
    for part in reversed(parts):
        if not _is_customer_folder_name(part) and not re.match(r"^\d+$", part):
            return part, subfolder_name
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
        for directory in dirs:
            codes.extend(_extract_drawing_codes_from_text(directory))

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


def _document_metadata_state(
    folder_path: str,
    fallback: datetime.datetime | None = None,
) -> tuple[datetime.datetime | None, str]:
    latest = fallback
    signature_parts: list[str] = [f"version|{DOCUMENT_SCAN_VERSION}"]

    try:
        root_stat = os.stat(folder_path)
        root_mtime = datetime.datetime.utcfromtimestamp(root_stat.st_mtime)
        latest = max(latest or datetime.datetime.min, root_mtime)
        signature_parts.append(f".|d|{root_stat.st_mtime_ns}|0")
    except OSError:
        return latest, ""

    for root, dirs, files in os.walk(folder_path):
        dirs[:] = [d for d in dirs if d not in DOCUMENT_SCAN_EXCLUDES]

        for name in dirs:
            path = os.path.join(root, name)
            rel = os.path.relpath(path, folder_path).replace("\\", "/")
            try:
                stat = os.stat(path)
            except OSError:
                continue
            dir_mtime = datetime.datetime.utcfromtimestamp(stat.st_mtime)
            if latest is None or dir_mtime > latest:
                latest = dir_mtime
            signature_parts.append(f"{rel}|d|{stat.st_mtime_ns}|0")

        for name in files:
            ext = os.path.splitext(name)[1].lower()
            if ext not in DOCUMENT_EXTENSIONS:
                continue
            path = os.path.join(root, name)
            rel = os.path.relpath(path, folder_path).replace("\\", "/")
            try:
                stat = os.stat(path)
            except OSError:
                continue
            file_mtime = datetime.datetime.utcfromtimestamp(stat.st_mtime)
            if latest is None or file_mtime > latest:
                latest = file_mtime
            signature_parts.append(f"{rel}|f|{stat.st_mtime_ns}|{stat.st_size}")

    digest = hashlib.sha1("\n".join(sorted(signature_parts)).encode("utf-8")).hexdigest()
    return latest, digest


def _propack_root() -> str:
    configured = os.getenv("PROPACK_ROOT")
    if configured:
        return configured
    return str(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", "..", "propack", "propack")))


def _used_codes_path() -> str:
    configured = os.getenv("PROPACK_USED_CODES_PATH")
    if configured:
        return configured
    return os.path.join(_propack_root(), "used_codes.json")


def _main_db_path() -> str:
    configured = os.getenv("PROPACK_MAIN_DB_PATH")
    if configured:
        return configured
    return os.path.join(_propack_root(), "DB.db")


def _extract_plan_code(folder_name: str) -> str:
    match = PROJECT_CODE_PATTERN.match((folder_name or "").strip())
    return match.group(1).upper() if match else ""


def _code_category(code: str) -> str:
    upper = (code or "").upper()
    for prefix, category in CODE_PREFIX_CATEGORIES.items():
        if upper.startswith(prefix):
            return category
    return ""


def _detect_folder_category(folder_name: str) -> str:
    source = (folder_name or "").upper()
    for category, keywords in FOLDER_CATEGORY_KEYWORDS.items():
        if any(keyword.upper() in source for keyword in keywords):
            return category
    return ""


def _created_code_time(item: dict) -> str:
    return str(item.get("time") or "")


def _load_created_code_for_plan(plan_code: str) -> list[str]:
    if not plan_code:
        return []
    path = _used_codes_path()
    if not os.path.isfile(path):
        return []
    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
    except Exception as exc:
        logger.warning("Cannot read code history %s: %s", path, exc)
        return []

    history = data.get("history") if isinstance(data, dict) else []
    if not isinstance(history, list):
        return []

    matches = [
        item
        for item in history
        if str(item.get("plan_code") or "").strip().upper() == plan_code.upper()
        and item.get("code")
    ]
    matches.sort(key=_created_code_time, reverse=True)
    return _filter_original_drawing_codes([str(item.get("code") or "") for item in matches])


def _load_project_drawing_code(plan_code: str) -> list[str]:
    if not plan_code:
        return []
    path = _main_db_path()
    if not os.path.isfile(path):
        return []
    try:
        conn = sqlite3.connect(path)
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            """
            SELECT ma_ban_ve_ky_thuat
            FROM projects
            WHERE UPPER(COALESCE(ma_ban_ve, '')) = ?
            ORDER BY tracking_id DESC
            LIMIT 1
            """,
            (plan_code.upper(),),
        ).fetchone()
    except Exception as exc:
        logger.warning("Cannot read project drawing code for %s: %s", plan_code, exc)
        return []
    finally:
        try:
            conn.close()
        except Exception:
            pass

    if not row:
        return []
    raw = str(row["ma_ban_ve_ky_thuat"] or "")
    return _filter_original_drawing_codes(_extract_drawing_codes_from_text(raw))


def _filter_original_drawing_codes(
    codes: list[str],
    folder_name: str = "",
    require_category_match: bool = False,
) -> list[str]:
    normalized = [code.strip().upper() for code in codes if code and _is_drawing_code(code.strip().upper())]
    unique = list(dict.fromkeys(normalized))
    if not unique:
        return []

    folder_category = _detect_folder_category(folder_name)
    candidates = [
        code
        for code in unique
        if ROOT_DRAWING_CODE_PATTERN.match(code) or SJT_DRAWING_CODE_PATTERN.match(code)
    ]
    if not candidates:
        return []

    if folder_category:
        same_category = [code for code in candidates if _code_category(code) == folder_category]
        if same_category:
            candidates = same_category
        elif require_category_match:
            return []

    non_sjt = [code for code in candidates if _code_category(code) != "SJT"]
    if folder_category != "SJT" and non_sjt:
        candidates = non_sjt

    return candidates[:1]


def _resolve_original_drawing_codes(
    folder_name: str,
    scanned_codes: list[str],
    allow_history_fallback: bool = False,
) -> list[str]:
    plan_code = _extract_plan_code(folder_name)
    scanned = _filter_original_drawing_codes(scanned_codes, folder_name)
    if scanned or not allow_history_fallback:
        return scanned

    for source_codes in (_load_created_code_for_plan(plan_code), _load_project_drawing_code(plan_code)):
        fallback = _filter_original_drawing_codes(source_codes, folder_name, require_category_match=True)
        if fallback:
            return fallback
    return []


def _get_document_metadata_mtime(
    folder_path: str,
    fallback: datetime.datetime | None = None,
) -> datetime.datetime | None:
    return _document_metadata_state(folder_path, fallback)[0]


def _clean_salesperson_name(value: str) -> str:
    return os.path.splitext((value or "").strip())[0].strip()


def _extract_salesperson_from_customer_folder(customer_folder_path: str) -> Optional[str]:
    for root, dirs, files in os.walk(customer_folder_path):
        dirs[:] = [d for d in dirs if d not in DOCUMENT_SCAN_EXCLUDES]
        for file in files:
            name_without_ext = os.path.splitext(file)[0]
            match = SALESPERSON_PATTERN.match(name_without_ext)
            if match:
                return _clean_salesperson_name(match.group(1))

            if os.path.splitext(file)[1].lower() == ".txt":
                path = os.path.join(root, file)
                try:
                    with open(path, "r", encoding="utf-8", errors="ignore") as fh:
                        for line in fh:
                            match = SALESPERSON_PATTERN.match(line.strip())
                            if match:
                                return _clean_salesperson_name(match.group(1))
                except OSError:
                    continue
    return None


class DocumentScanner:
    """Filesystem inspector for A0 folders and cached document metadata."""

    def __init__(self, smb_root: str | None = None):
        self.smb_root = normalize_smb_root(smb_root or settings.SMB_ROOT)

    def scan_folder_path(
        self,
        folder_path: str,
        folder_name: str | None = None,
        allow_history_fallback: bool = False,
    ) -> DocumentScanResult:
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
                    if sub.is_dir() and _is_customer_folder_name(sub.name):
                        customer_name, customer_subfolder_name = _extract_customer_name(sub.name)
                        salesperson_name = _extract_salesperson_from_customer_folder(sub.path)
                        found = bool(customer_name or salesperson_name)
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

        drawing_codes = _resolve_original_drawing_codes(
            folder_name,
            _scan_files_for_drawing_codes(folder_path),
            allow_history_fallback=allow_history_fallback,
        )

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
        source_mtime, document_signature = _document_metadata_state(folder.absolute_path, source_mtime)

        if (
            not force
            and folder.document_signature
            and folder.document_signature == document_signature
            and folder.source_mtime
            and source_mtime
            and folder.source_mtime >= source_mtime
        ):
            return False

        result = self.scan_folder_path(folder.absolute_path, folder.name)
        folder.customer_name = result.customer_name
        folder.customer_subfolder_name = result.customer_subfolder_name
        folder.salesperson_name = result.salesperson_name
        folder.drawing_codes_json = json.dumps(result.drawing_codes, ensure_ascii=False)
        folder.source_mtime = source_mtime
        folder.document_signature = document_signature
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
                    source_mtime, document_signature = _document_metadata_state(
                        entry.path,
                        datetime.datetime.utcfromtimestamp(stat.st_mtime),
                    )
                    folder = db_folders.get(rel_path)

                    if (
                        db is not None
                        and folder is not None
                        and not force
                        and folder.document_signature
                        and folder.document_signature == document_signature
                        and folder.source_mtime
                        and source_mtime
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
                        folder.document_signature = document_signature
                        folder.document_scanned_at = datetime.datetime.utcnow()
        except Exception as exc:
            logger.error("Cannot scan %s: %s", root, exc)
            raise

        if db is not None:
            db.commit()

        return results
