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

Verify it works:
```bash
cartographer version
# cartographer 0.1.0
```

### VS Code Extension

Cartographer includes a VS Code extension for exploring your repository's knowledge graph from within the editor:

```bash
cd editors/vscode
npm install && npm run compile
```

Then install the extension by copying the `editors/vscode` folder to `~/.vscode/extensions/cartographer` or packaging it with `vsce package`.

Available commands:
- `Cartographer: Index Repository` — index the current workspace
- `Cartographer: Search Graph` — search entities by name
- `Cartographer: Show Repository Summary` — node/edge counts and breakdowns
- `Cartographer: Show Architecture` — detect layers and patterns
- `Cartographer: Impact Analysis` — find dependents of a symbol
- `Cartographer: Open Graph View` — interactive graph visualization

### Dependencies

| Dependency | Purpose |
|---|---|
| Python 3.11+ | Runtime |
| click 8.1+ | CLI framework |
| Tree-sitter 0.23+ | AST parsing for 20 languages |
| mcp 1.0+ | Model Context Protocol server |
| fastembed 0.8+ | Vector embeddings for semantic search |
| pathspec | `.gitignore` pattern matching |
| pyyaml 6+ | YAML config support |
| packaging 24+ | Package version detection |
| python-dotenv 1.0+ | `.env` file loading |
| tqdm | Progress bars |
| numpy | Batched similarity computation |
| fastembed 0.8+ | Vector embeddings for semantic search |
| pathspec | `.gitignore` pattern matching |
| pyyaml 6+ | YAML config support |
| packaging 24+ | Package version detection |

Tree-sitter language grammars are downloaded on demand when you index a file in that language. The embedding model (default `BAAI/bge-small-en-v1.5`, ~33MB) downloads on first `cartographer embed`. Model and batch size are configurable via environment variables (see `.env.example`).

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

By default the database goes to `~/.cartographer/index.db`. Use `--db` or `CARTOGRAPHER_DB` env var to change it:

```bash
cartographer --db /tmp/my.db index /path/to/repo
export CARTOGRAPHER_DB=/tmp/my.db
cartographer index /path/to/repo
```

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

### 8. MCP server (AI assistant integration)

```bash
cartographer mcp
```

Starts a Model Context Protocol server that exposes all Cartographer tools to AI assistants like Claude Desktop, Cursor, and OpenCode.

---

## All Commands

| Command | Description |
|---|---|
| `init` | Initialize and index a repository |
| `index` | Index a repository into the knowledge graph |
| `ask` | Search the graph (text or `--semantic`) |
| `query` | Natural language query with auto intent detection |
| `impact` | Analyze what depends on a file or symbol |
| `neighbors` | Show neighbors of a node |
| `path` | Find shortest path between two nodes |
| `summarize` | Generate repository summary |
| `context` | Generate a structured context package (summary + architecture + key nodes) |
| `embed` | Generate vector embeddings for semantic search |
| `similar` | Find semantically similar nodes |
| `architecture` | Detect or show repository architecture |
| `graph-data` | Export graph as JSON for VS Code extension |
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

---

## Configuration

| Environment Variable | Default | Description |
|---|---|---|---|
| `CARTOGRAPHER_DB` | `~/.cartographer/index.db` | Path to the SQLite database |
| `CARTOGRAPHER_EMBEDDING_MODEL` | `BAAI/bge-small-en-v1.5` | Embedding model name (HuggingFace) |
| `CARTOGRAPHER_EMBEDDING_DIM` | `384` | Model output dimension |
| `CARTOGRAPHER_EMBEDDING_BATCH_SIZE` | `256` | Embedding batch size |
| `CARTOGRAPHER_EMBEDDING_PARALLELISM` | `0` | CPU threads (0 = auto) |

---

## How It Works

Cartographer has a modular pipeline architecture:

1. **Ingestion Engine** — walks the file tree, detects languages and frameworks, skips binaries and ignored files (`.gitignore` + `.cartographerignore`)
2. **Parser Engine** — 20 Tree-sitter language parsers (Python, JS, TS/TSX, Go, Rust, Java, Kotlin, C#, PHP, Ruby, C, C++, Swift, Scala, Elixir, Lua, Julia, Zig, Groovy)
3. **Graph Engine** — SQLite persistence with nodes, edges, directories, embeddings, and git metadata
4. **Retrieval Engine** — search, traversal, impact analysis, path finding, summarization
5. **Architecture Engine** — multi-strategy layer detection, pattern matching, dependency flow
6. **Embedding Engine** — fastembed + bge-small-en-v1.5 (384-dim) for semantic search; numpy-batched similarity (280x faster than pure Python)
7. **Git Intelligence Engine** — commit/author tracking, co-change analysis, why-introduced queries
8. **Compression Engine** — token-aware output compression (4 strategies for LLM context budgets)
9. **Query Planner** — intent-driven NL query classification (9 intent types)
10. **MCP Server** — exposes all tools via Model Context Protocol for AI assistants

---

## Documentation

| Document | Description |
|---|---|---|
| [Getting Started](docs/getting-started.md) | Installation, first index, quick start workflows |
| [Command Reference](docs/commands.md) | All commands, options, and examples |
| [Architecture Deep Dive](docs/architecture.md) | How the system works internally |
| [Technical Reference](docs/technical.md) | Comprehensive technical architecture |
| [OpenCode Integration](docs/opencode.md) | Using Cartographer with AI coding assistants |
| [Benchmarks](docs/benchmarks.md) | Performance data across 14 real-world repos |
| [Whitepaper](docs/whitepaper.md) | Full technical whitepaper with benchmarks and token savings analysis |
| [Troubleshooting](docs/troubleshooting.md) | Common issues and solutions |

---

## Development

```bash
pip install -e .
ruff check cartographer/
pytest
```

## License

MIT
