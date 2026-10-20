---
description: Audit a screen or component for keyboard, focus, names and roles, form errors, announcements, contrast, and motion, reporting WCAG-mapped findings.
argument-hint: Screen, component, or path to audit
agent: ask
---

# Audit accessibility

Find barriers that stop people from completing the task with a keyboard,
screen reader, zoom, or reduced motion. Report; do not edit.

## Input

- The user-supplied argument names the screen, component, or path. When it is
  empty, audit the UI files changed in the working tree.

## Procedure

1. Load [kit-accessibility](../skills/kit-accessibility/SKILL.md) and fill its
   accessibility worksheet for the target.
2. Name the primary task and its success and error feedback.
3. Semantics: check that links navigate, buttons act, headings form an outline,
   landmarks exist, and lists and tables use native elements.
4. Names and roles: every control has an accessible name matching its visible
   label; ARIA appears only where native semantics are insufficient and is
   valid for the role.
5. Keyboard: tab order follows reading order, every action is reachable and
   operable, Escape closes overlays, focus returns to the trigger, and no trap
   exists.
6. Focus: focus is always visible and moves only on deliberate context
   changes.
7. Forms: labels are associated, required format is explained up front,
   errors are tied to fields in text, and an error summary is reachable.
8. Dynamic updates: asynchronous status uses a live region without moving
   focus or repeating every update.
9. Visual: text and non-text contrast, reflow at 400 percent zoom, target size,
   and reduced-motion handling in every component state.
10. When tooling is available, run the project's automated accessibility
    checks and record results; automated passes are not a full audit.
11. Cross-check component-level issues with
    [kit-ui-review](../skills/kit-ui-review/SKILL.md) for missing states.

## Acceptance gates

- [ ] Each finding cites `path:line` or a component state and the WCAG success
      criterion it violates.
- [ ] Findings state user impact and a concrete fix.
- [ ] Manual checks not performed (for example a screen reader run) are listed.

## Output

Findings grouped by severity (blocks task, degrades task, polish) with
location, criterion, impact, and fix; then passed checks and checks not run.
