# EngBrain: Product Requirements Document v1.1

**Version:** 1.1 | **Status:** Build spec for the 24-hour solo hackathon | **Author:** Ariz (Arijit Roy) | **Date:** 2026-10-26 | **Supersedes:** v1.0 | **License:** MIT (proposed)

## 1. Summary

EngBrain is a local-first, open-source memory layer for AI coding agents. It records what was tried, what failed, and what was verified to work in a repository, then serves that history to any MCP-compatible agent when it is relevant. Every memory carries graded evidence and a computed staleness label, so an agent can tell a verified fix on unchanged code from an old guess about code that has since been rewritten.

**Pitch:** Agents forget failed attempts between sessions. EngBrain remembers them, proves them, and flags them when they go stale.

### 1.1 Changes from v1.0

| Area | v1.0 | v1.1 | Reason |
| --- | --- | --- | --- |
| Retrieval | Single-query FTS5 | Multi-query FTS5, error signatures, and file anchors, fused with RRF | v1.0 demo required paraphrased queries, which lexical search misses |
| Capture | Manual 10-field form | Hook-based fail-to-pass detection producing draft episodes with mechanical evidence; manual form kept as fallback | Manual capture is the adoption bottleneck |
| Staleness | P2 | P0, computed from git anchors | Main differentiator |
| Recall trigger | Agent must choose to call the tool | Anchor-triggered recall via hooks where supported; tool-call fallback with a paths parameter | Optional tools are called inconsistently |
| Git import | P0 episode source | Removed as episode source; Git used for anchors and staleness only | Commit messages lack reasoning |
| Agent writes | record\_episode saves directly | propose\_episode creates a draft; only a human can accept | Prevents memory poisoning |
| Evaluation | 10-20 incidents, single run | 12+ incidents, 5+ from real public issues, 3 runs per condition, retrieval metrics reported separately | Reduces noise and leakage |
| Schedule | MCP at hours 10-14 | MCP and a real client working by hour 5 | Integration is the largest unknown |

## 2. Problem

### 2.1 Problem statement

Engineering knowledge about failure does not survive between sessions. A developer or coding agent spends an hour learning that a connection pool is exhausted, that three plausible fixes did not work, and which change held up under load. Weeks later a new session meets a similar symptom with none of that context and repeats the same approaches.

**One sentence:** The reasoning, failed attempts, and evidence behind past fixes are not stored in a reusable, trustworthy, and current form.

### 2.2 Who has the problem

- Developers on long-lived repositories who use AI coding agents across many sessions
- Solo developers and small teams without maintained documentation
- Maintainers who inherit code with unexplained pins, workarounds, and configuration

### 2.3 Observable pain points

- **Repeated failed approaches:** a new session re-runs fixes that already failed.
- **Lost rationale:** a dependency pin or workaround has no recorded reason.
- **Silent staleness:** where notes or memories exist, nothing checks whether they are still true of the current code.
- **Unverifiable memory:** transcripts and extracted facts mix hypotheses, wrong suggestions, and confirmed fixes with no grading.

### 2.4 Current alternatives and gaps

| Alternative | What it does | Gap EngBrain targets |
| --- | --- | --- |
| Rules files (CLAUDE.md, AGENTS.md, GEMINI.md) | Static instructions loaded at session start | Manually maintained, no failure history, no staleness check |
| Git history and PRs | Records what changed | Rarely records what was tried and failed, or why |
| Generic agent memory (Mem0, Letta, vendor memory features) | Stores extracted facts and preferences, often over MCP | In the author's October 2026 review, none graded evidence or computed git-based staleness; this is not an exhaustive survey and must be re-checked before launch |
| Chat history search | Finds old conversations | Noisy; indexes hypotheses next to confirmed facts |

**Honest limits:** No market size is claimed. The hypothesis that retrieved history reduces repeated failed attempts is exactly what the benchmark in section 12 tests.

## 3. Solution

### 3.1 Product definition

EngBrain is episodic engineering memory with four capabilities:

