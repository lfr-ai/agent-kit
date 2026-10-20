---
description: Apply to prompt templates, prompt catalogs, and prompt construction code.
applyTo: "**/*prompt*.py,**/prompts/**"
---

- Keep prompt identifiers, versions, and intended inputs explicit and reviewable.
- Store prompt text as versioned templates with a declared input schema, and render with strict missing-variable errors.
- Separate trusted instructions from user-controlled content and preserve clear delimiters; never concatenate user text into system or developer instructions.
- Treat retrieved documents and tool output as untrusted data that may contain injected instructions.
- Validate structured model output at the boundary; never trust a prompt to enforce a schema.
- Avoid embedding credentials, private records, or production examples in prompt source.
- Version changes that affect output behavior and add representative, privacy-safe fixtures.
- Record the prompt identifier and version with each model call for traceability, without logging rendered personal content.
- Evaluate prompt changes against a fixed synthetic dataset before replacing the active version.
- Keep model names, sampling settings, and other provider-specific request options in adapters or configuration rather than registry policy.
- Use the `kit-llm-client` skill, when installed, for provider adapters and output validation.
