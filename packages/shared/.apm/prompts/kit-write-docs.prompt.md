---
description: Update documentation for a changed behavior, setup step, or failure mode, written for one reader and checked against the code.
argument-hint: What changed, or the document to update
agent: agent
---

# Write or update documentation

Document the user-visible contract of a change so a reader without this
session's context can succeed. Accuracy beats volume.

## Input

- The user-supplied argument names the change or the document. When it is
  empty, use the working-tree diff to find user-visible changes that lack
  documentation.

## Procedure

1. Load [kit-documentation](../skills/kit-documentation/SKILL.md) and follow its
   procedure.
2. Identify the reader and the task they face. Choose one document type:
   tutorial, how-to guide, reference, or explanation. Do not mix them on one
   page.
3. Find the owning document before creating a new one. Search for existing
   pages, README sections, and changelog entries that already cover the topic.
4. Read the code, configuration, and tests that define the behavior. Every
   command, option, default, and error message you document must appear there.
5. Write task-first: prerequisites, steps with exact commands, expected
   result, and what to do when it fails. State supported scope and known
   limitations explicitly.
6. Use neutral, synthetic examples. Never include secrets, internal host
   names, or personal data.
7. Update cross-references and any table of contents. Add a changelog entry
   when the project keeps one.
8. Run the project's documentation checks (Markdown lint, spell check, link
   check) on the touched files. Execute every new command example you can run
   safely and record the result.

## Acceptance gates

- [ ] Each documented command, flag, and default matches the source.
- [ ] Failure handling and limitations are stated, not implied.
- [ ] No duplicated content: other pages link to the single owning page.
- [ ] Documentation checks pass, or remaining findings are listed.

## Output

The files changed with a one-line summary each, the command examples verified,
check results, and any statement you could not verify against the code.
