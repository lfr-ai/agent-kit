"""Run repository-owned check commands without changing input files.

``all`` checks the lock first, then runs the read-only static gates in parallel and
prints each gate's output in declaration order with a timing summary. Tests run last,
only after every static gate passes, because they already use every core.
``static`` runs only the parallel static gates; the pre-push hook uses it so pushes
and CI share one gate registry.
"""

import argparse
from concurrent.futures import ThreadPoolExecutor
import contextlib
import io
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import threading
import time

from agent_kit.infrastructure.apm import APM_ENVIRONMENT_FLAGS

_ROOT = Path(__file__).resolve().parent.parent
_PYTHON = sys.executable
_ALL = "all"  # pseudo-gate: every deterministic check in declaration order
_STATIC = "static"  # pseudo-gate: parallel read-only gates without lock/tests
_FIRST = "lock"
_LAST = "tests"
# A gate that exceeds its bound is reported as failed instead of hanging the loop.
_GATE_TIMEOUT_SECONDS = 900
_TESTS_TIMEOUT_SECONDS = 5400
_DRAIN_SECONDS = 10
_running: set[subprocess.Popen[str]] = set()
_RUNNING_LOCK = threading.Lock()
_TASKKILL = Path(os.environ.get("SYSTEMROOT", r"C:\Windows")) / "System32/taskkill.exe"
_CHECKS = {
    "lock": ("uv", "lock", "--check"),
    "format": (_PYTHON, "-m", "ruff", "format", "--check"),
    "lint": (_PYTHON, "-m", "ruff", "check"),
    "types": (_PYTHON, "-m", "ty", "check"),
    "architecture": ("lint-imports",),
    "source": (_PYTHON, "-m", "scripts.checks.source"),
    "profiles": (_PYTHON, "scripts/build_profiles.py"),
    "native": (_PYTHON, "-m", "scripts.checks.native"),
    "roles": (_PYTHON, "-m", "scripts.render_native"),
    "coverage": (_PYTHON, "-m", "scripts.checks.coverage"),
    "conventions": (_PYTHON, "-m", "scripts.checks.conventions"),
    "suppressions": (_PYTHON, "-m", "scripts.checks.suppressions"),
    "governance": (_PYTHON, "-m", "scripts.checks.governance"),
    "delivery": (
        _PYTHON,
        "packages/delivery/check.py",
        "--workflow-root",
        ".github/workflows",
    ),
    "licenses": (
        _PYTHON,
        "packages/shared/.apm/skills/kit-agent-runtime/assets/license_guard.py",
        "--allowlist",
        "license-allowlist.json",
    ),
    "pins": (
        _PYTHON,
        "packages/shared/.apm/skills/kit-verify-change/assets/check_pins.py",
        "--root",
        ".",
    ),
    "drift": ("apm", "audit", "--ci", "--policy", "./apm-policy.yml", "--no-fail-fast"),
    "docs": (_PYTHON, "-m", "scripts.checks.docs"),
    "tests": (
        _PYTHON,
        "-m",
        "pytest",
        "--numprocesses=auto",
        "--cov",
        "--cov-report=term-missing:skip-covered",
    ),
}
# Network gates are selected explicitly so the default gate stays deterministic.
_NETWORK_CHECKS = {
    "dependencies": (_PYTHON, "scripts/audit_dependencies.py"),
}


def _timeout(name: str) -> int:
    return _TESTS_TIMEOUT_SECONDS if name == _LAST else _GATE_TIMEOUT_SECONDS


def _command(name: str, command: tuple[str, ...]) -> list[str] | None:
    executable = shutil.which(command[0])
    if executable is None:
        sys.stderr.write(f"{name}: required executable {command[0]} is missing\n")
        return None
    return [executable, *command[1:]]


