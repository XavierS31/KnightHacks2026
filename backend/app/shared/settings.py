from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=(".env", ".env.local"), extra="ignore")
    app_mode: Literal["fixture", "live"] = "fixture"
    hf_token: SecretStr = SecretStr("")
    hf_model_id: str = ""
    hf_provider: str = ""
    hf_coding_model_id: str = ""
    hf_max_inflight: int = Field(default=4, ge=1, le=32)
    hf_request_timeout_seconds: float = Field(default=20, gt=0)
    experiment_budget_limit: float = Field(default=0, ge=0)
    database_url: SecretStr = SecretStr("")
    github_token: SecretStr = SecretStr("")
    search_api_key: SecretStr = SecretStr("")
    artifact_root: Path = Path("artifacts")
    browser_concurrency: int = Field(default=4, ge=1, le=8)
    population_target: int = Field(default=500, ge=1)
    featured_personas: int = Field(default=10, ge=1, le=10)
    viewer_token: SecretStr = SecretStr("")


def get_settings() -> Settings:
    return Settings()
