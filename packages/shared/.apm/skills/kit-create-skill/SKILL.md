---
name: kit-create-skill
description: Use when authoring a reusable agent skill with explicit triggers, safe boundaries, and verifiable steps.
license: MIT
---

# Author a reusable skill

## Procedure

1. State the narrow task and the situation that should trigger the skill.
   Write three should-trigger requests and three near-misses before writing
   anything else.
2. Check the catalog and neighboring skills for overlap; extend or link an
   existing skill instead of adding a competing trigger.
3. Choose a stable, lowercase `kit-` identifier equal to its flat directory.
4. Write the description as a routing rule following
   [trigger descriptions](references/triggers.md): trigger first, the
   requester's task words, and what distinguishes it from neighbors.
5. Lay out the skill for progressive disclosure as in
   [structure](references/structure.md): a short numbered procedure with
   acceptance gates in `SKILL.md`, detail in references, copyable files in
   assets, deterministic checks in scripts. Start from the
   [skill template](assets/SKILL.md.template) and the
   [reference template](assets/reference.md.template).
6. Write original guidance grounded in official documentation, listed under
   `## Sources` in each reference; never reproduce proprietary or
   incompatibly licensed text.
7. Order steps around evidence, decisions, action and outcome checks; include
   concrete failure modes and stop conditions.
8. Do not assume tools, credentials or runtime support exist. Separate optional
   tool assistance from the required reasoning and its manual fallback.
9. Keep permissions, destructive operations and external actions explicit and
   behind an approval or an `--execute` style flag.
10. Make scripts stdlib-only, read-only by default, with `--self-test`, and add
    regression tests; make structured templates parse.
11. Evaluate triggering, task outcomes against a no-skill baseline, and safety
    following [evaluating skills](references/evaluation.md), using the
    [trigger cases](assets/trigger-evals.json.template) and the
    [evaluation checklist](assets/eval-checklist.md.template).
12. Check frontmatter, links, spelling and lint; report structural checks
    separately from evaluation results.

The [authoring checks](references/guide.md) summarize ownership and the
resource contract.

## Acceptance gates

- Every should-trigger case loads the skill and no near-miss does, or the
  remaining misses are listed with the planned description change.
- The body is within the line budget; every reference and asset is linked and
  no link leaves the skill directory.
- Templates parse, scripts pass lint and `--self-test`, and regression tests
  cover passing and failing inputs.
- Each reference lists official sources; no copied third-party or proprietary
  text, credentials or private facts.
- The skill does not claim to install a tool, enforce a policy or guarantee an
  outcome it cannot verify.
