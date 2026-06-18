# Cartographer

**Repository Intelligence Operating System** — transforms any code repository into a navigable semantic knowledge graph that you can search, query, and explore using natural language.

Instead of searching for filenames, you ask questions like *"What does the auth module depend on?"* or *"Explain the architecture of this project."* Cartographer builds a graph of all your code's entities (classes, functions, methods, interfaces, etc.) and the relationships between them, then lets you traverse, analyze, and compress that graph.

---

## Installation

### From source

```bash
git clone https://github.com/your-org/cartographer.git
cd cartographer
pip install -e .
```

Optional watch mode support:
```bash
pip install -e ".[watch]"
```

Verify it works:
```bash
cartographer version
# cartographer 0.1.0
```

### VS Code Extension

```bash
cd editors/vscode
npm install && npm run compile
```

Package and install:
```bash
npx vsce package
code --install-extension cartographer-0.1.0.vsix
```

---

## Quick Start

### 1. Index a repository

```bash
cartographer index /path/to/repo
```

Output shows files indexed, languages detected, entities parsed, frameworks found, and cross-file references:
```
Indexed 152 files in 24 directories
Duration: 2431.18ms
Languages: python: 89, javascript: 43, typescript: 20
Entities: 152 files parsed, 45 classes, 312 functions, 89 methods
Frameworks: Django (98% confidence)
References: 234 cross-file imports
```

