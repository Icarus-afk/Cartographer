<p align="center">
  <img src="logo.png" alt="Cartographer Logo" width="200"/>
</p>

<h1 align="center">Cartographer</h1>

<p align="center">
  <strong>Repository Intelligence — LLM-first Knowledge Graph</strong>
</p>

<p align="center">
  Index any repo into a semantic graph. Ask questions, trace dependencies, and save 90%+ tokens — built for humans and for AI agents.
</p>

<p align="center">
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-MIT-blue.svg" alt="MIT"></a>
  <img src="https://img.shields.io/badge/python-3.10%2B-blue.svg" alt="Python 3.10+">
  <img src="https://img.shields.io/badge/version-0.1.0-green.svg" alt="0.1.0">
</p>

<p align="center">
  <a href="https://github.com/Icarus-afk/Cartographer"><img src="https://img.shields.io/github/stars/Icarus-afk/Cartographer?style=social" alt="Stars"></a>
  <img src="https://img.shields.io/badge/languages-31-yellow.svg" alt="31 Languages">
  <img src="https://img.shields.io/badge/MCP-20%20tools-orange.svg" alt="20 MCP Tools">
  <img src="https://img.shields.io/badge/tests-84%20passed-brightgreen.svg" alt="84 Tests">
  <img src="https://img.shields.io/badge/embeddings-bge--small--en--v1.5%20%E2%80%A2%20384d%20%E2%80%A2%20hybrid-purple.svg" alt="Hybrid Embeddings">
  <img src="https://img.shields.io/badge/robust-%E2%80%94%20timeouts%20%E2%80%A2%20chunked%20%E2%80%A2%20retries-red.svg" alt="Robust">
</p>

---

**Cartographer turns code into answers.** Instead of grepping filenames, ask *"What does UserService depend on?"* or *"Explain the checkout flow"* — Cartographer builds a graph of classes, functions, files, and edges (calls, inherits, imports) and lets you query it with precision. Every CLI command and every MCP tool supports `--json` for LLM automation with `{"status","data","hint"}` envelopes.

---

## Why Cartographer

- **LLM-first:** Every command has `--json`; every MCP tool returns JSON `{status,human,data,hint}` with clamp/validation. An LLM checks `status` → `index` if empty → `search/file_summary` — no scraping text.
- **Token savings:** `file_summary` ~200 tokens vs 2000 for a full file (90%); `summarize` ~200 vs 60k for 50 files (98.8%); `impact` ~300 vs 12k grep.
- **Robust at scale:** 1 MiB/2 MiB caps + binary check + `30s` per-file timeout + generic fallback; isolated per-file errors (one file never kills indexing); chunked graph inserts (`1000`) + `SQLITE_BUSY` retry; embeddings chunked `500` + model retry + valid-blob filtering + hybrid keyword boost; `~22 repos / 25k files / 247k nodes` benchmarked.
- **31 languages, no lock-in:** Tree-sitter for 20 code grammars + `dart`, `markdown` (ADR/diagram), `yaml/json/toml/sql/html/css/shell/dockerfile/protobuf` via `GenericParser`; missing grammar auto-falls back to regex — add a language by adding an extension, not a parser.

---

## Installation

```bash
git clone https://github.com/Icarus-afk/Cartographer.git
cd Cartographer
pip install -e .                 # core
pip install -e ".[watch]"        # + watchdog for `cartographer watch`
pip install -e ".[dev,watch]"    # + ruff/pytest

cartographer version             # cartographer 0.1.0
cartographer status              # health + indexing check
```

**VS Code:**

```bash
cd editors/vscode
npm install && npm run compile
npx vsce package
code --install-extension cartographer-0.1.0.vsix
```

---

## Quick Start (human)

```bash
# 1. Index
cartographer index .

# 2. Check
cartographer status
cartographer summarize
cartographer architecture --detect

# 3. Search (keyword) vs Query (natural language)
cartographer ask "UserService" --limit 5
cartographer query "what is the architecture?" --limit 10

# 4. Traverse
cartographer impact src/auth/service.py
cartographer neighbors UserService --depth 2
cartographer path UserController Database

# 5. Human-readable file
cartographer file-summary src/auth/service.py
```