1. **Capture:** hooks observe command runs; a detector turns a failure-then-success sequence into a draft episode.
2. **Verify:** drafts carry mechanical evidence (commands, exit codes, diff summary). A human accepts or rejects them.
3. **Recall:** agents query over MCP with several phrasings and file paths; EngBrain returns at most five graded episodes.
4. **Staleness:** every result is labeled fresh, drifted, or stale by comparing its anchors to the current repository.

### 3.2 Principles

1. **Evidence over confidence:** show what was observed; never invent a root cause from a similar error.
2. **Memory informs, never commands:** retrieved fixes are context to check against the current state.
3. **Agents propose, humans accept:** agent-written memories stay drafts.
4. **Local-first:** all data stays on the developer's machine by default.
5. **Small retrieval:** return at most five records; detail only on request.
6. **Staleness is computed, not guessed:** it comes from git facts, not LLM judgment.

### 3.3 Non-goals

No autonomous coding agent, no execution of retrieved commands, no dashboard or SaaS, no team sync, no graph database, no silent capture of full terminal sessions, no embeddings in P0.

### 3.4 Positioning

EngBrain is a memory layer, not an agent harness. It plugs into harnesses (Claude Code, Antigravity, Cursor, or any MCP client) rather than competing with them. Differentiators: failure-first episodes (attempts and rejected alternatives are first-class), mechanically captured verification, git-computed staleness, harness-agnostic local storage, and a published benchmark. Harness vendors may ship their own memory features, so the defensible value is evidence, staleness, and measured results, not storage.

## 4. Users and use cases

| ID | Use case | Actor |
| --- | --- | --- |
| UC-1 | A test fails twice then passes; EngBrain drafts an episode with the commands and diff as evidence | Hook, developer |
| UC-2 | A new session searches with different wording and finds the earlier incident | Agent |
| UC-3 | The agent is about to edit a file with prior incidents and is shown them first | Agent via hook |
| UC-4 | A developer asks why a dependency is pinned | Developer, agent |
| UC-5 | A user inspects an episode's evidence, status, and staleness reasons | Developer |
| UC-6 | A developer reviews drafts and accepts, edits, or rejects them | Developer |

## 5. Goals and success metrics

**Goals:** G1 capture with low friction. G2 retrieve across wording changes. G3 never present stale or unverified memory as current fact. G4 install in under two minutes. G5 publish measured results with honest limits.

Targets below are initial hypotheses, not promises; the submission reports what was measured.

| Metric | Definition | Initial target |
| --- | --- | --- |
| Recall@5 (lexical queries) | Target episode in top 5 when the query shares wording | 0.9 or higher |
| Recall@5 (paraphrase queries) | Same, with no shared distinctive tokens | 0.7 or higher |
| MRR and Precision@5 | Rank quality and noise | Reported, no target |
| Repeated failed attempts | Agent actions matching a ground-truth failed attempt, with vs without memory | Fewer with memory; reported as counts with n |
| Tool calls to pass | Calls until the target test passes, capped at 30 | Median lower with memory; reported |
| Capture detection | Scripted fail-then-pass sessions producing a correct draft | 8 of 10 |
| Staleness correctness | Seeded drift cases labeled correctly (unit tests) | 100 percent of seeded cases |
| Search latency | p95 on 1,000 episodes, local | Under 200 ms |
| Install | Fresh machine to working MCP and hooks | Two commands, under two minutes |

## 6. Functional requirements

