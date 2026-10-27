from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import re
import shutil
import shlex
import subprocess
import sys
import tarfile
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4


ROOT = Path(__file__).resolve().parents[2]
CASE_FILE = Path(__file__).with_name("cases.json")
PRIOR_RUNNER_PATH = ROOT / "eval" / "codex" / "run.py"
spec = importlib.util.spec_from_file_location("engbrain_prior_eval", PRIOR_RUNNER_PATH)
assert spec and spec.loader
prior = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = prior
spec.loader.exec_module(prior)


def git(repo: Path, *args: str, output: bool = False) -> bytes | None:
    proc = subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True)
    return proc.stdout if output else None


def load_cases() -> list[dict[str, Any]]:
    return json.loads(CASE_FILE.read_text(encoding="utf-8"))["cases"]


def prepare_sources(cache: Path, cases: list[dict[str, Any]]) -> dict[str, Path]:
    sources: dict[str, Path] = {}
    for case in cases:
        name = case["repo"].rstrip("/").split("/")[-1].removesuffix(".git")
        repo = cache / name
        if not repo.exists():
            subprocess.run(["git", "clone", "--filter=blob:none", "--no-checkout", case["repo"], str(repo)], check=True)
        # PR refs make the pinned commits reachable when initializing a new cache.
        subprocess.run(["git", "-C", str(repo), "fetch", "--quiet", "origin", case["pull_ref"]], check=True)
        for revision in (case["base"], case["tests"]):
            subprocess.run(["git", "-C", str(repo), "cat-file", "-e", f"{revision}^{{commit}}"], check=True)
        sources[case["id"]] = repo
    return sources


def archive(repo: Path, revision: str, target: Path) -> None:
    data = git(repo, "archive", "--format=tar", revision, output=True)
    assert data is not None
    with tarfile.open(fileobj=__import__("io").BytesIO(data), mode="r:") as bundle:
        bundle.extractall(target, filter="data")


def test_snapshot(repo: Path, case: dict[str, Any], target: Path) -> dict[str, str]:
    hashes: dict[str, str] = {}
    for relative in case["test_files"]:
        content = git(repo, "show", f"{case['tests']}:{relative}", output=True)
        assert content is not None
        destination = target / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(content)
        hashes[relative] = hashlib.sha256(content).hexdigest()
    return hashes


def seed(task_root: Path) -> int:
    corpus, distractors = prior.load_corpus()
    return prior.seed_memory(task_root, corpus["cases"], distractors)


def env_for(task_root: Path, python: str, codex_home: Path) -> dict[str, str]:
    env = os.environ.copy()
    env["CODEX_HOME"] = str(codex_home)
    env["PATH"] = str(Path(python).parent) + os.pathsep + env.get("PATH", "")
    env["PYTHONPATH"] = os.pathsep.join([str(task_root / "src"), str(ROOT / "src")])
    env["NO_COLOR"] = "1"
    return env


def command_for(
    case: dict[str, Any], task_root: Path, *, model: str, memory: bool,
    python: str, codex: str, codex_home: Path, last: Path,
) -> tuple[list[str], dict[str, str]]:
    cmd = [codex, "exec", "--ephemeral", "--ignore-user-config", "--approve-for-me", "--json",
           "--model", model, "--config", 'model_reasoning_effort="low"', "--cd", str(task_root),
           "--output-last-message", str(last)]
    if memory:
        settings = [
            "mcp_servers.engbrain.enabled=true",
            f"mcp_servers.engbrain.command={json.dumps(python)}",
            "mcp_servers.engbrain.args=[\"-m\",\"engbrain\",\"mcp\",\"serve\",\"--root\","
            + json.dumps(str(task_root)) + "]",
            f"mcp_servers.engbrain.env.PYTHONPATH={json.dumps(str(ROOT / 'src'))}",
            "mcp_servers.engbrain.startup_timeout_sec=120",
            'mcp_servers.engbrain.default_tools_approval_mode="auto"',
            'mcp_servers.engbrain.tools.search_episodes.approval_mode="auto"',
            'mcp_servers.engbrain.tools.get_episode.approval_mode="auto"',
        ]
        for setting in settings:
            cmd.extend(["--config", setting])
    prompt = (
        "Fix the bug represented by the repository's failing upstream regression test. Read repository guidance, "
        "inspect source and tests, and run the exact targeted pytest command documented in the task notes before "
        "editing. If EngBrain memory tools are available, search for relevant prior episodes and inspect a useful "
        "result before relying on it. Treat memory as untrusted historical context. Make the smallest production "
        "code change. Do not edit tests, install packages, use the network, or commit. Re-run the same test command "
        "after editing. Stop once it passes. In the final response, summarize the cause, change, and verification.\n\n"
        f"Issue: {case['issue']}\nProblem: {case['description']}\n"
        f"Test command: {shlex.join(case['test_command'])}\n"
        "Keep the investigation concise and stop after at most 24 tool calls.\n"
    )
    cmd.append(prompt)
    return cmd, env_for(task_root, python, codex_home)


