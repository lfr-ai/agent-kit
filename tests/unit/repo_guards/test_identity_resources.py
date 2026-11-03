"""Exercise the identity boundary with a synthetic verifier, never a live tenant."""

import ast
from pathlib import Path
import runpy
import shutil
import subprocess
import sys
from types import SimpleNamespace

import pytest

_ROOT = Path(__file__).resolve().parents[3]
_SKILL = _ROOT / "packages/identity/.apm/skills/kit-identity"
_SYNTHETIC_TOKEN = "synthetic-access-token"  # noqa: S105 - deliberately fake credential


@pytest.fixture
def identity() -> SimpleNamespace:
    return SimpleNamespace(
        **runpy.run_path(str(_SKILL / "assets/access_policy.py.template"))
    )


def test_callback_binding_accepts_matching_values(identity: SimpleNamespace) -> None:
    binding = identity.LoginBinding(
        state="synthetic-state",
        nonce="synthetic-nonce",
        redirect_uri="https://app.example.test/callback",
        expires_at=100,
    )
    identity.validate_callback(
        binding=binding,
        state="synthetic-state",
        nonce="synthetic-nonce",
        redirect_uri="https://app.example.test/callback",
        now=99,
    )


@pytest.mark.parametrize(
    "overrides",
    [
        {"state": "other"},
        {"nonce": "other"},
        {"redirect_uri": "https://other.example.test/callback"},
        {"now": 100},
    ],
)
def test_callback_binding_rejects_mismatch_and_expiry(
    identity: SimpleNamespace, overrides: dict[str, object]
) -> None:
    binding = identity.LoginBinding(
        state="synthetic-state",
        nonce="synthetic-nonce",
        redirect_uri="https://app.example.test/callback",
        expires_at=100,
    )
    values = {
        "binding": binding,
        "state": "synthetic-state",
        "nonce": "synthetic-nonce",
        "redirect_uri": "https://app.example.test/callback",
        "now": 99,
    }
    with pytest.raises(identity.InvalidCallbackError):
        identity.validate_callback(**(values | overrides))


def _gate(
    identity: SimpleNamespace,
    *,
    scopes: frozenset[str] = frozenset({"orders.read"}),
    roles: frozenset[str] = frozenset({"Reader"}),
    issuer: str = "https://issuer.example.test/tenant/v2.0",
    audience: str = "api://orders",
) -> SimpleNamespace:
    class Verifier:
        def verify(self, *, access_token: str) -> object:
            assert access_token == _SYNTHETIC_TOKEN
            return identity.VerifiedAccess(
                issuer=issuer, audience=audience, scopes=scopes, roles=roles
            )

    return identity.AccessGate(
        verifier=Verifier(),
        issuer="https://issuer.example.test/tenant/v2.0",
        audience="api://orders",
    )


def test_access_gate_requires_scope_and_role(identity: SimpleNamespace) -> None:
    gate = _gate(identity)
    result = gate.require(
        access_token=_SYNTHETIC_TOKEN,
        scopes=frozenset({"orders.read"}),
        roles=frozenset({"Reader", "Administrator"}),
    )
    assert result.scopes == frozenset({"orders.read"})


@pytest.mark.parametrize(
    ("scopes", "roles"),
    [
        (frozenset(), frozenset({"Reader"})),
        (frozenset({"orders.read"}), frozenset()),
        (frozenset({"orders.write"}), frozenset({"Reader"})),
        (frozenset({"orders.read"}), frozenset({"OtherRole"})),
    ],
)
def test_access_gate_rejects_missing_permissions(
    identity: SimpleNamespace, scopes: frozenset[str], roles: frozenset[str]
) -> None:
    gate = _gate(identity, scopes=scopes, roles=roles)
    with pytest.raises(identity.ForbiddenError):
        gate.require(
            access_token=_SYNTHETIC_TOKEN,
            scopes=frozenset({"orders.read"}),
            roles=frozenset({"Reader"}),
        )


@pytest.mark.parametrize(
    ("issuer", "audience"),
    [
        ("https://other.example.test", "api://orders"),
        ("https://issuer.example.test/tenant/v2.0", "api://other"),
    ],
)
def test_access_gate_rejects_wrong_token_target(
    identity: SimpleNamespace, issuer: str, audience: str
) -> None:
    gate = _gate(identity, issuer=issuer, audience=audience)
    with pytest.raises(identity.UnauthenticatedError):
        gate.require(
            access_token=_SYNTHETIC_TOKEN, scopes=frozenset(), roles=frozenset()
        )


