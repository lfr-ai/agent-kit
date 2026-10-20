---
name: kit-ui-review
description: Use when reviewing a user interface change for state completeness, responsiveness, clarity, and accessibility.
license: MIT
---

# Review the rendered experience

## Resources

- [Rendered review guide](references/guide.md): severity and acceptance gates.
- [UI review rubric](references/review-rubric.md): task hierarchy, state
  completeness, layout, content, interaction, accessibility, consistency,
  evidence discipline.
- [Visual regression](references/visual-regression.md): setup, capture choice,
  thresholds, baseline updates.
- [State and finding worksheet](assets/ui-review-worksheet.md),
  [review matrix](assets/review-matrix.json.template), and
  [review report](assets/review-report.md.template).
- Templates: [visual spec](assets/orders.visual.spec.ts.template),
  [layout resilience spec](assets/layout-resilience.spec.ts.template),
  [pseudo-locale helper](assets/pseudo-locale.ts.template) with
  [tests](assets/pseudo-locale.test.ts.template).

## Procedure

1. Read the guide; fill the worksheet and pick screens, states, viewports,
   preferences, and locales from the review matrix.
2. Inspect the actual route and identify the task the feature helps complete.
3. Review loading, empty, populated, long-content, validation, permission,
   network-failure, pending, and success states.
4. Check 320px reflow, wide layouts, 200% zoom, text spacing, and reduced motion.
5. Verify controls communicate action, disabled and pending state, and feedback.
6. Check keyboard order, visible unobscured focus, labels, and announced updates.
7. Confirm color and icons are not the sole carriers of meaning.
8. Review content: verbs, terminology, locale formats, truncation, and
   pseudo-localized expansion; check destructive-action recovery.
9. Compare neighboring screens for established terminology and patterns.
10. Use only synthetic or redacted screenshots; separate observations from
    inferences.
11. Rate findings by task impact; give reproduction, impact, repair, and retest
    evidence for each.
12. Mark unseen states and unavailable browser or assistive-technology checks; a
    source review or screenshot alone is not rendered-interaction verification.

## Acceptance gates

- [ ] Every matrix state was seen or listed as not verified with a reason.
- [ ] Findings have severity, state, viewport, evidence, and a concrete repair.
- [ ] Reflow, zoom, text spacing, and pseudo-locale checks ran or are listed as
      not run.
- [ ] Visual baselines (if used) were reviewed image by image.