By default the database goes to `~/.cartographer/index.db`. Use `--db` or `CARTOGRAPHER_DB` env var to change it. For per-project isolation, see [Per-Project Configuration](#per-project-configuration).

### 2. Search for symbols

```bash
cartographer ask "UserService"
```

```text
Found 5 result(s):
  [class       ] UserService
           src/services/user_service.py
  [class       ] UserServiceImpl
           src/services/impl/user_service_impl.py
  [interface   ] IUserService
           src/services/user_service.py
  [function    ] create_user_service
           src/factories/service_factory.py
  [method      ] get_user_service
           src/controllers/user_controller.py
```

Semantic search (needs `cartographer embed` first):
```bash
cartographer ask --semantic "classes that handle user authentication"
```

### 3. Ask natural language questions

The `query` command auto-detects what you're asking and runs the right analysis:

```bash
cartographer query "what is the architecture"
cartographer query "explain Preprocessor"
cartographer query "what depends on config.py"
cartographer query "path between cmd and config"
cartographer query "summarize this project"
cartographer query "who wrote the auth module"
```

### 4. Analyze architecture

```bash
cartographer architecture --detect
```

Detects layers (Controller, Data, Business, etc.), frameworks (Django, FastAPI, Spring, etc.), architecture patterns (MVC, Layered, Hexagonal, etc.), and dependency flows between layers.

### 5. Graph traversal

```bash
cartographer neighbors Preprocessor --depth 2
cartographer impact render.py
cartographer path "cmd" "config"
cartographer summarize
```

### 6. Semantic embeddings

```bash
cartographer embed
cartographer similar "error handling middleware"
```

### 7. Git intelligence

```bash
cartographer git index --repo-path /path/to/repo
cartographer git blame Preprocessor
cartographer git why render.rs
cartographer git cochange config.rs
cartographer git authors
```

### 8. Incremental file watching

Automatically update the graph when files change:

```bash
cartographer watch /path/to/repo
```

Or update/delete individual files:
```bash
cartographer update-index /path/to/repo/src/main.py
cartographer delete-file /path/to/repo/src/removed.py
```

### 9. MCP server (AI assistant integration)

```bash
cartographer mcp start
```

Starts a Model Context Protocol server that exposes all Cartographer tools to AI assistants like Claude Desktop, Cursor, and OpenCode. The MCP server supports 15+ tools including `search`, `impact`, `neighbors`, `path`, `graph_data` (with pagination and directory filtering), `context` (compressed context packages), `update_index` (incremental re-index), `delete_file`, and `db_info`.

---

## Per-Project Configuration

Place a `.cartographer/config.json` in your project root to customize behavior:

```json
{
  "dbPath": ".cartographer/my-project.db",
  "autoReindex": true,
  "watch": false,
  "mcpPort": 0,
  "graphLimit": 400,
  "maxResults": 40
}
```

| Option | Default | Description |
|---|---|---|
| `dbPath` | `.cartographer/data.db` | Database path (relative to project root or absolute) |
| `autoReindex` | `true` | Auto-update the graph when files are saved (VS Code extension) |
| `watch` | `false` | Enable file system watching via watchdog (CLI) |
| `mcpPort` | `0` | Run MCP server on a TCP port (0 = stdio) |
| `graphLimit` | `400` | Max nodes in graph visualization |
| `maxResults` | `40` | Default max search results |

---

## VS Code Extension

The VS Code extension provides an interactive knowledge graph, entity browser, and search right in your editor.

### Features

- **Interactive Graph Visualization** — dynamic D3 force graph with pagination ("Load More"), directory tree sidebar filter, debounced search, click-to-expand neighbors, cluster-by-directory layout, zoom (0.05x–15x), and smart labels
- **Incremental File Watching** — files are re-indexed incrementally on save, delete, or rename (no full re-scan); changes are batched and debounced
- **Multi-Root Workspace Support** — each workspace folder gets its own client, database, and MCP connection; commands resolve to the active folder automatically; graph view shows a folder picker
- **MCP-First Architecture** — persistent MCP connection for all tools; transparent fallback to CLI if MCP is unavailable
- **Per-Project Config** — `.cartographer/config.json` read per workspace folder, live-reloaded on change
- **Entity Browser** — tree view shows nodes by type, click to search
- **Hover Provider** — debounced hover shows entity info from the knowledge graph
- **Search + Impact + Path** — all graph tools available from the command palette

### Available Commands

| Command | Keybinding | Description |
|---|---|---|
| `Cartographer: Index Repository` | `Ctrl+Shift+C I` | Index all workspace folders |
| `Cartographer: Open Graph Visualization` | `Ctrl+Shift+C G` | Interactive knowledge graph |
| `Cartographer: Search Graph` | `Ctrl+Shift+C S` | Search entities by name |
| `Cartographer: Ask a Question` | `Ctrl+Shift+C A` | Natural language query |
| `Cartographer: Watch for File Changes` | `Ctrl+Shift+C W` | Watch via watchdog CLI |
| `Cartographer: Database Info` | `Ctrl+Shift+C D` | Show DB statistics |
| `Cartographer: Generate Context Package` | `Ctrl+Shift+C C` | Summary + architecture + key nodes |
| `Cartographer: Repository Summary` | | Node/edge counts and breakdowns |
| `Cartographer: Detect Architecture` | | Detect layers and patterns |
| `Cartographer: Impact Analysis` | | Find dependents of a symbol |
| `Cartographer: Show Neighbors` | | Traverse the graph |
| `Cartographer: Find Path` | | Shortest path between two nodes |
| `Cartographer: Similar Entities` | | Semantic similarity search |
| `Cartographer: Generate Embeddings` | | Vector embeddings for semantic search |
| `Cartographer: Index Git History` | | Git commit tracking |
| `Cartographer: Select Database` | | Pick a different database |
| `Cartographer: Refresh Views` | | Refresh all tree views |

### Extension Settings

| Setting | Default | Description |
|---|---|---|
| `cartographer.dbPath` | `""` | Override database path (per-project config takes precedence) |
| `cartographer.binPath` | `"cartographer"` | CLI binary path |
| `cartographer.maxResults` | `20` | Max search results |
| `cartographer.autoReindex` | `true` | Auto re-index on file save |
| `cartographer.graphLimit` | `400` | Max graph nodes |
| `cartographer.mcpEnabled` | `true` | Use persistent MCP connection |

---

## All CLI Commands

| Command | Description |
|---|---|
| `index` | Index a repository into the knowledge graph |
| `ask` | Search the graph (text or `--semantic`) |
| `query` | Natural language query with auto intent detection |
| `impact` | Analyze what depends on a file or symbol |
| `neighbors` | Show neighbors of a node |
| `path` | Find shortest path between two nodes |
| `summarize` | Generate repository summary |
| `context` | Generate a structured context package |
| `embed` | Generate vector embeddings for semantic search |
| `similar` | Find semantically similar nodes |
| `architecture` | Detect or show repository architecture |
| `graph-data` | Export graph as JSON (supports `--offset`, `--dir`, `--expand-node-id`) |
| `watch` | Watch a repo for changes and auto-update (requires watchdog) |
| `update-index` | Incrementally re-index a single file |
| `delete-file` | Remove a deleted file from the graph |
| `git index` | Index git history (commits, authors, changes) |
| `git blame` | Show commit history for a file or symbol |
| `git author` | Show an author's contributions |
| `git cochange` | Find files that change together |
| `git why` | Find which commit introduced a symbol |
| `git authors` | List all authors |
| `mcp start` | Start MCP server for AI assistant integration |
| `mcp stop` | Stop a running MCP server |
| `repo list` | List all indexed repositories |
| `repo remove` | Remove a repository and its data |
| `db vacuum` | Reclaim storage space (VACUUM) |
| `db info` | Show database statistics |
| `version` | Show version |

### Common options

- `--db PATH`, `CARTOGRAPHER_DB` env var — specify database path (default: `~/.cartographer/index.db`)
- `--repo`, `-r` — filter by repository name (for multi-repo databases)
- `--max-tokens`, `-m` — compress output to fit a token budget (for LLM context windows)
- `--limit`, `-l` — limit number of results
- `--type`, `-t` — filter by node type
- `--offset`, `-o` — skip N hub groups for graph pagination
- `--dir`, `-d` — filter graph by directory prefix
- `--expand-node-id` — fetch a specific node and its immediate neighbors

---

## Environment Configuration

| Variable | Default | Description |
|---|---|---|
| `CARTOGRAPHER_DB` | `~/.cartographer/index.db` | Path to the SQLite database |
| `CARTOGRAPHER_EMBEDDING_MODEL` | `BAAI/bge-small-en-v1.5` | Embedding model name (HuggingFace) |
| `CARTOGRAPHER_EMBEDDING_DIM` | `384` | Model output dimension |
| `CARTOGRAPHER_EMBEDDING_BATCH_SIZE` | `256` | Embedding batch size |
| `CARTOGRAPHER_EMBEDDING_PARALLELISM` | `0` | CPU threads (0 = auto) |

---

## How It Works

Cartographer has a modular pipeline architecture:

1. **Ingestion Engine** — walks the file tree, detects languages and frameworks, skips binaries and ignored files (`.gitignore` + `.cartographerignore`). Supports incremental `update_index` for single-file changes.
2. **Parser Engine** — 20 Tree-sitter language parsers (Python, JS, TS/TSX, Go, Rust, Java, Kotlin, C#, PHP, Ruby, C, C++, Swift, Scala, Elixir, Lua, Julia, Zig, Groovy)
3. **Graph Engine** — SQLite persistence with nodes, edges, directories, embeddings, and git metadata. Supports incremental `update_file_in_graph` and `delete_file_from_graph`.
4. **Retrieval Engine** — search, traversal, impact analysis, path finding, summarization
5. **Architecture Engine** — multi-strategy layer detection, pattern matching, dependency flow
6. **Embedding Engine** — fastembed + bge-small-en-v1.5 (384-dim) for semantic search; numpy-batched similarity (280x faster than pure Python)
7. **Git Intelligence Engine** — commit/author tracking, co-change analysis, why-introduced queries
8. **Compression Engine** — token-aware output compression (4 strategies for LLM context budgets)
9. **Query Planner** — intent-driven NL query classification (9 intent types)
10. **MCP Server** — exposes all tools via Model Context Protocol for AI assistants. Tools: `search`, `impact`, `neighbors`, `path`, `similar`, `ask`, `architecture`, `summarize`, `graph_data`, `index`, `context`, `update_index`, `delete_file`, `db_info`, plus resources for repos/nodes.
11. **VS Code Extension** — MCP-first TypeScript client with CLI fallback, interactive graph visualization, entity browser, hover provider, incremental file watcher, multi-root workspace support, and per-project configuration.

---

## Dependencies

| Dependency | Purpose |
|---|---|
| Python 3.10+ | Runtime |
| click 8.1+ | CLI framework |
| Tree-sitter 0.23+ | AST parsing for 20 languages |
| mcp 1.0+ | Model Context Protocol server |
| fastembed 0.8+ | Vector embeddings for semantic search |
| pathspec | `.gitignore` pattern matching |
| watchdog 4.0+ | File system watching (optional) |
| numpy | Batched similarity computation |

Tree-sitter language grammars are downloaded on demand when you index a file in that language. The embedding model (default `BAAI/bge-small-en-v1.5`, ~33MB) downloads on first `cartographer embed`.

---

## Documentation

| Document | Description |
|---|---|
| [Getting Started](docs/getting-started.md) | Installation, first index, quick start workflows |
| [Command Reference](docs/commands.md) | All commands, options, and examples |
| [Architecture Deep Dive](docs/architecture.md) | How the system works internally |
| [Technical Reference](docs/technical.md) | Comprehensive technical architecture |
| [OpenCode Integration](docs/opencode.md) | Using Cartographer with AI coding assistants |
| [Benchmarks](docs/benchmarks.md) | Performance data across 14 real-world repos |
| [Whitepaper](docs/whitepaper.md) | Full technical whitepaper |
| [Troubleshooting](docs/troubleshooting.md) | Common issues and solutions |

---

## Development

```bash
pip install -e ".[dev,watch]"
ruff check cartographer/
pytest
```

## License

MIT
