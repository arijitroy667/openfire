# EngBrain

EngBrain is a local-first, repository-scoped engineering memory for AI coding agents. It records problems, failed attempts, evidence, and repository anchors; an MCP server lets an agent retrieve accepted episodes and see whether their anchors have changed.

The [product analysis and build record](BUILD_PLAN.md) explains the design choices and limitations. The original requirements are in [EngBrain PRD v1.1](<EngBrain PRD v1.1.md>).

## What it solves

Engineering reasoning disappears between coding sessions. Developers and agents repeat failed approaches, miss the reason behind workarounds, and may trust notes that no longer match the repository. EngBrain keeps failure history with its evidence and computes whether relevant code or dependency anchors have drifted.

## How it works

1. Asynchronous Claude Code hooks capture supported shell command outcomes locally. Likely secrets are redacted before persistence and event tails expire after seven days.
2. Two or more failures followed by a successful run of the same normalized command create a draft episode with the observed commands, exit codes, and a safe diff summary.
3. A person reviews, edits, accepts, or rejects drafts. Only accepted episodes are searchable; mechanically captured evidence can become verified after human acceptance.
4. When Claude Code is about to use Edit or Write on a file, a pre-tool hook searches its path anchors and injects up to three matching episodes with freshness reasons. CLI or MCP search also combines FTS5 text, normalized error signatures, and file or dependency anchors with reciprocal-rank fusion.
5. Agents can propose an episode, but proposals stay unverified drafts. EngBrain never executes a retrieved command.

## Architecture

~~~mermaid
flowchart LR
    Agent[Claude Code or another MCP client] -->|MCP stdio| MCP[MCP server]
    Agent -->|command hook JSON| Hook[Hook adapter]
    CLI[CLI] --> Engine[Shared memory engine]
    MCP --> Engine
    Hook --> Engine
    Engine --> SQLite[SQLite and FTS5]
    Engine --> Git[Git CLI and dependency manifests]
~~~

The CLI, MCP server, and hook adapter use one Python engine. SQLite is stored under the repository's ignored .engbrain directory. MCP processes are scoped to a repository root, and their returned episode text is marked untrusted context.

## Technology

- Python 3.11 or later
- Typer CLI and Pydantic v2 models
- SQLite through Python's standard library, with FTS5
- Official Python MCP SDK over stdio
- Git CLI subprocesses for repository anchors and staleness
- pytest for the local suite

The core requires no hosted service, LLM, embedding model, or network access.

## Install and initialize

Requirements: Python 3.11+, Git, SQLite with FTS5, and Claude Code for the reference hook integration. From a checkout of this repository, install the editable package and initialize Claude Code:

~~~powershell
pipx install --editable .
engbrain init --client claude-code
engbrain doctor
~~~

The first two commands are the setup path after obtaining the checkout; doctor is an optional diagnostic. The EngBrain command must be on PATH. Initialization creates the local database, excludes .engbrain from this repository's Git info/exclude file, and registers the project MCP server and asynchronous command hooks in Claude Code configuration. Review the generated config and approve the project MCP server in Claude Code when prompted.

For development, use uv instead:

~~~powershell
uv sync --extra dev
uv run engbrain init
uv run engbrain doctor
~~~

The database and captured events stay local by default. Redaction is best-effort; inspect drafts before accepting them and do not treat the hook as a secure boundary for secrets.

## Use the CLI

~~~powershell
engbrain status
engbrain episode create --title "Pool exhaustion under load" --problem "Concurrent workers exhaust the connection pool" --attempt "Raised the request timeout; failure persisted" --path src/pool.py
engbrain episode list
engbrain episode show EPISODE_ID
engbrain episode supersede OLD_EPISODE_ID --with NEW_EPISODE_ID
engbrain review
engbrain review edit EPISODE_ID --solution "Raised the pool limit" --verification "Pool check passed"
engbrain review accept EPISODE_ID
engbrain recall --query "pool exhausted by parallel requests" --query "connection limit reached under concurrency" --path src/pool.py
engbrain feedback EPISODE_ID helpful
~~~

Manual episodes are accepted but remain unverified unless they carry mechanical evidence. Hook-created and MCP-proposed records begin as drafts. Use **engbrain review reject EPISODE_ID** to reject a draft.

Create and accept the replacement episode before superseding an older accepted record. The old episode remains available for inspection but leaves search results; the new record keeps a link to the old one.

After a recall, record whether a result helped with **engbrain feedback EPISODE_ID helpful** or **engbrain feedback EPISODE_ID not-helpful**. Feedback is stored locally and does not change ranking automatically.

The supported hook client in this release is Claude Code. EngBrain uses its [command hooks](https://code.claude.com/docs/en/hooks) and project [MCP configuration](https://code.claude.com/docs/en/mcp). The pre-edit hook is synchronous so Claude Code can add its context before the tool call; its timeout is three seconds, and it fails open when no safe matches are available. Other MCP clients can run **engbrain mcp serve --root REPOSITORY_PATH** using stdio and call **search_episodes**, **get_episode**, and **propose_episode**. The MCP server returns no event output tails.

## Demo

The [demo repository](examples/demo-repo/README.md) reproduces a connection-pool failure. Copy it outside this checkout, initialize it as its own Git repository, install EngBrain, and then run the same check twice, increase the pool limit, and run it once more. The Claude Code hooks should produce a draft for human review.

## Retrieval evaluation

Run the deterministic bundled fixture with:

~~~powershell
engbrain eval
engbrain eval --json
~~~

This run uses 12 synthetic target episodes, 30 synthetic distractors, and 24 lexical/paraphrase queries. On the local run recorded for this release, lexical Recall@5 was 1.00 (n=12) and paraphrase Recall@5 was 0.75 (n=12); the corresponding MRR values were 1.00 and 0.542. These are measurements of a small synthetic fixture, not public-issue data or agent behavior. They do not establish that EngBrain reduces failed attempts.

The runner accepts a custom JSON corpus; the format and metric definitions are in [eval/README.md](eval/README.md). The separate [Codex agent evaluation](eval/codex/README.md) has five simplified public-issue fixtures, seven synthetic fixtures, and a harness for 72 controlled runs. Its two-run setup pilot passed both conditions on one public-issue fixture; this is a harness check only, not evidence that memory improves agent outcomes. The full experiment remains to be run.

## Safety and known limits

- Redaction covers common secrets, but cannot guarantee that every sensitive value is removed.
- Hook capture is best-effort and supports documented Claude Code Bash and PowerShell hook payloads. It does not block the agent.
- A fail-then-pass sequence records observed outcomes; it does not prove which edit caused the pass.
- Staleness may be unknown when Git history is unavailable or anchors are missing. Recognized dependency manifests are listed in the build record.
- Retrieval is lexical with error-signature and anchor matching. Paraphrase recall is not guaranteed.
- Data is local and project-scoped; there is no team sync, dashboard, or remote database.
- The pre-edit hook matches Claude Code Edit and Write calls. Other MCP clients can use the paths parameter as a fallback.
- Semantic embeddings and LLM drafting are not implemented.

## Development

See [CONTRIBUTING.md](CONTRIBUTING.md) for setup and repository invariants. CI runs the pytest suite on Python 3.11 and 3.12 on Linux and Windows.

## License

MIT. See [LICENSE](LICENSE).