**Quick Start (LLM / automation):**

```bash
cartographer --json status
# {"status":"empty","hint":"Run index(path=\".\")"} → then:
cartographer --json index .
cartographer --json ask "UserService" --limit 5
cartographer --json file-summary src/auth/service.py
# every command: {"status":"ok|empty|error","data":{...},"hint":"..."}
```

```python
# MCP (Opencode, Claude Desktop, Cursor)
# opencode.json already has: { "mcp": { "cartographer": { "command": ["cartographer-mcp"] } } }
# Tools: status, ensure_indexed, search, file_summary, impact, neighbors, path, ask, summarize, architecture, similar, graph_data, index, context, update_index, delete_file, db_info, list_repos, doctor, health
```

---

## CLI Reference

Global flags (before subcommand): `--db PATH` (`$CARTOGRAPHER_DB`), `--json`, `--verbose/-v`, `--quiet/-q`, `-h/--help`.

| Command | What it does | Example |
|---|---|---|
| `status` / `doctor` / `health` | DB + indexing + health (`tree_sitter/fastembed/mcp`, 31 langs) | `cartographer --json status` |
| `init [path] [--force]` | Init project DB + index | `cartographer init .` |
| `index [path]` | Index repo (idempotent) → `{files, languages, frameworks}` | `cartographer --json index /path` |
| `ask <query> [-t type] [-r repo] [-l 1-100] [-s]` | Keyword search (use `query` for NL) | `cartographer ask "UserService" -t class` |
| `query <text> [-r repo] [-l 1-100]` | Natural-language query (intent: search/explain/impact/path/architecture/summarize) | `cartographer query "explain checkout"` |
| `impact <target> [-r repo]` | Reverse deps (who imports/calls) | `cartographer --json impact UserService` |
| `neighbors <name> [-r repo] [-d 1-5]` | Graph traversal | `cartographer neighbors UserService -d 2` |
| `path <from> <to> [--max-depth 1-10]` | Shortest path | `cartographer path UserController DB` |
| `summarize [-r repo]` | Repo overview `{total_nodes, node_breakdown, top_files}` | `cartographer --json summarize` |
| `context [--top-n 10] [--max-tokens 1500]` | Compressed context package (summary+arch+nodes) | `cartographer context --top-n 20` |
| `architecture [--detect] [--verbose]` | Layers/patterns/frameworks | `cartographer architecture --detect` |
| `embed [-r repo]` | Generate `bge-small-en-v1.5` 384-d embeddings (chunked 500, retry, valid-blob filter) | `cartographer embed` |
| `similar <target> [-r repo] [-l 1-100]` | Hybrid semantic search (cosine + keyword boost) | `cartographer similar "auth middleware"` |
| `file-summary <path> [-r repo]` | ~200-token file summary vs 2000 | `cartographer file-summary src/main.py` |
| `graph-data [-r repo] [-l 80] [-o offset] [-d dir] [--expand-node-id N]` | JSON for graph viz | `cartographer graph-data --dir src/` |
| `watch [path] [-v]` | Incremental `update_index/delete_file` on change (all 31 langs) | `cartographer watch .` |
| `update-index <file>` | Re-parse single file + re-embed | `cartographer update-index src/main.py` |
| `delete-file <file>` | Remove file nodes + re-embed | `cartographer delete-file src/old.py` |
| `git index [-p path]` / `blame` / `why` / `cochange` / `author` / `authors` | Git history | `cartographer git index --repo-path .` |
| `repo list` / `repo remove <name>` | Multi-repo DB | `cartographer repo list` |
| `db info` / `db vacuum` | DB stats / VACUUM | `cartographer db info --json` |
| `mcp start [--db PATH] [--port N] [--verbose]` | MCP stdio/SSE server | `cartographer mcp start` |
| `version` | Version | `cartographer --json version` |

