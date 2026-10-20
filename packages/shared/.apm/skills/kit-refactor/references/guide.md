# Preserve behavior through structural change

## Characterize before moving

Identify public imports, calls, serialized values, exception types, ordering,
defaults, side-effect timing and cancellation. Run the owning tests before the
transformation. For poorly covered code add one focused characterization at
the boundary callers actually observe.

Move one responsibility at a time. Search indirect imports, configuration names,
plugin registrations and package-data paths. Delete old implementations only
after every owned caller resolves the new one.

## Quality gates

- Ordinary, boundary and failing inputs preserve observable results.
- Side effects remain atomic and happen the same number of times.
- Package installation and resource lookup work outside the source tree.
- Static import/type contracts pass after moves.
- Public compatibility breaks are separately authorized and documented.

## Failure and recovery

A test that only reproduces private call choreography can block a safe change
without protecting behavior; prefer a public result assertion, but do not weaken
an assertion merely to get green. Avoid catch-all compatibility wrappers and
fallback imports that hide broken packaging. If a move fails, revert only the
owned transformation through the approved workflow, not unrelated local work.

Source: [Python import system](https://docs.python.org/3/reference/import.html).
