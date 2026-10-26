# Local models with Ollama

Reviewed 2026-10-23 against the Ollama documentation.

## When local models fit

| Need | Local model | Hosted model |
| --- | --- | --- |
| Data must not leave the machine or network | Yes | Only with approved terms |
| Offline development and deterministic integration tests of plumbing | Yes | No |
| Highest quality on hard reasoning tasks | Rarely | Usually |
| Embeddings for a private corpus | Often sufficient | Optional |
| Predictable cost at steady volume | After hardware cost | Per token |

A local model is a different model, not a free copy of a hosted one. It must
pass the same evaluation suite (`kit-llm-evaluation`) before it serves any
alias that a hosted model also serves.

## Pin models

- Reference models by name and explicit tag (`<model>:<size-or-quant>`),
  never by an implicit or `latest` tag. A tag can be re-pushed; record the
  model digest shown by `ollama show` or `ollama list` with every evaluation
  run and compare it on deployment.
- Pull models in a provisioning step, not on first request. Keep the model
  store on a persistent volume and back it up or re-pull from a pinned list.
- Pin the server image by tag and digest; server releases change defaults
  (context length, scheduling, cloud features).

## Endpoints

| Endpoint | Use |
| --- | --- |
| `http://<host>:11434/v1/` | OpenAI-compatible chat, completions and embeddings subset; any API key value is accepted and ignored |
| `/api/chat`, `/api/generate` | Native API with model options such as `num_ctx` |
| `/api/embed` | Native embeddings, batched input |
| `/api/tags`, `/api/ps` | Installed and loaded models, for health and capacity checks |

The OpenAI-compatible endpoint supports a subset of parameters; test every
parameter the application relies on (structured output, tools, streaming)
against the pinned server version. Behind LiteLLM, use `ollama_chat/<model>:<tag>`
for chat and `ollama/<model>:<tag>` for embeddings, with `api_base` from the
environment.

## Context length

- The server default context window is small (4096 tokens per the FAQ at
  review time). Longer prompts can be truncated without an error, which
  silently drops instructions or retrieved context.
- Set `OLLAMA_CONTEXT_LENGTH` for the server or `num_ctx` per request to the
  length the feature needs, and test with a prompt near that limit.
- Larger contexts increase memory for the key-value cache roughly linearly;
  size hardware for the context you configure, not the model's maximum.

## Resource sizing

| Setting | Effect |
| --- | --- |
| Model size and quantization | Dominant memory cost; a quantized model needs roughly its file size plus context cache |
| `OLLAMA_NUM_PARALLEL` | Concurrent requests per loaded model; multiplies context memory |
| `OLLAMA_MAX_LOADED_MODELS` | Models kept resident at once |
| `OLLAMA_KEEP_ALIVE` | How long an idle model stays loaded; trades memory for cold-start latency |

- Check placement with `ollama ps`: `100% GPU` is expected; a CPU/GPU split
  means the model or context does not fit and latency will be much higher.
- Measure tokens per second and time to first token at the configured
  concurrency before setting gateway `timeout`, `rpm` and `tpm`.
- Embedding and chat models compete for the same memory; size for both or
  run them on separate servers.

## Security and privacy

- The server has no authentication. Bind it to loopback or a private network
  and put access control in front (the gateway or a reverse proxy).
- Disable cloud features (`OLLAMA_NO_CLOUD=1`) where data must stay local;
  otherwise some model names route to a hosted service.
- Set `HTTPS_PROXY` only for model pulls; do not set `HTTP_PROXY` on the server.

## Health

- Liveness: the server answers `/api/tags` (or `ollama list` in the
  container).
- Readiness: the pinned models are present; optionally a tiny generation
  within a timeout. Do not load every model on each probe.

## Primary sources

- [Ollama FAQ: context length, configuration, network exposure, cloud features](https://docs.ollama.com/faq)
- [OpenAI compatibility](https://docs.ollama.com/api/openai-compatibility)
- [Embeddings](https://docs.ollama.com/capabilities/embeddings)
- [Embed API](https://docs.ollama.com/api/embed)
- [Docker image](https://docs.ollama.com/docker)
- [GPU support](https://docs.ollama.com/gpu)
- [LiteLLM Ollama provider](https://docs.litellm.ai/docs/providers/ollama)
