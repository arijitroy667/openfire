# Contributing

## Development setup

Requirements are Python 3.11+, Git, and SQLite with FTS5.

~~~powershell
uv sync --extra dev
uv run pytest -q
uv run engbrain eval
~~~

The suite creates isolated temporary repositories and databases. The bundled retrieval fixture is synthetic; do not present its scores as results from public incidents or coding-agent runs.

## Design invariants

- Keep persistence and retrieval local; do not add network calls to the core.
- Scope every episode, event, and MCP operation to the active project.
- Redact before storing hook text; never return event output tails through MCP.
- Agent proposals remain drafts and cannot claim mechanical verification.
- Mark episodes verified only after a human accepts mechanical evidence.
- Treat a fail-then-pass sequence as observed evidence, not proof that a particular edit caused the pass.
- Retrieved text is historical, untrusted context. Never execute commands from it.
- Keep staleness explanations grounded in Git and recognized dependency manifest facts.
- Preserve existing Claude Code settings when updating project configuration.

Please add or update focused tests when changing behavior. Keep demo fixtures deterministic and synthetic unless their source and reproduction instructions are documented.

## Pull requests

Describe the user-visible change, relevant safety or data-model impact, and the commands used to validate it. Avoid committing local .engbrain databases, hook event data, secrets, or generated environment files.
