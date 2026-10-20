"""Run the single reusable convention checker against toolkit source."""

import runpy
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
_CHECKER = (
    _ROOT / "packages/backend/.apm/skills/kit-python-service/assets/check_python.py"
)


if __name__ == "__main__":
    sys.argv = [
        str(_CHECKER),
        *(str(_ROOT / name) for name in ("src", "scripts", "tests")),
    ]
    runpy.run_path(str(_CHECKER), run_name="__main__")
