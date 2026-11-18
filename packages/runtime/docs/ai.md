# Async text inference

An opt-in, in-process LiteLLM SDK adapter, independent of health and identity.
There are no AI HTTP routes, agents, streaming, retrieval, proxy services,
provider fleets, or deployment resources.

## Dependency and import boundary

The runtime `ai` extra constraints are `litellm>=1.103.7,<1.104` and
`filelock>=4.2.1,<5`. The exact reviewed maintainer selections are
`litellm==1.103.7` and `filelock==4.2.1`. Pinning the SDK avoids resolving a
younger compatible patch under the root's fourteen-day update cooldown.
The filelock floor requires the released advisory fixes; it does not override
any SDK metadata. LiteLLM 1.103.7 does not declare the incompatible
`filelock<4` requirement found in the later SDK series.

The checked root lock passed `task verify -- dependencies` before
`uv sync --locked`. The installed SDK was exercised against mocked HTTP for
OpenAI-compatible and Azure-compatible request/response and error contracts;
no provider network request or credential was used. Re-run the repository
dependency audit before changing these constraints or pins.

Importing `platform_kit_runtime` or `platform_kit_runtime.ai` does not import
LiteLLM. `create_text_generator` loads the SDK; absent or incompatible optional
dependencies raise `AIDependencyError`. LiteLLM 1.103.7 supports Python
`>=3.10,<3.15`; this runtime integration targets Python 3.13 and 3.14.

For offline/on-premises processes, set `LITELLM_LOCAL_MODEL_COST_MAP=True`
**before importing LiteLLM**, using the application's environment configuration.
Otherwise the SDK may fetch its public model-cost map on import. The runtime
does not change environment variables, SDK globals, log levels or callbacks.

## Public interface

Microsoft Entra (keyless, managed identity) authentication is the recommended
path for Azure OpenAI and Microsoft Foundry, including resources that set
`disableLocalAuth=true`:

```python
from azure.identity.aio import ManagedIdentityCredential, get_bearer_token_provider

from platform_kit_runtime.ai import (
    AIMessage,
    AIRole,
    TextGenerationConfig,
    TextGenerator,
    TextRequest,
    TextResult,
    create_text_generator,
)


def build_generator(credential: ManagedIdentityCredential) -> TextGenerator:
    return create_text_generator(
        config=TextGenerationConfig(
            entra_authentication=True,
            model="openai/<deployment>",
            api_base="https://<resource>.openai.azure.com/openai/v1/",
            timeout_seconds=30.0,
            num_retries=0,
        ),
        token_provider=get_bearer_token_provider(
            credential, "https://ai.azure.com/.default"
        ),
    )


async def answer(generator: TextGenerator, question: str) -> TextResult:
    return await generator.generate(
        request=TextRequest(
            messages=(AIMessage(role=AIRole.USER, content=question),),
            max_output_tokens=1024,
        )
    )
```

Create `ManagedIdentityCredential(client_id=...)` in the application lifespan
and close it on shutdown, including failed startup; the runtime never closes it.
For local development, use `DefaultAzureCredential` from `azure.identity.aio`
with `AZURE_TOKEN_CREDENTIALS=dev`, which limits the chain to developer sign-in.
Grant the identity **Cognitive Services OpenAI User** (or an equivalent data
role) on the resource. Key-based providers pass `api_key=...` and no
`token_provider`; see the provider configuration below.

Construct once within the application's lifecycle and reuse the returned
`TextGenerator`. Application code can inject any implementation of that Protocol,
or use `TextGenerationService(generator=...)` from `application.ai` for the same
safe diagnostic boundary. Neither the service nor its factory opens a provider
connection itself; SDK initialization can perform the cost-map fetch noted above.

All configuration, message, request, result and usage records are frozen,
keyword-only and slotted. Secrets, model selectors, endpoint/version details,
messages and generated text are excluded from their representations.

### Provider configuration

