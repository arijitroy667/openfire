from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import selectors
import shutil
import signal
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

CORPUS_PATH = Path(__file__).with_name("corpus.json")
DEFAULT_CODEX_HOME = Path("/mnt/c/Users/ariji/.codex")
TOOL_TYPES = {"command_execution", "file_change", "mcp_tool_call"}
VERIFIER = ("python3", "-m", "unittest")


def load_corpus() -> tuple[dict[str, Any], list[dict[str, Any]]]:
    corpus = json.loads(CORPUS_PATH.read_text(encoding="utf-8"))
    cases = corpus["cases"]
    ids = {case["id"] for case in cases}
    if len(cases) != corpus["target_count"] or len(ids) != len(cases):
        raise ValueError("Corpus target count or identifiers are invalid")
    public_cases = [case for case in cases if case.get("source")]
    if len(public_cases) < corpus["public_issue_minimum"]:
        raise ValueError("Corpus does not meet its public-issue minimum")
    dev_ids = {case["id"] for case in cases if case["split"] == "development"}
    test_ids = {case["id"] for case in cases if case["split"] == "test"}
    if dev_ids != set(corpus["development_cases"]) or test_ids != set(corpus["test_cases"]):
        raise ValueError("Declared development/test split does not match the cases")
    if dev_ids & test_ids or dev_ids | test_ids != ids:
        raise ValueError("Development/test split must partition all cases")
    distractor_path = ROOT / corpus["distractor_source"]
    demo = json.loads(distractor_path.read_text(encoding="utf-8"))
    distractors = demo["distractors"]
    if len(distractors) < corpus["distractor_count"]:
        raise ValueError("The selected demo corpus has too few distractors")
    return corpus, distractors[: corpus["distractor_count"]]


def fixture_files(case: dict[str, Any]) -> list[tuple[Path, bytes]]:
    folder = Path(__file__).parent / "cases" / case["id"]
    result: list[tuple[Path, bytes]] = []
    for name in case["files"]:
        source = folder / name
        if not source.is_file():
            raise FileNotFoundError(source)
        result.append((Path(name), source.read_bytes()))
    return result


def run_fixture_preflight(cases: list[dict[str, Any]]) -> list[dict[str, Any]]:
    results = []
    for case in cases:
        folder = Path(__file__).parent / "cases" / case["id"]
        proc = subprocess.run(VERIFIER, cwd=folder, text=True, capture_output=True, check=False)
        output = proc.stdout + proc.stderr
        discovered = re.search(r"Ran (\d+) tests?", output)
        results.append(
            {
                "case": case["id"],
                "baseline_exit_code": proc.returncode,
                "tests_discovered": int(discovered.group(1)) if discovered else None,
                "baseline_failing": proc.returncode != 0,
                "output": output[-2000:],
            }
        )
    return results


def seed_memory(task_root: Path, cases: list[dict[str, Any]], distractors: list[dict[str, Any]]) -> int:
    from engbrain.config import initialize_project
    from engbrain.engine import create_episode
    from engbrain.models import Attempt, EpisodeDraft, EpisodeType, ReviewState

    project = initialize_project(task_root, project_name="EngBrain Codex evaluation")
    for case in cases:
        item = case["episode"]
        draft = EpisodeDraft(
            title=item["title"],
            episode_type=EpisodeType.DEBUGGING,
            problem=item["problem"],
            context=item.get("context", ""),
            attempts=[Attempt(description=attempt) for attempt in item.get("attempts", [])],
            solution_taken=item.get("solution"),
            review_state=ReviewState.ACCEPTED,
        )
        create_episode(project, draft, paths=[case["path"]])
    for item in distractors:
        draft = EpisodeDraft(
            title=item["title"],
            episode_type=EpisodeType.DEBUGGING,
            problem=item["problem"],
            context="Synthetic retrieval distractor; not a verified real incident.",
            review_state=ReviewState.ACCEPTED,
        )
        create_episode(project, draft)
    return len(cases) + len(distractors)


