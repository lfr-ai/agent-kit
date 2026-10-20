# Trigger descriptions

An agent sees only each skill's `name` and `description` when deciding which
skill to load. The description is therefore a routing rule, not a summary. A
vague description means the skill never loads; an over-broad one means it
loads for everything and crowds out better matches.

## Anatomy of a good description

1. **Trigger first**: start with the situation, for example "Use when ...".
2. **Concrete task nouns and verbs** the requester will actually say: "rotate
   signing keys", "split an invoice", "review a Terraform plan".
3. **Distinguishing scope**: what makes this skill different from its nearest
   neighbor ("... without publishing or changing remote state").
4. **One line, short**: stay well within the host's limit (the open
   specification allows 1024 characters; many catalogs budget far less).

```yaml
description: Use when reviewing a Terraform plan for destructive changes, drift or policy violations before apply.
```

## Patterns that fail

| Description | Problem | Better |
| --- | --- | --- |
| "Helps with documents." | no trigger, no scope | "Use when converting scanned invoices to structured CSV with validated totals." |
| "Use for all coding tasks." | matches everything | name the specific task the skill improves |
| "Advanced framework for robust, scalable excellence." | adjectives, no task words | the verbs and nouns of the task |
| "Use when using the tool described in this skill." | circular | the user's goal, not the tool name |
| Two skills: "Use when writing tests" / "Use when testing" | indistinguishable | split by approach or artifact: "red-green-refactor cycles" vs "property-based tests for parsers" |

## Check for overlap

Before adding a skill:

1. List every existing description in the catalog.
2. For the new skill, write three requests that should trigger it and three
   near-misses that should trigger a neighbor instead.
3. Read only the descriptions and decide which skill each request would pick.
   If you cannot tell, sharpen the wording or extend the existing skill instead
   of adding a new one.
4. Turn these requests into trigger evaluations (see
   [evaluating skills](evaluation.md)).

## Names

- Lowercase letters, digits and single hyphens; no leading or trailing hyphen;
  at most 64 characters; equal to the directory name.
- A consistent prefix per catalog (for example `kit-`) groups related skills.
- Name the task (`kit-release`), not a person, product or internal codename.

## Sources

- [Agent Skills specification: frontmatter](https://agentskills.io/specification)
- [Claude Code: skills](https://code.claude.com/docs/en/skills)
- [VS Code: agent skills](https://code.visualstudio.com/docs/agent-customization/agent-skills)
- [Anthropic: skill authoring best practices](https://platform.claude.com/docs/en/agents-and-tools/agent-skills/best-practices)
