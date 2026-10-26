# Mermaid diagrams

A diagram earns its place when it shows structure or sequence that prose
would need several paragraphs for: who calls whom, in what order, which
states are legal, how data relates. Mermaid keeps diagrams as text next to the
code, so they are reviewed in diffs and rendered by GitHub, GitLab, Azure
DevOps, MkDocs and Sphinx plugins. Review date: 2026-10-23.

## When a diagram helps

| Question the reader has | Diagram | Mermaid type |
| --- | --- | --- |
| What is this system and what does it talk to? | context | `flowchart` with the system as one node (C4 level 1 style) |
| Which deployable parts exist and how do they communicate? | container | `flowchart` with `subgraph` boundaries (C4 level 2 style) |
| What happens, in order, for one request or job? | sequence | `sequenceDiagram` |
| Which decisions and branches does a process take? | flow | `flowchart TD` |
| Which states can an entity be in, and what moves it? | state | `stateDiagram-v2` |
| How are stored entities related? | entity relationship | `erDiagram` |

Do not draw a diagram for a linear list of steps, a single call, or anything a
generated reference already shows (class lists, OpenAPI operations).

Mermaid also has experimental `C4Context` and `C4Container` diagram types.
Their layout control is limited and renderer support varies; a `flowchart`
with consistent node shapes and labeled edges is the portable choice.

## Rules for readable diagrams

- **One question per diagram**, stated in the sentence before it.
- **Stay under about 30 nodes**; split by boundary or by scenario when it grows.
- **Label every edge** with the verb or protocol (`HTTPS JSON`, `publishes
  InvoicePaid`); unlabeled arrows force the reader to guess.
- **Use names from the code** (service, queue, table and state names) so
  search finds both.
- **Show boundaries** (trust, deployment, team) with `subgraph`.
- **Keep direction consistent**: left to right for data flow, top to bottom for
  decisions and hierarchy.
- **Avoid styling** beyond what conveys meaning; renderers and dark themes
  differ, and custom colors often become unreadable.
- **Write accessible text**: add `accTitle` and `accDescr` lines, and say the
  key point in the surrounding prose so the diagram is not the only carrier.
- **Quote labels** that contain punctuation (`A["Invoice (draft)"]`).
- **No secrets or internal host names**; use role names (`payment provider`).

## Templates

The [diagram templates](../assets/diagrams.md.template) contain a context,
container, sequence, flow, state and entity relationship diagram for one
synthetic invoicing system. Copy the block that answers the reader's
question and rename the nodes.

## Validation

1. Render locally before committing: the Mermaid CLI (`mmdc`) from the
   project's locked JavaScript tooling, for example
   `mmdc -i docs/diagram.mmd -o build/diagram.svg`. A syntax error fails the
   command. For Markdown files, `mmdc` can render every fenced block
   (`-i page.md -o build/page.md`).
2. Preview in the target renderer (GitHub, the documentation site); renderers
   lag behind the latest Mermaid release, so avoid brand-new syntax.
3. Check the diagram against the code: every node exists, every edge is a
   real call or relationship.
4. Keep the rendered output out of version control unless the publishing
   system cannot render Mermaid.

## Failure modes

- A diagram copied from a design document that no longer matches the code.
- Fifty-node diagrams that show everything and explain nothing.
- Edges without labels, or arrows that mean different things in one diagram.
- Diagrams as images with no text source, which nobody can update.

## Primary sources

- Mermaid, [Flowchart syntax](https://mermaid.js.org/syntax/flowchart.html)
- Mermaid, [Sequence diagrams](https://mermaid.js.org/syntax/sequenceDiagram.html)
- Mermaid, [State diagrams](https://mermaid.js.org/syntax/stateDiagram.html)
- Mermaid, [Entity relationship diagrams](https://mermaid.js.org/syntax/entityRelationshipDiagram.html)
- Mermaid, [C4 diagrams](https://mermaid.js.org/syntax/c4.html)
- Mermaid, [Accessibility options](https://mermaid.js.org/config/accessibility.html)
- [Mermaid CLI](https://github.com/mermaid-js/mermaid-cli)
- [The C4 model](https://c4model.com/)
- GitHub, [Creating diagrams](https://docs.github.com/en/get-started/writing-on-github/working-with-advanced-formatting/creating-diagrams)
