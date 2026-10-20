# The self-reflection loop

At the end of a task, spend a few minutes turning what happened into durable,
evidenced improvements. Without the loop, the same surprises cost time on every
task; with an undisciplined loop, the knowledge base fills with opinions.

## When to run it

- After a task finishes or is abandoned.
- After a check failed for a reason nobody expected.
- After a correction from a reviewer or the requester.
- Before handing work to another person or agent.

## The loop

1. **Collect evidence.** List what actually happened, with sources: commands
   and their results, failing tests, review comments, files that were harder to
   find than expected. Facts only.
2. **Compare with expectations.** For each item, what did you expect and why?
   The gap between expectation and outcome is the lesson candidate.
3. **Classify each candidate.**

   | Candidate | Destination |
   | --- | --- |
   | A rule that must always hold | operating policy or an automated check |
   | A command, version or path fact | project facts |
   | A design reason or trade-off | decision record |
   | A surprising local fact with evidence | memory entry |
   | A procedure step that was missing | the owning skill or runbook |
   | Something only true for this task | hand-off note, then discard |
   | A preference or guess without evidence | nowhere |

4. **Prefer enforcement over prose.** If a lesson can become a test, a lint
   rule, a schema or a check script, do that; a written rule is the fallback.
5. **Write the smallest durable change** in the destination owner. One lesson,
   one place. Link to the evidence.
6. **Retire what the task disproved.** Mark contradicted memory entries
   superseded, fix stale commands in project facts, and correct guidance that
   led you astray.
7. **Verify the change**: run the check you added, run the context and memory
   freshness checkers, and re-read the edited entry as a newcomer would.

## Questions that surface good lessons

- What did I search for more than twice?
- Which command failed first, and was the error message enough to fix it?
- What did I assume about the code that turned out false?
- What would have let me skip the slowest part of this task?
- Did any instruction contradict the code? Which one was right?

## Quality bar for a recorded lesson

- It names the evidence (file, test, command, document) and the date.
- It states its scope and the conditions under which it stops being true.
- A reader can act on it without the original conversation.
- It contains no credentials, personal data or transcript excerpts.
- It is not already enforced by a check; if it is, record nothing.

## Anti-patterns

- **Diary entries**: "Today I worked on invoices" records activity, not
  knowledge.
- **Rules from one incident**: generalizing a single failure into an
  always-on rule bloats the policy. Record it as a memory entry first; promote
  it when it recurs.
- **Duplicated lessons**: the same fact in a memory entry, a skill and the
  policy will drift. Keep one and link.
- **Self-congratulation**: "the approach worked well" is not actionable.
- **Silent edits to history**: superseded decisions stay visible with a link to
  their replacement.

## Sources

- [Google SRE book: postmortem culture](https://sre.google/sre-book/postmortem-culture/)
- [Anthropic: effective context engineering for AI agents](https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents)
- [Claude Code memory](https://code.claude.com/docs/en/memory)
