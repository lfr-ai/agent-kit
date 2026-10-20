# Native roles

[agents.json](../assets/agents.json) is the single source for this skill's native
roles. A renderer projects each role into Copilot and Claude agent files; the
procedure body is shared and only the frontmatter differs per runtime. Never edit
the projected files by hand.

## Schema

Top level: `schema_version` (integer `1`) and `roles` (list). Each role is a closed
object; unknown fields and duplicate keys are rejected.

| Field | Rule |
| --- | --- |
| `id` | `kit-` plus lowercase words joined by `-`; unique across all role assets |
| `kind` | `primary` (selectable by the user) or `worker` (called by a coordinator) |
| `tier` | `readonly`, `implementer`, or `coordinator` |
| `description` | One line, at most 180 characters |
| `body` | Visible text, at most 125 lines, no secret-like values |
| `workers` | Required and non-empty for coordinators; empty for every other tier |
| `models` | Optional worker preference; only the supported small models are accepted |

A coordinator must be `primary`, and each listed worker must exist with kind `worker`.

## Tiers and native capability

The tier, not the body, decides what a role may do. The renderer grants read and
search to every tier, adds editing and command execution for implementers, and adds
delegation, limited to the listed workers, for coordinators. Body text never grants
a capability; do not name native tools in a body as if it did. Native approval
modes and permission rules still apply to every call.

Copilot projections of primary roles are user-invocable and are not offered for
automatic model invocation; worker projections are the reverse. Claude delegation
limits apply when a coordinator is the main agent, not when it runs as a worker.

## Body structure

Every body follows the same outline so reviewers can compare roles:

1. **Mission**: the one outcome the role exists for.
2. **Inputs**: what the assignment must provide.
3. **Method**: numbered steps, evidence before conclusions.
4. **Quality gates**: conditions the result must meet before it is returned.
5. **Stop conditions**: when to return, including forbidden actions for the tier.
6. **Report**: the exact return shape.

Keep bodies between roughly 15 and 60 lines. Move long guidance into a skill
reference and keep the body procedural.

## Changing a role

1. Edit only `agents.json`. Keep `id`, `kind`, `tier`, `workers`, and `models`
   unchanged unless the change is a reviewed contract change.
2. Run `uv run --locked agent-kit check --root .` to validate the schema and links.
3. Regenerate repository projections with the documented renderer task and review
   the projected diff; do not hand-edit generated agent files.
4. Record native host behavior separately in the
   [certification worksheet](../assets/certification.md.template). Rendering and
   parsing do not prove a runtime honors the tool limits.

## Sources

- [VS Code custom agents](https://code.visualstudio.com/docs/agent-customization/custom-agents)
- [VS Code subagents](https://code.visualstudio.com/docs/agents/subagents)
- [Claude Code subagents](https://code.claude.com/docs/en/sub-agents)
- [GitHub Copilot custom agents](https://docs.github.com/en/copilot/how-tos/use-copilot-agents/coding-agent/create-custom-agents)
