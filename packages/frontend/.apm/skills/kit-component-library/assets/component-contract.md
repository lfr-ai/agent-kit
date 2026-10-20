# Shared component contract worksheet

- Primitive and semantic purpose: {{name, native element/widget pattern}}
- Existing consumers: {{consumer A, consumer B, shared behavior}}
- Keep feature-local: {{policy/data behavior or one-off counterexample}}
- Public export and supported stack: {{entrypoint, framework/version}}
- Tokens reused: {{color, spacing, typography, focus, motion}}

## API decisions

| Concern | Supported contract | Rejected combination or non-goal |
| --- | --- | --- |
| State ownership | {{controlled value/event OR default/internal ownership}} | {{mode switch or duplicate owner}} |
| Content and labels | {{content slots, label/description relationships}} | {{unnamed control}} |
| Native behavior | {{form type, attributes, ref/focus forwarding}} | {{silently swallowed attribute}} |
| Variants | {{evidenced variants}} | {{speculative mode}} |

## Behavioral gates

| Case | Expected outcome | Evidence or blocker |
| --- | --- | --- |
| Two labeled instances | Unique associations and independent state | {{result}} |
| Keyboard/default/focus | Correct activation and visible focus | {{result}} |
| Disabled, pending and invalid | Honest semantics, readable feedback, no unintended action | {{result}} |
| Controlled/default state changes | No drift or implicit mode switch | {{result}} |
| Long label, zoom, narrow width | No lost action, clipped label or obscured focus | {{result}} |
| Public-export use in both consumers | No hidden providers, form or style regressions | {{result}} |

## Adoption and recovery

- Compatibility change: {{old API to new API, or none}}
- Migration order and fallback: {{bounded callers, compatibility adapter/revert}}
- Exact type/component/consumer checks: {{commands and results}}
- Browser/visual checks and limits: {{environment, results or not run}}
- API decision: {{promote / keep local / repair; rationale}}
