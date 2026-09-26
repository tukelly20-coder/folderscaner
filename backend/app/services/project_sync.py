"""
Sync scanner project metadata into the main Propack project table.

The scanner stores project folders such as ``P002-2605-005-A0 ...``.  The
main project table stores the corresponding big-project row in ``DB.db``.
This module updates the main row after scanner metadata has been refreshed.
"""

from __future__ import annotations

import datetime
import json
import logging
import os
import re
import sqlite3
from pathlib import Path
from typing import Any

from app.models.folder import Folder, FolderStatus

logger = logging.getLogger(__name__)

PROJECT_CODE_PATTERN = re.compile(
    r"^([A-Z][A-Z0-9]{0,7}-(\d{2})(0[1-9]|1[0-2])-(\d{3})(?:-[A-Z0-9]+)?)",
    re.IGNORECASE,
)
COPY_SUFFIX_PATTERN = re.compile(
    r"(?:[-_\s]*(?:副本|复件|复制|copy|copie|duplicate)(?:\s*\(\d+\))?)+$",
    re.IGNORECASE,
)
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
PRODUCT_TYPE_LABELS = {
    "WLJ": "WLJ物料架 - Giá đựng vật liệu",
    "ZZC": "ZZC周转车 - Xe trung chuyển",
    "GZT": "GZT工作台 - Bàn thao tác",
    "WCP": "WCP无尘棚 - Phòng sạch",
    "LSX": "LSX流水线 - Băng tải",
    "ZWJ": "ZWJ转弯机 - Băng tải chuyển hướng 90,180",
    "GZL": "GZL改造类 - Cải tạo",
    "SJT": "SJT散件图 - Bản vẽ tách chi tiết",
    "BSX": "BSX倍速线 - Băng chuyền xích",
    "WLL": "WLL围栏类 - Hàng rào",
    "GTX": "GTX滚筒线 - Băng chuyền con lăn",
    "ZHT": "ZHT展会图 - Bản vẽ mặt bằng",
    "LHX": "LHX老化线 - Băng chuyền lão hóa",
}
PRODUCT_KEYWORDS = {
    "SJT": ("SJT", "散件图", "软件图", "导条皮带", "护罩", "设备门", "设备们"),
    "WLJ": ("WLJ", "物料架", "货架", "千层车", "料车", "周转架", "移动架"),
    "ZZC": ("ZZC", "周转车"),
    "GZT": ("GZT", "工作台"),
    "WCP": ("WCP", "无尘棚"),
    "LSX": ("LSX", "流水线", "回流线", "皮带线", "输送线", "PVC皮带线"),
    "ZWJ": ("ZWJ", "转弯机", "顶升移栽", "移栽机"),
    "GZL": ("GZL", "改造", "技改"),
    "BSX": ("BSX", "倍速线"),
    "WLL": ("WLL", "围栏", "护栏"),
    "GTX": ("GTX", "滚筒线"),
    "ZHT": ("ZHT", "展会图", "平面"),
    "LHX": ("LHX", "老化线"),
}

UNKNOWN_PRODUCT_NOTICE_STATUS = "Cần phân loại sản phẩm - Không đoán được từ quy cách/thư mục"


def _main_db_path() -> Path:
    configured = os.getenv("PROPACK_MAIN_DB_PATH")
    if configured:
        return Path(configured)
    return Path(__file__).resolve().parents[4] / "propack" / "propack" / "DB.db"


def _clean(value: Any) -> str:
    return str(value or "").strip()


def _strip_copy_suffix(value: str) -> str:
    previous = ""
    cleaned = _clean(value)
    while cleaned and cleaned != previous:
        previous = cleaned
        cleaned = COPY_SUFFIX_PATTERN.sub("", cleaned).strip(" -_")
    return cleaned


def _is_copy_marker(value: Any) -> bool:
    raw = _clean(value)
    return bool(raw and not _strip_copy_suffix(raw))


def _extract_folder_parts(folder_name: str) -> dict[str, str]:
    match = PROJECT_CODE_PATTERN.match(_clean(folder_name))
    if not match:
        return {}

    plan_code, year, month, sequence = match.groups()
    project_identity = f"{plan_code.split('-')[0]}-{year}{month}-{sequence}".upper()
    return {
        "plan_code": plan_code.upper(),
        "project_identity": project_identity,
        "project_key": f"{year}{month}{sequence}",
        "project_key_dashed": f"{year}{month}-{sequence}",
        "year_month": f"{year}年{int(month)}月",
    }


