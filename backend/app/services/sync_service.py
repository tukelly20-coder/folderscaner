"""
Sync Service — high-level orchestration and FastAPI lifespan management.
"""

import asyncio
import datetime
import logging
import time
from dataclasses import dataclass, field
from typing import Optional

from fastapi import FastAPI
from sqlalchemy import inspect, text

from app.config import normalize_smb_root, settings
from app.database.database import SessionLocal, engine, Base
from app.models.user_smb_root import UserSmbRoot
from app.services.folder_scanner import FolderScanner

logger = logging.getLogger(__name__)


def _utc_now() -> datetime.datetime:
    return datetime.datetime.utcnow()


def _root_key(root: str) -> str:
    return normalize_smb_root(root).replace("\\", "/").lower()


@dataclass
class RootScanState:
    root: str
    running: bool = False
    scan_count: int = 0
    last_started_at: Optional[datetime.datetime] = None
    last_finished_at: Optional[datetime.datetime] = None
    last_duration_seconds: Optional[float] = None
    last_success: Optional[bool] = None
    last_error: Optional[str] = None
    last_summary: dict = field(default_factory=dict)
    last_full_scan_at: Optional[datetime.datetime] = None

    def as_dict(self) -> dict:
        return {
            "root": self.root,
            "running": self.running,
            "scan_count": self.scan_count,
            "last_started_at": self.last_started_at.isoformat() if self.last_started_at else None,
            "last_finished_at": self.last_finished_at.isoformat() if self.last_finished_at else None,
            "last_duration_seconds": self.last_duration_seconds,
            "last_success": self.last_success,
            "last_error": self.last_error,
            "last_summary": self.last_summary,
            "last_full_scan_at": self.last_full_scan_at.isoformat() if self.last_full_scan_at else None,
        }


class BackgroundScanScheduler:
    """Run one polling worker per SMB root with global concurrency limits."""

    def __init__(self) -> None:
        self._tasks: dict[str, asyncio.Task] = {}
        self._states: dict[str, RootScanState] = {}
        self._stop_event: asyncio.Event | None = None
        self._reconcile_event: asyncio.Event | None = None
        self._semaphore: asyncio.Semaphore | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._supervisor_task: asyncio.Task | None = None

    @property
    def running(self) -> bool:
        return self._supervisor_task is not None and not self._supervisor_task.done()

    async def start(self) -> None:
        if self.running:
            return
        self._loop = asyncio.get_running_loop()
        self._stop_event = asyncio.Event()
        self._reconcile_event = asyncio.Event()
        self._semaphore = asyncio.Semaphore(max(1, settings.SCANNER_MAX_WORKERS))
        self._supervisor_task = asyncio.create_task(self._supervise())

    async def stop(self) -> None:
        if self._stop_event:
            self._stop_event.set()
        if self._reconcile_event:
            self._reconcile_event.set()

        tasks = list(self._tasks.values())
        for task in tasks:
            task.cancel()

        if self._supervisor_task:
            self._supervisor_task.cancel()
            try:
                await self._supervisor_task
            except asyncio.CancelledError:
                pass

        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

        self._tasks.clear()

    def request_reconcile(self) -> None:
        if not self._loop or not self._reconcile_event:
            return
        self._loop.call_soon_threadsafe(self._reconcile_event.set)

    def status(self) -> dict:
        return {
            "mode": "per_root_workers",
            "scan_strategy": "initial_full_then_incremental_with_repair",
            "running": self.running,
            "scan_interval": settings.SCAN_INTERVAL,
            "reconcile_interval": settings.SCANNER_RECONCILE_INTERVAL,
            "full_repair_interval": settings.SCANNER_FULL_REPAIR_INTERVAL,
            "max_workers": max(1, settings.SCANNER_MAX_WORKERS),
            "active_workers": sum(1 for task in self._tasks.values() if not task.done()),
            "roots": [state.as_dict() for state in self._states.values()],
        }

    async def _supervise(self) -> None:
        assert self._stop_event is not None
        assert self._reconcile_event is not None

        while not self._stop_event.is_set():
            self._reconcile_event.clear()
            self._reconcile_roots(_scan_roots_from_db())

            try:
                await asyncio.wait_for(
                    self._reconcile_event.wait(),
                    timeout=max(1, settings.SCANNER_RECONCILE_INTERVAL),
                )
            except asyncio.TimeoutError:
                pass

    def _reconcile_roots(self, roots: list[str]) -> None:
        wanted = {_root_key(root): normalize_smb_root(root) for root in roots}

        for key, task in list(self._tasks.items()):
            if key not in wanted:
                task.cancel()
                self._tasks.pop(key, None)
                self._states.pop(key, None)

        for key, root in wanted.items():
            state = self._states.setdefault(key, RootScanState(root=root))
            state.root = root
            task = self._tasks.get(key)
            if task is None or task.done():
                self._tasks[key] = asyncio.create_task(self._root_worker(key, root))

        if not wanted:
            logger.info("No SMB roots configured for background scanner")

    async def _root_worker(self, key: str, root: str) -> None:
        assert self._stop_event is not None
        while not self._stop_event.is_set():
            await self._scan_root(key, root)
            try:
                await asyncio.wait_for(
                    self._stop_event.wait(),
                    timeout=max(1, settings.SCAN_INTERVAL),
                )
            except asyncio.TimeoutError:
                pass

    async def _scan_root(self, key: str, root: str) -> None:
        assert self._semaphore is not None
        state = self._states.setdefault(key, RootScanState(root=root))

        async with self._semaphore:
            state.running = True
            state.last_started_at = _utc_now()
            state.last_error = None
            started = time.monotonic()
            try:
                force_full_scan = self._should_full_scan(state)
                summary = await asyncio.to_thread(_scan_root_once, root, force_full_scan)
                state.last_summary = summary
                if summary.get("full_scan"):
                    state.last_full_scan_at = _utc_now()
                state.last_success = not bool(summary.get("errors"))
                if summary.get("errors"):
                    state.last_error = "; ".join(str(err) for err in summary["errors"][:3])
            except Exception as exc:
                logger.exception("Background scan failed for %s", root)
                state.last_success = False
                state.last_error = str(exc)
                state.last_summary = {"errors": [str(exc)]}
            finally:
                state.running = False
                state.scan_count += 1
                state.last_finished_at = _utc_now()
                state.last_duration_seconds = round(time.monotonic() - started, 3)

    @staticmethod
    def _should_full_scan(state: RootScanState) -> bool:
        if state.last_full_scan_at is None:
            return True
        elapsed = (_utc_now() - state.last_full_scan_at).total_seconds()
        return elapsed >= max(60, settings.SCANNER_FULL_REPAIR_INTERVAL)


