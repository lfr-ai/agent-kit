# Telemetry

Opt-in distributed tracing through FastAPI's native OpenTelemetry support,
plus content-free GenAI spans around LiteLLM calls. Configuration comes from the
standard `OTEL_*` environment variables; the runtime adds no settings of its
own beyond the on/off switch.

## Install and enable

Install `platform-kit-runtime[telemetry]` and turn tracing on:

```python
from platform_kit_runtime import RuntimeConfig, create_app

app = create_app(config=RuntimeConfig(tracing=True), probes=())
```

| Situation | Result |
| --- | --- |
| `tracing=False` (the default) | No server spans, even if another component installed a tracer provider |
| `tracing=True` without the extra | No spans; one `runtime.telemetry_unavailable` warning when the app is created |
| `tracing=True` with the extra | Server spans for every route except `/health/live` and `/health/ready` |

The base install never imports the OpenTelemetry SDK or an exporter. Metrics
and exception log records are not exported. An inbound W3C `traceparent` header
is honored, so the server span joins the caller's trace.

## Configuration from the environment

At ASGI lifespan startup, FastAPI installs a tracer provider with an OTLP
exporter if an endpoint is configured. If the application already installed an
SDK provider, FastAPI adds the exporter to that provider instead. The server
must run the lifespan (the uvicorn default).

| Variable | Purpose |
| --- | --- |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | Base URL; `/v1/traces` is appended. Without an endpoint, nothing is exported |
| `OTEL_EXPORTER_OTLP_TRACES_ENDPOINT` | Full traces URL, used as is |
| `OTEL_EXPORTER_OTLP_HEADERS` | Exporter headers such as `Authorization`; supply the value from a secret store |
| `OTEL_SERVICE_NAME`, `OTEL_RESOURCE_ATTRIBUTES` | Resource identity, for example `deployment.environment.name=prod` |
| `OTEL_TRACES_SAMPLER`, `OTEL_TRACES_SAMPLER_ARG` | Sampling, for example `parentbased_traceidratio` and `0.1` |
| `OTEL_TRACES_EXPORTER=none` | Add no exporter, for applications that configure their own |
| `OTEL_SDK_DISABLED=true` | Turn automatic configuration off |

Only the OTLP `http/protobuf` protocol is configured automatically. With any
other `OTEL_EXPORTER_OTLP_PROTOCOL`, FastAPI logs a warning and exports nothing;
configure that exporter yourself (see the Azure Container Apps section).

