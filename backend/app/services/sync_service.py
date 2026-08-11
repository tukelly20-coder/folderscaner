"""
Sync Service — high-level orchestration and FastAPI lifespan management.
"""

import asyncio
import logging

from fastapi import FastAPI

from app.config import settings
from app.database.database import SessionLocal, engine, Base
from app.services.folder_scanner import FolderScanner

logger = logging.getLogger(__name__)


def create_tables():
    """Create all database tables (no Alembic in dev / Phase 1)."""
    Base.metadata.create_all(bind=engine)


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
