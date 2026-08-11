"""
FastAPI application entry point for the Folder Sync System.

Run:  uvicorn app.main:app --reload
"""

import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.api.folders import router as folders_router
from app.api.events import router as events_router
from app.api.scanner import router as scanner_router
from app.api.websocket import router as websocket_router
from app.api.documents import router as documents_router
from app.services.sync_service import lifespan

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="Folder Sync System",
    description="Two-way folder sync: Local PC -> SMB -> Scanner -> Database -> Web",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # TODO: restrict in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(folders_router)
app.include_router(events_router)
app.include_router(scanner_router)
app.include_router(websocket_router)
app.include_router(documents_router)


@app.get("/health")
def health_check():
    return {"status": "healthy", "service": "folder-sync-backend"}


@app.get("/")
def root():
    return {
        "service": "Folder Sync System",
        "version": "1.0.0",
        "docs": "/docs",
        "endpoints": {
            "folders": "/api/folders",
            "events": "/api/folder-events",
            "scanner": "/api/scanner",
            "websocket": "/ws/folders",
        },
    }
