"""Typed application settings. The only place environment variables are read (spec 001 AC7)."""

from functools import lru_cache
from typing import Literal, Self

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

Environment = Literal["development", "test", "production"]
LLMProviderName = Literal["fake", "openrouter", "vertex"]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        # Repo-root .env when running from apps/api; a local .env also works.
        env_file=("../../.env", ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    env: Environment = "development"
    log_level: str = "INFO"
    cors_origins: list[str] = Field(default_factory=lambda: ["http://localhost:5173"])

    # Datastores
    database_url: str
    redis_url: str

    # Object storage (S3-compatible)
    s3_bucket: str
    s3_endpoint_url: str | None = None  # None = real AWS S3
    s3_region: str = "us-east-1"
    s3_access_key_id: SecretStr | None = None
    s3_secret_access_key: SecretStr | None = None

    # LLM providers (D24). Fake is the default so nothing calls a paid API by accident.
    llm_provider: LLMProviderName = "fake"
    openrouter_api_key: SecretStr | None = None
    google_application_credentials: str | None = None
    gcp_project_id: str | None = None
    gcp_location: str = "us-central1"

    @model_validator(mode="after")
    def _provider_credentials(self) -> Self:
        if self.llm_provider == "openrouter" and not self.openrouter_api_key:
            raise ValueError("LLM_PROVIDER=openrouter requires OPENROUTER_API_KEY")
        if self.llm_provider == "vertex" and not (
            self.google_application_credentials and self.gcp_project_id
        ):
            raise ValueError(
                "LLM_PROVIDER=vertex requires GOOGLE_APPLICATION_CREDENTIALS and GCP_PROJECT_ID"
            )
        return self

    @property
    def is_production(self) -> bool:
        return self.env == "production"


@lru_cache
def get_settings() -> Settings:
    return Settings()  # required fields come from the environment
