# Plan observable vertical changes

## Start with evidence

Name the public behavior, caller, owning boundary, nearest implementation and
current test. Reuse existing mechanisms before proposing a new abstraction.
Separate desired behavior from incidental folder naming.

A slice must connect input to an observable result, including its important
failure path. Do not schedule all models, then all services, then all tests:
that postpones integration until there is too much to debug at once.

## Dependency and risk review

Record actual prerequisites, not list order. Schema changes, public contract
decisions and shared fixtures need one owner. Independent read-only research or
non-overlapping resources can proceed together. A worker must not begin an
implementation that depends on an unresolved interface.

For persistence changes, define old/new compatibility and rollback before the
first write. For external services, list offline tests separately from live
approval and unavailable credentials. Do not invent a deployment requirement.

## Quality gates

- Each slice names an owning path, observable test and completion condition.
- Negative inputs and recovery are covered at the changed trust boundary.
- A gate command is executable in the declared environment, not a slogan.
- Existing behavior that must remain stable is listed explicitly.
- Scope excludes unrelated cleanup and unsupported runtime claims.

## Failure and recovery

When evidence contradicts the plan, update remaining work and dependencies;
do not force code into an obsolete design. Stop before destructive work when
ownership or rollback is unknown. For small fixes the filled plan can be a few
lines; a large tracking document is not itself acceptance evidence.

Source: [GitHub issue planning](https://docs.github.com/en/issues/tracking-your-work-with-issues/about-issues).
