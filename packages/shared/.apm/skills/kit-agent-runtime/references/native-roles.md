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
| `tier` | `verifier`, `implementer`, or `coordinator` |
| `description` | One line, at most 180 characters |
| `body` | Visible text, at most 125 lines, no secret-like values |
| `workers` | Required and non-empty for coordinators; empty for every other tier |
| `optional_workers` | Optional coordinator-only list; linked only when the worker's bundle is selected; must not repeat required workers |
| `models` | Optional worker preference; only the supported small models are accepted |

A coordinator must be `primary`, and each listed worker must exist with kind `worker`.

## Tiers and native capability

The tier, not the body, decides which tools a role receives:

| Tier | Copilot tools | Claude tools |
| --- | --- | --- |
| `verifier` | `read`, `search`, `execute`, `todo` | `Read`, `Grep`, `Glob`, `Bash` |
| `implementer` | `read`, `search`, `edit`, `execute`, `todo` | `Read`, `Grep`, `Glob`, `Edit`, `Write`, `Bash` |
| `coordinator` | `read`, `search`, `edit`, `execute`, `agent`, `todo` | Explicit `Agent(worker, ...)`, plus implementer tools |

Every role can read and search files and run offline commands, so analysis,
review and verification roles can inspect history, diffs and focused checks
even when their source-editing intent is read-only. There is no tier without a
shell. A `verifier` receives no edit or delegation tools. Existing role-specific restrictions on live operations,
model calls and other actions still apply.

Tool availability is not a command sandbox. A shell can modify files, access the
network or invoke other programs even without an edit tool. Verifier bodies
restrict intent to offline verification without source edits, but host approvals,
permission rules and any separately configured execution sandbox must enforce
command boundaries. Checks can also create caches or reports. Do not equate
source-read-only intent with filesystem-read-only enforcement, or claim a tool
list makes arbitrary shell commands safe. Body text alone grants no capability.

Copilot projections of primary roles are user-invocable and are not offered for
automatic model invocation; worker projections are the reverse. Claude delegation
limits apply when a coordinator is the main agent, not when it runs as a worker.

## Discovery and picker roster

Both adapters emit files directly in `.github/agents/` and `.claude/agents/`.
Do not put workers in `subagents/`: the standard VS Code agent-folder scan reads
direct child files, unlike its recursive instruction scan. Folder nesting is not
a visibility or permission control. Flat output also avoids depending on
different native Claude discovery behavior.

The deliberate main roster is `kit-orchestrator` and `kit-debug`.
Specialist advisers (`kit-ddd`,
`kit-sdd`, `kit-deep-thinking`), `kit-refactor`, and
implementation, research and review helpers are hidden workers. `kit-refactor`,
`kit-test-author` and `kit-devops-implementer` stay hidden because the
orchestrator delegates to them with owned paths and acceptance
checks; picking one directly would skip that planning and review. Each worker
owns one job: `kit-planner` also checks placement, dependency direction, reuse
and blast radius; `kit-code-reviewer` also reviews coupling; `kit-deep-thinking`
also plans incremental upgrades. Test-first work
is the `kit-test-first` skill plus the `kit-test-author` worker; `kit-testing`
and `kit-tdd` are not separate roles. Cross-layer, frontend and model-backed
features run through `kit-orchestrator` with the selected workers. Coordinators list exact worker IDs, never
`*`; the orchestrator links optional specialists only when their bundles are
selected.

For Copilot, `user-invocable: false` hides workers from the picker while
`disable-model-invocation: false` keeps them callable. These are independent
controls. `agents: [...]` names exact, case-sensitive worker names; listing a
name explicitly can override that target's `disable-model-invocation: true`.
Only coordinators receive an `agents` allowlist and the delegation tool.

Repository refresh still validates the previous ownership hashes before moving
an attested nested file to its flat destination. It refuses independently edited
workers and unowned destination files. Legacy `subagents/` paths are accepted
only in the previous ledger for guarded reads, removal and rollback; they never
authorize new nested output or adoption of unowned files. Audit drift before an
explicit refresh; never move generated files or rewrite the ownership ledger by
hand.

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
2. For Agent Kit's canonical role source, maintainers run
   `task verify -- source` to validate the schema and links. Consumers use
   their repository's applicable validation.
3. Audit repository projection drift with
   `uv run --locked python -m scripts.render_native`, then explicitly refresh
   with `--write` only after review. Source-driven drift is expected after a
   change; independently edited outputs must be resolved by their owner.
   Unchanged attested files and their unchanged ledger are not rewritten.
   Review the projected diff; do not hand-edit generated agent files or locks.
4. Record native host behavior separately in the
   [certification worksheet](../assets/certification.md.template). Rendering and
   parsing do not prove a runtime honors the tool limits.

## Sources

Checked against the current public documentation and discovery implementation on
2026-11-03. File tests prove rendering and ownership, not a live IDE session.

- [VS Code custom agents and picker controls](https://code.visualstudio.com/docs/copilot/customization/custom-agents)
- [VS Code subagents and exact allowlists](https://code.visualstudio.com/docs/copilot/agents/subagents)
- [VS Code agent file reference and tool aliases](https://code.visualstudio.com/docs/agents/reference/custom-agent-file-reference)
- [VS Code standard folder scan](https://github.com/microsoft/vscode/blob/main/src/vs/workbench/contrib/chat/common/promptSyntax/utils/promptFilesLocator.ts#L660-L695)
- [Claude Code subagents](https://code.claude.com/docs/en/sub-agents)
- [GitHub Copilot custom agents](https://docs.github.com/en/copilot/how-tos/use-copilot-agents/coding-agent/create-custom-agents)
