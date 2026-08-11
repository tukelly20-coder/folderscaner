"""
REST API endpoints for document folder scanning.
"""

from fastapi import APIRouter, Query

from app.config import settings
from app.schemas.document_scan import DocumentScanResponse
from app.services.document_scanner import DocumentScanner

router = APIRouter(prefix="/api/documents", tags=["documents"])


@router.post("/scan", response_model=DocumentScanResponse)
def scan_documents(
    root: str | None = Query(default=None),
):
    """POST /api/documents/scan — Scan a root path for A0 folders and customer names."""
    scan_root = root or settings.SMB_ROOT
    scanner = DocumentScanner(smb_root=scan_root)
    results = scanner.scan()
    return DocumentScanResponse(
        root=scan_root,
        total_scanned=len(results),
        results=results,
    )
