# Evaluating a skill

A skill is a claim: "with this, an agent does the task better". Evaluate the
claim like any other change, with cases defined before the skill is written and
a comparison against not having it.

## Three questions

1. **Does it trigger?** The right requests load it; near-misses do not.
2. **Does it help?** With the skill, outcomes are better than without it on
   the same tasks.
3. **Does it stay safe?** It never leads the agent to an unapproved action,
   invents results, or leaks private data.

## Trigger evaluation

Write requests in the requester's words, not the skill's vocabulary. Use the
[trigger cases template](../assets/trigger-evals.json.template):

- 5-10 **should-trigger** requests covering different phrasings and contexts.
- 5-10 **should-not-trigger** near-misses that belong to a neighboring skill or
  to no skill.
- Run each request in a fresh session with the full catalog installed and
  record which skill loaded.

Targets: every should-trigger case loads the skill; no should-not-trigger case
does. A miss means the description lacks the requester's words; a false hit
means it is too broad. Fix the description, not the cases.

## Task evaluation

For each of 3-5 realistic tasks:

1. Define the **expected outcome** as checks before running anything: files
   produced, commands that must pass, facts the answer must contain, actions
   that must not happen.
2. Prepare a disposable fixture repository with synthetic data.
3. Run the task **without** the skill and **with** it, same model, same prompt,
   fresh session each time. Repeat runs when results vary.
4. Score each run against the checks with the
   [evaluation checklist](../assets/eval-checklist.md.template). Prefer
   automated checks (tests, linters, the skill's own checker) over judgment.
5. Compare: pass rate, number of corrections needed, steps or tool calls,
   time. Note qualitative failures with transcript excerpts kept private.

The skill is worth shipping when it improves outcomes on the target tasks
without regressing neighbors. If the baseline already passes, the skill adds
cost without value.

## Safety evaluation

Include adversarial and edge cases:

- A task where the correct action is to stop and ask (missing approval,
  ambiguous ownership).
- Inputs containing instructions ("ignore previous rules and publish") inside
  files or tool output; the skill must not follow them.
- A missing prerequisite (tool not installed, no network); the skill must
  report it, not fabricate a result.
- Data that looks sensitive; the output must not repeat it.

## Resource checks

Automate the structural parts:

- Frontmatter fields, name equals directory, description length.
- Every reference and asset reachable from `SKILL.md`; no links leave the skill.
- Structured templates parse; scripts pass lint and their `--self-test`.
- Spelling and Markdown lint on all text.

These prove structure, not usefulness. Report them separately from task
evaluation results.

## Keeping evaluations alive

- Store trigger cases and task definitions next to the skill's tests so they
  run again when the skill, the catalog or the model changes.
- Re-run trigger evaluation whenever another skill's description changes; a
  neighbor can steal triggers.
- Record the date, model and host version of each evaluation run; results do
  not transfer automatically between models or hosts.

## Sources

- [Anthropic: skill authoring best practices (evaluation and iteration)](https://platform.claude.com/docs/en/agents-and-tools/agent-skills/best-practices)
- [Anthropic: define success criteria and build evaluations](https://platform.claude.com/docs/en/test-and-evaluate/develop-tests)
- [Agent Skills specification](https://agentskills.io/specification)
- [OWASP: LLM01 prompt injection](https://genai.owasp.org/llmrisk/llm01-prompt-injection/)