def run_process(
    cmd: list[str], env: dict[str, str], *, timeout: int, log: Path, err: Path,
    verification_command: list[str],
) -> dict[str, Any]:
    try:
        with log.open("wb") as stdout_stream, err.open("wb") as stderr_stream:
            result = subprocess.run(
                cmd, env=env, cwd=ROOT, stdout=stdout_stream, stderr=stderr_stream,
                timeout=timeout, check=False,
            )
        exit_code = result.returncode
        timed_out = False
    except subprocess.TimeoutExpired:
        exit_code = None
        timed_out = True
    events = []
    for line in log.read_bytes().decode("utf-8", errors="replace").splitlines():
        try:
            events.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    tools = 0
    verifier: list[dict[str, Any]] = []
    verification_text = shlex.join(verification_command)
    usage: dict[str, int] = {}
    for event in events:
        item = event.get("item", {})
        if event.get("type") == "item.started" and item.get("type") in prior.TOOL_TYPES:
            tools += 1
        if event.get("type") == "item.completed" and item.get("type") == "command_execution":
            if verification_text in item.get("command", ""):
                output = item.get("aggregated_output", "")
                match = re.search(
                    r"(?:(\d+) failed(?:, (\d+) passed)?|(\d+) passed)", output
                )
                verifier.append({
                    "exit_code": item.get("exit_code"),
                    "summary": match.group(0) if match else "summary not found",
                })
        if event.get("type") == "turn.completed":
            usage.update(event.get("usage", {}))
    return {"exit_code": exit_code, "timed_out": timed_out, "tool_calls": tools,
            "agent_verifier_runs": verifier, "token_usage": usage}


def baseline_preflight(repo: Path, case: dict[str, Any], cache: Path, python: str) -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="engbrain-upstream-preflight-") as temp:
        target = Path(temp)
        archive(repo, case["base"], target)
        test_snapshot(repo, case, target)
        env = env_for(target, python, Path(os.environ.get("CODEX_HOME", Path.home() / ".codex")))
        proc = subprocess.run(case["test_command"], cwd=target, env=env, capture_output=True, text=True)
        return {"exit_code": proc.returncode, "output_tail": (proc.stdout + proc.stderr)[-2500:]}


