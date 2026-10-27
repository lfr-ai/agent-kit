# Change classes

Choose the lane before editing. A wrong lane either pollutes the kit with one
project's facts or leaves a reusable defect to be rediscovered everywhere.

## Decide the class

| Class | Examples | Lane | Version effect | Evidence to record |
| --- | --- | --- | --- | --- |
| Project fact | This project's stack, commands, owners, naming | This project's own `AGENTS.md`, `PROJECT.md` or instructions; never the kit | None | None |
| Trivial | Typo, dead link, unclear sentence, stale version number | Pull request to the kit | Patch | The corrected text |
| Behavior | A skill steers the agent wrongly, a step is missing, a template does not run | Pull request with the failing prompt and expected result | Patch or minor | Prompt, observed result, expected result |
| Contract | Rename or remove a capability, change `applyTo`, widen role tools, change policy | Issue or discussion first, then a pull request labelled `breaking` | Minor while 0.x, major after | Migration and replacement mapping |
| Urgent or security | A harmful instruction, leaked secret, hidden Unicode | Stop using the capability, patch release | Patch, immediately | Minimal description; report privately |

## Ask before filing

1. Is the fact true for every project that installs this package? If not, keep
   it local.
2. Does an existing capability already cover it? Extend that owner instead of
   adding a new skill.
3. Is the behavior caused by the kit, by the model, or by this project's own
   instructions? Fix the owner of the cause.
4. Can it be said in fewer lines? Context cost is paid in every session.

## Edit rules that avoid regressions

- Prefer deleting or tightening text over adding more.
- A skill body is a short numbered procedure; detail belongs in `references/`,
  templates in `assets/`.
- Do not raise a context budget to fit a change; trim or split instead.
- A new validation rule needs a failing synthetic test first.
- Content-only edits need no new test, but record the observed failure.

## Escalate

Security reports go through the repository's private advisory route, never a
public issue or pull request. A change that needs another repository or a
tag/release is an operator action; hand it back with the exact commands.
