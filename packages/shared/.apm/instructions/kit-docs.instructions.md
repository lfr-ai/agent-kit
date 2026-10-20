---
description: Apply to Markdown documentation content and user-facing examples.
applyTo: "**/*.md"
---

- Follow the nearest docs conventions; prefer brief headings, precise bullets, and links, written for a reader without this session's context.
- Lead with what the reader can do and its prerequisites; put background and rationale after the task.
- Document observable behavior, inputs, outputs, defaults, limits, and failure recovery, not implementation narration.
- Keep commands, flags, names, defaults, and versions identical to what the code ships; copy them from source, not memory.
- Make every example runnable as written or label it as an excerpt; use neutral, synthetic data.
- State each fact in one canonical place and link to it; do not copy policy or reference tables between pages.
- Mark unsupported, experimental, or unverified behavior explicitly; never imply guarantees the code does not enforce.
- Keep secrets, private host names, personal data, and internal identifiers out of docs and screenshots.
- Update or delete stale sections in the same change instead of appending contradictory notes.
- Use the `kit-documentation` skill for structured documentation work.
- Run only relevant spelling, formatting, and link checks; report their exact results.
