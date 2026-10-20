---
description: Draft a Conventional Commits message for the staged changes, with an accurate type, scope, body, and breaking-change footer.
argument-hint: Optional hint, e.g. an issue reference or the intended scope
agent: ask
---

# Write a commit message for the staged changes

Draft one commit message that a reviewer and a changelog generator can both
trust. Do not create the commit; the user or an operator workflow does that.

## Input

- The staged diff. If nothing is staged, say so and describe the unstaged
  changes instead, recommending what to stage together.
- The user-supplied argument may add an issue reference, scope, or context.

## Procedure

1. Read the staged diff in full, not only file names. Identify the one
   user-visible outcome. If the diff mixes unrelated outcomes, propose a split
   and draft one message per group.
2. Read the project's commit convention (contributing guide, commitizen or
   commitlint configuration). Load [kit-release](../skills/kit-release/SKILL.md)
   and follow its
   [Conventional Commits](../skills/kit-release/references/conventional-commits.md)
   guidance when the project declares none.
3. Choose the type by effect: `feat` adds behavior, `fix` corrects behavior,
   `refactor` preserves behavior, `perf`, `test`, `docs`, `build`, `ci`,
   `chore` otherwise.
4. Choose the scope from the owning module or package name already used in
   history; omit it rather than invent one.
5. Write the subject in imperative mood, lower case after the colon, no final
   period, at most 72 characters.
6. Write a body that explains why and notes behavior a reviewer could miss
   (migrations, defaults, removed options). Wrap at 72 characters.
7. Add `BREAKING CHANGE:` with the migration step when a public contract
   changes, and `Refs:` or `Closes:` footers when an issue applies.
8. Check the message against the diff: every claim must be visible in it.

## Acceptance gates

- [ ] Type and breaking marker match the actual effect on consumers.
- [ ] No secrets, internal host names, or personal data in the message.
- [ ] The subject would read correctly in a generated changelog.

## Output

The message in a fenced `text` block, followed by one line explaining the type
choice and, when relevant, the suggested split.
