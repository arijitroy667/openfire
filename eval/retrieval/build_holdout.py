"""Build the frozen retrieval challenge set from the curated incident fixtures."""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SOURCE_CORPUS = ROOT / "eval" / "codex" / "corpus.json"
DISTRACTOR_CORPUS = ROOT / "src" / "engbrain" / "data" / "demo_corpus.json"
OUTPUT = Path(__file__).with_name("holdout-v1.json")

# Query phrasings were written separately from the stored episode prose to
# test language variation, including 5 issue-derived and 7 synthetic cases.
PARAPHRASES = {
    "requests-6071": "An empty trust-bundle override accidentally turns off TLS certificate checking.",
    "requests-4673": "Installing a dependency release succeeds, but importing the package rejects that same release.",
    "pytest-12659": "Package tests loaded through the alternate importer show a bare assertion without expected and actual values.",
    "click-1884": "The generated version switch looks up metadata under the import module's name and crashes when distribution naming differs.",
    "click-3059": "A command group that can run empty still prints a mandatory child-command placeholder.",
    "pool-exhaustion": "Parallel workers queue forever because the configured connection slots are fewer than active workers.",
    "cache-deletion": "A removed resource still receives a not-modified response because its saved timestamp remains in cache.",
    "environment-precedence": "A blank shell setting is treated as absent, so a dotenv file silently overrides the operator's choice.",
    "cors-preflight": "The browser's OPTIONS negotiation inherits an error code from the later resource request.",
    "queue-ack-order": "A broker discards work after the consumer confirms delivery but before the durable write completes.",
    "timezone-normalization": "Serializing a timestamp keeps its local offset or leaves a timezone-free value ambiguous.",
    "sqlite-busy-timeout": "A brief database lock immediately fails writes instead of allowing a bounded wait.",
}

SYMPTOMS = {
    "requests-6071": "HTTPS requests stop validating peers when a deployment variable is set to nothing.",
    "requests-4673": "A clean install passes dependency resolution and then emits an incompatibility warning at import time.",
    "pytest-12659": "CI failure output omits the useful diff only for tests inside packages under the alternate load mode.",
    "click-1884": "Running --version raises a missing-package-metadata error even though the application is installed.",
    "click-3059": "The usage line wraps COMMAND in no brackets despite a callback that should run without a subcommand.",
    "pool-exhaustion": "Load checks hang at four simultaneous jobs while the service has only one DB slot.",
    "cache-deletion": "A deleted file is reported as unchanged to a client that supplied a cached validator.",
    "environment-precedence": "Setting a variable to an empty string does not survive configuration loading.",
    "cors-preflight": "A cross-origin browser request is blocked because its preliminary request returns the resource's failure status.",
    "queue-ack-order": "Messages disappear when persistence raises between delivery and acknowledgment.",
    "timezone-normalization": "Equivalent instants produce different strings depending on whether the input carried an offset.",
    "sqlite-busy-timeout": "Concurrent writers fail immediately during a short-lived lock burst.",
}


def main() -> None:
    source = json.loads(SOURCE_CORPUS.read_text(encoding="utf-8"))
    distractors = json.loads(DISTRACTOR_CORPUS.read_text(encoding="utf-8"))["distractors"]
    targets = []
    for case in source["cases"]:
        episode = case["episode"]
        case_id = case["id"]
        targets.append(
            {
                "id": case_id,
                "source": case.get("source"),
                "title": episode["title"],
                "type": episode.get("type", "debugging"),
                "problem": episode["problem"],
                "queries": {
                    "lexical": f"{episode['title']} {episode['problem']}",
                    "paraphrase": PARAPHRASES[case_id],
                    "symptom": SYMPTOMS[case_id],
                },
            }
        )
    output = {
        "name": "engbrain-retrieval-holdout-v1",
        "kind": "issue-derived and synthetic challenge corpus",
        "notice": (
            "Freshly written retrieval phrasings over the existing 5 simplified public-issue and 7 synthetic "
            "incident fixtures. The target incidents are not independent from the Codex fixture corpus; use this "
            "as a frozen retrieval challenge, not as evidence from full upstream repositories."
        ),
        "targets": targets,
        "distractors": distractors,
    }
    OUTPUT.write_text(json.dumps(output, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Wrote {OUTPUT} ({len(targets)} targets, {len(distractors)} distractors)")


if __name__ == "__main__":
    main()
