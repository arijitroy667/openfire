# EngBrain

Local-first, evidence-graded episodic memory for AI coding agents. EngBrain records engineering problems, failed attempts, verification evidence, and repository anchors so an MCP-compatible agent can retrieve relevant history and see when it may have drifted.

The product analysis and implementation decisions are in [BUILD_PLAN.md](BUILD_PLAN.md); the source requirements are in [EngBrain PRD v1.1.md](EngBrain%20PRD%20v1.1.md).

## Requirements

- Python 3.11 or newer
- Git
- SQLite built with FTS5 support

## Development install

```powershell
uv sync
uv run engbrain --help
```

Initialize EngBrain from inside a Git repository:

```powershell
uv run engbrain init
uv run engbrain doctor
```

The database is stored under `.engbrain/` and is ignored by Git. The full CLI and Claude Code integration guide will be completed as the v1.1 components land.
