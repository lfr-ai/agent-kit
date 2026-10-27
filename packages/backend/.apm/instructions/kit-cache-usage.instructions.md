---
description: Apply to cache modules and Redis-compatible client code.
applyTo: "**/*cache*.py,**/cache/**/*.py,**/*redis*.py,**/*valkey*.py"
---

- Bound every in-process cache; use `functools.cache` only for zero-argument factories.
- Never apply `lru_cache` or `cache` to instance methods or `async def` functions.
- Set a TTL on every shared cache entry and include prefix, namespace, schema version, and tenant in keys.
- Decode cached bytes with JSON or another data-only codec; never `pickle` values from a shared store.
- Map client errors to one cache-unavailable error and fall back to the source; a cache write never fails a request.
- Invalidate after the source write commits; the TTL remains the backstop.
- Create one client per process in the lifespan with short timeouts and TLS outside local development; close it on shutdown.
- Use the `kit-caching` skill for layer choice, invalidation, stampede control, and HTTP validators.
