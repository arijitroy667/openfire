from __future__ import annotations

import json
import re
import tomllib
from pathlib import Path

_PINNED_REQUIREMENT = re.compile(r"^\s*([A-Za-z0-9_.-]+)(?:\[[^]]+\])?\s*(?:===|==)\s*([^,;\s]+)")


def normalize_name(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def dependency_snapshot(root: Path) -> dict[str, str | None] | None:
    """Read recognized local lock/requirements files without importing project code."""
    versions: dict[str, str | None] = {}
    found = False

    for filename in ("uv.lock", "poetry.lock"):
        path = root / filename
        if not path.is_file():
            continue
        found = True
        try:
            with path.open("rb") as handle:
                data = tomllib.load(handle)
        except (OSError, tomllib.TOMLDecodeError):
            continue
        packages = data.get("package", []) if filename == "poetry.lock" else data.get("package", data.get("packages", []))
        for item in packages:
            name, version = item.get("name"), item.get("version")
            if name:
                versions[normalize_name(str(name))] = str(version) if version is not None else None

    pip_lock = root / "Pipfile.lock"
    if pip_lock.is_file():
        found = True
        try:
            data = json.loads(pip_lock.read_text(encoding="utf-8"))
            for section in ("default", "develop"):
                for name, spec in data.get(section, {}).items():
                    version = spec.get("version") if isinstance(spec, dict) else None
                    versions[normalize_name(name)] = str(version).lstrip("=") if version else None
        except (OSError, json.JSONDecodeError):
            pass

    requirement_files = sorted(root.glob("requirements*.txt"))
    for path in requirement_files:
        found = True
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except OSError:
            continue
        for line in lines:
            if line.lstrip().startswith(("#", "-", "git+", "http://", "https://")):
                continue
            match = _PINNED_REQUIREMENT.match(line)
            if match:
                versions[normalize_name(match.group(1))] = match.group(2)
            else:
                name_match = re.match(r"^\s*([A-Za-z0-9_.-]+)", line)
                if name_match:
                    versions.setdefault(normalize_name(name_match.group(1)), None)

    pyproject = root / "pyproject.toml"
    if pyproject.is_file():
        try:
            with pyproject.open("rb") as handle:
                data = tomllib.load(handle)
            project = data.get("project", {})
            for requirement in project.get("dependencies", []):
                match = _PINNED_REQUIREMENT.match(requirement)
                if match:
                    versions.setdefault(normalize_name(match.group(1)), match.group(2))
        except (OSError, tomllib.TOMLDecodeError):
            pass

    return versions if found else None


def parse_dependency_anchor(value: str, snapshot: dict[str, str | None] | None) -> tuple[str, str | None]:
    if "==" in value:
        name, version = value.split("==", 1)
        return normalize_name(name.strip()), version.strip() or None
    name = normalize_name(value.strip())
    return name, snapshot.get(name) if snapshot is not None else None
