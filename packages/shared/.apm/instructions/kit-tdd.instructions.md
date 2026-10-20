---
description: Apply to test-first changes in test suites to keep red-green-refactor discipline.
applyTo: "**/tests/**,**/test/**,**/__tests__/**"
---

- Start new behavior or a defect fix with a test that fails for the expected reason; observe that failure before changing production code.
- Write the smallest test that pins one observable behavior through a public interface, not a private helper.
- Write only enough production code to pass the failing test; add the next case as a new test.
- Refactor only while the suite is green, and rerun it after each refactoring step.
- Reproduce a reported defect as a regression test that fails on the unfixed code, and keep it after the fix.
- Never edit an existing assertion to match new behavior without confirming that the contract changed.
- Prefer thin vertical slices through real boundaries over layer-by-layer test scaffolding.
- Keep the fast unit tier runnable in seconds so the loop stays short; move slow cases behind integration markers.
- Delete tests only when the behavior they pin is removed, and say so in the change.
- Use the `kit-test-first` skill for the full red-green-refactor procedure.
