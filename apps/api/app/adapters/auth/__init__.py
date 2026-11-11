from app.adapters.auth.clerk import ClerkAuthProvider, http_jwks_fetcher
from app.adapters.auth.dev import DevAuthProvider
from app.core.config import Settings
from app.ports.auth import AuthProvider


def build_auth_provider(settings: Settings) -> AuthProvider:
    if settings.resolved_auth_provider == "dev":
        return DevAuthProvider(settings.dev_auth_secret.get_secret_value())
    assert settings.clerk_issuer  # enforced by Settings validation
    issuer = settings.clerk_issuer.rstrip("/")
    return ClerkAuthProvider(
        issuer=issuer,
        authorized_parties=settings.clerk_authorized_parties or settings.cors_origins,
        fetch_jwks=http_jwks_fetcher(f"{issuer}/.well-known/jwks.json"),
    )
