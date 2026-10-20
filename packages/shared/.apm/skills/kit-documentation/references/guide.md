# Document the next reader's decision

## Procedure

Start with who needs the document and what they must do. Link the canonical
API/configuration rather than duplicating every option. Put prerequisites
before commands: version, working directory, input data, approval and effects.
Use synthetic examples; never publish a real token or private endpoint.

Show expected output shape and what failure looks like. For a mutating
procedure, include rollback and the point after which rollback is not safe.
Label illustrative commands that have not been exercised.

## Quality gates

- A reader without the authoring conversation can find the first action.
- Local links resolve and generated documentation has an owning source.
- Commands match the locked version and do not silently require global state.
- Defaults, errors and supported versions agree with implementation/tests.
- The page distinguishes inspection, executed tests and live certification.
- Old guidance made false by the change is removed or marked superseded.

## Failure and recovery

If the documented operation cannot run safely, validate syntax and explain the
unavailable prerequisite; do not claim it passed. If instructions conflict,
repair the authoritative page first and replace secondary text with a link.
Avoid introducing a second handbook that must be kept manually synchronized.

Source: [Diataxis](https://diataxis.fr/).