| ID | Requirement | Pri | Acceptance criteria |
| --- | --- | --- | --- |
| FR-01 | Init | P0 | `engbrain init --client claude-code` creates `.engbrain/`, detects repo fingerprint, registers the MCP server and hooks |
| FR-02 | Doctor | P0 | `engbrain doctor` checks FTS5, git, DB integrity, MCP and hook registration with clear errors |
| FR-03 | Episode model and CLI | P0 | Create, show, list episodes; validation per section 8; manual form works with no LLM |
| FR-04 | Anchors | P0 | Each episode stores file paths, dependencies with versions, and the commit SHA at capture |
| FR-05 | Error signature | P0 | Error text is normalized (paths, numbers, hex, UUIDs stripped) and stored for matching |
| FR-06 | Multi-query search | P0 | search\_episodes accepts 1 to 5 queries and optional paths; results fused by reciprocal rank |
| FR-07 | Staleness label | P0 | Every result shows level and reasons computed from git and dependency files |
| FR-08 | MCP tools | P0 | search\_episodes, get\_episode, propose\_episode work from one real client |
| FR-09 | Project scoping | P0 | No result crosses projects unless explicitly requested; IDs validated |
| FR-10 | Event capture | P0 | Post-command hook stores command, exit code, time, and redacted 2 KB output tail in a 7-day buffer |
| FR-11 | Fail-to-pass detector | P0 | Same normalized command failing 2 or more times then passing creates a draft with evidence\_kind mechanical |
| FR-12 | Review queue | P0 | `engbrain review` lists drafts; accept, edit, reject; accepted mechanical drafts become verified |
| FR-13 | Redaction | P0 | Common key, token, private-key, and connection-string patterns removed before any write |
| FR-14 | Benchmark runner | P0 | A script computes Recall@5, MRR, Precision@5 and launches agent runs per section 12 |
| FR-15 | No execution | P0 | Nothing in EngBrain runs retrieved commands or edits source |
| FR-16 | Anchor-triggered recall | P1 | Hook injects up to 3 episodes anchored to files being edited; where hooks cannot inject, FR-06 paths is the fallback |
| FR-17 | Supersession | P1 | A new episode can supersede an old one; superseded results are demoted and labeled |
| FR-18 | LLM narrative drafting | P1 | Optional adapter writes draft prose; off by default; core works without it |
| FR-19 | Semantic retrieval | P2 | Optional local embeddings added only if paraphrase Recall@5 misses target |
| FR-20 | Retrieval feedback | P2 | Helpful or not-helpful marks stored locally |

## 7. System design

### 7.1 Architecture

```
 Coding agent (Claude Code | Antigravity | any MCP client)
   |  MCP over stdio                      ^ hook events (JSON on stdin)
   v                                      |
 +----------------------+        +-----------------------+
 | MCP server           |        | Hook adapter          |
 | search / get / propose|       | post-command, session |
 +----------+-----------+        | start, pre-edit       |
            |                    +-----------+-----------+
            v                                v
 +--------------------------------------------------------+
 | Memory engine (one shared library)                     |
 | Retriever | Ranker | Staleness | Detector | Redactor    |
 +-----------+-------------------------+------------------+
             |                         |
             v                         v
     SQLite + FTS5               Git CLI (subprocess)
     .engbrain/engbrain.db       log, diff, rev-parse
             ^
             |
   CLI: init, doctor, recall, review, status, eval
```

### 7.2 Components

| Component | Responsibility |
| --- | --- |
| MCP server | Exposes three tools; enforces project scope; returns results flagged untrusted |
| Hook adapter | Converts client hook payloads into engine calls; never blocks the agent for more than 200 ms |
| Memory engine | Single library used by CLI, MCP, and hooks; owns all reads and writes |
| Retriever and ranker | Candidate generation, rank fusion, boosts and penalties |
| Staleness engine | Compares anchors with current git state and dependency files |
| Detector | Finds fail-to-pass sequences in the event buffer and builds drafts |
| Redactor | Removes secrets from events and episode text before persistence |
| SQLite and FTS5 | Local storage and keyword index |
| CLI | Setup, review, inspection, and benchmark entry points |

### 7.3 Key flows

**Capture:** (1) post-command hook sends command, exit code, and output tail; (2) redactor cleans it; (3) event stored in the buffer; (4) detector sees the same normalized command fail 2 or more times then pass; (5) engine collects files changed since the first failure with git diff, the dependency state, and the current SHA; (6) a draft episode is created with an error signature, attempts, mechanical evidence, and anchors; (7) the developer runs `engbrain review` and accepts, edits, or rejects.

