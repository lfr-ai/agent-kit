---
description: Apply to CSS, Sass, and component styling.
applyTo: "**/*.css,**/*.scss"
---

- Reuse the project's design tokens and naming conventions before adding new values; do not hard-code colors, spacing, or type scales.
- Scope selectors to the component or feature with the project's scoping method; avoid global element overrides and `!important`.
- Keep specificity low and flat; avoid ID selectors and deep descendant chains.
- Preserve visible focus (`:focus-visible`), forced-colors support, and at least WCAG AA contrast for text and UI boundaries.
- Respect `prefers-reduced-motion` and do not encode status by color alone.
- Size with relative units and fluid flex or grid layouts with `clamp()`; avoid fixed heights on text containers.
- Check wrapping, 200% zoom, 320 CSS pixel width, and long or translated content.
- Use logical properties (`margin-inline`, `padding-block`) where layout should follow writing direction.
- Reserve space for media and asynchronous content to avoid layout shifts.
- Avoid brittle selectors that depend on DOM position or generated framework internals.
- Hide content visually with a visually-hidden utility, not `display: none`, when assistive technology must still reach it.
- Use the `kit-ui-review` skill for visual and accessibility review.