- Azure OpenAI or Microsoft Foundry with Microsoft Entra (recommended): set
  `entra_authentication=True`, `model="openai/<deployment>"` and
  `api_base="https://<resource>.openai.azure.com/openai/v1/"` (or
  `https://<resource>.services.ai.azure.com/openai/v1/`), and pass a
  `token_provider` to `create_text_generator`. The base must be HTTPS with the
  exact `/openai/v1/` path; `api_key` and `api_version` must be absent, and a
  mismatch between the flag and the token provider raises
  `AIConfigurationError` before the SDK loads. The adapter awaits the provider
  for every generation within the total deadline and sends the token as
  `Authorization: Bearer`, never as an `api-key` header. Token acquisition
  failures and invalid tokens become `AIAuthenticationError`; token timeouts
  become `AIUnavailableError`.
- Azure OpenAI with a key, only where local authentication is enabled: use
  `model="azure/<deployment>"`, an explicit API key,
  `api_base="https://<resource>.openai.azure.com"` and the deployment's
  `api_version`. Azure is configuration, not a separate runtime adapter.
- Other API-key providers: use LiteLLM's documented model selector and key.
  Provider selection and authentication remain SDK responsibilities.
- An on-premises OpenAI-compatible service can use `model="openai/<model>"` with
  its own HTTPS `api_base` and key. Plain HTTP is accepted only for loopback
  development (`localhost`, `127.0.0.1`, `::1`).
- API-base URLs cannot contain user information, query parameters or fragments,
  including an empty `?` or `#`.
  Endpoints and credentials are trusted operator configuration, not user input.
- No provider allowlist or alias registry is added. A provider must support the
  SDK's async chat-completion interface and return text plus token usage.
  Unsupported SDK parameters/models produce explicit failures, not parameter
  dropping or routing implemented by this runtime.

The runtime does not resolve environment variables itself, create or discover
credentials, or provide Ollama, vLLM or OpenCode integration. Microsoft Entra
tokens come only from the caller-owned `token_provider`; API keys only from
explicit configuration. The host must not install global SDK callbacks or ambient SDK
routing/configuration overrides. Keep SDK/provider debug and HTTP wire logging
disabled; those host-controlled facilities are outside this library's logging
boundary. Never enable exception-local-variable capture for inference frames.

## Results, deadlines and failures

`generate(*, request: TextRequest) -> TextResult` is asynchronous. Its request
contains a nonempty tuple of text messages and a positive output token cap.
Roles are `system`, `user`, and `assistant`.

Calls explicitly set nonstreaming mode, one choice, output cap, SDK timeout,
retry count and SDK `no-log`. There is no custom retry loop, alternate-provider
fallback, cost calculation or global callback. Retry count defaults to zero and
is bounded to three. A cooperative total deadline, including SDK retries, must
be positive and finite and cannot exceed 300 seconds.

Caller cancellation propagates as `asyncio.CancelledError`. Deadline expiry
cancels the awaited SDK operation and becomes `AIUnavailableError`. As with
Python cooperative cancellation generally, this is not a hard termination
guarantee: LiteLLM can dispatch work through an executor, and a provider's
blocking work or already accepted remote request may outlive cancellation.
The runtime does not create its own executor, client pool or background service.

The adapter validates the **SDK-normalized** `ModelResponse`, not the original
provider wire bytes. It requires exactly one assistant text choice, no tools,
function call or refusal, a `stop` or `length` finish reason, and nonnegative
integer usage counters whose total equals input plus output. Booleans are not
counts. Missing usage, missing content, unknown reasons and non-text results
fail; nothing is replaced with empty text or zero tokens.

An explicitly returned empty string remains an empty string. `length` is an
explicit truncated result, not silently relabeled success. `AIUsage` reports
input, output and total token counts; provider/model names and raw responses are
not copied into results.

