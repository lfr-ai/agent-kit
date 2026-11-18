"""OpenTelemetry adapters: extra detection, GenAI spans and log correlation."""

from collections.abc import Generator
from contextlib import contextmanager
from importlib.util import find_spec
import logging

from opentelemetry import trace
from opentelemetry.trace import Span, SpanKind, Status, StatusCode, Tracer

from platform_kit_runtime.core.ai import AIError, TextResult
from platform_kit_runtime.core.correlation import current_request_id
from platform_kit_runtime.core.telemetry import InferenceSpan

_INSTRUMENTATION_SCOPE = "platform_kit_runtime"
_EXTRA_MODULES = ("opentelemetry.sdk.trace", "opentelemetry.exporter.otlp.proto.http")
_OPERATION = "chat"
# Gateway name when the model selector carries no provider prefix.
_UNPREFIXED_PROVIDER = "litellm"
# LiteLLM prefixes mapped to GenAI semantic-convention well-known provider names;
# other prefixes are reported unchanged, as the convention permits.
_PROVIDERS = {
    "anthropic": "anthropic",
    "azure": "azure.ai.openai",
    "azure_ai": "azure.ai.inference",
    "bedrock": "aws.bedrock",
    "cohere": "cohere",
    "deepseek": "deepseek",
    "gemini": "gcp.gemini",
    "groq": "groq",
    "mistral": "mistral_ai",
    "openai": "openai",
    "perplexity": "perplexity",
    "vertex_ai": "gcp.vertex_ai",
    "watsonx": "ibm.watsonx.ai",
    "xai": "x_ai",
}


def tracing_available() -> bool:
    """Return whether the ``telemetry`` extra's SDK and OTLP exporter import."""
    try:
        return all(find_spec(name) is not None for name in _EXTRA_MODULES)
    except ModuleNotFoundError:
        return False


class _OpenTelemetrySpan:
    def __init__(self, *, span: Span) -> None:
        """Wrap an active span.

        Args:
            span (Span): Span ended by the owning tracer context.
        """
        self._span = span

    def succeeded(self, *, result: TextResult) -> None:
        """Record usage and the finish reason, never the generated text."""
        self._span.set_attributes(
            {
                "gen_ai.usage.input_tokens": result.usage.input_tokens,
                "gen_ai.usage.output_tokens": result.usage.output_tokens,
                "gen_ai.response.finish_reasons": (result.finish_reason.value,),
            }
        )

    def failed(self, *, error: AIError) -> None:
        """Mark the span failed with the stable error code as ``error.type``."""
        self._span.set_attribute("error.type", error.code)
        self._span.set_status(Status(StatusCode.ERROR))


class OpenTelemetryInferenceTracer:
    """GenAI client spans through the OpenTelemetry API, without content.

    Spans are recorded only when the process has an SDK tracer provider; the
    API alone makes every call a no-op. Prompts and completions are never set.
    """

    def __init__(self, *, tracer: Tracer | None = None) -> None:
        """Bind an explicit tracer, or the global provider's tracer.

        Args:
            tracer (Tracer | None): Tracer to use; ``None`` resolves the global
                provider lazily, so later SDK configuration still applies.
        """
        self._tracer = tracer or trace.get_tracer(_INSTRUMENTATION_SCOPE)

    @contextmanager
    def span(self, *, model: str, max_output_tokens: int) -> Generator[InferenceSpan]:
        """Open a ``chat {model}`` client span with GenAI request attributes.

        Args:
            model (str): LiteLLM selector; its prefix selects the provider name.
            max_output_tokens (int): Requested output token cap.

        Yields:
            InferenceSpan: Recorder for the call's usage or failure type.
        """
        prefix, separator, name = model.partition("/")
        provider = _PROVIDERS.get(prefix, prefix) if separator else _UNPREFIXED_PROVIDER
        request_model = name if separator else model
        with self._tracer.start_as_current_span(
            f"{_OPERATION} {request_model}",
            kind=SpanKind.CLIENT,
            attributes={
                "gen_ai.operation.name": _OPERATION,
                "gen_ai.provider.name": provider,
                "gen_ai.request.model": request_model,
                "gen_ai.request.max_tokens": max_output_tokens,
            },
            record_exception=False,
            set_status_on_exception=False,
        ) as span:
            yield _OpenTelemetrySpan(span=span)


class RequestContextFilter(logging.Filter):
    """Add ``request_id`` and ``trace_id`` to records; attach it to handlers.

    Values already supplied through ``extra`` are kept. Either is ``None``
    outside a request or without an active, valid OpenTelemetry span.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        """Annotate ``record`` in place with request and trace ids; always ``True``."""
        context = trace.get_current_span().get_span_context()
        fields = vars(record)
        fields.setdefault("request_id", current_request_id())
        fields.setdefault(
            "trace_id",
            trace.format_trace_id(context.trace_id) if context.is_valid else None,
        )
        return True
