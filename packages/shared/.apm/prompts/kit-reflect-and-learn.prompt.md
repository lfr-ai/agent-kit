---
description: Reflect on the finished task and record only durable, evidenced lessons in their single owning place, preferring a check over prose.
argument-hint: Optional topic, e.g. a failure or surprise worth capturing
agent: agent
---

# Reflect and record durable lessons

Turn what this session learned into one improvement that prevents a repeat,
without filling memory with transcripts or one-off details.

## Input

- The current conversation and the changes it produced.
- The user-supplied argument may name a specific failure, surprise, or
  decision to focus on.

## Procedure

1. Load [kit-context-onboarding](../skills/kit-context-onboarding/SKILL.md) and
   follow its [self-reflection loop](../skills/kit-context-onboarding/references/self-reflection.md).
2. List candidate lessons: wrong assumptions, commands that failed, rules you
   had to discover, and checks that would have caught a mistake earlier.
3. Discard anything that is task-specific, unverified, already documented, or
   a restatement of general knowledge.
4. For each remaining lesson, choose the single owning place, in this order of
   preference: an automated check or test, the owning skill or instruction,
   the project facts file, then a dated memory entry.
5. Before writing, read the target file and search it for an existing entry;
   update or supersede instead of duplicating.
6. Write each memory entry with a date, scope, evidence (command or file), and
   the action it implies. Keep it to a few lines.
7. Never record credentials, personal data, conversation transcripts, or
   private facts in a portable bundle.
8. If the right fix is a code or policy change outside the current task,
   propose it instead of making it.

## Acceptance gates

- [ ] Each recorded lesson has evidence and a concrete future action.
- [ ] No lesson exists in two places.
- [ ] Nothing sensitive or transient was written.
- [ ] Zero lessons is an acceptable, reported outcome.

## Output

A short table (lesson, evidence, destination, action taken or proposed),
followed by the paths changed. If nothing qualified, say so in one line.
