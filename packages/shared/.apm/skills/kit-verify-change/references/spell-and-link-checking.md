# Spell checking and link checking

Documentation, identifiers, CLI help and error messages are user interface.
Typos in them cost search hits and trust; dead links strand readers. Both are
cheap to check automatically.

## Spell checking with CSpell

[`cspell.json.template`](../assets/cspell.json.template) is a starting
configuration:

- `dictionaries` enables built-in technical dictionaries (software terms,
  Python, shell) plus a project word list.
- `dictionaryDefinitions` points `project-words` at a plain text file, one
  word per line, kept sorted. Words go there only when they are real terms of
  the project (product names, domain vocabulary, tool names).
- `ignorePaths` excludes generated, vendored and lock files.
- `ignoreRegExpList` skips hashes, URLs and long upper-case tokens so they are
  not reported as misspellings.
- `flagWords` turns words into errors even when a dictionary accepts them:
  terms the project has retired (for example `blacklist` in favor of
  `denylist`) or misspellings that happen to be valid words.
- `overrides` adjust settings per file type (for example ignore fenced code
  blocks in Markdown).

Running it:

```text
npx --yes cspell@10 lint --no-progress --gitignore .
npx --yes cspell@10 lint --no-progress --no-summary "docs/**/*.md" "src/**/*.py"
npx --yes cspell@10 --words-only --unique "src/**/*.py"     # list unknown words
```

Triage each unknown word:

1. **Misspelling** - fix it. Rename identifiers with a refactoring tool.
2. **Real project term** - add it to the project word list in the same change.
3. **Foreign token** (hash, base64, generated identifier) - add an ignore
   pattern or exclude the file; do not add the token as a word.
4. **Abbreviation used once** - prefer spelling it out.

Never add a word just to make the check pass if it is actually a typo. Keep the
word list reviewed: an entry that matches nothing anymore can be removed.

Inline directives (`cspell:ignore word`, `cspell:disable-next-line`) are for
rare, local exceptions; a growing number of them means the configuration needs
a pattern or a dictionary instead.

## Link checking with lychee

lychee checks URLs and local file links in Markdown, HTML and other text:

```text
lychee --no-progress "**/*.md"                     # all Markdown files
lychee --no-progress --offline "**/*.md"           # local links only, no network
lychee --no-progress --config .lychee.toml "**/*.md"
```

Configuration worth setting in `.lychee.toml`: request timeout and retries,
accepted status codes, excluded hosts that block bots or require login,
caching of results between runs, and a user agent. Keep excludes specific
(one host or path) and commented.

Run local-only checks (`--offline`) in the fast tier: they are deterministic
and catch broken relative links immediately. Run network checks in the slow
tier or on a schedule; external sites go down, rate-limit and change, so a
network failure should create a visible report but not block unrelated work
for hours.

## What these checks do not prove

A passing spell check does not mean prose is correct or clear, and a resolving
link does not mean it points to the right or current content. Review those in
documentation changes.

## Sources

- CSpell, [Configuration](https://cspell.org/docs/Configuration)
- CSpell, [Getting started](https://cspell.org/docs/getting-started)
- CSpell, [Custom dictionaries](https://cspell.org/docs/dictionaries/custom-dictionaries)
- lychee, [project site](https://lychee.cli.rs/), [CLI guide](https://lychee.cli.rs/guides/cli/)
  and [configuration guide](https://lychee.cli.rs/guides/config/)
