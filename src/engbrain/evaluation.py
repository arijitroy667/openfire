from __future__ import annotations

import json
import math
import subprocess
import tempfile
import time
from collections import defaultdict
from importlib.resources import files
from pathlib import Path
from typing import Any

from engbrain.config import initialize_project
from engbrain.engine import create_episode
from engbrain.models import EpisodeDraft, EpisodeType, ReviewState
from engbrain.retrieval import search_memory


def _load_corpus(dataset_path: Path | None) -> dict[str, Any]:
    if dataset_path is None:
        source = files("engbrain").joinpath("data", "demo_corpus.json")
        corpus = json.loads(source.read_text(encoding="utf-8"))
    else:
        corpus = json.loads(dataset_path.read_text(encoding="utf-8"))
    if not isinstance(corpus, dict):
        raise ValueError("Evaluation corpus must be a JSON object")
    targets = corpus.get("targets")
    distractors = corpus.get("distractors")
    if not isinstance(targets, list) or not isinstance(distractors, list):
        raise ValueError("Evaluation corpus must contain target and distractor arrays")
    if not targets:
        raise ValueError("Evaluation corpus must include at least one target episode")
    seen_ids: set[str] = set()
    for target in targets:
        if not isinstance(target, dict):
            raise ValueError("Every target episode must be a JSON object")
        target_id = target.get("id")
        if not isinstance(target_id, str) or not target_id.strip():
            raise ValueError("Every target episode needs a non-empty string id")
        if target_id in seen_ids:
            raise ValueError(f"Duplicate target id: {target_id}")
        seen_ids.add(target_id)
        for field in ("title", "problem"):
            if not isinstance(target.get(field), str) or not target[field].strip():
                raise ValueError(f"Target {target_id} needs a non-empty string {field}")
        queries = target.get("queries")
        if not isinstance(queries, dict) or not queries:
            raise ValueError(f"Target {target_id} needs at least one query")
        if any(not isinstance(query, str) or not query.strip() for query in queries.values()):
            raise ValueError(f"Target {target_id} queries must be non-empty strings")
        try:
            EpisodeType(target.get("type", "debugging"))
        except ValueError as exc:
            raise ValueError(f"Target {target_id} has an unsupported episode type") from exc
    for index, distractor in enumerate(distractors, start=1):
        if not isinstance(distractor, dict):
            raise ValueError(f"Distractor {index} must be a JSON object")
        for field in ("title", "problem"):
            if not isinstance(distractor.get(field), str) or not distractor[field].strip():
                raise ValueError(f"Distractor {index} needs a non-empty string {field}")
        try:
            EpisodeType(distractor.get("type", "debugging"))
        except ValueError as exc:
            raise ValueError(f"Distractor {index} has an unsupported episode type") from exc
    return corpus


def _git(root: Path, *arguments: str) -> None:
    subprocess.run(
        ["git", "-C", str(root), *arguments],
        check=True,
        capture_output=True,
        text=True,
    )


def _p95(values: list[float]) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = max(0, math.ceil(0.95 * len(ordered)) - 1)
    return ordered[index]


def _metrics(observations: list[dict[str, Any]]) -> dict[str, float | int]:
    count = len(observations)
    if not count:
        return {"n": 0, "recall_at_5": 0.0, "mrr": 0.0, "precision_at_5": 0.0}
    hits = [item["rank"] for item in observations if item["rank"] is not None and item["rank"] <= 5]
    reciprocal_ranks = [1.0 / rank if rank is not None and rank <= 5 else 0.0 for rank in (item["rank"] for item in observations)]
    return {
        "n": count,
        "recall_at_5": len(hits) / count,
        "mrr": sum(reciprocal_ranks) / count,
        "precision_at_5": len(hits) / (5 * count),
    }


def run_retrieval_evaluation(dataset_path: Path | None = None) -> dict[str, Any]:
    """Run a deterministic local retrieval evaluation in an isolated temporary repository."""
    corpus = _load_corpus(dataset_path)
    observations: dict[str, list[dict[str, Any]]] = defaultdict(list)
    latencies: list[float] = []
    with tempfile.TemporaryDirectory(prefix="engbrain-eval-") as directory:
        root = Path(directory).resolve()
        _git(root, "init", "-q")
        _git(root, "config", "user.name", "EngBrain Evaluation")
        _git(root, "config", "user.email", "engbrain-evaluation@example.invalid")
        (root / "README.md").write_text("temporary EngBrain evaluation repository\n", encoding="utf-8")
        _git(root, "add", "README.md")
        _git(root, "commit", "-m", "evaluation fixture")
        project = initialize_project(root, project_name="EngBrain evaluation")
        target_ids: dict[str, str] = {}
        for target in corpus["targets"]:
            episode_type = EpisodeType(target.get("type", "debugging"))
            episode = create_episode(
                project,
                EpisodeDraft(
                    title=target["title"],
                    episode_type=episode_type,
                    problem=target["problem"],
                    review_state=ReviewState.ACCEPTED,
                ),
            )
            target_ids[target["id"]] = episode.id
        for distractor in corpus["distractors"]:
            create_episode(
                project,
                EpisodeDraft(
                    title=distractor["title"],
                    episode_type=EpisodeType(distractor.get("type", "debugging")),
                    problem=distractor["problem"],
                    review_state=ReviewState.ACCEPTED,
                ),
            )
        for target in corpus["targets"]:
            for query_type, query in target["queries"].items():
                started = time.perf_counter()
                results = search_memory(project, [query], limit=5)
                latencies.append((time.perf_counter() - started) * 1000)
                ranks = [index for index, result in enumerate(results, start=1) if result.episode.id == target_ids[target["id"]]]
                observations[query_type].append(
                    {"case_id": target["id"], "rank": ranks[0] if ranks else None}
                )
    metrics = {query_type: _metrics(items) for query_type, items in sorted(observations.items())}
    return {
        "dataset": corpus.get("name", "custom evaluation corpus"),
        "corpus_kind": corpus.get("kind", "custom"),
        "notice": corpus.get("notice", ""),
        "target_episodes": len(corpus["targets"]),
        "distractor_episodes": len(corpus["distractors"]),
        "query_count": sum(len(target["queries"]) for target in corpus["targets"]),
        "retrieval_metrics": metrics,
        "latency_ms": {"p95": round(_p95(latencies), 3), "n": len(latencies)},
        "cases": dict(observations),
    }
