# Getting Started

You can be productive in 2 minutes — one command indexes, the next answers.

## Install

```bash
git clone https://github.com/Icarus-afk/Cartographer.git
cd Cartographer
pip install -e .              # core
pip install -e ".[watch]"     # adds watchdog for `cartographer watch`
pip install -e ".[dev,watch]" # adds ruff + pytest
cartographer version          # cartographer 0.1.0
```

Requirements: `Python 3.10+`, `click`, `tree-sitter`, `fastembed`, `pathspec`, `mcp`, `numpy`, `tqdm`. Optional `watchdog`.

## Index your first repo

```bash
cartographer index /path/to/repo
# or inside the repo:
cartographer index .
# JSON for agents:
cartographer --json index .
```

Output:

```
Indexed 152 files in 24 directories
Duration: 2431ms
Languages: python: 89, typescript: 20
Frameworks: Django (98%)
Entities: 152 files parsed, 52 classes, 371 functions, 331 methods
References: 199 cross-file imports
```

By default DB is `~/.cartographer/index.db`. Override with `--db` or `$CARTOGRAPHER_DB` or per-project `.cartographer/config.json`.

Check health:

```bash
cartographer status
cartographer --json status    # {"status":"ok","counts":{"nodes":1890,"edges":3283},...}
cartographer doctor           # alias for status
```

## Search

```bash
# keyword search (exact symbol)
cartographer ask "UserService" --limit 5
cartographer ask "UserService" -t class
cartographer --json ask "UserService" --limit 5

# semantic (needs embed first)
cartographer embed
cartographer ask --semantic "classes that handle user authentication"
cartographer --json ask --semantic "auth middleware" --limit 10
```

## Ask natural language

```bash
cartographer query "what is the architecture?" 
cartographer query "explain Preprocessor"
cartographer query "who wrote auth module"
cartographer --json query "what depends on UserService"
```

`query` auto-detects intent: `architecture | summarize | explain | impact | path | git_blame/git_why/git_cochange | search`.

## Traverse

```bash
cartographer impact src/auth/service.py
cartographer neighbors UserService --depth 2
cartographer path UserController Database
cartographer summarize
cartographer file-summary src/auth/service.py   # ~200 tokens vs 2000
cartographer context --top-n 20                  # summary + arch + key nodes
```

All support `--json` and `--max-tokens` to fit LLM windows.

## Architecture

```bash
cartographer architecture --detect          # writes layers to DB
cartographer architecture                   # reads cached
cartographer --json architecture --detect
```

Detects `controller | business | data | presentation | api | middleware | config | infrastructure | migration | testing | utility | documentation`, frameworks (`django | rails | spring_boot | flutter/dart | nestjs | express | next.js | laravel | actix_web | axum`), patterns (`MVC | layered | clean | hexagonal | repository`).

## MCP for AI agents (one-time)

`opencode.json` is already configured:

```json
{ "mcp": { "cartographer": { "type": "local", "command": ["cartographer-mcp"], "enabled": true } } }
```

For Claude Desktop `claude_desktop_config.json`:

```json
{ "mcpServers": { "cartographer": { "command": "cartographer-mcp", "args": [] } } }
```

Start manually:

```bash
cartographer mcp start --verbose
cartographer mcp start --port 8080   # SSE
```

Tools (20): `status, doctor, health, list_repos, ensure_indexed, search, impact, neighbors, path, summarize, architecture, similar, ask, graph_data, index, context, update_index, delete_file, db_info, file_summary` + resources `cartographer://repos`.

LLM workflow:

```
status() → if empty: index(path=".")
search(query="UserService") → file_summary(file_path="src/...") → impact(target="UserService")
```

## Watch

```bash
cartographer watch /path/to/repo   # needs watchdog, handles all 31 langs
# or per-file:
cartographer update-index src/main.py
cartographer delete-file src/removed.py
```

VS Code does this automatically on save/rename/delete (batched 2s, `update_index`/`delete_file` via MCP).

## Next steps

- `docs/commands.md` — full CLI reference
- `docs/mcp.md` — all 20 MCP tools with JSON shapes
- `docs/architecture.md` — how ingestion → parsing → graph → embeddings works and where robustness lives
- `docs/troubleshooting.md` — doctor, common errors

`cartographer --help`, `cartographer status --help`, `cartographer ask --help` all show examples.
