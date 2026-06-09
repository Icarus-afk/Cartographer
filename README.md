# Cartographer

**Repository Intelligence Operating System** — transforms repositories into navigable semantic knowledge graphs.

## Installation

### From source

```bash
git clone https://github.com/your-org/cartographer.git
cd cartographer
pip install -e .
```

### Dependencies

- Python 3.11+
- Tree-sitter grammars (installed automatically per-language during indexing)
- fastembed with bge-small-en-v1.5 model (downloaded on first `embed` command)

## Quick Start

### 1. Index a repository

```bash
cartographer index /path/to/repo
# Default DB: ~/.cartographer/index.db
# Custom DB:  cartographer --db /tmp/my.db index /path/to/repo
```

Output shows files indexed, languages detected, entities parsed, and cross-file references found.

### 2. Search the graph

```bash
# Basic text search
cartographer ask "Preprocessor"

# Semantic search (requires 'cartographer embed' first)
cartographer ask --semantic "request handling classes"
```

### 3. Ask natural language questions

```bash
cartographer query "what is the architecture"
cartographer query "explain Preprocessor"
cartographer query "what depends on mdbook"
cartographer query "path between cmd and config"
cartographer query "summarize this"
```

The `query` command auto-detects intent (architecture, explain, impact, path, summarize, search) and dispatches to the appropriate retrieval strategy.

### 4. Analyze architecture

```bash
cartographer architecture --detect
# Shows layers, patterns, framework detection, and dependency flow
```

### 5. Graph traversal

```bash
# Find neighbors of a node
cartographer neighbors Preprocessor --depth 2

# Analyze impact (what depends on this)
cartographer impact render.py

# Find path between two nodes
cartographer path "cmd" "config"

# Generate repository summary
cartographer summarize
```

### 6. Git intelligence

```bash
# Index git history
cartographer git index --repo-path /path/to/repo

# Find who wrote a symbol
cartographer git blame Preprocessor

# Find when something was introduced
cartographer git why render.rs

# Find files that change together
cartographer git cochange config.rs

# List authors
cartographer git authors
```

### 7. Semantic embeddings

```bash
# Generate embeddings for all nodes
cartographer embed

# Find semantically similar nodes
cartographer similar "error handling middleware"
```

## All Commands

| Command | Description |
|---------|-------------|
| `index` | Index a repository into the knowledge graph |
| `ask` | Search the knowledge graph (text or --semantic) |
| `query` | Natural language query with intent detection |
| `impact` | Analyze what depends on a file or symbol |
| `neighbors` | Show neighbors of a node |
| `path` | Find path between two nodes |
| `summarize` | Generate repository summary |
| `architecture` | Detect or show repository architecture |
| `embed` | Generate vector embeddings |
| `similar` | Find semantically similar nodes |
| `git index` | Index git history |
| `git blame` | Show commit history for a file or symbol |
| `git author` | Show an author's contributions |
| `git cochange` | Find files that change together |
| `git why` | Find which commit introduced a symbol |
| `git authors` | List all authors |
| `version` | Show version |

### Common options

- `--db`, `CARTOGRAPHER_DB` env var — specify SQLite database path
- `--repo`, `-r` — filter by repository name
- `--max-tokens`, `-m` — compress output to fit token budget

## Configuration

| Environment Variable | Default | Description |
|---------------------|---------|-------------|
| `CARTOGRAPHER_DB` | `~/.cartographer/index.db` | Path to the SQLite database |
| `HF_TOKEN` | (none) | HuggingFace token for embedding model download |

## Detailed Documentation

| Document | Description |
|----------|-------------|
| [Getting Started](docs/getting-started.md) | Installation, first index, quick start workflows |
| [Command Reference](docs/commands.md) | All commands, options, and examples |
| [Architecture Deep Dive](docs/architecture.md) | How the system works internally |
| [OpenCode Integration](docs/opencode.md) | Using Cartographer with AI coding assistants |
| [Troubleshooting](docs/troubleshooting.md) | Common issues and solutions |

## Using with OpenCode

Cartographer integrates with OpenCode as a knowledge-graph provider. The `query` command is designed to be called from OpenCode agents to answer questions about repositories.

### OpenCode Agent Configuration

Add to your `~/.config/opencode/config.jsonc` or `opencode.json`:

```jsonc
{
  "tools": {
    "cartographer-query": {
      "command": "cartographer query --db /path/to/index.db",
      "description": "Query the repository knowledge graph. Arguments: a natural language question about the codebase.",
      "args": ["{{input}}"]
    },
    "cartographer-ask": {
      "command": "cartographer ask --db /path/to/index.db",
      "description": "Search the repository knowledge graph for specific symbols. Arguments: a symbol name to search for.",
      "args": ["{{input}}"]
    },
    "cartographer-architecture": {
      "command": "cartographer architecture --detect --db /path/to/index.db",
      "description": "Detect and return the architecture of the current repository.",
      "args": []
    },
    "cartographer-impact": {
      "command": "cartographer impact --db /path/to/index.db",
      "description": "Analyze what depends on a given symbol. Arguments: symbol name to analyze.",
      "args": ["{{input}}"]
    },
    "cartographer-summarize": {
      "command": "cartographer summarize --db /path/to/index.db",
      "description": "Generate a high-level summary of the repository.",
      "args": []
    }
  }
}
```

### Usage from an OpenCode Agent

Once configured, an OpenCode agent can call:

```
Cartographer, what is the architecture of this project?
→ cartographer-architecture → "Layered architecture with Controller, Business, Data layers..."

Cartographer, explain the Preprocessor interface
→ cartographer-query "explain Preprocessor" → "Found 20 nodes, 4 dependents..."

Cartographer, summarize the repository
→ cartographer-summarize → "1108 nodes, 1247 edges, top types: function, variable, method..."
```

## Architecture

Cartographer has a modular pipeline architecture:

1. **Ingestion Engine** — file discovery, language detection, framework fingerprinting
2. **Parser Engine** — 19 Tree-sitter language parsers (Python, JS, TS, Go, Rust, Java, Kotlin, C#, PHP, Ruby, C, C++, Swift, Scala, Elixir, Lua, Julia, Zig, Groovy)
3. **Graph Engine** — SQLite persistence with nodes, edges, directories, embeddings, and git metadata
4. **Retrieval Engine** — search, traversal, impact analysis, path finding, summarization
5. **Architecture Engine** — multi-strategy layer detection, pattern matching, dependency flow
6. **Embedding Engine** — fastembed + bge-small-en-v1.5 for semantic search
7. **Git Intelligence Engine** — commit/author tracking, co-change analysis, why-introduced queries
8. **Compression Engine** — token-aware output compression with 4 strategies
9. **Query Planner** — intent-driven NL query classification and dispatch

## Development

```bash
# Install in dev mode
pip install -e .

# Lint
ruff check cartographer/

# Run tests
pytest
```

## License

MIT
