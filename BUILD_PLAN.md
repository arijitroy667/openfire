# EngBrain v1.1: critical analysis and build plan

## Product analysis

### What the product is

EngBrain is a local-first, repository-scoped memory service for AI coding agents. It stores engineering episodes: the problem, attempted approaches, chosen solution, verification evidence, repository anchors, and review history. A CLI and an MCP server expose the same memory engine to developers and compatible agents.

### What problem it solves

Repository knowledge is often trapped in prior sessions, pull requests, or undocumented workarounds. A new session may repeat failed approaches, miss the reason behind a dependency pin, or trust a note that no longer matches the code. Existing chat history and static rules do not reliably distinguish guesses from evidence or report when context has drifted.

### How it solves it

1. Capture command events locally, redact likely secrets, and identify a repeated fail-then-pass sequence.
2. Save a proposed episode as a draft with the observed commands and exit codes. A person reviews it before it can be searched.
3. Let agents search with several phrasings and paths. Combine full-text, error-signature, and anchor matches, then return a small ranked set.
4. Compare accepted episodes' Git and dependency anchors with the current repository and attach a fresh, drifted, stale, or unknown label with reasons.
5. Keep agent-proposed memories in the draft queue and never execute commands from a retrieved episode.

### Architecture

CLI, MCP, and client hook adapters call one Python memory engine. The engine validates models, redacts content, and coordinates capture, review, retrieval, ranking, and staleness. SQLite stores projects, episodes, anchors, hook events, and retrieval logs; an FTS5 virtual table provides lexical candidates. Git CLI subprocesses provide commit and path history. Each MCP process is scoped to its repository root, and every database read and write is project-filtered.

### Technology choices

- Python 3.11+ and `pyproject.toml` for packaging.
- Typer for the developer CLI.
- Pydantic v2 for input and stored-record validation.
- SQLite's standard-library driver with FTS5 for local persistence and search.
- The official Python MCP SDK over stdio for the reference agent connection.
- Git CLI subprocesses for repository anchors and staleness.
- pytest is the intended project test framework; no remote service, embedding model, or LLM is required for the core product.

## Critical assessment and implementation decisions

The PRD has a focused differentiator: the memory includes failed attempts, evidence provenance, and computed freshness. Its local-only boundary and human review step are also useful safeguards. The main risks are in the semantics and operational edge cases, not the high-level architecture.

1. **A pass is evidence, not proof of causality.** A failing command followed by the same command passing proves that the observed run changed outcome. It does not prove a particular edit fixed the issue. The UI and schema will describe this as mechanical run evidence; review acceptance will not turn a manual or asserted episode into a mechanically verified one.
2. **Review and episode status are separate concepts.** Draft/accepted/rejected describe review. Unresolved/unverified/verified/superseded describe the episode. The implementation will keep these dimensions explicit and only mark a human-accepted episode verified when it has mechanical evidence.
3. **Git staleness is repository- and history-dependent.** A captured SHA that is unavailable, unrelated to the current branch, or outside shallow history cannot support a reliable commit count. Such cases must be `unknown`, not silently `fresh`. Deletions and changed paths should include concrete reasons. Dependency support must name which manifests are recognized.
4. **Hooks are best-effort adapters.** Client hook payloads evolve and do not all expose shell exit status/output in the same form. The initial supported client is Claude Code. Its hook integration will capture only events with documented command/result fields and will fail open if the payload is incomplete. MCP search remains the reliable fallback for clients without context-injection hooks.
5. **Redaction cannot guarantee secret removal.** Redaction runs before persistence and covers common token, private-key, password, and connection-string forms, but the product must say this is best-effort. Event output remains short-lived and is never returned from MCP.
6. **Lexical retrieval cannot guarantee paraphrase recall.** Multi-query search, normalized error signatures, and path anchors improve coverage without embeddings. The benchmark should determine whether optional semantic retrieval is justified; a high paraphrase target is a hypothesis, not a promise.
7. **The PRD's 24-hour plan describes a hackathon slice, not a maintenance guarantee.** The product should ship documented limitations and a runnable deterministic demo. Public-issue corpus curation and agent-level experiments are separate evaluation work and cannot be represented as completed without actual data and runs.

## Delivery sequence

Each completed component is committed and pushed to the configured GitHub remote.

| Step | Component | Exit condition | Commit scope |
| --- | --- | --- | --- |
| 0 | Product analysis and build plan | Decisions and limitations are recorded | Documentation |
| 1 | Package scaffold, schemas, local database, redaction | The package installs and initializes a project database | Foundation |
| 2 | CLI and episode lifecycle | Init, doctor, status, create/list/show, and human review are available | CLI workflows |
| 3 | Git anchors and staleness | Episodes expose reproducible fresh/drifted/stale/unknown reasons | Repository awareness |
| 4 | Retrieval and MCP | Search/get/propose use the shared engine and enforce project scope | Agent interface |
| 5 | Hook capture and fail-to-pass drafts | Supported Claude Code events can safely create reviewable drafts | Capture workflow |
| 6 | Demo, evaluation harness, docs, and release setup | Quickstart, seeded demo, metrics runner, license, and CI config are present | Release readiness |

## Completion boundary

The implemented runtime covers the v1.1 P0 CLI, SQLite/FTS5 memory engine, Git-aware staleness, Claude Code MCP connection, safe agent proposals, hook-based event capture, human review queue, deterministic demo, and retrieval-metrics runner. The PRD's evaluation experiment is incomplete: this release has no public-issue corpus and does not launch or analyze agent runs. The P1 Claude Code Edit/Write pre-tool hook injects at most three anchored episodes when available; other MCP clients can search with paths.

The spec's two-minute install target depends on Python 3.11+, Git, and a supported client already being installed. The first release will document those prerequisites and the supported hook contract rather than promise universal client setup.

## Release review

The core v1.1 workflow is implemented: local initialization, doctor checks, manual episodes, hook event capture, fail-to-pass draft detection, human review, repository and dependency anchors, scoped MCP search/get/propose, and deterministic retrieval metrics. The supported real client is Claude Code. The build and CI use pytest and exercise Python 3.11 and 3.12 on Linux and Windows.

The evaluation requirement is only partially fulfilled. The shipped runner computes Recall@5, MRR, Precision@5, and local retrieval latency from a synthetic corpus. It does not launch coding-agent runs or parse transcripts. The bundled corpus has 12 targets and 30 distractors, but contains no incidents sourced from public issues. No claim about reducing repeated failed attempts or agent tool calls is supported by this fixture.

The product does not implement P1 LLM narrative drafting, P2 semantic embeddings, or P2 retrieval feedback. Supersession is represented in the episode model but has no dedicated review workflow. The Claude Code pre-edit hook is synchronous, has a three-second timeout, and only targets Edit/Write calls with file paths.

The release measurements and corpus format are documented in the root README and eval/README.md. They should be replaced or supplemented with the PRD's public-issue corpus and agent-level experiment before making product-effectiveness claims.
