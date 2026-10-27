from __future__ import annotations

import importlib.util
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

DEMO_ROOT = Path(__file__).resolve().parents[1] / "examples" / "demo-repo"
_SPEC = importlib.util.spec_from_file_location(
    "engbrain_offline_demo", DEMO_ROOT / "scripts" / "offline_demo.py"
)
assert _SPEC is not None and _SPEC.loader is not None
offline_demo = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(offline_demo)


@pytest.fixture
def demo_copy(tmp_path: Path) -> Path:
    target = tmp_path / "demo-repo"
    shutil.copytree(DEMO_ROOT, target)
    return target


@pytest.mark.parametrize("name", sorted(offline_demo.INCIDENTS))
def test_fixture_fails_at_baseline_and_passes_after_fix(demo_copy: Path, name: str) -> None:
    incident = offline_demo.INCIDENTS[name]
    check = [sys.executable, incident["script"]]

    before = subprocess.run(check, cwd=demo_copy, capture_output=True, text=True)
    assert before.returncode != 0, before.stdout + before.stderr

    (demo_copy / incident["fix_path"]).write_text(incident["fixed"], encoding="utf-8")

    after = subprocess.run(check, cwd=demo_copy, capture_output=True, text=True)
    assert after.returncode == 0, after.stdout + after.stderr
