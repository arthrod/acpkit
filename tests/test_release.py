from __future__ import annotations as _annotations

import subprocess
import sys
from pathlib import Path

import acpkit

_ROOT = Path(__file__).resolve().parents[1]
_SCRIPT = _ROOT / "scripts" / "release.py"


def _run_release(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(_SCRIPT), *args],
        cwd=_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )


def test_release_metadata_matches_current_version_and_tag() -> None:
    result = _run_release("check", "--tag", f"v{acpkit.__version__}")

    assert result.returncode == 0
    assert f"Release metadata valid for {acpkit.__version__}." in result.stdout


def test_release_metadata_rejects_mismatched_tag() -> None:
    result = _run_release("check", "--tag", "v999.0.0")

    assert result.returncode == 1
    assert "does not match workspace version" in result.stderr
