# Secrets scanning

A credential committed once is compromised, even if the next commit removes
it: history, forks, caches and CI logs keep it. Scanning prevents most leaks;
rotation is the only real fix for the rest.

## Layers of defense

| Layer | Tool examples | When it runs | Catches |
| --- | --- | --- | --- |
| Editor / pre-commit | detect-secrets hook, gitleaks | before a commit exists | new secrets in staged files |
| CI on every change | same scanner, all files | every pull request | anything that bypassed hooks |
| CI scheduled, full history | gitleaks on the git history | nightly or weekly | old leaks, new detection rules |
| Hosting platform | GitHub secret scanning and push protection | on push | known provider token formats |
| Runtime | secret stores, short-lived tokens | always | reduces the value of any leak |

## Baselines (detect-secrets)

detect-secrets compares findings against an audited baseline file so the hook
only reports *new* candidates:

```text
detect-secrets scan > .secrets.baseline            # create once
detect-secrets audit .secrets.baseline             # mark each finding true/false positive
pre-commit run detect-secrets --all-files          # check-only run against the baseline
```

- Commit the baseline and review changes to it like code; an added entry is a
  claim that something is *not* a secret.
- Re-audit after upgrading the scanner, because new plugins add candidates.
- Prefer excluding a specific file or using an inline allowlist comment over
  disabling a detector globally.

Regenerating the baseline is a fix action, not a check. A gate step that runs
`scan --baseline` and rewrites the file can silently accept a new secret.

## What not to commit

- Real credentials of any kind, including "temporary" or test credentials for
  shared environments.
- `.env` files with values; commit a `.env.example` with placeholders.
- Private keys, certificates with keys, Kubernetes config files, cloud CLI profiles.
- Logs, HAR files or recorded HTTP fixtures that contain authorization headers
  or cookies; scrub recordings before saving them.

Test fixtures need obviously fake values (`test-token`, `example.invalid`), so
scanners and reviewers can tell them apart from real ones.

## When a secret leaks

1. **Revoke or rotate it first.** Assume it is already copied.
2. Check the provider's access logs for use since the leak.
3. Remove it from the current tree and replace usage with a secret store or
   environment injection.
4. Decide whether to rewrite history (only meaningful before wide
   distribution; rotation is still mandatory).
5. Add a detection rule or test that would have caught it, and record the
   incident without repeating the secret.

## CI hygiene that limits exposure

- Give workflows the minimum `permissions` (start from `contents: read`).
- Do not persist checkout credentials when later steps do not need them.
- Never echo secrets; mask custom values; do not upload environment dumps as
  artifacts.
- Pin third-party actions to commit SHAs.

## Sources

- detect-secrets, [project documentation](https://github.com/Yelp/detect-secrets)
- gitleaks, [project documentation](https://github.com/gitleaks/gitleaks)
- GitHub, [About secret scanning](https://docs.github.com/en/code-security/secret-scanning/introduction/about-secret-scanning)
- GitHub, [Security hardening for GitHub Actions](https://docs.github.com/en/actions/security-for-github-actions/security-guides/security-hardening-for-github-actions)
- GitHub, [Controlling permissions for GITHUB_TOKEN](https://docs.github.com/en/actions/writing-workflows/choosing-what-your-workflow-does/controlling-permissions-for-github_token)