def _extract_spec(folder_name: str, plan_code: str) -> str:
    if not plan_code:
        return ""
    spec = _clean(folder_name)[len(plan_code) :].lstrip("-_ ").strip()
    return _strip_copy_suffix(spec)


def _category_from_drawing_codes(folder: Folder) -> str:
    for code in folder.drawing_codes:
        upper = code.upper()
        for prefix, category in CODE_PREFIX_CATEGORIES.items():
            if upper.startswith(prefix):
                return category
    return ""


def _category_from_code(code: Any) -> str:
    upper = _clean(code).upper()
    for prefix, category in CODE_PREFIX_CATEGORIES.items():
        if upper.startswith(prefix):
            return category
    return ""


def _category_from_folder_text(folder_name: str, spec: str) -> str:
    source = f"{folder_name} {spec}".upper()
    for category, keywords in PRODUCT_KEYWORDS.items():
        if any(keyword.upper() in source for keyword in keywords):
            return category
    return ""


def _detect_product_type(folder: Folder, spec: str) -> str:
    category = _category_from_drawing_codes(folder) or _category_from_folder_text(folder.name, spec)
    return PRODUCT_TYPE_LABELS.get(category, "")


def _primary_drawing_code(folder: Folder) -> str:
    return folder.drawing_codes[0] if folder.drawing_codes else ""


def _used_codes_path() -> Path:
    configured = os.getenv("PROPACK_USED_CODES_PATH")
    if configured:
        return Path(configured)
    return _main_db_path().parent / "used_codes.json"


def _normalize_parent_lookup_code(code: Any) -> str:
    return _clean(code).upper()


def _parent_code_from_history(drawing_code: str) -> str:
    lookup_code = _normalize_parent_lookup_code(drawing_code)
    if not lookup_code:
        return ""

    path = _used_codes_path()
    if not path.exists():
        return ""

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        logger.warning("Cannot read used code history for parent lookup: %s", exc)
        return ""

    for item in data.get("history", []):
        if _normalize_parent_lookup_code(item.get("code")) != lookup_code:
            continue
        parent_code = _clean(item.get("parent_code"))
        if parent_code:
            return parent_code
    return ""


def _parent_code_from_cache(drawing_code: str, cursor: sqlite3.Cursor) -> str:
    lookup_code = _normalize_parent_lookup_code(drawing_code)
    if not lookup_code:
        return ""

    try:
        cursor.execute(
            "SELECT parent_code FROM parent_code_cache WHERE engineer_fig_no = ?",
            (lookup_code,),
        )
        row = cursor.fetchone()
    except sqlite3.Error as exc:
        logger.warning("Cannot read parent_code_cache for %s: %s", lookup_code, exc)
        return ""

    if not row:
        return ""
    return _clean(row["parent_code"] if isinstance(row, sqlite3.Row) else row[0])


def _lookup_parent_code(drawing_code: str, cursor: sqlite3.Cursor) -> str:
    return _parent_code_from_history(drawing_code) or _parent_code_from_cache(drawing_code, cursor)