**Recall:** (1) the agent calls search\_episodes with 1 to 5 phrasings and optional paths; (2) each query runs against FTS5; error-signature and anchor matches are added; (3) rankings are fused and boosted; (4) staleness is computed for the top candidates; (5) at most five summaries return; (6) the agent calls get\_episode for full evidence and checks the current environment before acting.

**Agent-proposed memory:** the agent calls propose\_episode; a draft with origin agent and evidence\_kind asserted is saved; it is excluded from search until a human accepts it.

### 7.4 Retrieval and ranking

1. **Candidates per query:** FTS5 MATCH using the porter tokenizer with tokens OR-joined and syntax escaped; initial column weights: error\_signature 4, title 3, problem 2, attempts and solution 1.
2. **Exact lookups:** error-signature equality and anchor path or dependency overlap.
3. **Fusion:** reciprocal rank fusion across the query lists with k = 60.
4. **Adjustments:** bounded boosts for signature match and anchor overlap; small penalties for stale, superseded, and unverified. Adjustments reorder only the fused top candidates and never promote an irrelevant episode into the results.
5. **Output:** top five. Weights are initial and tuned on the dev split only (section 12).

### 7.5 Staleness engine

Anchors recorded at verification: file paths, dependency names with versions, commit SHA.

| Level | Rule (initial, configurable) |
| --- | --- |
| fresh | No commits touched the anchored paths since the SHA, and dependency versions are unchanged |
| drifted | 1 to 19 commits touched anchored paths, or a dependency changed within the same major version |
| stale | An anchored path was deleted or renamed, a dependency major version changed, or 20 or more commits touched anchored paths |

Every label lists its reasons, for example: 3 commits touched src/db/pool.py since verification. Episodes with no anchors are labeled unknown, never fresh.

## 8. Data model

**projects:** id, name, repo\_root, repo\_fingerprint, created\_at.

**episodes:** id, project\_id, title, episode\_type (debugging, architecture\_decision, dependency, deployment, operational\_gotcha), problem, context, error\_signature, attempts\_json, solution\_taken, rejected\_alternatives\_json, verification\_text, evidence\_kind (mechanical, asserted, none), evidence\_json (commands, exit codes, diff stat), status (unresolved, unverified, verified, superseded), review\_state (draft, accepted, rejected), origin (hook, manual, agent), verified\_at\_sha, supersedes\_episode\_id, created\_at, updated\_at.

**episode\_anchors:** id, episode\_id, kind (path, dependency, commit), value, version.

**events:** id, project\_id, session\_id, command, normalized\_command, exit\_code, output\_tail (redacted, 2 KB), cwd, created\_at; expires after 7 days.

**retrievals:** id, project\_id, queries\_json, returned\_ids\_json, created\_at; local only, used by the benchmark.

**episodes\_fts:** FTS5 virtual table over title, problem, context, error\_signature, attempts, solution, rejected alternatives.

**Notes:** foreign keys on; writes in transactions; indexes on project\_id, status, review\_state, error\_signature, anchor value; accepted episodes are never deleted, only superseded.

## 9. MCP interface

| Tool | Inputs | Behavior | Output |
| --- | --- | --- | --- |
| search\_episodes | queries (1 to 5 strings), paths (optional), episode\_type (optional), limit (max 5) | Accepted episodes in the active project only; fused ranking | Per result: id, title, summary, status, evidence\_kind, staleness level and reasons, match reason, anchors, created\_at |
| get\_episode | episode\_id | Full record, project-validated | Problem, context, attempts, solution, rejected alternatives, evidence, status, staleness, provenance |
| propose\_episode | title, type, problem, context, attempts, solution (optional), evidence text (optional) | Saves a draft with origin agent; cannot set verified; redacts secrets | Draft id and review\_state |

**Tool description requirement:** the search\_episodes description must instruct the calling agent to pass several rephrasings and the files it is about to touch.

