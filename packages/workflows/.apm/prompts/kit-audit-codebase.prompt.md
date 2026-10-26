---
description: Audit a repository or area with deterministic tools first, then targeted review, and report ranked, evidenced findings without fixing anything.
argument-hint: Repository area, package, or audit goal (defaults to the whole repository)
agent: agent
---

# Audit the codebase

Produce a ranked findings report that a team can plan remediation from. The
audit observes only: do not edit source, configuration, lockfiles or baselines,
and do not add dependencies to the project.

## Input

- The user-supplied argument names the area (path or package) or the goal of
  the audit. When it is empty, audit the whole repository excluding generated,
  vendored and build output.
- The project's declared commands and tool configuration, read from its
  contributing guide, task runner or project facts file.

## Procedure

1. Load [kit-codebase-audit](../skills/kit-codebase-audit/SKILL.md) and follow
   its procedure, rubric and report template.
2. Record the commit, scope, exclusions, goal and time box in the audit plan.
   Run the project's existing gates once and record the baseline.
3. Inventory languages, entry points, packages and layers, test tiers, CI gates
   and existing tool configuration.
4. Run deterministic tools first, preferring those the project already locks:
   Ruff with complexity and selected families, the configured type checker,
   import contracts, dead-code and dependency-hygiene checks, duplication,
   vulnerability scanning and spelling. Write all output into one `audit/`
   directory and record each tool version. If a tool is unavailable, record it
   under "not checked" instead of installing it into the project.
5. Merge mergeable outputs with the skill's findings summarizer and add
   count-only rows for the other tools.
6. Review hot spots, entry points and one module per layer manually with the
   skill's lenses: dependency direction, ports and adapters, naming, magic
   numbers, docstrings, error handling, logging, configuration, tests by tier
   and documentation.
7. Grade each finding for severity and confidence, collapse repeated root
   causes into systemic findings with counts, and name the owner skill.
8. Propose remediation batches ordered by risk removed per unit of effort.

## Acceptance gates

- [ ] Every finding has `path:line` or command evidence, severity, confidence
      and an owner skill.
- [ ] Tool versions and commands are recorded so the run can be repeated.
- [ ] Unchecked areas and blind spots are listed.
- [ ] No tracked file changed except the new audit outputs.

## Output

The audit report (summary, scope and baseline, ranked findings, tool summary,
systemic themes, remediation batches, not checked, reproduce commands) and the
path of the raw tool outputs.
