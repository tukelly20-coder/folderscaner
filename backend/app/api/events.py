"""
REST API endpoints for folder event history.
"""

from typing import List

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.database.database import get_db
from app.models.folder_event import FolderEvent
from app.schemas.event import FolderEventRead

router = APIRouter(prefix="/api/folder-events", tags=["events"])


@router.get("/", response_model=List[FolderEventRead])
def list_events(
    skip: int = 0,
    limit: int = 100,
    folder_id: int | None = Query(default=None, description="Filter by folder_id"),
    event_type: str | None = Query(default=None, description="Filter by event_type"),
    db: Session = Depends(get_db),
):
    """GET /api/folder-events — List events (optionally filtered)."""
    query = db.query(FolderEvent).order_by(FolderEvent.detected_at.desc())
    if folder_id is not None:
        query = query.filter(FolderEvent.folder_id == folder_id)
    if event_type is not None:
        query = query.filter(FolderEvent.event_type == event_type)
    return query.offset(skip).limit(limit).all()


@router.get("/{event_id}", response_model=FolderEventRead)
def get_event(
    event_id: int,
    db: Session = Depends(get_db),
):
    """GET /api/folder-events/{id}"""
    event = db.query(FolderEvent).filter(FolderEvent.id == event_id).first()
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")
    return event
