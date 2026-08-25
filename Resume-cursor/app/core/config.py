from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT_DIR = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=ROOT_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    database_url: str = "postgresql+asyncpg://resume:resume@127.0.0.1:5432/resume"
    deepseek_api_key: str = ""
    deepseek_base_url: str = "https://api.deepseek.com"
    deepseek_model: str = "deepseek-v4-flash"
    jwt_secret: str = "change-me"
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 60 * 24 * 7
    platform_admin_email: str = "admin@example.com"
    platform_admin_password: str = "ChangeMe123"
    upload_dir: str = "uploads"
    max_upload_bytes: int = 8 * 1024 * 1024
    invite_expire_days: int = 7

    @field_validator("deepseek_api_key", "deepseek_base_url", "deepseek_model", mode="before")
    @classmethod
    def strip_secret(cls, value: object) -> object:
        if isinstance(value, str):
            return value.strip().strip("\"'")
        return value


settings = Settings()