**Safety:** no tool executes commands or edits files; all text fields are returned inside structured data marked untrusted, so retrieved content is never an instruction; output tails from events are never returned over MCP; errors are logged without payloads.

## 10. Client integration

**Reference client:** Claude Code. MCP over stdio. Hooks: post-command (event capture), session start or prompt submit (context injection), pre-edit (anchor-triggered warning). **Stretch client:** Antigravity through its plugin and MCP mechanism.

**Hour 2-5 spike (required):** confirm the real hook payload fields (command, exit status or output) and whether each hook can inject context. If a hook cannot inject, fall back to the paths parameter plus an instruction in the project rules file telling the agent to search before editing. The spec's behavior does not change; only the delivery path does.

## 11. Security and privacy

- **Local only:** the core makes no network calls; the LLM adapter is off by default.
- **Redaction:** best-effort patterns for cloud and API key prefixes, bearer tokens, private key blocks, passwords in connection strings, and high-entropy strings near words like secret or token. Docs tell users to review drafts before accepting.
- **Event hygiene:** output tails truncated to 2 KB, 7-day expiry, configurable exclusion list for commands (environment dumps, reading .env files) and paths.
- **Poisoning:** agents write drafts only; drafts are not searchable; acceptance is human-only; mechanical evidence comes from hooks, not agent claims.
- **Injection:** untrusted flag and structured output; no tool returns raw event output.
- **Isolation:** every query is parameterized by project\_id.

## 12. Evaluation plan

**Corpus:** 12 target incidents plus at least 30 distractor episodes so ranking is not trivial. At least 5 incidents come from real, closed public issues the author did not write, reproduced as small fixtures; the rest come from the author's projects.

**Per incident:** a stored episode, two queries (one sharing wording, one paraphrased), a reproducible repro task, and ground-truth failed attempts expressed as normalized commands or files.

**Split:** tune ranking weights on 4 dev incidents; report on the other 8. If tuning uses all 12, say so.

**Retrieval metrics (deterministic, cheap):** Recall@5, MRR, Precision@5 for lexical and paraphrase sets, plus latency.

**Agent-level runs:** condition A no memory, condition B memory through MCP (and hooks where available); same model and settings, 3 runs per incident per condition, 30 tool-call cap. That is 72 runs: estimate wall-clock and API cost before starting and run in the background. Metrics: repeated failed attempts (a command or edit matching a ground-truth failed attempt, counted from the transcript), tool calls to pass, success.

**Staleness tests:** unit tests for fresh, file changed, file deleted, and dependency version changed.

**Reporting:** counts with n, not percentages alone; no significance claims; raw transcripts and scripts published; limitations stated (small n, author-built fixtures, one model).

## 13. Technology stack

| Layer | Choice | Rationale |
| --- | --- | --- |
| Language | Python 3.11+ | Fast iteration; strong CLI and MCP support |
| CLI | Typer | Typed, concise commands |
| Storage and search | SQLite with FTS5 (standard library sqlite3) | Local, zero infrastructure; `doctor` verifies FTS5 |
| MCP | Official Python MCP SDK, stdio transport | Standard client compatibility |
| Validation | Pydantic v2 | Schema and tool-input validation |
| Git | Git CLI via subprocess | Anchors and staleness without extra dependencies |
| Tests | pytest | Isolation, idempotency, staleness, MCP contracts |
| Packaging | pyproject.toml, console script, pipx or uvx install | Two-command install |
| Optional | LLM adapter; fastembed with sqlite-vec | Off by default; added only per FR-18 and FR-19 |

**Repository layout:** `src/engbrain/` with cli.py, config.py, models.py, db.py, engine.py, retrieval.py, staleness.py, detector.py, redaction.py, hooks.py, mcp\_server.py; `tests/`; `examples/demo-repo/` and `examples/incidents/`; `eval/` for the benchmark; README.md, LICENSE, CONTRIBUTING.md.

**CLI:** init, doctor, status, recall, episode (show, list, create), review, mcp serve, hook (internal), eval.

