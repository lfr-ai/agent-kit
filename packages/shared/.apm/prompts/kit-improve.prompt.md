---
description: Fix a misbehaving kit skill, instruction, prompt or template at its source repository so every project gets the change, not just this one.
argument-hint: What went wrong, e.g. "kit-python-service tells me to use a deprecated API"
agent: agent
---

# Improve the kit at its source

Turn a problem found in this project into a reviewed change to the shared kit.
Do not patch the installed copy and do not keep a local workaround.

## Input

- The user-supplied argument: what went wrong or what should change.
- The installed file or capability involved, if the user names one.

## Procedure

1. Load [kit-improve](../skills/kit-improve/SKILL.md) and follow its procedure.
2. Classify the change. If it is a fact about this project only, say so, add it
   to this project's own instructions instead, and stop.
3. Trace the installed file to its package and ask for the kit checkout path.
   Verify the checkout's origin and a clean tree before editing anything.
4. Reproduce the problem with a synthetic example that contains nothing from
   this project, and state the expected behavior.
5. Edit the owning source in the checkout, run `task verify` there, and commit
   on a branch only because the user asked for this change.
6. Show the exact push and pull request commands and wait for approval before
   running them. Never push or merge to the default branch.

## Acceptance gates

- [ ] The change is in the owning source, not an installed or generated copy.
- [ ] The example is synthetic and no private material left this project.
- [ ] `task verify` output was read and reported exactly.
- [ ] Every remote action was approved by the user first.

## Output

The change class, the owning source path, the verification result, and either
the pull request link or the exact commands awaiting approval.
