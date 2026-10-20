---
name: kit-accessibility
description: Use when implementing or reviewing inclusive interaction, semantics, keyboard use, and assistive-technology feedback.
license: MIT
---

# Verify accessible interaction

## Resources

- [Interaction guide](references/guide.md): negative cases and recovery gates.
- [WCAG 2.2 AA checks](references/wcag22-checks.md): criteria mapped to
  automated, test, or manual verification, including the 2.2 additions.
- [ARIA patterns, focus, and announcements](references/aria-patterns.md):
  native-first selection, composite keyboard model, names, focus rules, live
  regions, hiding techniques.
- [Accessibility worksheet](assets/accessibility-worksheet.md) per flow and
  [component checklist](assets/component-checklist.md.template) per component.
- Templates: [axe helper for component tests](assets/axe.ts.template),
  [app announcer](assets/announcer.tsx.template),
  [tabs pattern](assets/tabs.tsx.template) with
  [tests](assets/tabs.test.tsx.template).

## Procedure

1. Read the guide; fill the worksheet for the changed flow and the checklist for
   each changed component.
2. Identify the primary task, input methods, and meaningful success or error
   feedback.
3. Use native elements matching the action; links navigate and buttons act.
   Add ARIA only with its full keyboard model.
4. Associate every input with a visible label; explain required formats before
   submission.
5. Test all controls by keyboard: order, activation, arrows in composites,
   Escape, and focus return.
6. Keep focus visible and unobscured; move it only on intentional context changes.
7. Assert roles and accessible names in tests with role queries.
8. Announce asynchronous outcomes through persistent live regions without moving
   focus or repeating every update.
9. Tie errors to fields in text and make them reachable after submission.
10. Check contrast, 320px reflow and zoom, text spacing, reduced motion, target
    size, and dragging alternatives on real component states.
11. Run axe in component tests and in a real browser; inspect the accessibility
    tree; test a representative flow with a screen reader when available.
12. Record unavailable checks. A clean scan or tree inspection is not evidence of
    screen-reader usability.

## Acceptance gates

- [ ] Component and browser axe scans report no violations, or each exclusion is
      owned and justified.
- [ ] Keyboard-only completion of the flow is tested.
- [ ] Focus destinations for open, close, delete, error, and navigation are tested.
- [ ] Status and errors are announced and associated correctly.
- [ ] WCAG 2.2 additions (2.4.11, 2.5.7, 2.5.8, 3.2.6, 3.3.7, 3.3.8) were checked
      where they apply.
- [ ] Manual and assistive-technology evidence is reported separately from
      automated results.
