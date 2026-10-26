# Diataxis: four kinds of documentation

Diataxis sorts documentation by what the reader needs at that moment. Most
confusing pages mix two kinds, for example a tutorial that stops to list every
option, or a reference that tries to teach. Decide the kind first, then write.

## The four kinds

| Kind | Reader's need | Form | Answers | Avoid |
| --- | --- | --- | --- | --- |
| Tutorial | learning by doing, new to the subject | a lesson with a guaranteed outcome | "Can you show me how to get started?" | choices, alternatives, explanations of why |
| How-to guide | completing a specific task, already competent | numbered steps toward a goal | "How do I rotate the signing key?" | teaching basics, exhaustive options |
| Reference | looking up facts while working | structured, complete, consistent description | "What does `--dry-run` do? What fields does an order have?" | instructions, opinions, narrative |
| Explanation | understanding context and reasons | discussion | "Why does the service use an event log?" | step-by-step instructions, option lists |

The two axes: tutorials and how-to guides are about **action**; reference and
explanation are about **cognition**. Tutorials and explanation serve
**acquisition** (study); how-to guides and reference serve **application**
(work).

## Writing each kind

### Tutorial

- One path, no branches. Every step is tested and produces a visible result.
- Start from a clean, stated environment and end at a working outcome.
- Explain only what is needed for the next step; link to explanation for more.
- Re-run the whole tutorial when dependencies change; tutorials rot fastest.

### How-to guide

- Title it as a task: "Export invoices to CSV", not "CSV".
- State prerequisites first: versions, permissions, inputs, working directory.
- Number the steps; one action per step; show the expected result.
- Include failure and recovery: what an error means, safe retry, rollback, and
  the point after which rollback is no longer possible.
- The [procedure template](../assets/procedure.md.template) has this structure.

### Reference

- Mirror the structure of the thing described (one section per command, module,
  endpoint, configuration key).
- Be complete and consistent: every item has the same fields (name, type,
  default, constraints, example).
- Generate it from the source where possible; see
  [API reference generation](api-reference.md).
- No instructions beyond minimal usage examples.

### Explanation

- Discuss one topic: architecture, a design decision, a trade-off, history.
- Connect to alternatives and constraints; it is allowed to have a point of
  view.
- Decisions with lasting consequences get a decision record, written with
  the `kit-project-memory` skill's record template; explanation pages link to them.

## Organizing a documentation set

```text
docs/
  index.md               what this is, who it is for, where to start
  tutorials/
    first-order.md
  how-to/
    export-invoices.md
    rotate-signing-key.md
  reference/
    cli.md               generated or structured
    configuration.md
    api/                 generated
  explanation/
    architecture.md
    decisions/
      0001-record-decisions.md
```

A small project can keep the same separation inside `README.md` sections
(see the [README template](../assets/README.md.template)) and grow into a
`docs/` tree later.

## Classifying an existing page

Ask of each section: is the reader acting or studying, working or learning?

- A how-to step that explains internals: move the explanation to an
  explanation page and link.
- A reference table inside a tutorial: link to the reference instead.
- A tutorial with "alternatively you can...": remove the alternative or make
  it a separate how-to guide.

## Sources

- [Diataxis](https://diataxis.fr/)
- [Diataxis: the compass](https://diataxis.fr/compass/)
- [Diataxis: how-to guides](https://diataxis.fr/how-to-guides/)
- [Diataxis: reference](https://diataxis.fr/reference/)
