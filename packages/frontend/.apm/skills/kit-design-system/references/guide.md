# Design tokens and theming

Reviewed 2026-10-23 against Tailwind CSS 4.3, shadcn/ui documentation, and
WCAG 2.2. Confirm the installed versions before copying syntax; the CSS-first
configuration below does not apply to Tailwind 3 projects.

## Token layers

| Layer | Example name | Who may reference it | Changes when |
| --- | --- | --- | --- |
| Palette (raw) | `--palette-blue-600` | Semantic layer only | Brand palette changes |
| Semantic role | `--color-action`, `--color-text-muted` | Components, utilities | Theme or mode changes |
| Component | `--button-height-md` | One component | That component needs a separate dial |

- Name semantic tokens by role and state (`surface`, `surface-raised`,
  `text`, `text-muted`, `action`, `action-foreground`, `border`, `focus-ring`,
  `danger`, `success`), never by hue (`blue`), so dark mode swaps values only.
- Pair every background role with a foreground role (`action` with
  `action-foreground`) so contrast is checked per pair, not per color.
- Cover color, spacing, typography (family, size, line height, weight),
  radius, shadow, and motion (duration, easing). Breakpoints and container
  sizes are tokens too.
- Prefer `oklch()` for palette values: perceptual lightness makes contrast
  steps predictable. Keep a fallback only if a supported browser lacks it.

## Tailwind CSS v4 configuration

| Decision | Choose | Reason |
| --- | --- | --- |
| Token source | `@theme { ... }` in the main CSS file | Generates utilities and CSS variables from one place |
| Runtime-switchable values | `:root` / `.dark` variables mapped by `@theme inline` | Utilities reference the variable, so themes swap without rebuilding |
| Remove default palette | `--color-*: initial;` inside `@theme` | Prevents off-system utilities such as `bg-red-500` |
| Dark mode trigger | `@custom-variant dark (&:where(.dark, .dark *));` or default media query | Pick one; a class enables a user toggle |
| JavaScript config | Only via `@config` for a plugin without a CSS-first form | Two sources of truth drift |
| Arbitrary values | `w-[37px]`, `bg-[#123456]` are findings | Bypass the token scale and dark mode |
| Content detection | Automatic; add `@source` only for files outside the project root | Explicit lists rot |

`@theme` must be top level, not nested in selectors or media queries. Use
`:root` for variables that should not create utilities.

## Dark mode and preferences

- Override semantic variables under `.dark` (or the media query); components
  stay identical. Set `color-scheme` so native controls match.
- Apply the stored or system theme before first paint (inline script in the
  document head or server-rendered class) to avoid a flash of the wrong theme.
- Under `prefers-reduced-motion: reduce`, set motion duration tokens to zero
  or switch to opacity-only transitions.
- Under `forced-colors: active`, keep borders and focus outlines visible with
  system colors; do not rely on shadows or background color alone.

## shadcn/ui ownership

- The CLI copies component source into the repository. From then on it is
  your code: review it, keep it under your lint, type, and test gates, and
  change it freely.
- Map its CSS variables (`--background`, `--foreground`, `--primary`,
  `--primary-foreground`, `--muted`, `--border`, `--ring`, `--radius`) to the
  semantic layer instead of keeping a parallel palette.
- Record the upstream registry item and date in the component file header or
  worksheet; compare upstream changes deliberately rather than re-running the
  CLI over local edits.
- Keep Radix or Base UI primitives for behavior; do not re-implement focus
  management a primitive already provides.

## Variants with class-variance-authority

- One `cva` definition per component; derive props with `VariantProps`.
- Always set `defaultVariants`; use `compoundVariants` for real combinations
  only, not to emulate boolean mode props.
- Merge consumer classes last with a conflict-aware merger (`tailwind-merge`)
  so overrides are predictable.
- Keep semantics (element, ARIA, keyboard) outside variants; a variant changes
  appearance, not role.

## Contrast and accessibility of tokens

| Pair | WCAG 2.2 AA minimum |
| --- | --- |
| Body text on its surface | 4.5:1 |
| Large text (24px, or 18.66px bold) | 3:1 |
| UI component boundary, focus indicator, icon conveying meaning | 3:1 against adjacent colors |
| Disabled controls | Exempt, but keep them identifiable |

Check every semantic pair in light and dark themes and in hover, focus, and
selected states. Use the measurement steps in the `kit-accessibility` skill.

## Failure modes and anti-patterns

| Symptom | Cause | Repair |
| --- | --- | --- |
| Dark mode misses some components | Hue-named tokens or hard-coded colors | Semantic roles; run the scan |
| Utility class missing at build | Token defined in `:root` instead of `@theme` | Move or map with `@theme inline` |
| Theme flash on load | Theme class applied after hydration | Apply before first paint |
| Copied component diverges silently | CLI re-run over local edits | Record origin, diff deliberately |
| Variant explosion | Boolean props per style | `cva` variants with compounds |
| Focus ring invisible in dark mode | Ring token not overridden | Pair `focus-ring` with each surface |

## Verification

1. Build the CSS and confirm expected utilities exist for new tokens.
2. Run `check_design_tokens.py` on changed files (exit 1 on findings).
3. Render stories in light, dark, forced colors, and reduced motion; run the
   accessibility addon and contrast measurements per pair.
4. Review visual diffs image by image (see the `kit-ui-review` skill).

## Primary sources

- Tailwind CSS theme variables: <https://tailwindcss.com/docs/theme>
- Tailwind CSS dark mode: <https://tailwindcss.com/docs/dark-mode>
- Tailwind CSS functions and directives: <https://tailwindcss.com/docs/functions-and-directives>
- shadcn/ui theming: <https://ui.shadcn.com/docs/theming>
- shadcn/ui Tailwind v4 notes: <https://ui.shadcn.com/docs/tailwind-v4>
- class-variance-authority: <https://cva.style/docs>
- Design Tokens Community Group format: <https://www.designtokens.org/tr/drafts/format/>
- WCAG 2.2 contrast (minimum): <https://www.w3.org/WAI/WCAG22/Understanding/contrast-minimum.html>
- WCAG 2.2 non-text contrast: <https://www.w3.org/WAI/WCAG22/Understanding/non-text-contrast.html>
- CSS Color Level 4 (`oklch`): <https://www.w3.org/TR/css-color-4/>