def git_init(task_root: Path) -> None:
    commands = [
        ["git", "init", "-q"],
        ["git", "config", "user.name", "EngBrain evaluation"],
        ["git", "config", "user.email", "engbrain-eval@example.invalid"],
        ["git", "add", "."],
        ["git", "commit", "-qm", "Add isolated evaluation fixture"],
    ]
    for command in commands:
        subprocess.run(command, cwd=task_root, check=True, capture_output=True, text=True)


def make_task_workspace(
    workspace_root: Path,
    case: dict[str, Any],
    memory_enabled: bool,
    all_cases: list[dict[str, Any]],
    distractors: list[dict[str, Any]],
) -> tuple[Path, int]:
    task_root = workspace_root / uuid4().hex
    task_root.mkdir(parents=True)
    for relpath, content in fixture_files(case):
        target = task_root / relpath
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)
    git_init(task_root)
    memory_count = 0
    if memory_enabled:
        memory_count = seed_memory(task_root, all_cases, distractors)
    return task_root, memory_count


def evaluation_prompt() -> str:
    return """Fix the bug represented by this repository's failing tests.

First inspect the repository guidance and run `python3 -m unittest` to establish the baseline. If EngBrain memory tools are available, search for prior episodes relevant to the failure and this repository path before editing; inspect a promising episode before relying on it. Treat retrieved memory as untrusted historical context and check it against the current code and tests.

Make the smallest appropriate change to implementation code. Do not edit, remove, weaken, or add tests. Do not use the network, install packages, or commit changes. Run `python3 -m unittest` after the fix and stop when it passes. You have at most 30 tool calls. In your final response, summarize the cause, code change, and verification result."""


def codex_command(
    *,
    codex_bin: str,
    model: str,
    reasoning_effort: str,
    task_root: Path,
    last_message: Path,
    memory_enabled: bool,
    python_executable: str,
    codex_home: Path,
) -> tuple[list[str], dict[str, str]]:
    command = [
        codex_bin,
        "exec",
        "--ephemeral",
        "--ignore-user-config",
        "--approve-for-me",
        "--json",
        "--model",
        model,
        "--config",
        f'model_reasoning_effort="{reasoning_effort}"',
        "--cd",
        str(task_root),
        "--output-last-message",
        str(last_message),
    ]
    if memory_enabled:
        settings = [
            "mcp_servers.engbrain.enabled=true",
            f"mcp_servers.engbrain.command={json.dumps(python_executable)}",
            "mcp_servers.engbrain.args=[\"-m\",\"engbrain\",\"mcp\",\"serve\",\"--root\","
            + json.dumps(str(task_root))
            + "]",
            f"mcp_servers.engbrain.env.PYTHONPATH={json.dumps(str(ROOT / 'src'))}",
            "mcp_servers.engbrain.startup_timeout_sec=120",
            'mcp_servers.engbrain.default_tools_approval_mode="auto"',
            'mcp_servers.engbrain.tools.search_episodes.approval_mode="auto"',
            'mcp_servers.engbrain.tools.get_episode.approval_mode="auto"',
        ]
        for setting in settings:
            command.extend(["--config", setting])
    command.append(evaluation_prompt())
    env = os.environ.copy()
    env["CODEX_HOME"] = str(codex_home)
    env["PYTHONPATH"] = str(ROOT / "src")
    env["NO_COLOR"] = "1"
    return command, env


