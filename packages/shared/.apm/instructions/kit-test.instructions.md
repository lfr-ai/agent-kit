---
description: Apply to test files and test configuration.
applyTo: "**/test_*.py,**/*_test.py,**/*.test.*,**/*.spec.*"
---

- Assert observable outcomes, boundary errors, and side effects instead of private call order.
- Name each test after the behavior and condition it proves; keep one reason to fail per test.
- Keep arrange, act, and assert steps visible; put shared setup in fixtures or factories, not hidden module state.
- Use deterministic fixtures and synthetic data; do not require live credentials, network access, or services.
- Control time, randomness, locale, and environment through injected values or fixtures, never sleeps.
- Mock only at boundaries you own an adapter for; prefer simple fakes over deep mock chains.
- Exercise failure, boundary, and recovery paths when they are part of the contract.
- Keep tests independent of execution order, wall-clock timing, and undeclared local state; clean up created files.
- Use parameterized cases for input tables instead of loops with shared assertions.
- Keep unit, integration, and end-to-end tests in their declared locations and markers.
- Preserve meaningful assertions; diagnose failures rather than weakening, skipping, or retrying gates.
- Mark an expected failure only with a linked reason and a removal condition.