| Exception | Meaning |
| --- | --- |
| `AIConfigurationError` | Invalid local configuration/request, or SDK bad-request, missing-model, unsupported-parameter or unprocessable-input failure |
| `AIAuthenticationError` | Authentication or permission rejected |
| `AIUnavailableError` | Total/SDK timeout, connection failure, throttling or SDK service/API failure |
| `AIProtocolError` | Unexpected SDK exception, malformed response, missing usage or unsupported non-text outcome |
| `AIDependencyError` | Optional SDK import failed or required SDK surface is absent |

All derive from `AIError`, with fixed messages and fixed `code` values. Errors
contain no provider messages, status bodies, URLs, credentials or text. The
adapter classifies vendor errors, exits their exception handler, then raises a
safe typed error chained to a new content-free `AIError`. The original vendor
exception and its context/cause chain are deliberately not retained, so normal
later exception logging cannot reintroduce their contents.

The application service logs one `ai.inference_failed` warning with the fixed
`ai_failure` code; it does not log exceptions or request/provider metadata.
Cancellation is not logged as a failure. Consumers own transport mapping; no
existing health/problem handlers are modified.

## Offline verification and source grounding

Tests mock SDK/network boundaries and use only synthetic values. The
`test_ai_sdk.py` cases additionally exercise the installed SDK's actual
`ModelResponse` and exception classes with network access blocked; they skip
explicitly when the dependency owner has not provisioned LiteLLM. These tests
do not certify live credentials, provider reachability, model quality, SDK
retry execution or deployment behavior.

Inspected on 2026-11-05:

- [PyPI 1.103.7 release](https://pypi.org/project/litellm/1.103.7/) and
  [release metadata](https://pypi.org/pypi/litellm/1.103.7/json):
  Windows wheel `litellm-1.103.7-cp310-abi3-win_amd64.whl`, uploaded
  2026-10-21T09:36:06.256888Z, not yanked. Its verified SHA-256 is
  `1ff7e90c72663f79981e79e02a069643ec3f195516d7eaa81f0339f807430cec`.
  All eight artifacts are non-yanked; the last upload was
  2026-10-21T09:36:09.647455Z. Of 66 inspected stable, non-yanked releases from
  1.95.0 through 1.108.0, this is the highest version without the direct
  filelock cap whose artifacts precede the fourteen-day cutoff of
  2026-10-22T15:17:28.447Z. Every inspected stable release from 1.104.0 onward
  declares `filelock>=3.16.1,<4.0`.
- [GHSA-69hj-f68j-2879](https://github.com/advisories/GHSA-69hj-f68j-2879)
  affects every filelock version through 4.2.0 and is fixed in 4.2.1.
  Selecting an older filelock 3.x cannot make the later SDK graph clean.
  OSV queries returned thirteen findings for filelock 3.32.7, and none for
  filelock 4.2.1 or LiteLLM 1.103.7.
- SHA-verified 1.103.7 and 1.106.2 wheels were inspected in memory without
  installing or executing either. The async signature and all twelve mapped
  exception implementations are unchanged, as are the message, choice, usage
  and callback `no-log` definitions. The later response ID helper spelling,
  optional control-option processing and custom retry-policy lookup do not
  change this adapter's used surface. Per-call API-base handling, retry count,
  cooperative executor behavior and the local-cost-map setting are retained.
  This is static compatibility evidence, not an installed-SDK test.
- [Completion inputs](https://docs.litellm.ai/docs/completion/input):
  model, messages, API key/base/version, timeout, token limit and retries.
- [Completion output](https://docs.litellm.ai/docs/completion/output):
  normalized choices, messages and finish reasons.
- [Azure configuration](https://docs.litellm.ai/docs/providers/azure):
  deployment selector and per-call credentials, endpoint and API version.
- [Exception mapping](https://docs.litellm.ai/docs/exception_mapping):
  normalized provider authentication, request, timeout and service failures.

Existing APM `kit-llm-client` guidance informed the inward port boundary and
privacy tests. Its custom retry/policy stack, model registry, raw exception
chaining and response fallbacks are intentionally not copied into this bounded
runtime capability.