def stop_process(proc: subprocess.Popen[str]) -> None:
    if proc.poll() is not None:
        return
    try:
        os.killpg(proc.pid, signal.SIGTERM)
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            os.killpg(proc.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass


def run_codex(
    command: list[str],
    env: dict[str, str],
    *,
    log_path: Path,
    stderr_path: Path,
    timeout_seconds: int,
    tool_call_cap: int,
) -> dict[str, Any]:
    tool_count = 0
    tool_ordinals: dict[str, int] = {}
    verifier_results: list[dict[str, Any]] = []
    token_usage: dict[str, int] = {}
    timed_out = False
    cap_exceeded = False
    started_at = time.monotonic()
    stderr_stream = stderr_path.open("w", encoding="utf-8")
    with log_path.open("w", encoding="utf-8") as log_stream:
        proc = subprocess.Popen(
            command,
            cwd=ROOT,
            env=env,
            stdout=subprocess.PIPE,
            stderr=stderr_stream,
            text=True,
            bufsize=1,
            start_new_session=True,
        )
        assert proc.stdout is not None
        selector = selectors.DefaultSelector()
        selector.register(proc.stdout, selectors.EVENT_READ)
        while proc.poll() is None:
            if time.monotonic() - started_at > timeout_seconds:
                timed_out = True
                stop_process(proc)
                break
            ready = selector.select(timeout=0.5)
            if not ready:
                continue
            line = proc.stdout.readline()
            if not line:
                continue
            log_stream.write(line)
            log_stream.flush()
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            item = event.get("item", {})
            item_id = item.get("id")
            item_type = item.get("type")
            if event.get("type") == "turn.completed":
                token_usage.update(event.get("usage", {}))
            if event.get("type") == "item.started" and item_type in TOOL_TYPES:
                tool_count += 1
                if item_id:
                    tool_ordinals[item_id] = tool_count
                if tool_count > tool_call_cap:
                    cap_exceeded = True
                    stop_process(proc)
                    break
            elif event.get("type") == "item.completed":
                if item_type == "command_execution":
                    command_text = item.get("command", "")
                    is_verifier = "python3 -m unittest" in command_text
                    if is_verifier:
                        verifier_results.append(
                            {
                                "exit_code": item.get("exit_code"),
                                "tool_ordinal": tool_ordinals.get(item_id),
                            }
                        )
        if proc.poll() is None:
            stop_process(proc)
        # Drain any final event lines after the process exits.
        for line in proc.stdout:
            log_stream.write(line)
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            item = event.get("item", {})
            item_id = item.get("id")
            if event.get("type") == "turn.completed":
                token_usage.update(event.get("usage", {}))
            if event.get("type") == "item.started" and item.get("type") in TOOL_TYPES:
                tool_count += 1
                if item_id:
                    tool_ordinals[item_id] = tool_count
                if tool_count > tool_call_cap:
                    cap_exceeded = True
            elif event.get("type") == "item.completed" and item.get("type") == "command_execution":
                if "python3 -m unittest" in item.get("command", ""):
                    verifier_results.append(
                        {"exit_code": item.get("exit_code"), "tool_ordinal": tool_ordinals.get(item_id)}
                    )
        exit_code = proc.wait()
        selector.close()
    stderr_stream.close()
    passed_ordinal = next(
        (
            result["tool_ordinal"]
            for result in verifier_results
            if result["exit_code"] == 0 and result["tool_ordinal"] is not None
        ),
        None,
    )
    failures_before_pass = 0
    for result in verifier_results:
        if result["exit_code"] == 0:
            break
        failures_before_pass += 1
    return {
        "exit_code": exit_code,
        "tool_calls": min(tool_count, tool_call_cap),
        "tool_calls_to_pass": passed_ordinal if passed_ordinal is not None else tool_call_cap,
        "verifier_runs": verifier_results,
        "token_usage": token_usage,
        "repeat_failed_verifications": max(0, failures_before_pass - 1),
        "timed_out": timed_out,
        "tool_cap_exceeded": cap_exceeded,
        "duration_seconds": round(time.monotonic() - started_at, 2),
    }


def independent_verification(task_root: Path, case: dict[str, Any], check_root: Path) -> dict[str, Any]:
    check_dir = check_root / uuid4().hex
    check_dir.mkdir(parents=True)
    original_files = dict(fixture_files(case))
    source_path = Path(case["path"])
    candidate = task_root / source_path
    if not candidate.exists():
        return {"passed": False, "exit_code": None, "output": "Candidate implementation file was deleted."}
    for relpath, original in original_files.items():
        if relpath.name.startswith("test_"):
            content = original
        elif relpath == source_path:
            content = candidate.read_bytes()
        else:
            # Future fixtures may include immutable support data alongside the tested source.
            content = (task_root / relpath).read_bytes() if (task_root / relpath).exists() else original
        (check_dir / relpath).parent.mkdir(parents=True, exist_ok=True)
        (check_dir / relpath).write_bytes(content)
    proc = subprocess.run(VERIFIER, cwd=check_dir, text=True, capture_output=True, check=False)
    output = proc.stdout + proc.stderr
    return {
        "passed": proc.returncode == 0,
        "exit_code": proc.returncode,
        "output": output[-4000:],
    }


def hash_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def test_integrity(task_root: Path, case: dict[str, Any]) -> dict[str, Any]:
    integrity: dict[str, Any] = {}
    for relpath, original in fixture_files(case):
        if relpath.name.startswith("test_"):
            current = (task_root / relpath).read_bytes() if (task_root / relpath).exists() else b"<missing>"
            integrity[relpath.as_posix()] = {
                "unchanged": current == original,
                "original_sha256": hash_bytes(original),
                "final_sha256": hash_bytes(current),
            }
    return integrity


def build_trials(cases: list[dict[str, Any]], repetitions: int) -> list[tuple[dict[str, Any], str, int]]:
    trials: list[tuple[dict[str, Any], str, int]] = []
    for repetition in range(1, repetitions + 1):
        for case_index, case in enumerate(cases):
            order = ["control", "memory"] if (repetition + case_index) % 2 else ["memory", "control"]
            trials.extend((case, condition, repetition) for condition in order)
    return trials


def aggregate(results: list[dict[str, Any]]) -> dict[str, Any]:
    def median(values: list[float]) -> float | None:
        if not values:
            return None
        values.sort()
        middle = len(values) // 2
        if len(values) % 2:
            return values[middle]
        return round((values[middle - 1] + values[middle]) / 2, 2)

    summary: dict[str, Any] = {}
    for split in ("development", "test", "all"):
        filtered = [item for item in results if split == "all" or item["split"] == split]
        by_condition = {}
        for condition in ("control", "memory"):
            group = [item for item in filtered if item["condition"] == condition]
            by_condition[condition] = {
                "n": len(group),
                "successes": sum(item.get("independent_verification", {}).get("passed", False) for item in group),
                "success_rate": round(
                    sum(item.get("independent_verification", {}).get("passed", False) for item in group)
                    / len(group),
                    4,
                )
                if group
                else None,
                "median_tool_calls_to_pass": median(
                    [item["tool_calls_to_pass"] for item in group if item.get("tool_calls_to_pass") is not None]
                ),
                "median_repeat_failed_verifications": median(
                    [item["repeat_failed_verifications"] for item in group]
                ),
                "input_tokens": sum(item.get("token_usage", {}).get("input_tokens", 0) for item in group),
                "output_tokens": sum(item.get("token_usage", {}).get("output_tokens", 0) for item in group),
                "test_tamper_trials": sum(
                    any(not detail["unchanged"] for detail in item.get("test_integrity", {}).values())
                    for item in group
                ),
            }
        summary[split] = by_condition
    return summary


def write_summary(run_dir: Path, results: list[dict[str, Any]], metadata: dict[str, Any]) -> None:
    summary = {
        "metadata": metadata,
        "trial_count": len(results),
        "results": aggregate(results),
        "limitation": (
            "Five public-issue cases are simplified behavioral reproductions, not full upstream repository fixes. "
            "The remaining seven are synthetic. Small n=3 per condition and one model do not establish general efficacy. "
            "Repeat failed verifications count failing verifier invocations after the first baseline failure; "
            "tool calls to pass count Codex tool events through its first successful verifier, capped at 30."
        ),
    }
    (run_dir / "summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    lines = [
        "# EngBrain Codex agent evaluation",
        "",
        f"Model: `{metadata['model']}` (reasoning effort `{metadata['reasoning_effort']}`)",
        f"Completed trials: {len(results)}",
        "",
        "| Split | Condition | n | Passed | Success rate | Median calls to pass | Median repeat failed checks | Input tokens | Output tokens | Test tampering |",
        "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    summary_rows = aggregate(results)
    for split in ("development", "test", "all"):
        for condition in ("control", "memory"):
            item = summary_rows[split][condition]
            rate = "—" if item["success_rate"] is None else f"{item['success_rate']:.0%}"
            calls = "—" if item["median_tool_calls_to_pass"] is None else str(item["median_tool_calls_to_pass"])
            repeat = "—" if item["median_repeat_failed_verifications"] is None else str(item["median_repeat_failed_verifications"])
            lines.append(
                f"| {split} | {condition} | {item['n']} | {item['successes']} | {rate} | {calls} | {repeat} | "
                f"{item['input_tokens']} | {item['output_tokens']} | {item['test_tamper_trials']} |"
            )
    lines.extend(["", "## Limitations", "", summary["limitation"], ""])
    (run_dir / "summary.md").write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the EngBrain Codex agent evaluation.")
    parser.add_argument("--runs-dir", type=Path, default=Path(__file__).parent / "runs" / datetime.now().strftime("%Y%m%d-%H%M%S"))
    parser.add_argument("--limit", type=int, help="Run only the first N trials in counterbalanced order.")
    parser.add_argument("--case", action="append", dest="case_ids", help="Restrict to a case ID; repeat as needed.")
    parser.add_argument("--model", default="gpt-6-luna")
    parser.add_argument("--reasoning-effort", choices=("low", "medium", "high", "xhigh", "max"), default="low")
    parser.add_argument("--timeout-seconds", type=int, default=900)
    parser.add_argument("--tool-call-cap", type=int, default=30)
    parser.add_argument("--codex-home", type=Path, default=Path(os.environ.get("CODEX_HOME", DEFAULT_CODEX_HOME)))
    parser.add_argument("--codex-bin", default=shutil.which("codex") or "/root/.local/bin/codex")
    parser.add_argument("--preflight-only", action="store_true")
    args = parser.parse_args()

    corpus, distractors = load_corpus()
    cases = corpus["cases"]
    if args.case_ids:
        missing = set(args.case_ids) - {case["id"] for case in cases}
        if missing:
            parser.error(f"Unknown case IDs: {', '.join(sorted(missing))}")
        cases = [case for case in cases if case["id"] in args.case_ids]
    if args.preflight_only:
        results = run_fixture_preflight(cases)
        print(json.dumps({"corpus": corpus["name"], "preflight": results}, indent=2))
        return 0 if all(item["tests_discovered"] and item["baseline_failing"] for item in results) else 1

    if not Path(args.codex_bin).exists() and shutil.which(args.codex_bin) is None:
        parser.error(f"Codex CLI not found: {args.codex_bin}")
    if not args.codex_home.exists():
        parser.error(f"Codex home not found: {args.codex_home}")
    if args.limit is not None and args.limit < 1:
        parser.error("--limit must be positive")

    run_dir = args.runs_dir.resolve()
    run_dir.mkdir(parents=True, exist_ok=True)
    workspaces = run_dir / "workspaces"
    checks = run_dir / "verification"
    workspaces.mkdir(exist_ok=True)
    checks.mkdir(exist_ok=True)
    preflight = run_fixture_preflight(cases)
    if not all(item["tests_discovered"] and item["baseline_failing"] for item in preflight):
        raise SystemExit("A fixture does not have collected, initially failing tests; inspect --preflight-only output.")
    (run_dir / "preflight.json").write_text(json.dumps(preflight, indent=2) + "\n", encoding="utf-8")
    metadata = {
        "corpus": corpus["name"],
        "model": args.model,
        "reasoning_effort": args.reasoning_effort,
        "codex_bin": args.codex_bin,
        "tool_call_cap": args.tool_call_cap,
        "timeout_seconds": args.timeout_seconds,
        "runs_per_condition": corpus["runs_per_condition"],
        "run_started_at": datetime.now(timezone.utc).isoformat(),
    }
    (run_dir / "metadata.json").write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")

    all_results: list[dict[str, Any]] = []
    trials = build_trials(cases, corpus["runs_per_condition"])
    if args.limit is not None:
        trials = trials[: args.limit]
    for index, (case, condition, repetition) in enumerate(trials, start=1):
        trial_id = f"{case['id']}--{condition}--r{repetition}"
        result_path = run_dir / "results" / f"{trial_id}.json"
        result_path.parent.mkdir(exist_ok=True)
        if result_path.exists():
            stored = json.loads(result_path.read_text(encoding="utf-8"))
            all_results.append(stored)
            print(f"[{index}/{len(trials)}] resume {trial_id}: already complete", flush=True)
            continue
        memory_enabled = condition == "memory"
        trial_started_at = datetime.now(timezone.utc).isoformat()
        task_root, seeded_episodes = make_task_workspace(
            workspaces, case, memory_enabled, corpus["cases"], distractors
        )
        logs = run_dir / "logs"
        logs.mkdir(exist_ok=True)
        last_message = logs / f"{trial_id}.last.txt"
        jsonl_path = logs / f"{trial_id}.jsonl"
        stderr_path = logs / f"{trial_id}.stderr.txt"
        command, env = codex_command(
            codex_bin=args.codex_bin,
            model=args.model,
            reasoning_effort=args.reasoning_effort,
            task_root=task_root,
            last_message=last_message,
            memory_enabled=memory_enabled,
            python_executable=sys.executable,
            codex_home=args.codex_home,
        )
        print(
            f"[{index}/{len(trials)}] {trial_id} ({'EngBrain memory' if memory_enabled else 'control'})",
            flush=True,
        )
        codex_result = run_codex(
            command,
            env,
            log_path=jsonl_path,
            stderr_path=stderr_path,
            timeout_seconds=args.timeout_seconds,
            tool_call_cap=args.tool_call_cap,
        )
        integrity = test_integrity(task_root, case)
        if any(not item["unchanged"] for item in integrity.values()):
            codex_result["tool_calls_to_pass"] = args.tool_call_cap
            codex_result["repeat_failed_verifications"] = max(0, len(codex_result["verifier_runs"]) - 1)
        external = independent_verification(task_root, case, checks)
        result = {
            "trial_id": trial_id,
            "case_id": case["id"],
            "split": case["split"],
            "source": case.get("source"),
            "condition": condition,
            "repetition": repetition,
            "model": args.model,
            "reasoning_effort": args.reasoning_effort,
            "memory_seeded_episode_count": seeded_episodes,
            "task_workspace": str(task_root),
            "started_at": trial_started_at,
            **codex_result,
            "test_integrity": integrity,
            "independent_verification": external,
            "last_message_path": str(last_message),
            "transcript_path": str(jsonl_path),
        }
        result_path.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
        all_results.append(result)
        write_summary(run_dir, all_results, metadata)
        print(
            f"  exit={result['exit_code']} calls={result['tool_calls']} pass={external['passed']} "
            f"duration={result['duration_seconds']}s",
            flush=True,
        )
    write_summary(run_dir, all_results, metadata)
    print(f"Evaluation results: {run_dir / 'summary.md'}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
