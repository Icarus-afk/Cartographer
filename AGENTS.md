# AGENTS.md — Cartographer

## Quick Start
```bash
pip install -e ".[dev,watch]"   # install + dev deps
make lint                        # ruff check cartographer/ tests/
make test                        # pytest -v (90 tests)
make lint-fix                    # auto-fix sortable issues
make vscode-compile              # tsc for editors/vscode (run from root)
```

## Architecture

- **Python package** (`cartographer/`) — 8 engine modules: ingestion, parser (20 tree-sitter languages), graph (+ `paging.py` hub sampler), embedding (384-dim), query, architecture, compression, git, setup
- **Entrypoints**: `cartographer.cli:main` (26 CLI commands + `git`/`repo`/`db`/`mcp` groups), `cartographer.mcp.server:main` (MCP stdio server, 20 tools + 3 resources)
- **VS Code extension** (`editors/vscode/`) — TypeScript, MCP-first client with CLI fallback
- **DB**: SQLite WAL mode, per-project `.cartographer/data.db` by default

## Key Conventions
- Python: ruff defaults (line-length 100, select E/F/I/N/W)
- TypeScript: project tsconfig, no linter config yet
- Conventional commits: `fix:`, `feat:`, `perf:`, `chore:`, `docs:`
- Prefer editing existing files over creating new ones
- No comments in code unless necessary
- No emojis in code or docs unless user requests

## CLI Commands
```bash
cartographer setup               # full-suite setup: MCP configs + VS Code ext (--scope project|global|all, --check)
cartographer index PATH          # full re-index
cartographer watch PATH          # incremental watch (needs watchdog)
cartographer update-index FILE   # incremental re-index (one file)
cartographer delete-file FILE    # remove deleted file from graph
cartographer graph-data          # JSON graph export (hub-seed --offset cursor → next_offset/has_more, --dir, --expand-node-id)
cartographer mcp start           # MCP stdio server
```

## MCP Protocol
- JSON-RPC 2.0 over stdio, newline-delimited
- **Notifications must NOT have an `id` field** (use `sendNotification()` helper) — `fastmcp` rejects with `-32602`
- MCP server reads `.cartographer/config.json` per project

## VS Code Extension
- Build: `make vscode-compile` (or `cd editors/vscode && npm install && npm run compile`)
- Package: `make vscode-package` (or `cd editors/vscode && npx vsce package`) → install via `code --install-extension`
- 21 commands, Ctrl+Shift+C prefix, multi-root workspace support
- Graph: cursor Load More (`next_offset`/`has_more`), type-filter chips, details panel (Open/Expand/Focus/Impact), pauseable layout
- MCP-first: tries persistent MCP connection, falls back to CLI spawn
- `update_index` MCP tool used for file save events (not full re-index)

## Testing Quirks
- `tests/test_parsers.py` has 44+ tests covering all 20 parsers
- `tests/test_integration.py` has 15 integration tests (index pipeline, graph persistence)
- Run `make test` from repo root

## Project Config (`.cartographer/config.json`)
```json
{"dbPath": ".cartographer/data.db", "autoReindex": true, "graphLimit": 400}
```
- `dbPath` relative to project root or absolute
- `mcpPort: 0` means stdio transport

## Environment
- `CARTOGRAPHER_DB` overrides default DB path
- `--db` flag available on most commands