def _scan_root_once(root: str, force_full_scan: bool = False) -> dict:
    db = SessionLocal()
    try:
        scanner = FolderScanner(db=db, smb_root=root, force_full_scan=force_full_scan)
        return scanner.scan_once()
    finally:
        db.close()


scanner_scheduler = BackgroundScanScheduler()


def create_tables():
    """Create all database tables (no Alembic in dev / Phase 1)."""
    Base.metadata.create_all(bind=engine)
    migrate_folder_cache_columns()


def _scan_roots_from_db() -> list[str]:
    roots: list[str] = []

    db = SessionLocal()
    try:
        saved_roots = (
            db.query(UserSmbRoot)
            .filter(UserSmbRoot.active == True, UserSmbRoot.smb_root != "")
            .all()
        )
        roots.extend(root.smb_root for root in saved_roots if root.smb_root)
    finally:
        db.close()

    deduped: list[str] = []
    seen: set[str] = set()
    for root in roots:
        normalized = normalize_smb_root(root)
        key = normalized.replace("\\", "/").lower()
        if normalized and key not in seen:
            seen.add(key)
            deduped.append(normalized)
    return deduped


def migrate_folder_cache_columns():
    """Add lightweight document-cache columns to existing deployments."""
    inspector = inspect(engine)
    if "folders" not in inspector.get_table_names():
        return

    existing = {column["name"] for column in inspector.get_columns("folders")}
    wanted = {
        "source_mtime": "DATETIME",
        "document_signature": "VARCHAR",
        "document_scanned_at": "DATETIME",
        "customer_name": "VARCHAR",
        "customer_subfolder_name": "VARCHAR",
        "salesperson_name": "VARCHAR",
        "drawing_codes_json": "TEXT",
        "scan_root": "VARCHAR",
    }

    with engine.begin() as conn:
        for column, column_type in wanted.items():
            if column not in existing:
                conn.execute(text(f"ALTER TABLE folders ADD COLUMN {column} {column_type}"))

        indexes = inspector.get_indexes("folders")
        for index in indexes:
            if index.get("unique") and index.get("column_names") == ["relative_path"]:
                conn.execute(text(f"DROP INDEX {index['name']}"))
                conn.execute(text("CREATE INDEX ix_folders_relative_path ON folders (relative_path)"))
                break


async def lifespan(app: FastAPI):
    """Startup / shutdown lifecycle for the FastAPI app."""
    # Import models so SQLAlchemy registers them before create_all
    from app.models import folder, folder_event, scan_snapshot, user_smb_root  # noqa: F401

    create_tables()
    await scanner_scheduler.start()
    app.state.scanner_scheduler = scanner_scheduler
    logger.info(
        "Background scanner started (interval=%ds, max_workers=%d)",
        settings.SCAN_INTERVAL,
        max(1, settings.SCANNER_MAX_WORKERS),
    )

    yield

    # Shutdown
    await scanner_scheduler.stop()
    logger.info("Background scanner stopped")
