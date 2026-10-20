# Structure: progressive disclosure, references, assets and scripts

A skill loads in three stages: metadata (name and description) for every
skill at startup, the `SKILL.md` body when the skill is chosen, and other
files only when the body points the agent at them. Structure the content so
each stage carries just what that stage needs.

## Layout

```text
kit-example/
  SKILL.md                 frontmatter + procedure + acceptance gates
  references/
    topic-a.md             detail loaded on demand
    topic-b.md
  assets/
    output.md.template     copyable starting points
    config.json.template
    check_example.py       runnable, stdlib-only checker
```

| Part | Holds | Loaded | Size guidance |
| --- | --- | --- | --- |
| Frontmatter | name, trigger description, license | always | one line of description |
| `SKILL.md` body | numbered procedure, decision points, acceptance gates, links | when chosen | short; this kit caps it at 300 lines, the open spec suggests under 500 |
| `references/*.md` | explanations, catalogs, failure modes, examples, sources | when a step links to it | one topic per file |
| `assets/*.template` | files the user copies and fills | when copied | complete and correct, placeholders obvious |
| `assets/*.py` (or `scripts/`) | deterministic checks or generators | when run | stdlib only unless documented |

## Writing the body

- A numbered procedure in the order the work happens: gather evidence, decide,
  act, verify, report.
- Each step is an action with an observable result. "Consider X" is not a step;
  "Run X and record its exit status" is.
- Link each reference and asset from the step where it is needed, with a
  relative path. Keep links one level deep where possible: the body links to
  references, references may link to assets.
- End with acceptance gates: checkable statements that are true when the task
  is done.
- State stop conditions: when to ask, when not to proceed.
- No background essays in the body; move them to a reference.

## Writing references

Use the [reference template](../assets/reference.md.template):

- One topic per file, named after the topic.
- Start with the decision the reader faces, then the procedure or catalog.
- Include failure modes and recovery, not only the happy path.
- End with a `## Sources` list of official or primary documentation.
- Write original text grounded in the sources; never paste proprietary or
  incompatibly licensed material.

## Writing assets

- Templates are complete files a user can copy: valid syntax for their format,
  every placeholder obviously a placeholder (`REPLACE_WITH_...`,
  `REVIEWED_COMMIT_SHA`), no credentials, no real host names or identities.
- Structured templates (JSON, YAML, TOML, Python) must parse; test that they do.
- Prefer one template per output file, named `<target-name>.template`.

## Writing scripts

A script earns its place when the same deterministic check or transformation
would otherwise be done by hand or re-derived each time.

Contract for portable scripts:

- Standard library only, no network, no imports of the consumer's code.
- `argparse` interface; paths and thresholds as flags with sensible defaults;
  nothing hard-wired to one repository layout.
- Read-only by default. Any write or external effect requires an explicit flag
  such as `--execute`, and the default prints what would happen.
- Deterministic output, one finding per line as `path:line: message`.
- Exit status: 0 clean, 1 findings, 2 unusable input or usage error.
- A `--self-test` flag that exercises passing and failing cases on in-memory or
  disposable synthetic data.
- Type annotations, docstrings, and a lint configuration they pass.
- Regression tests in the repository that owns the skill.

## Delivery and portability

- Every file must be reachable by a link chain from `SKILL.md`; unlinked files
  are dead weight and may not be shipped by every host.
- Links must stay inside the skill directory; another skill may not be
  installed. Mention a related skill by name instead of linking into it.
- Do not rely on the skill's install location; scripts receive paths as
  arguments.
- Host-specific fields (tool allowlists, model choice, permissions) belong in
  the host's native configuration, not in portable skill text.

## Sources

- [Agent Skills specification](https://agentskills.io/specification)
- [Claude Code: skills](https://code.claude.com/docs/en/skills)
- [VS Code: agent skills](https://code.visualstudio.com/docs/agent-customization/agent-skills)
- [Python argparse](https://docs.python.org/3/library/argparse.html)
