from app.adapters.llm.fake import FakeLLMGateway
from app.core.config import Settings
from app.ports.llm import LLMGateway


def build_llm_gateway(settings: Settings) -> LLMGateway:
    if settings.llm_provider == "fake":
        return FakeLLMGateway()
    # OpenRouter adapter lands with spec 000 (benchmark); Vertex + registry with spec 005.
    raise NotImplementedError(f"LLM provider '{settings.llm_provider}' is not implemented yet")
