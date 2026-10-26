---
description: Apply to design tokens, theme CSS, and styled React components.
applyTo: "**/theme.css,**/tokens.css,**/components/**/*.tsx,**/ui/**/*.tsx"
---

- Reference semantic tokens (`bg-surface`, `text-foreground`, `var(--primary)`); never raw palette variables or hue names in components.
- Keep palette values, `@theme` scales, and light and dark semantic overrides in the single theme file; add no second token source or JavaScript Tailwind config without a plugin that requires it.
- Do not use hard-coded hex, `rgb()`, `oklch()` literals, or arbitrary pixel values (`w-[37px]`, `bg-[#123456]`) outside the theme file; mark an unavoidable exception with `design-tokens: allow` and its reason.
- Express visual variants with one `cva` definition and `defaultVariants`; variants change appearance only, never element, role, or keyboard behavior.
- Pair every background role with its foreground role and keep WCAG 2.2 AA contrast in light, dark, and forced-colors modes.
- Treat copied shadcn/ui components as owned source with recorded origin and the same tests as local components.
- Give each new variant or state a story with an interaction or accessibility check.
- Use the `kit-design-system` skill for token, theme, and Storybook procedures.
