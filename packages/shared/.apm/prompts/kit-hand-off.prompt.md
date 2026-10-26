---
description: Write a handoff that lets another session, agent or host resume or review the current work without the conversation transcript.
argument-hint: Optional audience, e.g. "next session", "coordinator", or a task id
agent: agent
---

# Hand off the current work

Capture the state of this work so the next reader can continue or review it
from files alone. The handoff is evidence, not a narrative of the session.

## Input

- The current conversation, the working-tree changes, and any plan file.
- The user-supplied argument names the audience. "coordinator" or a task id
  means a delegated worker handoff; anything else, or nothing, means a
  session handoff for whoever resumes the work.

## Procedure

1. For a session handoff, load [kit-project-memory](../skills/kit-project-memory/SKILL.md)
   and start from its [session handoff template](../skills/kit-project-memory/assets/session-handoff.md.template).
   For a worker handoff, load [kit-subagent-delivery](../skills/kit-subagent-delivery/SKILL.md)
   and use its [handoff template](../skills/kit-subagent-delivery/assets/handoff.md.template).
2. List changed paths from the actual diff or file listing, not from memory.
3. Record each command you ran after the last edit, exactly, with its result.
   Mark anything not run as not verified, with the missing prerequisite.
4. State the outcome status (done, partial or blocked), the next smallest
   action, open questions and assumptions.
5. Move durable residue to its owner first: lessons and decisions go through
   `kit-project-memory`; the handoff only links them.
6. Leave out transcripts, full logs, secrets, personal data and absolute
   local paths.
7. For a worker handoff, run the skill's `check_handoff.py` on the file and
   fix every finding before returning it.

## Acceptance gates

- [ ] Every changed path appears, and no path is listed that did not change.
- [ ] Every claimed check has an exact command and result.
- [ ] Limitations and unverified surfaces are explicit.
- [ ] A reader without the conversation can take the next action.

## Output

The handoff Markdown file path (or the handoff text when no file is wanted),
followed by one line: the status and the next action.
