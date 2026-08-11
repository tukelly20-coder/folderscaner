"""
Sync Service — high-level orchestration and FastAPI lifespan management.
"""

import asyncio
import logging

from fastapi import FastAPI
from sqlalchemy import inspect, text

from app.config import settings
from app.database.database import SessionLocal, engine, Base
from app.services.folder_scanner import FolderScanner

logger = logging.getLogger(__name__)


def create_tables():
    """Create all database tables (no Alembic in dev / Phase 1)."""
    Base.metadata.create_all(bind=engine)
    migrate_folder_cache_columns()


def migrate_folder_cache_columns():
    """Add lightweight document-cache columns to existing deployments."""
    inspector = inspect(engine)
    if "folders" not in inspector.get_table_names():
        return

    existing = {column["name"] for column in inspector.get_columns("folders")}
    wanted = {
        "source_mtime": "DATETIME",
        "document_scanned_at": "DATETIME",
        "customer_name": "VARCHAR",
        "customer_subfolder_name": "VARCHAR",
        "salesperson_name": "VARCHAR",
        "drawing_codes_json": "TEXT",
    }

    with engine.begin() as conn:
        for column, column_type in wanted.items():
            if column not in existing:
                conn.execute(text(f"ALTER TABLE folders ADD COLUMN {column} {column_type}"))


async def lifespan(app: FastAPI):
    """Startup / shutdown lifecycle for the FastAPI app."""
    # Import models so SQLAlchemy registers them before create_all
    from app.models import folder, folder_event  # noqa: F401

    create_tables()
    db = SessionLocal()
    scanner = FolderScanner(db=db)

    # Start background scanner
    task = asyncio.create_task(scanner.scan_loop())
    app.state.scanner = scanner
    app.state.scanner_task = task
    app.state.db = db
    logger.info("Background scanner started (interval=%ds)", settings.SCAN_INTERVAL)

    yield

    # Shutdown
    scanner.stop()
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass
    db.close()
    logger.info("Background scanner stopped")