`--json` everywhere returns `{"status":"ok|empty|error","data":{...},"hint":"try ..."}` — preferred for agents. Limits are clamped (`1-100`), empty query → `[]`, missing DB → `hint`.

---

## MCP for LLMs

`cartographer-mcp` (stdio) exposes via `FastMCP` with workflow instructions:

> 1) `status()` → if empty `index(path=".")`  
> 2) `search` (exact), `ask` (NL), `file_summary` (90% savings)  
> 3) `impact/neighbors/path` for deps  
> 4) `architecture/similar/graph_data` for structure/semantics

**Tools (20):** `status, doctor, health, list_repos, ensure_indexed, search, impact, neighbors, path, summarize, architecture, similar, ask, graph_data, index, context, update_index, delete_file, db_info, file_summary` + resources `cartographer://repos` / `cartographer://repo/{name}` / `cartographer://node/{id}`.

Each has rich description with params, return shape, example, and `hint` on empty/error. `search`/`similar` clamp `limit 1-100`, `neighbors` `depth 1-5`, `path` `max_depth 1-10`, `graph_data` `limit 1-500`. Per-project DB detection mirrors CLI (`.cartographer/config.json` + `$CARTOGRAPHER_DB`).

**Opencode / Claude Desktop:**

```json
// opencode.json
{ "mcp": { "cartographer": { "type": "local", "command": ["cartographer-mcp"], "enabled": true } } }
```

```json
// claude_desktop_config.json
{ "mcpServers": { "cartographer": { "command": "cartographer-mcp", "args": [] } } }
```

Agent rule (save ~96k tokens / 5-turn session):

```
When analyzing code, use cartographer tools, not raw reads:
- file_summary instead of reading files (90%)
- summarize for overview
- impact instead of grep
- architecture for structure
```

---

## Supported Languages (31)

| Category | Languages |
|---|---|
| Code (20 Tree-sitter) | `python`, `javascript`, `typescript`, `tsx`, `go`, `rust`, `java`, `kotlin`, `csharp`, `php`, `ruby`, `c`, `cpp`, `swift`, `scala`, `elixir`, `lua`, `julia`, `zig`, `groovy` |
| New (3 dedicated) | `dart` (regex + `tree_sitter_dart` if present), `markdown` (headings `markdown`/`adr`, `mermaid`→`diagram`, wiki links), `protobuf` |
| Generic (8 via `GenericParser`) | `yaml` (`.yaml/.yml`), `json`, `toml`, `sql`, `html` (`.html/.htm`), `css` (`.css/.scss/.less`), `shell` (`.sh/.bash/.zsh/.fish` + `Makefile`), `dockerfile` |

Missing grammar → `GenericParser` regex (`class/struct/interface/enum` + `func/function/def/fn` + `import`) — not a crash. Add a language by `register_parser(Language.MY, MyParser, [".myext"])` plus `LANGUAGE_EXTENSIONS`.

`EMBEDDABLE_TYPES`: `class, function, method, file, interface, enum, type_alias` (others indexed but not embedded).

---

## How It Works

```
discover_files (.gitignore + .cartographerignore, 10MiB skip, symlink loop guard)
  → detect_languages / fingerprint_frameworks / package_managers
  → _parse_repository (ThreadPool 8, 30s timeout, per-file isolation, Generic fallback)
    → BaseParser (1MiB/2MiB caps, b"\x00" check, has_error, errors=replace)
  → extract_references (import regex per lang, suffix-index, 199 edges)
  → extract_schema (Django/JPA/Prisma/SQL)
  → build_graph (reclassify Controller/Service…, chunked 1000, SQLITE_BUSY retry, WAL)
  → embeddings (bge-small-en-v1.5, 384d, chunked 500, retry 3×, valid-blob filter, hybrid keyword boost)
  → storage (SQLite WAL, busy_timeout 5s, indices on repo/type/file_path/name)
```

