---
description: Keep Temporal workflow execution replay-safe and effects in Activities.
applyTo: "**/workflows/**/*.py,**/activities/**/*.py,**/temporal/**/*.py"
---

- Workflow code is deterministic orchestration: no network, filesystem, provider
  SDK, environment reads, wall-clock time or ordinary randomness.
- Put LLM, identity, database and tool I/O in Activities; bound attempts and total
  duration, and persist idempotency at the effect destination.
- Use SDK decorators directly for workflow/activity/signal/query/update entry
  points. Keep reusable domain policy framework-free.
- Never record credentials or personal content in history, Search Attributes,
  failure messages or logs. Authorize callers outside workflow determinism.
- Replay representative old histories before promotion; preserve old workers
  until the deployment/versioning drain policy permits retirement.
