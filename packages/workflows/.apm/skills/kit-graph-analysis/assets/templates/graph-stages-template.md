# Graph analysis stage worksheet

Use for investigations that take more than one sitting. Keep the commands
exact so another person can rerun them at the same revision.

## 1. Question

- Question type: impact / call chain / refactor blast radius
- Target: `<module or symbol>`
- Revision: `<commit>`
- Expected answer before querying:

## 2. Discovery

- Tools and versions:
- Index or graph freshness (built from which revision):
- Commands run, with arguments:

```text
<command>
```

- Output excerpts (trim to the relevant lines):

## 3. Analysis

- Direct dependents and classification:
- Transitive summary by package:
- Cycles involved:
- Chain from entry point to symptom (for debugging):

## 4. Validation

- Edges confirmed by reading source (path:line):
- Text searches for string references and results:
- Blind spots checked (dynamic imports, plugins, configuration, other
  repositories):
- Surprises compared with the expected answer:

## 5. Decision

- Proposed change and step plan:
- Tests to add or run:
- Owners to notify or who approved:
- Contracts to add so the structure holds:

## Evidence attached

- [ ] Commands and outputs
- [ ] Impact report or chain diagram
- [ ] Owner acknowledgements