- **Ingestion:** `ThreadPoolExecutor(min(cpu,8))` + `as_completed(timeout=30s)`, per-file `try/except` → never kills whole index; `30s` timeout + generic fallback.
- **Discovery:** `TEXT_EXTENSIONS` includes all 31 langs, `BINARY_EXTENSIONS` skip, `MAX_DISCOVER_FILE_BYTES 10MiB`, `.git`/`node_modules`/`__pycache__` ignored.
- **Graph:** `nodes(id,repo,type,name,file_path,metadata_json)`, `edges(id,repo,src,tgt,edge_type)` (`CONTAINS/DEFINES/DECLARES/CALLS/INHERITS/IMPLEMENTS/DECORATES/IMPORTS`), `architecture`/`commits`/`embeddings(vector BLOB)`.
- **Embeddings:** `TextEmbedding` pooled, `EMBEDDING_BATCH_SIZE 256`, `parallelism 0`, `hybrid` boost `+0.1*overlap` when `cosine<0.35`, filter `<0.15`.
- **Retrieval:** `search_nodes` (name `LIKE`, type priority, `ref_count` log-norm, depth) + `impact_analysis` (transitive `target_id`), `get_neighbors` DFS, `find_path` BFS, `generate_summary`.

---

## VS Code Extension

`editors/vscode` — MCP-first (`ClientManager` per workspace folder) + CLI fallback, `cartographer.dbPath/binPath/maxResults/autoReindex/graphLimit/mcpEnabled`.

Features: D3 graph (pagination `offset`, `dir` filter, expand, zoom `0.05x-15x`), incremental watch (batched 2s, `update_index/delete_file`), multi-root, per-project `.cartographer/config.json` live-reload, entity browser, hover (`300ms` debounce + 60s cache), status bar `graph N/E`.

Commands (`Ctrl+Shift+C`): `Index`, `Graph`, `Search`, `Ask`, `Watch`, `DB Info`, `Context`, `File Summary` + `Summarize`, `Architecture`, `Impact`, `Neighbors`, `Path`, `Similar`, `Embed`, `Git Index`, `Select DB`, `Refresh`.

`npm install && npm run compile` / `npx vsce package`.

---

## Configuration

**Per-project** `.cartographer/config.json` (CLI + MCP + VSCode all read):

```json
{
  "dbPath": ".cartographer/my.db",
  "autoReindex": true,
  "watch": false,
  "mcpPort": 0,
  "graphLimit": 400,
  "maxResults": 40
}
```

Resolution: `--db` > `$CARTOGRAPHER_DB` > `.cartographer/config.json` `dbPath` > `.cartographer/data.db` > `~/.cartographer/index.db`.

**Env:**

| Var | Default | Desc |
|---|---|---|
| `CARTOGRAPHER_DB` | `~/.cartographer/index.db` | DB path |
| `CARTOGRAPHER_EMBEDDING_MODEL` | `BAAI/bge-small-en-v1.5` | HF model |
| `CARTOGRAPHER_EMBEDDING_DIM` | `384` | Dim |
| `CARTOGRAPHER_EMBEDDING_BATCH_SIZE` | `256` | Batch |
| `CARTOGRAPHER_EMBEDDING_PARALLELISM` | `0` | `0`=auto |

**`make`:** `lint` (`ruff`), `test` (`pytest -v`, 84 tests).

---

## Development

```bash
pip install -e ".[dev,watch]"
make lint && make test
```

Structure: `cartographer/ingestion`, `parser/{base,registry,languages/*.py}`, `graph/builder`, `storage/connection`, `embedding/engine`, `retrieval/{searcher,traversal,summarizer}`, `architecture/engine`, `git/engine`, `query/engine`, `compression/engine`, `cli.py`, `mcp/server.py`.

Add a language:

```python
from cartographer.parser.registry import register_parser
from cartographer.core.models import Language
from cartographer.parser.base import BaseParser
class MyParser(BaseParser): ...
register_parser(Language.MY, MyParser, [".my"])
```

---

## License

MIT — see `LICENSE`.

<p align="center">Built with Tree-sitter, SQLite, fastembed — for humans and for agents.</p>
