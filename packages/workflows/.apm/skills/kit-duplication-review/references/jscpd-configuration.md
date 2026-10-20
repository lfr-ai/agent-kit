# jscpd configuration

jscpd detects copy-paste by tokenizing source in a language-aware way and
searching for repeated token sequences. These notes cover the options that
matter for reviews. Option names and defaults change between major versions;
check `jscpd --help` for the installed version and record it with results.

## Installing and running

- Run without installing: `npx jscpd <paths>`.
- Pin the version in CI (for example as a dev dependency, a tool manifest, or
  `npx jscpd@<version>`), so thresholds do not drift with releases.
- Configuration is discovered from `.jscpd.json` at the working directory, or
  passed explicitly with `--config <file>`. Command-line flags override file
  values.
- Keys in the configuration file are camelCase versions of the long flags
  (`--min-tokens` becomes `minTokens`).

## Options that shape detection

| Key | Flag | Effect | Review guidance |
| --- | --- | --- | --- |
| `format` | `--format` | Languages to scan | List only the project's languages; unknown names fail the run |
| `minTokens` | `--min-tokens` | Smallest clone, in tokens | 50-100 for application code; lower finds trivia |
| `minLines` | `--min-lines` | Smallest clone, in lines | 5-10; pair with `minTokens` so long thin code is not over-reported |
| `maxLines` | `--max-lines` | Skip source files longer than this | Use to skip giant generated files you cannot exclude by path |
| `maxSize` | `--max-size` | Skip files larger than a size | Same purpose as `maxLines` for minified assets |
| `mode` | `--mode` | `strict`, `mild` (default) or `weak` | `mild` ignores whitespace and comments; `weak` also ignores more tokens |
| `ignore` | `--ignore` | Glob patterns to exclude | Generated, vendored, build, snapshots, fixtures |
| `ignorePattern` | `--ignore-pattern` | Regular expressions removed before tokenizing | License headers and generated banners; keep patterns narrow |
| `gitignore` | `--gitignore` | Respect `.gitignore` | Turn on to avoid scanning build output |
| `skipLocal` | `--skip-local` | Ignore clones inside one directory | Useful when a folder intentionally holds parallel variants |
| `threshold` | `--threshold` | Fail when total duplication percentage exceeds this | A ratchet, not a target; see below |
| `reporters` | `--reporters` | Output formats such as `console`, `json`, `html`, `markdown`, `sarif` | Always include `json` for the summarizer |
| `output` | `--output` | Directory for file reporters | Keep out of source folders and in `ignore` |
| `absolute` | `--absolute` | Absolute paths in reports | Leave off so reports compare across machines |

Recent releases add opt-in detection of clones that differ only in names or
literals, near-miss merging, baselines that fail only on new clones, and
changed-file scans. Prefer a baseline or changed-file gate in CI over a global
percentage when the codebase already has legacy duplication.

## Ignoring regions in source

Wrap a region in comments containing `jscpd:ignore-start` and
`jscpd:ignore-end`, using the language's comment syntax:

```python
# jscpd:ignore-start
STATUS_LABELS = {"draft": "Draft", "sent": "Sent", "paid": "Paid"}
# jscpd:ignore-end
```

Use in-source suppression only with a reason in the surrounding comment and
only for intentional duplication (for example, a mirrored table that a test
compares against). Path-level exclusions belong in `ignore`.

## Choosing thresholds

1. Measure the current percentage on the main branch with the final
   configuration; record it with the jscpd version.
2. Set `threshold` slightly above the measured value so the gate fails only on
   growth.
3. Lower it after each cleanup that reduces duplication. Never raise it to make
   a change pass; record a decision for the specific clone instead.
4. For pull requests, a per-clone gate (the summarizer's `--min-lines`) or a
   baseline of known clones is more useful than a global percentage, which a
   large change can dilute.

## Scope recipes

| Situation | Paths and options |
| --- | --- |
| Pull request review | Changed packages only; `minLines` 8, `minTokens` 70 |
| Test code review | Test folders with `minLines` 12; table-driven tests often look duplicated by design |
| Monorepo audit | Each package separately, then across packages for shared-library candidates |
| Infrastructure as code | `format` for the template languages; expect module-like repetition and judge by environment ownership |
| Documentation | `format` `markdown`; repeated warnings and snippets are often intentional |

## Interpreting the JSON report

The `json` reporter writes `jscpd-report.json` in the output directory. Each
entry in `duplicates` has a `format`, `lines`, `tokens`, and `firstFile` and
`secondFile` objects with `name` and start and end lines; `statistics.total`
holds overall counts and `percentage`. The
[summarizer](../assets/summarize_jscpd_report.py) validates that shape and
fails loudly if a version changes it.

## Sources

- [jscpd repository and documentation](https://github.com/kucherenko/jscpd)
- [jscpd on npm](https://www.npmjs.com/package/jscpd)
- [npx documentation](https://docs.npmjs.com/cli/commands/npx)
