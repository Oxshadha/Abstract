"""Typed application settings. The only place environment variables are read (spec 001 AC7)."""

import secrets
from functools import lru_cache
from typing import Literal, Self

from pydantic import AliasChoices, Field, SecretStr, model_validator
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
    # What browsers use for pre-signed links when it differs from the internal endpoint
    # (local: the API reaches http://s3:8333, the browser http://localhost:8333).
    s3_public_endpoint_url: str | None = None
    s3_region: str = "us-east-1"
    s3_access_key_id: SecretStr | None = None
    s3_secret_access_key: SecretStr | None = None

    # LLM providers (D24). Fake is the default so nothing calls a paid API by accident.
    llm_provider: LLMProviderName = "fake"
    openrouter_api_key: SecretStr | None = None
    google_application_credentials: str | None = None
    gcp_project_id: str | None = None
    gcp_location: str = "global"  # where the D69 Gemini models were benchmarked

    # Error monitoring (D37, D76). The DSN is public by design; off when unset.
    sentry_dsn: str | None = None
    sentry_environment: str | None = None

    # Baseline rate limits per minute by route group (spec 002 AC15; plans in spec 012).
    rate_limits: dict[str, int] = Field(
        default_factory=lambda: {"auth": 30, "read": 300, "write": 60, "upload": 20, "search": 120}
    )

    # Upload limits (spec 004, D57). Plan-specific limits move to entitlements in spec 012.
    upload_max_bytes: int = 50 * 1024 * 1024
    upload_url_ttl_seconds: int = 600
    upload_max_pages: int = 300

    # Malware scanning (D77, spec 004 AC16). Unset: fake in development/test; production must
    # choose a scanner or opt out explicitly with "disabled-with-sanitization".
    malware_scan: Literal["fake", "clamav", "guardduty", "disabled-with-sanitization"] | None = None
    clamav_host: str = "clamav"
    clamav_port: int = 3310

    # Tracing (spec 005 AC14, D37): metadata only; off unless both keys are set (EU region).
    langfuse_public_key: str | None = None
    langfuse_secret_key: SecretStr | None = None
    # LANGFUSE_BASE_URL is the SDK's current name; LANGFUSE_HOST is accepted too.
    langfuse_base_url: str = Field(
        default="https://cloud.langfuse.com",
        validation_alias=AliasChoices("langfuse_base_url", "langfuse_host"),
    )
    app_release: str | None = None  # e.g. the git SHA; tags traces with the deployed version

    # LLM spend control (spec 005 AC8; owner-approved defaults until plans exist in spec 012).
    llm_daily_cap_usd: float = Field(default=5.0, ge=0)
    llm_user_daily_cap_usd: float = Field(default=0.5, ge=0)
    llm_max_concurrency_per_provider: int = Field(default=8, ge=1, le=256)

    # Progress event stream (spec 004 AC12).
    sse_poll_seconds: float = 1.0
    sse_heartbeat_seconds: float = 15.0
    sse_max_seconds: float = 600.0  # the client reconnects with Last-Event-ID

    # Authentication (spec 002, D70). "auto": Clerk when configured, otherwise the dev
    # adapter in development/test. Production must use Clerk.
    auth_provider: Literal["auto", "clerk", "dev"] = "auto"
    clerk_issuer: str | None = None  # e.g. https://<instance>.clerk.accounts.dev
    clerk_authorized_parties: list[str] = Field(default_factory=list)
    clerk_webhook_secret: SecretStr | None = None  # "whsec_..." from the Clerk dashboard
    dev_auth_secret: SecretStr = Field(default_factory=lambda: SecretStr(secrets.token_urlsafe(32)))

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
        if self.llm_provider == "fake" and self.env == "production":
            raise ValueError("LLM_PROVIDER=fake is for development and tests only")
        if self.resolved_auth_provider == "dev" and self.env == "production":
            raise ValueError("The development auth adapter is not allowed when ENV=production")
        if self.malware_scan == "fake" and self.env == "production":
            raise ValueError("MALWARE_SCAN=fake is for development only")
        if self.malware_scan is None and self.env == "production":
            raise ValueError(
                "Production needs a malware scanner (MALWARE_SCAN=clamav or guardduty) or the "
                "explicit opt-out MALWARE_SCAN=disabled-with-sanitization (D77)"
            )
        if self.resolved_auth_provider == "clerk" and not self.clerk_issuer:
            raise ValueError("Clerk auth requires CLERK_ISSUER")
        return self

    @property
    def resolved_auth_provider(self) -> Literal["clerk", "dev"]:
        if self.auth_provider != "auto":
            return self.auth_provider
        if self.clerk_issuer or self.env == "production":
            return "clerk"
        return "dev"

    @property
    def resolved_malware_scan(self) -> str:
        return self.malware_scan or "fake"  # unset is only allowed outside production

    @property
    def scanning_enabled(self) -> bool:
        return self.resolved_malware_scan != "disabled-with-sanitization"

    @property
    def is_production(self) -> bool:
        return self.env == "production"


@lru_cache
def get_settings() -> Settings:
    return Settings()  # required fields come from the environment
