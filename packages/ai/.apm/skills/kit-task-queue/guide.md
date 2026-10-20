# Task queue guide

Purpose

Detailed references, copyable templates, and tests are indexed in [references/guide.md](references/guide.md).

Provide practical guidance for designing recoverable background work with clear delivery semantics and operator tooling.

Acceptance gates

- Message schema includes id, owner, created_at, version, and a stable deduplication key.
- Dead-letter handling, replay tools, and poison-message thresholds are documented.
- Worker lease/visibility timeout strategy is matched to expected work duration.

Failure modes

- Unbounded retries causing duplicate side effects.
- Poison messages repeatedly failing and consuming worker capacity.
- Missing correlation IDs preventing operator diagnosis.

Verification prerequisites

- Replay and dead-letter tests with representative messages.
- Duplicate delivery test to verify idempotency.

Authoritative references

- AWS SQS Developer Guide (concepts): <https://docs.aws.amazon.com/AWSSimpleQueueService/latest/SQSDeveloperGuide/welcome.html>
- RabbitMQ guides: <https://www.rabbitmq.com/documentation.html>

Scope and limits

These recommendations validate message-level contract and operational readiness. They are not a replacement for provider-specific config reviews or performance/load testing.
