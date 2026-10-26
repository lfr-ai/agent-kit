# Static analysis for security

Static analysis catches known-dangerous calls cheaply and on every change. It
cannot see design flaws, missing authorization or business logic abuse, so it
complements the threat model and negative tests. Review date: 2026-10-23.

## Tool roles

| Tool | Role | Where it runs | Notes |
| --- | --- | --- | --- |
| Ruff `S` (flake8-bandit) | fast per-file security lint | editor, pre-commit, gate | same rule ids as Bandit (`S` + Bandit number); see the [snippet](../assets/ruff-security.toml.template) |
| Bandit | reference implementation of the same checks with confidence and severity levels, SARIF output | CI | useful when a report format or baseline is required; avoid duplicating Ruff locally |
| Semgrep (community rules) | pattern and taint-style rules across files and frameworks | CI, scheduled | pin the rule set version; review new rules before blocking |
| CodeQL | deep data-flow analysis | hosted CI | operator-enabled code scanning |
| [check_secure_patterns.py](../assets/check_secure_patterns.py) | stdlib AST checker for the highest-risk Python calls | anywhere, no dependencies | small, explicit rule set for portable use |
| Secrets scanner | committed credentials | pre-commit, CI | see the `kit-verify-change` skill |

Pick Ruff `S` as the always-on baseline. Add one deeper tool (Semgrep or
CodeQL) for exposed services. Running Bandit and Ruff `S` side by side adds
noise without coverage.

## Checker rules

`check_secure_patterns.py` reports:

| Rule | Pattern | Why |
| --- | --- | --- |
| `shell-true` | any call with `shell=True` | shell parsing of arguments enables injection |
| `eval-exec` | `eval(...)`, `exec(...)` | executes arbitrary code |
| `pickle-load` | `pickle.load(s)`, `pickle.Unpickler`, `marshal.load(s)` | executes code during deserialization |
| `yaml-unsafe` | `yaml.load` without `SafeLoader`/`CSafeLoader`, `yaml.unsafe_load`, `yaml.full_load` | constructs arbitrary objects |
| `mktemp` | `tempfile.mktemp` | race between name and creation |
| `http-no-timeout` | `requests`/`httpx` request functions without `timeout=` | hangs forever on a stalled peer |

It resolves `import x as y` and `from x import y` aliases, ignores calls it
cannot attribute, and accepts `# secure: allow[rule] reason` on the same line
for a reviewed exception. It does not follow data flow, so a finding means
"review this call", not "exploitable".

```text
python check_secure_patterns.py src
python check_secure_patterns.py src --rule shell-true --rule eval-exec
```

Exit status: 0 clean, 1 findings, 2 usage or read errors.

## Suppression policy

- Suppress one rule on one line with a reason: `# noqa: S603 - fixed argv`.
- Never add a rule family to a global ignore list to pass a gate.
- Tests may ignore `S101` (assert) and fake-credential rules (`S105`, `S106`)
  per directory, as the snippet shows; nothing else by default.
- Review the suppression list in every security review; delete stale ones.

## Verification

1. Introduce one deliberate violation per rule in a scratch file; confirm Ruff
   and the checker report it.
2. Run the gate on the whole tree; record finding counts before and after the
   change.
3. Confirm CI runs the same configuration (no local-only rules).

## Primary sources

- Ruff, [flake8-bandit (S) rules](https://docs.astral.sh/ruff/rules/#flake8-bandit-s)
- [Bandit documentation](https://bandit.readthedocs.io/)
- [Semgrep documentation](https://semgrep.dev/docs/)
- GitHub, [About code scanning with CodeQL](https://docs.github.com/en/code-security/code-scanning/introduction-to-code-scanning/about-code-scanning-with-codeql)
- Python, [ast module](https://docs.python.org/3/library/ast.html)