Do not also enable the contrib FastAPI instrumentation (`FastAPIInstrumentor`,
`opentelemetry-instrument`, or a distro's FastAPI instrumentation). It replaces
FastAPI's native tracing, so health routes would no longer be excluded.

## What spans contain

Server spans follow the HTTP semantic conventions: method, route template,
status code, and the URL path and query string. FastAPI redacts only some
sensitive query parameters. Request and response bodies, client addresses and
user agents are not recorded.

The Azure starter drops `url.path` and `url.query` before export and keeps the
`http.route` template, so Application Insights receives no raw URLs. The
runtime's automatic OTLP path (above) cannot wrap FastAPI's own span processor
and still exports both attributes. On that path, keep secrets and personal data
out of paths and query strings, or configure your own provider with a filtering
processor. `OTEL_PYTHON_FASTAPI_EXCLUDED_URLS` belongs to the contrib
instrumentation, which this runtime does not use (unverified for native
tracing), and it would only exclude whole URLs, not redact queries.

Traces export only when configured: the runtime does nothing without
`tracing=True` and the extra, and the Azure starter loads the Azure SDKs only
when `APPLICATIONINSIGHTS_CONNECTION_STRING` is set. Console logs reach Log
Analytics through Container Apps log collection; the starter installs only a
trace exporter, so Application Insights receives no log records or metrics.
`RequestContextFilter` adds the current `trace_id` to log records next to the
request ID; see [http-middleware.md](http-middleware.md).

## GenAI spans

`OpenTelemetryInferenceTracer` records one `chat {model}` client span per text
generation call, following the OpenTelemetry GenAI semantic conventions:

| Attribute | Value |
| --- | --- |
| `gen_ai.operation.name` | `chat` |
| `gen_ai.provider.name` | Taken from the LiteLLM prefix, for example `azure` becomes `azure.ai.openai`; `litellm` without a prefix |
| `gen_ai.request.model` | The model or deployment name after the prefix |
| `gen_ai.request.max_tokens` | Requested output token limit |
| `gen_ai.usage.input_tokens`, `gen_ai.usage.output_tokens` | Reported token usage |
| `gen_ai.response.finish_reasons` | Normalized finish reason |
| `error.type` | Stable runtime error code, such as `ai_unavailable`, on failure |

Prompts, completions, messages, credentials, endpoints and exception messages
are never recorded. The tracer uses the global provider when the span starts,
so it records nothing until a tracer provider is installed. These spans do not
depend on `RuntimeConfig.tracing`.

`create_text_generator` does not pass a tracer, so its calls record nothing.
To record GenAI spans, inject the tracer into the LiteLLM adapter:

```python
from platform_kit_runtime.infrastructure.litellm import (
    LiteLLMTextGenerator,
    load_litellm,
)
from platform_kit_runtime.telemetry import OpenTelemetryInferenceTracer

generator = LiteLLMTextGenerator(
    config=config,
    sdk=load_litellm(),
    tracer=OpenTelemetryInferenceTracer(),
)
```

You can inject any `InferenceTracer` implementation. When no tracer is given,
the adapter uses `SilentInferenceTracer`, which records nothing.

## Langfuse

Langfuse Cloud and self-hosted Langfuse (v3.22 or later) accept OTLP traces over
HTTP. Use the region's base URL, or `https://<host>/api/public/otel` when
self-hosted:

```text
OTEL_SERVICE_NAME=my-service
OTEL_EXPORTER_OTLP_ENDPOINT=https://cloud.langfuse.com/api/public/otel
OTEL_EXPORTER_OTLP_HEADERS=Authorization=Basic%20<base64 of public-key:secret-key>,x-langfuse-ingestion-version=4
```

The US region uses `https://us.cloud.langfuse.com/api/public/otel`. The header
value contains the secret key, so mount it from a secret store, never a
committed file or image. Langfuse shows the GenAI spans as generations with
model and token usage; the server span is their parent.

## Azure

### Application Insights

Prefer the starter's pattern: a trace-only `AzureMonitorTraceExporter` with a
`ManagedIdentityCredential`, installed once before the app starts. If you use
the Azure Monitor OpenTelemetry distro instead, it installs the global tracer
provider, which FastAPI's native tracing then uses, but it also exports Python
log records and metrics by default. On Container Apps that duplicates the
console logs already collected into Log Analytics, so turn both off:

```python
import os

from azure.identity import ManagedIdentityCredential
from azure.monitor.opentelemetry import configure_azure_monitor

from platform_kit_runtime import RuntimeConfig, create_app

os.environ.setdefault("OTEL_LOGS_EXPORTER", "none")
os.environ.setdefault("OTEL_METRICS_EXPORTER", "none")
configure_azure_monitor(
    credential=ManagedIdentityCredential(client_id=os.environ["AZURE_CLIENT_ID"]),
    instrumentation_options={"fastapi": {"enabled": False}},
)
app = create_app(config=RuntimeConfig(tracing=True), probes=())
```

The distro reads `APPLICATIONINSIGHTS_CONNECTION_STRING`; supply it as a
nonsecret setting (it is an ingestion endpoint, not a credential, once local
authentication is disabled). The credential authenticates ingestion with
Entra ID, which Application Insights requires once local authentication is
disabled; grant the runtime identity `Monitoring Metrics Publisher` on the
component. Disabling the distro's FastAPI instrumentation
keeps native tracing and the health route exclusion (the environment variable
`OTEL_PYTHON_DISABLED_INSTRUMENTATIONS=fastapi` does the same). Leave the
`OTEL_EXPORTER_OTLP_*` endpoints unset unless spans should also go to a second
backend.

### Azure Container Apps managed OpenTelemetry agent

The managed agent injects `OTEL_EXPORTER_OTLP_ENDPOINT` and accepts gRPC only,
so automatic configuration declines it with a warning. Install
`opentelemetry-exporter-otlp-proto-grpc`, configure the provider before the app
starts, and set `OTEL_TRACES_EXPORTER=none` so no HTTP exporter is added:

```python
from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

provider = TracerProvider()
provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter()))
trace.set_tracer_provider(provider)
```

The agent then forwards spans to the destinations configured on the Container
Apps environment, such as Application Insights. Langfuse accepts only OTLP over
HTTP, so export to it directly with the variables shown above instead.
