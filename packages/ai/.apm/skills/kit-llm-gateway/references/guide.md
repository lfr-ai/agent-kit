# Model gateway guide

## Purpose

Run a model gateway that gives applications job-named aliases, central
credentials, budgets, rate limits, fallbacks and traces, without moving
application policy into the gateway. Calling the gateway from code stays in
the `kit-llm-client` skill: one port, typed errors, one retry layer.

## When not to add a gateway

| Situation | Prefer |
| --- | --- |
| One service, one provider, no shared quota | Direct SDK behind the `kit-llm-client` port |
| Several providers in one service, no central keys needed | In-process LiteLLM SDK adapter |
| Several services share keys, budgets, quotas or audit | Self-hosted gateway (this skill) |
| Platform already provides a managed gateway with required controls | Managed gateway; keep the same port |

A gateway is another service to secure, patch, monitor and pay for. Add it
when its central controls are needed, not to avoid writing an adapter.

## References

| Topic | Reference |
| --- | --- |
| Config sections, aliases, routing, retries, timeouts, fallbacks, virtual keys, budgets, caching, Langfuse callbacks, health | [litellm-proxy.md](litellm-proxy.md) |
| Ollama models: pinning, endpoints, context length, sizing, embeddings, security | [local-models.md](local-models.md) |

## Assets and copy targets

| Asset | Copy to | Depends on |
| --- | --- | --- |
| [litellm_config.yaml.template](../assets/litellm_config.yaml.template) | `gateway/litellm_config.yaml` | pinned LiteLLM proxy |
| [compose.gateway.yaml.template](../assets/compose.gateway.yaml.template) | `gateway/compose.gateway.yaml` | Docker Compose, pinned images |
| [gateway_client.py.template](../assets/gateway_client.py.template) | `llm/gateway_settings.py` | stdlib |
| [check_gateway_config.py](../assets/check_gateway_config.py) | `tools/check_gateway_config.py` or run in place | stdlib |

```text
python -c "import json,sys,yaml; json.dump(yaml.safe_load(sys.stdin), sys.stdout)" \
  < gateway/litellm_config.yaml | python check_gateway_config.py --production chat-default -
docker compose -f gateway/compose.gateway.yaml config --format json \
  | python check_gateway_config.py -
```

The checker reads JSON only; the conversion step needs PyYAML or an
equivalent converter in the consumer. Exit codes: 0 clean, 1 findings, 2
invalid input. Findings never print configuration values.

## Verification

- Run the checker on the configuration and the resolved compose images in CI.
- Start the stack locally, probe `/health/liveliness` and
  `/health/readiness`, then send one request per alias with a test virtual
  key and confirm the served model, cost record and trace metadata.
- Induce a provider error in a non-production environment to confirm the
  fallback path; confirm a budget-exhausted key is rejected.
- Run the evaluation suite (`kit-llm-evaluation`) for every alias after a
  model, fallback or gateway version change.

## Limits

The toolkit tests parse the templates and run the checker and the settings
loader offline. They do not start the proxy, Ollama, Redis or Postgres, pull
images, contact providers, or verify budgets, fallbacks or traces at runtime.
