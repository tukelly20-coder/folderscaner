from typing import Optional
import os
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def normalize_smb_root(value: str | None) -> str:
    """Normalize a scan root without breaking drive roots like D:\\."""
    raw = (value or "").strip()
    if not raw:
        return raw

    drive, tail = os.path.splitdrive(raw)
    if drive and tail in ("", "\\", "/"):
        return drive + os.sep

    return raw.rstrip("/\\")


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(PROJECT_ROOT / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    DATABASE_URL: str = "sqlite:///./folders.db"
    SMB_ROOT: str = ""
    SMB_EXCLUDES: str = "sample_folder,test_folder,_deleted"
    SCAN_INTERVAL: int = 10
    SCANNER_MAX_WORKERS: int = 2
    SCANNER_RECONCILE_INTERVAL: int = 10
    SCANNER_FULL_REPAIR_INTERVAL: int = 21600
    SERVER_HOST: str = "127.0.0.1"
    SERVER_PORT: int = 18001
    SMB_USERNAME: Optional[str] = None
    SMB_PASSWORD: Optional[str] = None
    SMB_DOMAIN: Optional[str] = None
    EXPORT_DIR: str = "./exports"


settings = Settings()

if settings.DATABASE_URL.startswith("sqlite:///./"):
    db_name = settings.DATABASE_URL.removeprefix("sqlite:///./")
    settings.DATABASE_URL = f"sqlite:///{(PROJECT_ROOT / db_name).as_posix()}"