def _ensure_main_schema(cursor: sqlite3.Cursor) -> set[str]:
    cursor.execute("PRAGMA table_info(projects)")
    columns = {row[1] for row in cursor.fetchall()}
    if "version" not in columns:
        cursor.execute("ALTER TABLE projects ADD COLUMN version INTEGER DEFAULT 1")
        columns.add("version")
    if "updated_by" not in columns:
        cursor.execute("ALTER TABLE projects ADD COLUMN updated_by TEXT")
        columns.add("updated_by")
    if "updated_at" not in columns:
        cursor.execute("ALTER TABLE projects ADD COLUMN updated_at TEXT")
        columns.add("updated_at")
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS project_change_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tracking_id INTEGER NOT NULL,
            field_name TEXT NOT NULL,
            old_value TEXT,
            new_value TEXT,
            changed_by TEXT,
            changed_by_name TEXT,
            changed_at TEXT NOT NULL
        )
        """
    )
    return columns


def _find_main_project(
    cursor: sqlite3.Cursor,
    plan_code: str,
    project_identity: str,
    project_key: str,
    project_key_dashed: str,
) -> sqlite3.Row | None:
    candidates = [plan_code, project_identity, project_key, project_key_dashed]
    cursor.execute(
        """
        SELECT *
        FROM projects
        WHERE UPPER(COALESCE(ma_ban_ve, '')) IN (?, ?, ?, ?)
           OR CAST(tracking_id AS TEXT) IN (?, ?)
        ORDER BY
            CASE
                WHEN UPPER(COALESCE(ma_ban_ve, '')) IN (?, ?) THEN 0
                ELSE 1
            END,
            tracking_id DESC
        LIMIT 1
        """,
        (
            candidates[0].upper(),
            candidates[1].upper(),
            candidates[2].upper(),
            candidates[3].upper(),
            project_key,
            project_key_dashed,
            plan_code.upper(),
            project_identity.upper(),
        ),
    )
    return cursor.fetchone()


def _insert_change_log(
    cursor: sqlite3.Cursor,
    tracking_id: int,
    field_name: str,
    old_value: Any,
    new_value: Any,
    changed_at: str,
) -> None:
    cursor.execute(
        """
        INSERT INTO project_change_logs
            (tracking_id, field_name, old_value, new_value, changed_by, changed_by_name, changed_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            tracking_id,
            field_name,
            "" if old_value is None else str(old_value),
            "" if new_value is None else str(new_value),
            "scanner",
            "Dự án cá nhân",
            changed_at,
        ),
    )


def _next_tracking_id(cursor: sqlite3.Cursor) -> int:
    cursor.execute("SELECT MAX(tracking_id) FROM projects")
    max_id = cursor.fetchone()[0] or 0
    return int(max_id) + 1


def _insert_main_project(
    cursor: sqlite3.Cursor,
    columns: set[str],
    payload: dict[str, str],
    changed_at: str,
) -> int:
    tracking_id = _next_tracking_id(cursor)
    insert_payload: dict[str, Any] = {
        "tracking_id": tracking_id,
        "is_pending": "no",
        "version": 1,
        "updated_by": "scanner",
        "updated_at": changed_at,
    }
    insert_payload.update({key: value for key, value in payload.items() if key in columns})

    insert_columns = [key for key in insert_payload if key in columns]
    placeholders = ", ".join("?" for _ in insert_columns)
    cursor.execute(
        f"INSERT INTO projects ({', '.join(insert_columns)}) VALUES ({placeholders})",
        [insert_payload[key] for key in insert_columns],
    )

    for field_name, new_value in payload.items():
        if field_name in columns:
            _insert_change_log(cursor, tracking_id, field_name, "", new_value, changed_at)

    return tracking_id


