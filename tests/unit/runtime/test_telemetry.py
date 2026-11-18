import asyncio
from collections.abc import Iterator
import logging
import subprocess
import sys
from types import ModuleType
from typing import Final

from fastapi import FastAPI
from fastapi.telemetry import _runtime as fastapi_telemetry_runtime
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import (
    InMemorySpanExporter,
)
from opentelemetry.trace import SpanKind, StatusCode
from opentelemetry.util._once import Once
import pytest
from starlette.types import Message

from platform_kit_runtime import RuntimeConfig, create_app
from platform_kit_runtime.ai import (
    AIFinishReason,
    AIMessage,
    AIRole,
    AIUnavailableError,
    AIUsage,
    TextGenerationConfig,
    TextRequest,
    TextResult,
)
from platform_kit_runtime.core.correlation import bound_request_id
from platform_kit_runtime.infrastructure import telemetry as telemetry_adapter
from platform_kit_runtime.infrastructure.litellm import (
    LiteLLMTextGenerator,
    load_litellm,
)
from platform_kit_runtime.middleware import RequestContextFilter
from platform_kit_runtime.telemetry import (
    OpenTelemetryInferenceTracer,
    SilentInferenceTracer,
)

pytestmark = pytest.mark.unit

SENSITIVE_VALUE: Final[str] = "synthetic-prompt-completion-secret"
_OTEL_ENDPOINTS = (
    "OTEL_EXPORTER_OTLP_ENDPOINT",
    "OTEL_EXPORTER_OTLP_TRACES_ENDPOINT",
    "OTEL_SDK_DISABLED",
    "OTEL_TRACES_EXPORTER",
    "OTEL_EXPORTER_OTLP_PROTOCOL",
    "OTEL_EXPORTER_OTLP_TRACES_PROTOCOL",
)


class FakeConnectionError(Exception):
    pass


class FakeAuthenticationError(Exception):
    pass


class FakeBadRequestError(Exception):
    pass


class FakeResponse:
    def __init__(self, *, payload: object) -> None:
        self.payload = payload

    def model_dump(self) -> object:
        return self.payload


@pytest.fixture
def exporter() -> InMemorySpanExporter:
    return InMemorySpanExporter()


@pytest.fixture
def provider(exporter: InMemorySpanExporter) -> Iterator[TracerProvider]:
    provider = TracerProvider(shutdown_on_exit=False)
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    yield provider
    provider.shutdown()


