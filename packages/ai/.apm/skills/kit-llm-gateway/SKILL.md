---
name: kit-llm-gateway
description: Use when configuring or reviewing a model gateway such as a LiteLLM proxy or local Ollama models.
license: MIT
---

# Run a model gateway with explicit limits

## Procedure

1. Decide whether a gateway is needed at all; prefer the `kit-llm-client`
   port with a direct adapter until several services need shared keys,
   budgets or quotas ([references/guide.md](references/guide.md)).
2. Pin the gateway release and read its configuration reference for that
   version; record the review date
   ([litellm-proxy.md](references/litellm-proxy.md)).
3. Define job-named aliases in `model_list` mapped to pinned provider
   snapshots or tagged local models; clients send aliases only
   ([litellm_config.yaml.template](assets/litellm_config.yaml.template)).
4. Reference every credential with `os.environ/`; deliver values through the
   deployment's secret store, never in the file, image or compose defaults.
5. Set per-deployment and global timeouts, choose one retry layer, and keep
   cooldowns on.
6. Give each production alias a fallback to an alias that passed the same
   evaluation and shares data terms; no content-policy fallback across
   providers.
7. Issue virtual keys per service and environment with allowed models,
   budgets, rate limits and expiry; cap them with key-generation upper bounds.
8. Enable caching only with a TTL and a decision about personalized data;
   send Langfuse callbacks with message logging off unless content capture is
   approved.
9. For local models, pin tags and record digests, set context length and
   concurrency from measurements, and keep the server private
   ([local-models.md](references/local-models.md)).
10. Run the stack with pinned images, loopback ports and health checks
    ([compose.gateway.yaml.template](assets/compose.gateway.yaml.template));
    load client settings once at startup
    ([gateway_client.py.template](assets/gateway_client.py.template)).
11. Gate the configuration with
    [check_gateway_config.py](assets/check_gateway_config.py) in CI, then
    verify fallbacks, budgets and traces in a non-production environment.

## Acceptance gates

- The checker exits 0 for the LiteLLM configuration with every production
  alias passed as `--production`, and for the resolved compose images.
- No literal credential exists in configuration, compose files or images.
- Every deployment has a timeout; exactly one layer retries.
- Each production alias has a tested fallback with equivalent data terms.
- Every service uses its own virtual key with a budget and rate limit.
- Callbacks receive metadata only unless content capture was approved.
- Liveness and readiness probes do not call models; model health checks are
  scheduled and their details are not public.
- Local models are tagged, their digests recorded, and context length set.

## Failure modes

- Retries in client, adapter and gateway multiplying cost and latency.
- Fallback to a provider or region with different data terms.
- Floating image or model tags changing behavior without review.
- Database overlay silently overriding file configuration.
- Unauthenticated local model servers reachable from the network.
