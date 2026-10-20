# Docs as code

Treat documentation like source: it lives in the repository, changes in the
same pull request as the behavior it describes, is reviewed, linted, built and
tested in CI, and has an owner.

## Principles

1. **Same change, same review.** A behavior change and its documentation
   update land together. A reviewer who sees one without the other asks why.
2. **One source of truth per fact.** Generate reference material from code,
   schemas and configuration; link instead of copying values. Two places that
   state the same default will disagree within a few releases.
3. **Plain text formats** (Markdown, reStructuredText, AsciiDoc) that diff and
   merge well. Diagrams as text (Mermaid, PlantUML) where the renderer
   supports them, so they are reviewed like code.
4. **Executable examples.** Commands and snippets in docs are run in CI or
   explicitly labeled as illustrative.
5. **Owners.** CODEOWNERS or an equivalent maps each docs area to the people
   who review it.

## Checks to automate

| Check | Purpose | Examples of tools |
| --- | --- | --- |
| Markdown lint | consistent structure, headings, lists, code fences | markdownlint |
| Spelling | catch typos; maintain a project word list | cspell, codespell |
| Prose style | product terms, inclusive language, passive voice | Vale |
| Link check | broken internal and external links | lychee, the static site generator's own checker |
| Build | the site builds without warnings treated as errors | Sphinx `-W`, MkDocs `--strict` |
| Example execution | snippets still run | doctest, pytest `--doctest-glob`, a script that runs fenced commands |
| Generated reference freshness | committed generated docs match the source | regenerate in CI and diff |

Run the same checks locally through the repository's task runner so a writer
sees failures before CI does. Keep external link checks out of the blocking
gate or rate-limit them; third-party sites fail for reasons unrelated to the
change.

## Pull request checklist for documentation

- The page kind is clear (see [Diataxis](diataxis.md)) and the title says what
  the reader gets.
- Prerequisites, versions and working directory are stated before commands.
- Every command was run in the declared environment, or is labeled
  illustrative.
- Defaults, limits and error messages match the implementation and tests.
- Obsolete statements made false by the change are removed or marked
  superseded; no second page now contradicts this one.
- Examples use synthetic data: no real tokens, host names, customer or personal
  data.
- Links resolve; images have alt text; tables have header rows.
- The changelog has an entry when users can observe the change (see
  [changelog](changelog.md)).

## Versioned documentation

When several released versions are supported at once:

- Build documentation per release tag and publish each under its version, with
  a "latest" alias and a banner on outdated versions.
- Mark additions with the version that introduced them ("Added in 2.3").
- Never edit published documentation of an old version except for security or
  correctness notes.

## README, CONTRIBUTING and other root files

Root files are the most-read documentation and should stay short:

- `README.md`: what it is, who it is for, quick start, where to read more.
  Start from the [README template](../assets/README.md.template).
- `CONTRIBUTING.md`: how to set up, run checks, propose changes.
- `CHANGELOG.md`: user-visible changes per release, from the
  [changelog template](../assets/CHANGELOG.md.template).
- `SECURITY.md`: how to report vulnerabilities privately.
- `LICENSE`: the license text, unmodified.

## Sources

- [Write the Docs: docs as code](https://www.writethedocs.org/guide/docs-as-code/)
- [GitHub: about READMEs](https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/customizing-your-repository/about-readmes)
- [GitHub: setting guidelines for repository contributors](https://docs.github.com/en/communities/setting-up-your-project-for-healthy-contributions/setting-guidelines-for-repository-contributors)
- [GitHub: adding a security policy](https://docs.github.com/en/code-security/how-tos/report-and-fix-vulnerabilities/configure-vulnerability-reporting/add-security-policy)
- [markdownlint rules](https://github.com/DavidAnson/markdownlint/blob/main/doc/Rules.md)
- [Vale documentation](https://docs.vale.sh/)
- [MkDocs configuration: strict](https://www.mkdocs.org/user-guide/configuration/#strict)
- [Sphinx build options](https://www.sphinx-doc.org/en/master/man/sphinx-build.html)