@pytest.fixture
def isolated_otel(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in _OTEL_ENDPOINTS:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(trace, "_TRACER_PROVIDER_SET_ONCE", Once())
    monkeypatch.setattr(trace, "_TRACER_PROVIDER", None)
    monkeypatch.setattr(fastapi_telemetry_runtime, "_configured", [])
    monkeypatch.setattr(fastapi_telemetry_runtime, "_owned", [])


@pytest.fixture
def sdk(monkeypatch: pytest.MonkeyPatch) -> ModuleType:
    module = ModuleType("litellm")
    for name in ("AuthenticationError", "PermissionDeniedError"):
        setattr(module, name, FakeAuthenticationError)
    for name in (
        "BadRequestError",
        "NotFoundError",
        "UnprocessableEntityError",
        "UnsupportedParamsError",
    ):
        setattr(module, name, FakeBadRequestError)
    for name in (
        "Timeout",
        "APIConnectionError",
        "ServiceUnavailableError",
        "InternalServerError",
        "RateLimitError",
        "APIError",
    ):
        setattr(module, name, FakeConnectionError)
    vars(module)["ModelResponse"] = FakeResponse
    monkeypatch.setitem(sys.modules, "litellm", module)
    return module


def result() -> TextResult:
    return TextResult(
        text=SENSITIVE_VALUE,
        finish_reason=AIFinishReason.LENGTH,
        usage=AIUsage(input_tokens=3, output_tokens=5, total_tokens=8),
    )


def text_request() -> TextRequest:
    return TextRequest(
        messages=(AIMessage(role=AIRole.USER, content=SENSITIVE_VALUE),),
        max_output_tokens=64,
    )


async def completed(**kwargs: object) -> object:
    del kwargs
    return FakeResponse(
        payload={
            "choices": [
                {
                    "message": {"role": "assistant", "content": SENSITIVE_VALUE},
                    "finish_reason": "stop",
                }
            ],
            "usage": {"prompt_tokens": 4, "completion_tokens": 6, "total_tokens": 10},
        }
    )


def test_tracing_is_available_with_the_extra() -> None:
    assert telemetry_adapter.tracing_available()


def test_tracing_is_unavailable_when_a_module_is_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(telemetry_adapter, "find_spec", lambda _name: None)

    assert not telemetry_adapter.tracing_available()


def test_tracing_is_unavailable_when_a_parent_package_is_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def missing(name: str) -> None:
        raise ModuleNotFoundError(name)

    monkeypatch.setattr(telemetry_adapter, "find_spec", missing)

    assert not telemetry_adapter.tracing_available()


def test_successful_inference_span_has_genai_attributes_without_content(
    provider: TracerProvider, exporter: InMemorySpanExporter
) -> None:
    tracer = OpenTelemetryInferenceTracer(tracer=provider.get_tracer("test"))

    with tracer.span(model="azure/chat-deployment", max_output_tokens=64) as span:
        span.succeeded(result=result())

    [finished] = exporter.get_finished_spans()
    assert finished.name == "chat chat-deployment"
    assert finished.kind is SpanKind.CLIENT
    assert dict(finished.attributes or {}) == {
        "gen_ai.operation.name": "chat",
        "gen_ai.provider.name": "azure.ai.openai",
        "gen_ai.request.model": "chat-deployment",
        "gen_ai.request.max_tokens": 64,
        "gen_ai.usage.input_tokens": 3,
        "gen_ai.usage.output_tokens": 5,
        "gen_ai.response.finish_reasons": ("length",),
    }
    assert finished.status.status_code is StatusCode.UNSET
    assert SENSITIVE_VALUE not in repr(finished.to_json())


@pytest.mark.parametrize(
    ("model", "provider_name", "request_model"),
    [
        ("openai/gpt-4o-mini", "openai", "gpt-4o-mini"),
        ("bedrock/anthropic.claude/v1", "aws.bedrock", "anthropic.claude/v1"),
        ("azure_ai/phi", "azure.ai.inference", "phi"),
        ("ollama/llama3", "ollama", "llama3"),
        ("gpt-4o", "litellm", "gpt-4o"),
    ],
)
def test_provider_names_follow_genai_conventions(
    provider: TracerProvider,
    exporter: InMemorySpanExporter,
    model: str,
    provider_name: str,
    request_model: str,
) -> None:
    tracer = OpenTelemetryInferenceTracer(tracer=provider.get_tracer("test"))

    with tracer.span(model=model, max_output_tokens=1):
        pass

    [finished] = exporter.get_finished_spans()
    attributes = finished.attributes or {}
    assert attributes["gen_ai.provider.name"] == provider_name
    assert attributes["gen_ai.request.model"] == request_model


def test_failed_inference_span_records_only_the_error_code(
    provider: TracerProvider, exporter: InMemorySpanExporter
) -> None:
    tracer = OpenTelemetryInferenceTracer(tracer=provider.get_tracer("test"))

    with tracer.span(model="openai/test", max_output_tokens=8) as span:
        span.failed(error=AIUnavailableError())

    [finished] = exporter.get_finished_spans()
    assert (finished.attributes or {})["error.type"] == "ai_unavailable"
    assert finished.status.status_code is StatusCode.ERROR
    assert finished.status.description is None
    assert not finished.events


def test_exceptions_escaping_a_span_are_not_recorded(
    provider: TracerProvider, exporter: InMemorySpanExporter
) -> None:
    tracer = OpenTelemetryInferenceTracer(tracer=provider.get_tracer("test"))

    with (
        pytest.raises(asyncio.CancelledError),
        tracer.span(model="openai/test", max_output_tokens=8),
    ):
        raise asyncio.CancelledError(SENSITIVE_VALUE)

    [finished] = exporter.get_finished_spans()
    assert not finished.events
    assert finished.status.status_code is StatusCode.UNSET


def test_default_tracer_uses_the_global_provider_lazily(
    isolated_otel: None, provider: TracerProvider, exporter: InMemorySpanExporter
) -> None:
    tracer = OpenTelemetryInferenceTracer()
    trace.set_tracer_provider(provider)

    with tracer.span(model="openai/test", max_output_tokens=8):
        pass

    assert len(exporter.get_finished_spans()) == 1


def test_silent_tracer_ignores_every_outcome() -> None:
    with SilentInferenceTracer().span(model="openai/test", max_output_tokens=1) as span:
        assert span.succeeded(result=result()) is None
        assert span.failed(error=AIUnavailableError()) is None


def test_litellm_calls_are_wrapped_in_spans(
    sdk: ModuleType, provider: TracerProvider, exporter: InMemorySpanExporter
) -> None:
    vars(sdk)["acompletion"] = completed
    generator = LiteLLMTextGenerator(
        config=TextGenerationConfig(model="anthropic/test", api_key=SENSITIVE_VALUE),
        sdk=load_litellm(),
        tracer=OpenTelemetryInferenceTracer(tracer=provider.get_tracer("test")),
    )

    generated = asyncio.run(generator.generate(request=text_request()))

    assert generated.text == SENSITIVE_VALUE
    [finished] = exporter.get_finished_spans()
    attributes = finished.attributes or {}
    assert attributes["gen_ai.provider.name"] == "anthropic"
    assert attributes["gen_ai.usage.input_tokens"] == 4
    assert attributes["gen_ai.usage.output_tokens"] == 6
    assert attributes["gen_ai.response.finish_reasons"] == ("stop",)
    assert SENSITIVE_VALUE not in repr(finished.to_json())


def test_global_tracer_records_litellm_calls_once_an_sdk_provider_exists(
    isolated_otel: None,
    sdk: ModuleType,
    provider: TracerProvider,
    exporter: InMemorySpanExporter,
) -> None:
    vars(sdk)["acompletion"] = completed
    generator = LiteLLMTextGenerator(
        config=TextGenerationConfig(model="openai/test", api_key=SENSITIVE_VALUE),
        sdk=load_litellm(),
        tracer=OpenTelemetryInferenceTracer(),
    )
    asyncio.run(generator.generate(request=text_request()))
    assert exporter.get_finished_spans() == ()

    trace.set_tracer_provider(provider)
    asyncio.run(generator.generate(request=text_request()))

    [finished] = exporter.get_finished_spans()
    assert finished.name == "chat test"
    assert finished.kind is SpanKind.CLIENT


def test_litellm_failures_mark_spans_without_changing_errors(
    sdk: ModuleType, provider: TracerProvider, exporter: InMemorySpanExporter
) -> None:
    async def acompletion(**kwargs: object) -> object:
        raise FakeConnectionError(SENSITIVE_VALUE)

    vars(sdk)["acompletion"] = acompletion
    generator = LiteLLMTextGenerator(
        config=TextGenerationConfig(model="openai/test", api_key=SENSITIVE_VALUE),
        sdk=load_litellm(),
        tracer=OpenTelemetryInferenceTracer(tracer=provider.get_tracer("test")),
    )

    with pytest.raises(AIUnavailableError) as caught:
        asyncio.run(generator.generate(request=text_request()))

    assert caught.value.__context__ is None
    assert caught.value.__cause__ is not None
    assert caught.value.__cause__.__context__ is None
    [finished] = exporter.get_finished_spans()
    assert (finished.attributes or {})["error.type"] == "ai_unavailable"
    assert finished.status.status_code is StatusCode.ERROR
    assert SENSITIVE_VALUE not in repr(finished.to_json())


def make_record() -> logging.LogRecord:
    return logging.LogRecord("test", logging.INFO, __file__, 1, "message", None, None)


def test_log_filter_adds_empty_fields_outside_requests() -> None:
    record = make_record()

    assert RequestContextFilter().filter(record)
    assert vars(record)["request_id"] is None
    assert vars(record)["trace_id"] is None


def test_log_filter_adds_request_and_trace_ids(provider: TracerProvider) -> None:
    record = make_record()
    tracer = provider.get_tracer("test")

    with (
        bound_request_id(request_id="filter-1"),
        tracer.start_as_current_span("request") as span,
    ):
        assert RequestContextFilter().filter(record)
        expected = f"{span.get_span_context().trace_id:032x}"

    assert vars(record)["request_id"] == "filter-1"
    assert vars(record)["trace_id"] == expected


def test_log_filter_keeps_explicit_values() -> None:
    record = make_record()
    vars(record).update(request_id="explicit", trace_id="explicit-trace")

    with bound_request_id(request_id="bound"):
        RequestContextFilter().filter(record)

    assert vars(record)["request_id"] == "explicit"
    assert vars(record)["trace_id"] == "explicit-trace"


def run_lifespan(app: FastAPI) -> None:
    async def scenario() -> None:
        messages: list[Message] = [
            {"type": "lifespan.startup"},
            {"type": "lifespan.shutdown"},
        ]
        sent: list[Message] = []

        async def receive() -> Message:
            return messages.pop(0)

        async def send(message: Message) -> None:
            sent.append(message)

        await app({"type": "lifespan", "asgi": {"version": "3.0"}}, receive, send)
        assert [message["type"] for message in sent] == [
            "lifespan.startup.complete",
            "lifespan.shutdown.complete",
        ]

    asyncio.run(scenario())


def test_tracing_without_the_extra_is_disabled_with_one_warning(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    monkeypatch.setattr(telemetry_adapter, "find_spec", lambda _name: None)

    create_app(config=RuntimeConfig(tracing=True), probes=())

    [record] = caplog.records
    assert record.levelno == logging.WARNING
    assert vars(record)["event"] == "runtime.telemetry_unavailable"


def test_tracing_off_by_default_logs_nothing(caplog: pytest.LogCaptureFixture) -> None:
    create_app(config=RuntimeConfig(), probes=())

    assert not caplog.records


def test_tracing_without_otel_environment_configures_nothing(
    isolated_otel: None,
) -> None:
    run_lifespan(create_app(config=RuntimeConfig(tracing=True), probes=()))

    assert isinstance(trace.get_tracer_provider(), trace.ProxyTracerProvider)


def test_tracing_exports_from_standard_otel_environment(
    isolated_otel: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://127.0.0.1:4318")

    run_lifespan(create_app(config=RuntimeConfig(tracing=True), probes=()))

    configured = trace.get_tracer_provider()
    assert isinstance(configured, TracerProvider)
    configured.shutdown()


def test_disabled_tracing_never_reads_otel_environment(
    isolated_otel: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://127.0.0.1:4318")

    run_lifespan(create_app(config=RuntimeConfig(), probes=()))

    assert isinstance(trace.get_tracer_provider(), trace.ProxyTracerProvider)


def test_public_facades_import_no_optional_sdks() -> None:
    script = """
import importlib.abc
import logging
import sys

class Missing(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname.split('.')[0] == 'redis' or fullname.startswith(
            ('opentelemetry.sdk', 'opentelemetry.exporter')
        ):
            raise ModuleNotFoundError(fullname)
        return None

sys.meta_path.insert(0, Missing())
records = []
handler = logging.Handler()
handler.emit = records.append
logging.getLogger('platform_kit_runtime').addHandler(handler)
import platform_kit_runtime.middleware as middleware
import platform_kit_runtime.telemetry
from platform_kit_runtime import RuntimeConfig, create_app
policy = middleware.RateLimitPolicy(limit=1, window_seconds=1)
create_app(config=RuntimeConfig(rate_limit=policy, tracing=True), probes=())
assert [vars(record)['event'] for record in records] == [
    'runtime.telemetry_unavailable'
]
try:
    middleware.RedisRateLimitStore(client=object())
except ImportError:
    pass
else:
    raise AssertionError('redis store requires the extra')
"""
    completed = subprocess.run(  # noqa: S603 - fixed offline interpreter probe
        [sys.executable, "-I", "-c", script],
        check=False,
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert completed.returncode == 0, completed.stderr