def _kill_tree(process: subprocess.Popen[str]) -> None:
    """Kill a gate and its descendants; killing only the child can leave pipes open."""
    if os.name == "nt":
        subprocess.run(  # noqa: S603 - fixed system command, no shell
            [
                str(_TASKKILL),
                "/T",
                "/F",
                "/PID",
                str(process.pid),
            ],
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    else:
        with contextlib.suppress(ProcessLookupError):
            os.killpg(process.pid, signal.SIGKILL)
    process.kill()


def _run_gate(
    name: str, resolved: list[str], env: dict[str, str], *, capture: bool
) -> tuple[int, str]:
    """Run one resolved gate with its timeout; return code and captured output."""
    try:
        with _RUNNING_LOCK:
            process = subprocess.Popen(  # noqa: S603 - fixed repository commands, no shell
                resolved,
                cwd=_ROOT,
                # Python gates otherwise write the locale code page into the UTF-8 pipe.
                env=env | {"PYTHONIOENCODING": "utf-8"} if capture else env,
                stdout=subprocess.PIPE if capture else None,
                stderr=subprocess.STDOUT if capture else None,
                text=True,
                encoding="utf-8",
                errors="replace",
                # POSIX: a new session lets killpg reach grandchildren; Windows uses taskkill /T.
                start_new_session=os.name != "nt",
            )
            _running.add(process)
    except OSError as error:
        return 1, f"{name}: unable to start {resolved[0]}: {error}\n"
    try:
        output, _ = process.communicate(timeout=_timeout(name))
    except subprocess.TimeoutExpired:
        _kill_tree(process)
        with contextlib.suppress(subprocess.TimeoutExpired):
            process.communicate(timeout=_DRAIN_SECONDS)
        return 1, f"{name}: timed out after {_timeout(name)} s\n"
    except BaseException:
        _kill_tree(process)
        raise
    finally:
        with _RUNNING_LOCK:
            _running.discard(process)
    return process.returncode, output or ""


def _kill_running() -> None:
    """Kill every running gate tree; gates in their own session miss terminal signals."""
    with _RUNNING_LOCK:
        running = list(_running)
    for process in running:
        _kill_tree(process)


def _interrupt(_signum: int, _frame: object) -> None:
    raise KeyboardInterrupt


def _stream(name: str, command: tuple[str, ...], env: dict[str, str]) -> int:
    """Run one gate with inherited output so interactive use stays live."""
    resolved = _command(name, command)
    if resolved is None:
        return 1
    sys.stdout.write(f"Gate: {name}\n")
    sys.stdout.flush()
    code, message = _run_gate(name, resolved, env, capture=False)
    sys.stderr.write(message)
    return code


def _captured(
    name: str, command: tuple[str, ...], env: dict[str, str]
) -> tuple[int, str, float]:
    """Run one gate with captured output; return code, output and seconds."""
    started = time.monotonic()
    resolved = _command(name, command)
    if resolved is None:
        return 1, "", 0.0
    code, output = _run_gate(name, resolved, env, capture=True)
    return code, output, _elapsed(started)


def _elapsed(started: float) -> float:
    return time.monotonic() - started


def _run_static(env: dict[str, str]) -> int:
    """Run every read-only static gate in parallel and print a summary."""
    static = [name for name in _CHECKS if name not in {_FIRST, _LAST}]
    workers = min(len(static), os.cpu_count() or 1)
    pool = ThreadPoolExecutor(max_workers=workers)
    try:
        futures = {
            name: pool.submit(_captured, name, _CHECKS[name], env) for name in static
        }
        results = {name: future.result() for name, future in futures.items()}
    except BaseException:
        pool.shutdown(wait=False, cancel_futures=True)
        _kill_running()
        raise
    pool.shutdown()
    for name in static:
        _, output, _ = results[name]
        sys.stdout.write(f"Gate: {name}\n{output}")
    sys.stdout.write("\nSummary:\n")
    for name in static:
        code, _, seconds = results[name]
        status = "pass" if code == 0 else f"FAIL ({code})"
        sys.stdout.write(f"  {name:<14}{status:<12}{seconds:7.1f} s\n")
    sys.stdout.flush()
    return next((results[name][0] for name in static if results[name][0]), 0)


def _run_all(env: dict[str, str]) -> int:
    """Lock first, static gates in parallel, then tests after a clean static pass."""
    lock_code = _stream(_FIRST, _CHECKS[_FIRST], env)
    if lock_code:
        return lock_code
    static_code = _run_static(env)
    if static_code:
        return static_code
    return _stream(_LAST, _CHECKS[_LAST], env)


def main() -> int:
    """Run one named gate or every deterministic gate and report failures."""
    checks = {**_CHECKS, **_NETWORK_CHECKS}
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "gate", choices=[_ALL, _STATIC, *checks], nargs="?", default=_ALL
    )
    args = parser.parse_args()
    env = dict(os.environ)
    env.update(APM_ENVIRONMENT_FLAGS)
    if args.gate == _ALL:
        return _run_all(env)
    if args.gate == _STATIC:
        return _run_static(env)
    return _stream(args.gate, checks[args.gate], env)


if __name__ == "__main__":
    # A piped code-page stdout must not crash on replaced gate output.
    if isinstance(sys.stdout, io.TextIOWrapper):
        sys.stdout.reconfigure(errors="replace")
    # Termination becomes KeyboardInterrupt so running gate trees are killed.
    for _signal_name in ("SIGTERM", "SIGHUP"):
        if hasattr(signal, _signal_name):
            signal.signal(getattr(signal, _signal_name), _interrupt)
    raise SystemExit(main())
