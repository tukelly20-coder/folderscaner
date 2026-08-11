from typing import Optional

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    DATABASE_URL: str = "sqlite:///./folders.db"
    SMB_ROOT: str
    SMB_EXCLUDES: str = "sample_folder,test_folder,_deleted"
    SCAN_INTERVAL: int = 10
    SERVER_HOST: str = "0.0.0.0"
    SERVER_PORT: int = 8000
    SMB_USERNAME: Optional[str] = None
    SMB_PASSWORD: Optional[str] = None
    SMB_DOMAIN: Optional[str] = None
    EXPORT_DIR: str = "./exports"


settings = Settings()
