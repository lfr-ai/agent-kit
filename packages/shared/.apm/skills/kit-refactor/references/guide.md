# Preserve behavior through structural change

## Characterize before moving

Identify public imports, calls, serialized values, exception types, ordering,
defaults, side-effect timing and cancellation. Run the owning tests before the
transformation. For poorly covered code add one focused characterization at
the boundary callers actually observe.

Move one responsibility at a time. Search indirect imports, configuration names,
plugin registrations and package-data paths. Delete old implementations only
after every owned caller resolves the new one.

## Naming and shared ownership

Group several cohesive feature modules within their existing layer before
stripping a repeated feature prefix. Do not create a one-file directory merely
to shorten a name. Preserve public facades and update string imports, patch
targets and installed-package inventories alongside normal imports.

Keep constants with their semantic owner; share a value only when callers use
the same contract, not merely the same spelling. Use enums for closed domain
choices, not for every path, header or protocol token. Factories, inheritance,
decorators and common base classes need an actual lifecycle, substitution or
repeated-behavior benefit.

Validate untrusted wire, environment, filesystem and SDK data at the boundary.
Repeated type checks inside an already validated model can be redundant;
boundary checks are not. Standard parsers may normalize unsafe input, so
characterize canonical spelling, traversal, origin and failure behavior before
replacing a predicate. Move an equivalent shared invariant to an inward owner;
do not merge validators with different acceptance contracts.

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
