import pytest
from pydantic import ValidationError

from app.core.config import Settings
from tests.conftest import make_settings


def test_AC7_missing_required_setting_fails_fast(monkeypatch: pytest.MonkeyPatch) -> None:
    for var in ("DATABASE_URL", "REDIS_URL", "S3_BUCKET"):
        monkeypatch.delenv(var, raising=False)
    with pytest.raises(ValidationError) as info:
        Settings(_env_file=None)
    assert "database_url" in str(info.value)


def test_AC7_valid_settings_load_with_safe_defaults() -> None:
    settings = make_settings()
    assert settings.llm_provider == "fake"
    assert settings.is_production is False


def test_AC7_openrouter_requires_key() -> None:
    with pytest.raises(ValidationError, match="OPENROUTER_API_KEY"):
        make_settings(llm_provider="openrouter")


def test_AC7_vertex_requires_credentials() -> None:
    with pytest.raises(ValidationError, match="GOOGLE_APPLICATION_CREDENTIALS"):
        make_settings(llm_provider="vertex")
