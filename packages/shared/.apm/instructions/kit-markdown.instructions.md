---
description: Apply to Markdown structure, syntax, links, and front matter.
applyTo: "**/*.md"
---

- Use one H1 (or a front-matter title) per page and nest headings without skipping levels.
- Keep heading text unique among siblings and free of trailing punctuation; prefer sentence case.
- Use fenced code blocks with a language tag (`text` for plain output); never indent code blocks.
- Keep shell examples free of prompt characters unless output is shown alongside them.
- Use `-` for unordered lists with consistent nested indentation; leave blank lines around lists, headings, fences, and tables.
- Write descriptive link text, never "here"; prefer relative links for repository files and verify each target exists.
- Give images meaningful alt text; keep diagrams in a text format such as Mermaid when the renderer supports it.
- Keep tables small and simple; switch to a list when cells need paragraphs.
- Keep front matter valid YAML with only the fields the consuming tool reads.
- End files with one newline, no trailing spaces, and no hard tabs; let the configured linter decide line wrapping.
- Do not hand-edit generated Markdown; change its source and regenerate.
