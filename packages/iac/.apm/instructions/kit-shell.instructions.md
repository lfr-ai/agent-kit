---
description: Apply to shell scripts and operational command files.
applyTo: "**/*.sh,**/*.bash,**/*.ps1"
---

- Start Bash scripts with `set -euo pipefail`, and PowerShell scripts with `$ErrorActionPreference = 'Stop'` and `Set-StrictMode -Version Latest`.
- Quote every expansion and path; pass argument lists as arrays instead of relying on word splitting.
- Validate inputs, print usage when arguments are missing, and make failure exit codes explicit and non-zero.
- Avoid evaluating user-controlled text as code (`eval`, `Invoke-Expression`) or constructing shell commands by concatenation.
- Create temporary files through the platform API inside an owned directory and remove them in a `trap` or `finally` block.
- Guard recursive deletes against empty, root, or unchecked paths, and never delete outside the owned directory.
- Make retries bounded with backoff and operations idempotent where reruns are possible.
- Keep credentials out of arguments, transcripts, error messages, and committed files; read them from the environment or a secret store.
- Distinguish read-only inspection from destructive or remote side effects, and offer a dry-run mode for destructive scripts.
- Use only POSIX features in `sh` scripts and declare `bash` explicitly when Bash features are used.
- Lint with ShellCheck or PSScriptAnalyzer when available and report the result.
- Move logic that needs data structures or unit tests into the project language.
