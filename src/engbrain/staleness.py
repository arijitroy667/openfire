from __future__ import annotations

import re
import subprocess
from pathlib import Path

from engbrain.config import database_path
from engbrain.db import transaction
from engbrain.dependencies import dependency_snapshot
from engbrain.models import AnchorKind, Episode, EpisodeAnchor, EpisodeResult, Project, StalenessLevel


def current_commit(root: Path) -> str | None:
    try:
        result = subprocess.run(
            ["git", "-C", str(root), "rev-parse", "--verify", "HEAD"],
            capture_output=True,
            text=True,
            timeout=3,
            check=True,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return result.stdout.strip()


def _is_ancestor(root: Path, ancestor: str, descendant: str) -> bool:
    try:
        result = subprocess.run(
            ["git", "-C", str(root), "merge-base", "--is-ancestor", ancestor, descendant],
            capture_output=True,
            timeout=3,
            check=False,
        )
        return result.returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def _changed_commit_count(root: Path, since: str, until: str, paths: list[str]) -> int | None:
    try:
        result = subprocess.run(
            ["git", "-C", str(root), "rev-list", "--count", f"{since}..{until}", "--", *paths],
            capture_output=True,
            text=True,
            timeout=5,
            check=True,
        )
        return int(result.stdout.strip())
    except (OSError, ValueError, subprocess.SubprocessError):
        return None


def _working_tree_changes(root: Path, paths: list[str]) -> list[str] | None:
    try:
        result = subprocess.run(
            ["git", "-C", str(root), "status", "--short", "--untracked-files=all", "--", *paths],
            capture_output=True,
            text=True,
            timeout=3,
            check=True,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return [line.strip() for line in result.stdout.splitlines() if line.strip()]


def load_anchors(project: Project, episode_id: str) -> list[EpisodeAnchor]:
    with transaction(database_path(project)) as connection:
        rows = connection.execute(
            """SELECT a.id,a.episode_id,a.kind,a.value,a.version
               FROM episode_anchors a JOIN episodes e ON e.id = a.episode_id
               WHERE a.episode_id = ? AND e.project_id = ? ORDER BY a.kind,a.value""",
            (episode_id, project.id),
        ).fetchall()
    return [EpisodeAnchor.model_validate(dict(row)) for row in rows]


def compute_staleness(project: Project, episode: Episode) -> EpisodeResult:
    anchors = load_anchors(project, episode.id)
    path_anchors = [anchor.value for anchor in anchors if anchor.kind == AnchorKind.PATH]
    dependency_anchors = [anchor for anchor in anchors if anchor.kind == AnchorKind.DEPENDENCY]
    commit_anchor = next((anchor.value for anchor in anchors if anchor.kind == AnchorKind.COMMIT), None)
    base_commit = episode.verified_at_sha or commit_anchor
    head = current_commit(Path(project.repo_root))
    reasons: list[str] = []
    changed = False
    unknown = False
    stale = False

    if not path_anchors and not dependency_anchors:
        unknown = True
        reasons.append("No file or dependency anchors were recorded")
    elif head is None:
        unknown = True
        reasons.append("The current Git commit is unavailable")
    elif path_anchors:
        if base_commit is None:
            unknown = True
            reasons.append("No capture commit is available for the file anchors")
        elif not _is_ancestor(Path(project.repo_root), base_commit, head):
            unknown = True
            reasons.append("The capture commit is missing or is not an ancestor of the current checkout")
        else:
            missing = [path for path in path_anchors if not (Path(project.repo_root) / path).exists()]
            if missing:
                stale = True
                for path in missing:
                    reasons.append(f"Anchored path was deleted or renamed: {path}")
            count = _changed_commit_count(Path(project.repo_root), base_commit, head, path_anchors)
            if count is None:
                unknown = True
                reasons.append("Git could not count commits touching the anchored paths")
            elif count >= 20:
                stale = True
                reasons.append(f"{count} commits touched anchored paths since capture")
            elif count > 0:
                changed = True
                reasons.append(f"{count} commit(s) touched anchored paths since capture")
            else:
                reasons.append("No commits touched the anchored paths since capture")
            working_changes = _working_tree_changes(Path(project.repo_root), path_anchors)
            if working_changes is None:
                unknown = True
                reasons.append("Git could not inspect working-tree changes for the anchored paths")
            elif working_changes:
                changed = True
                reasons.append("Anchored paths have uncommitted changes: " + ", ".join(working_changes[:5]))

    if dependency_anchors:
        snapshot = dependency_snapshot(Path(project.repo_root))
        if snapshot is None:
            unknown = True
            reasons.append("No supported dependency lock or requirements file is available")
        else:
            for anchor in dependency_anchors:
                name = anchor.value
                captured = anchor.version
                if captured is None:
                    unknown = True
                    reasons.append(f"No captured version is available for dependency {name}")
                    continue
                if name not in snapshot:
                    stale = True
                    reasons.append(f"Anchored dependency was removed: {name} {captured}")
                    continue
                current = snapshot[name]
                if current is None:
                    unknown = True
                    reasons.append(f"Current version is not pinned for dependency {name}")
                elif current != captured:
                    captured_major = _major(captured)
                    current_major = _major(current)
                    if captured_major is not None and current_major is not None and captured_major != current_major:
                        stale = True
                        reasons.append(f"Dependency {name} changed major version: {captured} to {current}")
                    else:
                        changed = True
                        reasons.append(f"Dependency {name} changed version: {captured} to {current}")
                else:
                    reasons.append(f"Dependency {name} remains at {current}")

    if stale:
        level = StalenessLevel.STALE
    elif changed:
        level = StalenessLevel.DRIFTED
    elif unknown:
        level = StalenessLevel.UNKNOWN
    else:
        level = StalenessLevel.FRESH
    return EpisodeResult(episode=episode, anchors=anchors, staleness=level, staleness_reasons=reasons)


def _major(version: str) -> int | None:
    match = re.match(r"^\s*[v=]*([0-9]+)", version)
    return int(match.group(1)) if match else None