## 14. Demo

A deterministic demo repo with three seeded incidents: connection pool exhaustion, a dependency pin, and an environment-variable gotcha.

1. Run a failing test twice, then fix it; show the auto-drafted episode and its mechanical evidence.
2. Accept it in `engbrain review`.
3. Start a fresh agent session and ask using different wording; show retrieval, the evidence, and the staleness label.
4. Change an anchored file and show the label move from fresh to drifted with reasons.
5. Show the benchmark table: retrieval metrics and with-versus-without counts.

## 15. Delivery plan (24 hours, solo)

| Hours | Workstream | Exit criterion |
| --- | --- | --- |
| 0-2 | Scaffold, schema, init, doctor, redaction | init creates the DB; FTS5 confirmed; tests run |
| 2-5 | MCP server, reference client, hook payload spike | Client retrieves a hardcoded episode over MCP; hook fields confirmed or fallback chosen |
| 5-8 | Multi-query search, signatures, fusion, anchors, staleness | Paraphrase query returns a seeded episode in the top 5; 3 drift cases labeled correctly |
| 8-12 | Event capture, detector, review queue, anchor-triggered recall | A real fail-to-pass in the demo repo yields a draft; accepting it makes it searchable |
| 12-16 | Demo repo, incidents, benchmark harness; start agent runs in the background | Retrieval metrics produced; runs launched |
| 16-19 | Tests, README, install path, demo recording, results table | Fresh-machine install in two commands |
| 19-24 | Buffer for sleep, bugs, and resubmission | No new features |

**No-go rule:** if MCP retrieval does not work by hour 5, drop hooks and ship MCP plus manual capture.

**Cut order if behind:** (1) LLM narrative drafting, (2) anchor-triggered hook, keeping the paths fallback, (3) agent-level benchmark reduced to 6 incidents with 2 runs, (4) supersession. **Never cut:** the MCP slice, staleness, the review queue, retrieval metrics.

Realistic solo productive time is about 16 to 18 hours; the plan assumes the cut order will be used.

## 16. Risks and mitigations

| Risk | Likelihood | Impact | Mitigation |
| --- | --- | --- | --- |
| Hook payloads lack needed fields or cannot inject context | Medium | High | Hour 2-5 spike; paths fallback; manual capture |
| Paraphrase queries still miss under FTS5 | Medium | Medium | queries list, signatures, anchors; local embeddings only if the metric misses |
| False verified labels | Low | High | Verified only from mechanical evidence plus human acceptance |
| Agent ignores retrieved memory | Medium | Medium | Measure it in the benchmark; report honestly |
| Benchmark leakage or noise | High | Medium | Real public issues, dev/test split, 3 runs, distractors, disclosed limits |
| Secrets persisted | Low | High | Redaction, exclusions, 2 KB tails, review before accept |
| Memory space is crowded | High | Medium | Position on evidence, staleness, and results; re-check competitors before launch |
| Scope creep and 24-hour overrun | High | High | Cut order, no-go rule, buffer block |

## 17. Open-source readiness checklist

- MIT license, README with a three-minute quickstart, CONTRIBUTING.md
- Install in two commands: `pipx install` the package, then `engbrain init --client claude-code`
- CI running pytest; `engbrain doctor` output documented
- Demo recording and published benchmark results with scripts
- Documented limitations: best-effort redaction, small benchmark, Claude Code as the verified client

## 18. Roadmap after the hackathon

1. More clients (Antigravity, Cursor) and hook parity
2. Optional local embeddings and hybrid retrieval, if justified by the benchmark
3. Supersession workflows and duplicate detection
4. Opt-in team sharing with access controls
5. Larger benchmark from real repositories

## 19. Open questions

- Which hook events expose exit status and allow context injection in each client?
- Are the staleness thresholds (20 commits, major version change) reasonable on real repositories?
- Should accepted episodes be committed to the repo as files for team sharing, or stay local?
- What does the current competitive landscape show on evidence grading and staleness at launch time?