def sync_folder_to_main_project(folder: Folder) -> dict[str, Any]:
    """Copy scanner metadata to the matching main project row, creating it if needed."""
    if folder.status != FolderStatus.ACTIVE:
        return {"success": False, "reason": "inactive_folder"}

    parts = _extract_folder_parts(folder.name)
    if not parts:
        return {"success": False, "reason": "not_project_folder"}

    db_path = _main_db_path()
    if not db_path.exists():
        logger.warning("Main project DB not found: %s", db_path)
        return {"success": False, "reason": "main_db_missing", "path": str(db_path)}

    plan_code = parts["plan_code"]
    spec = _extract_spec(folder.name, parts["plan_code"])
    drawing_code = _primary_drawing_code(folder)
    detected_product_type = _detect_product_type(folder, spec)
    payload = {
        "Created_Date": parts["year_month"],
        "khach_hang": _clean(folder.customer_name),
        "nhan_vien_kinh_doanh": _clean(folder.salesperson_name),
        "quy_cach": spec,
        "ma_ban_ve": plan_code,
        "ma_ban_ve_ky_thuat": drawing_code,
        "loai_san_pham": detected_product_type,
    }
    if not detected_product_type:
        payload.update({
            "is_pending": "yes",
            "urgency_level": "normal",
            "tinh_trang_hoan_thanh": UNKNOWN_PRODUCT_NOTICE_STATUS,
        })
    payload = {key: value for key, value in payload.items() if _clean(value)}
    if not payload:
        return {"success": False, "reason": "no_source_data"}

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    try:
        columns = _ensure_main_schema(cursor)
        parent_code = _lookup_parent_code(drawing_code, cursor)
        if parent_code:
            payload["ma_me"] = parent_code

        project = _find_main_project(
            cursor,
            parts["plan_code"],
            parts["project_identity"],
            parts["project_key"],
            parts["project_key_dashed"],
        )
        if not project:
            now = datetime.datetime.now().isoformat()
            tracking_id = _insert_main_project(cursor, columns, payload, now)
            customer_name = payload.get("khach_hang")
            if customer_name:
                cursor.execute("INSERT OR IGNORE INTO customers (name) VALUES (?)", (customer_name,))
            conn.commit()
            return {
                "success": True,
                "created": True,
                "updated": True,
                "tracking_id": tracking_id,
                "changed_fields": list(payload.keys()),
                "plan_code": parts["plan_code"],
            }

        current = dict(project)
        updates = {
            key: value
            for key, value in payload.items()
            if key in columns and _clean(current.get(key)) != _clean(value)
        }
        current_product_type = _clean(current.get("loai_san_pham"))
        current_completion = _clean(current.get("tinh_trang_hoan_thanh"))
        if not detected_product_type and not current_product_type:
            if "is_pending" in columns and _clean(current.get("is_pending")).lower() != "yes":
                updates["is_pending"] = "yes"
            if "urgency_level" in columns and not _clean(current.get("urgency_level")):
                updates["urgency_level"] = "normal"
            if (
                "tinh_trang_hoan_thanh" in columns
                and current_completion != UNKNOWN_PRODUCT_NOTICE_STATUS
            ):
                updates["tinh_trang_hoan_thanh"] = UNKNOWN_PRODUCT_NOTICE_STATUS
        elif detected_product_type and current_completion == UNKNOWN_PRODUCT_NOTICE_STATUS:
            if "tinh_trang_hoan_thanh" in columns:
                updates["tinh_trang_hoan_thanh"] = ""
            if (
                "is_pending" in columns
                and _clean(current.get("is_pending")).lower() == "yes"
                and not _clean(current.get("accepted_by"))
            ):
                updates["is_pending"] = "no"
        folder_category = _category_from_folder_text(folder.name, spec)
        current_drawing_category = _category_from_code(current.get("ma_ban_ve_ky_thuat"))
        if (
            not drawing_code
            and folder.document_signature
            and _clean(current.get("ma_ban_ve_ky_thuat"))
            and "ma_ban_ve_ky_thuat" in columns
        ):
            updates["ma_ban_ve_ky_thuat"] = ""
        if not spec and "quy_cach" in columns and _is_copy_marker(current.get("quy_cach")):
            updates["quy_cach"] = ""
        if not updates:
            conn.rollback()
            return {
                "success": True,
                "updated": False,
                "tracking_id": current.get("tracking_id"),
                "changed_fields": [],
            }

        now = datetime.datetime.now().isoformat()
        set_clauses = [f"{key} = ?" for key in updates]
        values = list(updates.values())
        set_clauses.extend(["version = COALESCE(version, 1) + 1", "updated_at = ?", "updated_by = ?"])
        values.extend([now, "scanner"])
        values.append(current["tracking_id"])
        cursor.execute(
            f"UPDATE projects SET {', '.join(set_clauses)} WHERE tracking_id = ?",
            values,
        )

        for field_name, new_value in updates.items():
            _insert_change_log(
                cursor,
                int(current["tracking_id"]),
                field_name,
                current.get(field_name),
                new_value,
                now,
            )

        customer_name = updates.get("khach_hang")
        if customer_name:
            cursor.execute("INSERT OR IGNORE INTO customers (name) VALUES (?)", (customer_name,))

        conn.commit()
        return {
            "success": True,
            "updated": True,
            "tracking_id": current.get("tracking_id"),
            "changed_fields": list(updates.keys()),
        }
    except Exception as exc:
        conn.rollback()
        logger.warning("Cannot sync scanner folder %s to main project: %s", folder.name, exc)
        return {"success": False, "reason": "sync_error", "error": str(exc)}
    finally:
        conn.close()