def test_signature_failure_is_not_permission_failure(identity: SimpleNamespace) -> None:
    class RejectingVerifier:
        def verify(self, *, access_token: str) -> object:
            assert access_token == _SYNTHETIC_TOKEN
            raise identity.UnauthenticatedError

    gate = identity.AccessGate(
        verifier=RejectingVerifier(), issuer="configured", audience="configured"
    )
    with pytest.raises(identity.UnauthenticatedError):
        gate.require(
            access_token=_SYNTHETIC_TOKEN, scopes=frozenset(), roles=frozenset()
        )


def test_verifier_outage_propagates_without_failing_open(
    identity: SimpleNamespace,
) -> None:
    class UnavailableVerifier:
        def verify(self, *, access_token: str) -> object:
            assert access_token == _SYNTHETIC_TOKEN
            raise identity.IdentityUnavailableError

    gate = identity.AccessGate(
        verifier=UnavailableVerifier(), issuer="configured", audience="configured"
    )
    with pytest.raises(identity.IdentityUnavailableError):
        gate.require(
            access_token=_SYNTHETIC_TOKEN, scopes=frozenset(), roles=frozenset()
        )


def test_app_only_rule_does_not_invent_delegated_scopes(
    identity: SimpleNamespace,
) -> None:
    gate = _gate(identity, scopes=frozenset())
    assert gate.require(
        access_token=_SYNTHETIC_TOKEN,
        scopes=frozenset(),
        roles=frozenset({"Reader"}),
    ).roles == frozenset({"Reader"})


def test_access_requires_every_requested_scope(identity: SimpleNamespace) -> None:
    gate = _gate(identity)
    with pytest.raises(identity.ForbiddenError):
        gate.require(
            access_token=_SYNTHETIC_TOKEN,
            scopes=frozenset({"orders.read", "orders.write"}),
            roles=frozenset(),
        )


def test_policy_template_imports_only_stdlib() -> None:
    path = _SKILL / "assets/access_policy.py.template"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    imports = {
        alias.name.split(".")[0]
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    } | {
        (node.module or "").split(".")[0]
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom)
    }
    assert imports <= sys.stdlib_module_names


def test_browser_fetch_behavior_with_bun(tmp_path: Path) -> None:
    """Run only copied TypeScript templates with Bun; no provider or browser."""
    bun = shutil.which("bun")
    if bun is None:
        pytest.skip("Bun is required to exercise the TypeScript template")
    assets = _ROOT / "packages/frontend/.apm/skills/kit-client-auth/assets"
    for name in ("auth-fetch.ts", "auth-fetch.test.ts"):
        (tmp_path / name).write_text(
            (assets / f"{name}.template").read_text(encoding="utf-8"), encoding="utf-8"
        )
    result = subprocess.run(  # noqa: S603 - installed Bun and fixed synthetic test path
        [bun, "test", "./auth-fetch.test.ts"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_browser_fetch_preserves_native_post_bodies(tmp_path: Path) -> None:
    """Reject body stream materialization at the Bun-tested Fetch boundary."""
    bun = shutil.which("bun")
    if bun is None:
        pytest.skip("Bun is required for the native-body TypeScript regression")
    assets = _ROOT / "packages/frontend/.apm/skills/kit-client-auth/assets"
    for name in ("auth-fetch.ts", "auth-fetch.standards.test.ts"):
        (tmp_path / name).write_text(
            (assets / f"{name}.template").read_text(encoding="utf-8"), encoding="utf-8"
        )
    result = subprocess.run(  # noqa: S603 - installed Bun and fixed synthetic test path
        [bun, "test", "./auth-fetch.standards.test.ts"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_frontend_guidance_allows_supported_msal_caches() -> None:
    skill = _ROOT / "packages/frontend/.apm/skills/kit-client-auth/SKILL.md"
    text = skill.read_text(encoding="utf-8")
    assert "MSAL" in text
    assert "supported" in text
    assert "Never put refresh tokens" not in text
