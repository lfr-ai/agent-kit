# Duplication versus coincidence

A detector reports textual similarity. A reviewer decides whether the copies
encode the same knowledge. Unifying coincidental similarity couples code that
should evolve independently; leaving real duplicated knowledge apart lets the
copies drift until they disagree.

## The deciding questions

Ask in order; stop at the first decisive answer.

1. **Same reason to change?** Name the rule or fact each copy encodes (a tax
   rounding rule, a retry policy, a field list). If a change to that rule must
   reach both copies, it is duplicated knowledge.
2. **Same owner and release cycle?** Copies owned by different teams or shipped
   on different schedules should usually stay apart even if the rule is the
   same; share the rule through a contract or a published library instead.
3. **Mirror of a contract?** Request and response models on both sides of an
   API, database columns in code and in migrations, and event payloads in
   producers and consumers are expected mirrors. Unify by generating from the
   single source (schema, specification, migration), not by sharing code
   across the boundary.
4. **Rule of three?** Two copies of a young piece of code are cheap; the third
   copy usually reveals what varies. Defer extraction of a pair when the shape
   is still moving, and record the decision.
5. **Test code?** Tests repeat setup on purpose so each test reads alone.
   Extract only fixtures and builders that remove noise; keep the assertions
   visible in each test.

## Signals

| Signal | Leans toward duplicated knowledge | Leans toward coincidence |
| --- | --- | --- |
| History | Copies changed together in past commits | Copies changed separately |
| Names | Same domain terms and identifiers | Different domain terms with similar structure |
| Bug reports | A fix was applied to one copy and later to the other | Bugs never cross |
| Constants | Same magic values in both | Values differ but structure matches |
| Location | Same bounded context or package | Different contexts or services |
| Shape | Same control flow and the same data | Same control flow, unrelated data (boilerplate) |

Check history with:

```text
git log --format="%h %ad %s" --date=short -- <first-file> <second-file>
```

and compare commits that touch both files.

## Common categories

| Category | Typical decision |
| --- | --- |
| Business rule repeated in two services | Extract to the owning service or a versioned shared library; consumers call or depend on it |
| Validation duplicated in client and server | Generate client validation from the server schema, or accept the duplication with a contract test |
| Boilerplate imposed by a framework | Keep; reduce with the framework's own mechanism if one exists |
| Copy-pasted test setup | Extract a fixture or builder; keep assertions inline |
| Parallel table-driven tests | Merge into one parameterized test if they test the same function |
| Migration files | Keep; migrations are history and must not share code that later changes |
| Infrastructure per environment | Use the tool's module or parameter mechanism; keep environment-specific differences explicit |
| Documentation snippets | Keep when each page must stand alone; otherwise link to one canonical page |

## When unifying is harmful

- The shared helper grows a flag parameter that selects between the original
  behaviors: the copies were different after all. Split it back.
- The extraction forces a lower layer to import a higher one, or two
  independent packages to share a dependency they did not have.
- A shared library across team boundaries turns a local change into a
  coordinated release.

## Recording the decision

For each clone pair, write one line in the
[evidence worksheet](../assets/templates/duplication-evidence-template.md):
the knowledge encoded, the deciding question, the decision and the owner. A
`keep` decision is as valuable as an `extract` decision; it stops the next
reviewer from re-litigating the same pair.

## Sources

- [git log documentation](https://git-scm.com/docs/git-log)
- [pytest parametrize](https://docs.pytest.org/en/stable/how-to/parametrize.html)
- [OpenAPI Specification](https://spec.openapis.org/oas/latest.html)