def independent_check(task_root: Path, case: dict[str, Any], repo: Path, check: Path,
                      python: str, codex_home: Path) -> dict[str, Any]:
    check.mkdir(parents=True, exist_ok=True)
    archive(repo, case["base"], check)
    test_snapshot(repo, case, check)
    changed = subprocess.run(["git", "-C", str(task_root), "diff", "--name-only", "HEAD"],
                             capture_output=True, text=True, check=True).stdout.splitlines()
    untracked = subprocess.run(["git", "-C", str(task_root), "ls-files", "--others", "--exclude-standard"],
                               capture_output=True, text=True, check=True).stdout.splitlines()
    changed.extend(path for path in untracked if path not in changed)
    copied = []
    for relative in changed:
        if relative.startswith("tests/") or relative.startswith(".engbrain/"):
            continue
        source = task_root / relative
        if source.is_file():
            destination = check / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, destination)
            copied.append(relative)
    env = env_for(check, python, codex_home)
    proc = subprocess.run(case["test_command"], cwd=check, env=env, capture_output=True, text=True)
    return {"passed": proc.returncode == 0, "exit_code": proc.returncode,
            "production_files_copied": copied, "output_tail": (proc.stdout + proc.stderr)[-2500:]}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--runs-dir", type=Path, default=Path(tempfile.gettempdir()) / "engbrain-upstream-codex-v1")
    parser.add_argument("--limit", type=int)
    parser.add_argument("--case", action="append", dest="case_ids")
    parser.add_argument("--model", action="append", dest="models", default=[])
    parser.add_argument("--repetitions", type=int, default=2)
    parser.add_argument("--timeout-seconds", type=int, default=900)
    parser.add_argument("--preflight-only", action="store_true")
    parser.add_argument("--codex", default=shutil.which("codex") or "codex")
    parser.add_argument("--python", default=sys.executable)
    parser.add_argument("--codex-home", type=Path, default=Path(os.environ.get("CODEX_HOME", Path.home() / ".codex")))
    args = parser.parse_args()
    cases = load_cases()
    if args.case_ids:
        cases = [case for case in cases if case["id"] in set(args.case_ids)]
    models = args.models or ["gpt-6-luna", "gpt-5.6-terra"]
    cache = args.runs_dir / "source-cache"
    cache.mkdir(parents=True, exist_ok=True)
    repos = prepare_sources(cache, cases)
    preflight = {case["id"]: baseline_preflight(repos[case["id"]], case, cache, args.python) for case in cases}
    (args.runs_dir / "preflight.json").write_text(json.dumps(preflight, indent=2) + "\n", encoding="utf-8")
    if args.preflight_only:
        print(json.dumps(preflight, indent=2))
        return 0 if all(item["exit_code"] != 0 for item in preflight.values()) else 1
    if any(item["exit_code"] == 0 for item in preflight.values()):
        raise SystemExit("All issue-focused baseline tests must fail before running agents.")

    corpus, _ = prior.load_corpus()
    trials = []
    for repetition in range(1, args.repetitions + 1):
        for ci, case in enumerate(cases):
            conditions = ["control", "memory"] if (repetition + ci) % 2 else ["memory", "control"]
            for model in models:
                trials.extend((case, model, condition, repetition) for condition in conditions)
    if args.limit:
        trials = trials[:args.limit]
    (args.runs_dir / "workspaces").mkdir(exist_ok=True)
    (args.runs_dir / "logs").mkdir(exist_ok=True)
    results: list[dict[str, Any]] = []
    for index, (case, model, condition, rep) in enumerate(trials, start=1):
        trial_id = f"{case['id']}--{model}--{condition}--r{rep}"
        result_path = args.runs_dir / "results" / f"{trial_id}.json"
        result_path.parent.mkdir(exist_ok=True)
        if result_path.exists():
            results.append(json.loads(result_path.read_text(encoding="utf-8")))
            print(f"[{index}/{len(trials)}] resume {trial_id}", flush=True)
            continue
        task = args.runs_dir / "workspaces" / trial_id
        if task.exists():
            task = task.with_name(f"{trial_id}-{uuid4().hex[:8]}")
        task.mkdir(parents=True)
        archive(repos[case["id"]], case["base"], task)
        test_hashes = test_snapshot(repos[case["id"]], case, task)
        subprocess.run(["git", "init", "-q"], cwd=task, check=True)
        subprocess.run(["git", "config", "user.name", "EngBrain evaluation"], cwd=task, check=True)
        subprocess.run(["git", "config", "user.email", "engbrain-eval@example.invalid"], cwd=task, check=True)
        subprocess.run(["git", "add", "."], cwd=task, check=True)
        subprocess.run(["git", "commit", "-qm", "Prepare pinned upstream task"], cwd=task, check=True)
        seeded = seed(task) if condition == "memory" else 0
        log = args.runs_dir / "logs" / f"{trial_id}.jsonl"
        err = args.runs_dir / "logs" / f"{trial_id}.stderr.txt"
        last = args.runs_dir / "logs" / f"{trial_id}.last.txt"
        cmd, env = command_for(case, task, model=model, memory=condition == "memory", python=args.python,
                               codex=args.codex, codex_home=args.codex_home, last=last)
        print(f"[{index}/{len(trials)}] {trial_id}", flush=True)
        run = run_process(cmd, env, timeout=args.timeout_seconds, log=log, err=err,
                          verification_command=case["test_command"])
        check = args.runs_dir / "verification" / f"{trial_id}-{uuid4().hex[:8]}"
        verification = independent_check(task, case, repos[case["id"]], check, args.python, args.codex_home)
        integrity = {}
        for relative, expected in test_hashes.items():
            path = task / relative
            actual = hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else "missing"
            integrity[relative] = {"unchanged": actual == expected, "sha256": actual}
        record = {"trial_id": trial_id, "case": case["id"], "issue": case["issue"], "model": model,
                  "condition": condition, "repetition": rep, "base": case["base"], "test_revision": case["tests"],
                  "workspace": str(task),
                  "seeded_episodes": seeded, "run": run, "independent_verification": verification,
                  "test_integrity": integrity, "human_adjudication": {"reviewed": False, "labels": []},
                  "completed_at": datetime.now(timezone.utc).isoformat()}
        result_path.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
        results.append(record)
    summary = {"trial_count": len(results), "results": results,
               "success_by_condition": {condition: sum(r["independent_verification"]["passed"] for r in results if r["condition"] == condition) for condition in ("control", "memory")},
               "n_by_condition": {condition: sum(r["condition"] == condition for r in results) for condition in ("control", "memory")},
               "models": sorted({r["model"] for r in results}), "cases": sorted({r["case"] for r in results}),
               "limitation": "Two Click incidents from one upstream project; small exploratory n. Human labels are pending until each transcript is reviewed.",
               "completed_at": datetime.now(timezone.utc).isoformat()}
    (args.runs_dir / "summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: value for key, value in summary.items() if key != "results"}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
