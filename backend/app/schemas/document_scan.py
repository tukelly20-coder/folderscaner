from typing import List, Optional

from pydantic import BaseModel, ConfigDict


class DocumentScanResult(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    a0_folder_path: str
    a0_folder_name: str
    customer_name: Optional[str] = None
    customer_subfolder_name: Optional[str] = None
    salesperson_name: Optional[str] = None
    found: bool = False
    drawing_codes: List[str] = []


class DocumentScanResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    root: str
    total_scanned: int
    results: list[DocumentScanResult]
