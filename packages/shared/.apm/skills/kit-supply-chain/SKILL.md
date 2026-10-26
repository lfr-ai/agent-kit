---
name: kit-supply-chain
description: Use when adding or auditing dependencies, lockfiles, pins, SBOMs or provenance, or a package is compromised.
license: MIT
---

# Manage third-party dependencies and their provenance

Every package, action, image and build tool runs code you did not write.
Admit it deliberately, lock it by hash, audit it before it is installed, and
keep evidence of what shipped. Start with the [guide](references/guide.md),
which routes each concern to the skill that owns it.

## Procedure

1. Classify the change: new dependency, upgrade, removal, automation pin
   (action, hook, image), release provenance, or incident. For an incident go
   straight to step 10.
2. For a new dependency, first show that the standard library or an existing
   dependency cannot do the job. Then fill the
   [adoption review](assets/dependency-adoption-review.md.template) using the
   criteria in [dependency selection](references/dependency-selection.md):
   maintenance, maintainers, release cadence, adoption, license and security
   posture (OpenSSF Scorecard). Popularity alone never approves a package.
3. Confirm the exact name, owner and index before the first install, so a
   look-alike name or a public package shadowing an internal name cannot be
   pulled in ([dependency selection](references/dependency-selection.md)).
4. Choose the constraint with
   [locking and auditing](references/locking-and-auditing.md): applications
   and tools lock exact versions; published libraries declare ranges and lock
   the tested build. Change the manifest and the lockfile together without
   installing, for example `uv add --no-sync <name>`.
5. Run the [lock freshness checker](assets/check_lock_freshness.py)
   (`python check_lock_freshness.py --project pyproject.toml --lock uv.lock`)
   to prove the lock matches the manifest and every artifact has a hash. Run
   the pin checker owned by the `kit-verify-change` skill (`check_pins.py`)
   for floating versions in hooks, workflows, images and package runners.
6. Audit the changed lock before installing it: `pip-audit` on the hashed
   export or OSV-Scanner on the lockfile, and `bun audit` or `npm audit` for
   JavaScript. Install only from the lock (`uv sync --locked`, `npm ci`,
   `bun install --frozen-lockfile`), preferring wheels over source builds.
7. Check licenses after installation with the license guard owned by the
   `kit-agent-runtime` skill, and mirror the same allow-list in pull-request
   dependency review.
8. Keep updates flowing through one update bot with a release-age cooldown;
   security updates skip the cooldown. Start from the Dependabot or Renovate
   templates owned by the `kit-repository-setup` skill.
9. For automation and releases, follow
   [provenance and SBOM](references/provenance-and-sbom.md): actions pinned by
   full commit SHA and scanned with zizmor (`kit-ci-review`), images pinned by
   digest (`kit-containers`), build provenance for published artifacts, and
   trusted publishing (`kit-release`). Adopt the
   [SBOM workflow](assets/sbom.yml.template) only for an explicit consumer,
   compliance, or release-inventory requirement; reuse existing audit tools.
10. When a dependency is reported compromised or malicious, follow
    [incident response](references/incident-response.md): freeze, scope,
    remove, rotate, rebuild, and record.
11. Remove what is no longer used: run deptry or the ecosystem equivalent,
    confirm dynamic imports and plugins by hand, then delete the declaration
    and regenerate the lock.
12. Record the project's rules once in the
    [supply-chain policy](assets/supply-chain-policy.md.template) and report
    what was checked, what was accepted and why, and what needs an operator.

## Acceptance gates

- Each new runtime dependency has a completed adoption review with dated
  evidence, a named owner and a revisit date.
- `check_lock_freshness.py` exits 0; the lock was audited before it was
  installed and no known vulnerability is accepted without a tracked,
  time-boxed exception.
- Installed licenses pass the allow-list; unknown metadata has a reviewed,
  expiring exception rather than a broader allow-list.
- Every action, hook and image is pinned to a full commit SHA or digest, and
  version updates carry a cooldown while security updates do not.
- Published artifacts have provenance bound to their digests, or the gap is
  recorded as a limitation. SBOM adoption has a stated requirement or deferral
  reason; adopted SBOMs are attested to the same released digests.
- Operator actions (registry settings, token rotation, advisories, branch
  rules) are listed as handoffs, not reported as done.
