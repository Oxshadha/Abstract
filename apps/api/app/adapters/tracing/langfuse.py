"""Langfuse tracing with the official Python SDK v5 (spec 005 AC14, D37).

Follows Langfuse's trace best practices: one trace per unit of work with a verb-first name,
nested spans for pipeline steps, `generation`/`embedding` observations with model, token usage
and cost, user and session IDs, tags, environment and release.

Privacy (D76): input and output are never set; only metadata leaves the process. Langfuse runs
on its own isolated OpenTelemetry provider and exports only spans created through this adapter,
so auto-instrumented libraries (for example a model SDK) can never export prompt text through it.
Tracing failures are logged and never affect the observed work.
"""

from collections.abc import Iterator
from contextlib import ExitStack, contextmanager
from typing import Any

from opentelemetry.sdk.trace import ReadableSpan, TracerProvider
from opentelemetry.sdk.trace.export import SpanExporter

from app.core.logging import get_logger
from app.ports.tracing import Level, Observation, ObservationType

log = get_logger(__name__)
LANGFUSE_SCOPE = "langfuse-sdk"


def only_langfuse_spans(span: ReadableSpan) -> bool:
    scope = span.instrumentation_scope
    return scope is not None and scope.name.startswith(LANGFUSE_SCOPE)


class _Observation:
    def __init__(self, inner: Any) -> None:
        self._inner = inner

    def update(
        self,
        *,
        model: str | None = None,
        usage: dict[str, int] | None = None,
        cost_usd: float | None = None,
        level: Level | None = None,
        status_message: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        fields: dict[str, Any] = {}
        if model is not None:
            fields["model"] = model
        if usage is not None:
            fields["usage_details"] = usage
        if cost_usd is not None:
            fields["cost_details"] = {"total": cost_usd}
        if level is not None:
            fields["level"] = level
        if status_message is not None:
            fields["status_message"] = status_message
        if metadata is not None:
            fields["metadata"] = metadata
        try:
            self._inner.update(**fields)
        except Exception as exc:
            log.warning("langfuse_update_failed", error=type(exc).__name__)


class _Null:
    def update(self, **_: Any) -> None:
        return None


class LangfuseTracer:
    def __init__(
        self,
        public_key: str,
        secret_key: str,
        base_url: str,
        *,
        environment: str,
        release: str | None = None,
        span_exporter: SpanExporter | None = None,
    ) -> None:
        from langfuse import Langfuse

        self._client = Langfuse(
            public_key=public_key,
            secret_key=secret_key,
            base_url=base_url,
            environment=environment,
            release=release,
            tracer_provider=TracerProvider(),  # isolated: never the global provider
            should_export_span=only_langfuse_spans,
            span_exporter=span_exporter,
        )

    @contextmanager
    def _guard(self, enter: Any) -> Iterator[Observation]:
        """Enter a Langfuse context; if that fails, run the work untraced."""
        with ExitStack() as stack:
            try:
                inner = stack.enter_context(enter())
            except Exception as exc:
                log.warning("langfuse_observe_failed", error=type(exc).__name__)
                yield _Null()
                return
            yield _Observation(inner)

    @contextmanager
    def trace(
        self,
        name: str,
        *,
        user_id: str | None = None,
        session_id: str | None = None,
        tags: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> Iterator[Observation]:
        from langfuse import propagate_attributes

        @contextmanager
        def enter() -> Iterator[Any]:
            with (
                self._client.start_as_current_observation(
                    name=name, as_type="span", metadata=metadata
                ) as root,
                propagate_attributes(
                    user_id=user_id, session_id=session_id, tags=tags, trace_name=name
                ),
            ):
                yield root

        with self._guard(enter) as observation:
            yield observation

    @contextmanager
    def observe(
        self,
        name: str,
        *,
        as_type: ObservationType = "span",
        model: str | None = None,
        model_parameters: dict[str, Any] | None = None,
        version: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> Iterator[Observation]:
        def enter() -> Any:
            client: Any = self._client  # the SDK's per-type overloads are too many for mypy
            return client.start_as_current_observation(
                name=name,
                as_type=as_type,
                model=model,
                model_parameters=model_parameters,
                version=version,
                metadata=metadata,
            )

        with self._guard(enter) as observation:
            yield observation

    def flush(self) -> None:
        try:
            self._client.flush()
        except Exception as exc:
            log.warning("langfuse_flush_failed", error=type(exc).__name__)

    def auth_check(self) -> bool:
        return bool(self._client.auth_check())
