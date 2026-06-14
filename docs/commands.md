# Command Reference

This document covers every Cartographer command, its options, and practical examples.

---

## Global Options

Every command supports these global options, specified before the subcommand:

```
--db PATH     Path to SQLite database (default: ~/.cartographer/index.db)
              Also settable via CARTOGRAPHER_DB environment variable
```

---

## cartographer index

**Purpose:** Index a repository into the knowledge graph. This is the first command you run — it discovers files, parses them, extracts entities, resolves cross-file references, and builds the graph.

```bash
cartographer index [PATH]

# Examples
cartographer index .                          # Index current directory
cartographer index /path/to/repo              # Index a specific repo
cartographer --db /tmp/my.db index ./project  # Use custom database
```

### What happens during indexing

1. **File discovery** — walks the directory tree recursively, skipping binaries, hidden dirs, ignored patterns (`.gitignore` + `.cartographerignore`), and 23 standard ignored directories
2. **Language detection** — maps file extensions to languages using a built-in dictionary of 30+ extensions across 19 languages
3. **Framework fingerprinting** — checks for indicator files (`manage.py`, `package.json`, `Cargo.toml`, etc.) and parses config files to detect frameworks (Django, Flask, Rails, Spring Boot, Express, Next.js, NestJS, React, Vue, Laravel, Actix Web, Axum, FastAPI, and more)
4. **Package manager detection** — finds `package.json`, `Cargo.toml`, `requirements.txt`, `Gemfile`, `Pipfile`, `composer.json`, etc.
5. **Build system detection** — finds `Makefile`, `CMakeLists.txt`, `setup.py`, `pyproject.toml`, `build.gradle`, `pom.xml`
6. **Monorepo detection** — checks for `lerna.json`, `nx.json`, `turbo.json`, workspace configs
7. **Parsing** — each source file is parsed with the appropriate Tree-sitter parser to extract entities
8. **Reference resolution** — import/require/include statements are matched against discovered files using suffix matching
9. **Graph building** — all entities and relationships are stored as nodes and edges in SQLite

### What gets automatically skipped

- Binary files (via extension blocklist AND null-byte check)
- Hidden directories starting with `.` (`.git`, `.venv`, `.next`, `.nuxt`, etc.)
- 23+ well-known ignored directories (`node_modules`, `__pycache__`, `target`, `build`, `dist`, `vendor`, etc.)
- Files matching patterns in `.cartographerignore` (uses `fnmatch`)
- Files matching patterns in root `.gitignore` (uses `pathspec` library)

### Output explained

```
Indexed 152 files in 24 directories    ← How many files were discovered and indexed
Duration: 2431.18ms                    ← Total indexing time
Languages: python: 89, js: 43, ts: 20  ← Languages found, with file counts
Frameworks: Django (98% confidence)    ← Detected frameworks with confidence scores
Package Managers: pip                  ← Package managers detected
Build Systems: setuptools              ← Build systems detected
Monorepo: yes (pnpm)                   ← Monorepo detection
Entities: 45 classes, 312 functions...  ← Entities extracted from parsing
References: 234 cross-file imports     ← Resolved cross-file references
```

### Performance

- Indexing speed averages 86–540 files/second depending on language
- Memory scales with entity count (~100-120MB for typical repos)
- Tree-sitter parsers are loaded lazily (only for languages you actually use)

---

## cartographer ask

**Purpose:** Search the knowledge graph for symbols matching a text or semantic query.

```bash
cartographer ask [OPTIONS] QUERY

Options:
  -t, --type TEXT       Filter by node type (class, function, file, etc.)
  -r, --repo TEXT       Filter by repository name
  -l, --limit INT       Max results (default: 20)
  -s, --semantic        Use semantic (embedding) search instead of text
  -m, --max-tokens INT  Compress output to fit a token budget

Examples:
  # Basic text search
  cartographer ask "UserService"

  # Filter by node type
  cartographer ask --type class "User"

  # Filter by repository (if you have multiple repos indexed)
  cartographer ask --repo myproject "handler"

  # Limit to 5 results
  cartographer ask --limit 5 "parser"

  # Semantic search (requires embeddings)
  cartographer ask --semantic "error handling middleware"

  # Compressed output for LLM context
  cartographer ask -m 200 "Preprocessor"
```

### How text search works

Uses SQL `LIKE` with `%query%` wildcards on the node name column. Results are sorted by relevance:
1. **Exact match** — name equals the query exactly
2. **Prefix match** — name starts with the query
3. **Substring match** — name contains the query

### How semantic search works

The query is embedded into a 384-dimensional vector using `bge-small-en-v1.5`, then compared against all stored embeddings using cosine similarity. This finds conceptually related code even if it uses different terminology.

---

## cartographer query

**Purpose:** Natural language query with automatic intent detection. This is the most powerful command — it wraps multiple retrieval strategies behind a single interface and figures out which one to use based on your question.

```bash
cartographer query [OPTIONS] QUERY_STR

Options:
  -r, --repo TEXT         Filter by repository name
  -l, --limit INT         Max results per step (default: 20)
  -m, --max-tokens INT    Compress output to fit token budget
  -v, --verbose           Show detailed reasoning about intent detection

Examples:
  # Architecture
  cartographer query "what is the architecture"
  cartographer query "how is this project organized"
  cartographer query "what layers does this repo have"

  # Explanation
  cartographer query "explain Preprocessor"
  cartographer query "what is the UserService class"
  cartographer query "describe the database module"

  # Impact analysis
  cartographer query "what depends on config.py"
  cartographer query "impact of the auth module"
  cartographer query "what breaks if I change the API"

  # Path finding
  cartographer query "path between cmd and config"
  cartographer query "how are the CLI and API connected"
  cartographer query "relationship between controller and service"

  # Summary
  cartographer query "summarize this project"
  cartographer query "overview"
  cartographer query "give me a high-level view"

  # Git intelligence
  cartographer query "who wrote the auth module"
  cartographer query "what changes with config.py"
  cartographer query "why was render.rs introduced"

  # Search (fallback when no specific intent is detected)
  cartographer query "find the database connection pool"
  cartographer query "where is the error handler"

  # Compressed for LLM context
  cartographer query -m 200 "explain Preprocessor"

  # Verbose mode to see intent detection
  cartographer query -v "what is the architecture"
```

### Intent Detection

The query planner classifies queries by scanning for keywords. Architecture and summary intents get highest priority to avoid false matches.

| Intent | Example Queries | What It Does |
|---|---|---|
| `architecture` | "architecture", "layers", "patterns", "structure" | Runs architecture detection (layers, patterns, dependency flow) |
| `summarize` | "overview", "summarize", "what is this", "high-level" | Generates repo statistics (nodes, edges, types) |
| `explain` | "explain X", "what is X", "describe X", "how does X work" | Searches for matching nodes + shows impact/dependents |
| `impact` | "what depends on X", "impact of X", "what breaks if X" | Impact analysis (reverse dependency traversal) |
| `path` | "path between X and Y", "relationship", "how are X and Y connected" | Path finding (BFS between two nodes) |
| `git_blame` | "who wrote X", "blame X", "who changed X" | Git commit history for the target |
| `git_why` | "why was X introduced", "when was X added" | Finds the commit that first introduced the target |
| `git_cochange` | "what changes with X", "files that change with X" | Co-change analysis from git history |
| `search` | (anything else) | Falls back to plain text search |

### Verbose output

With `-v`, Cartographer shows which intent it detected and why:

```
$ cartographer query -v "explain the auth system"
Intent: explain (matched: explain)
Target: auth system
```

---

## cartographer impact

**Purpose:** Analyze what depends on (imports, extends, or otherwise references) a given file or symbol. Essential for understanding the blast radius of changes.

```bash
cartographer impact [OPTIONS] TARGET

Options:
  -r, --repo TEXT         Repository name
  -m, --max-tokens INT    Compress output to fit token budget

Examples:
  cartographer impact render.py
  cartographer impact UserService
  cartographer impact -r myproject auth.py
  cartographer impact -m 100 render.py
```

Results are grouped by edge type so you can distinguish direct imports from definitions:

```
Impact analysis for 'render.py':
  Via IMPORTS:
    [function] generate_output (src/output/generator.py)
    [class] Renderer (src/renderer.py)
  Via CONTAINS:
    [file] render.py (src/render.py)
```

---

## cartographer neighbors

**Purpose:** Show nodes connected to a given node in the graph — like a "knowledge graph explorer."

```bash
cartographer neighbors [OPTIONS] NAME

Options:
  -r, --repo TEXT         Repository name
  -d, --depth INT         Traversal depth (default: 2 — grows exponentially!)
  -m, --max-tokens INT    Compress output to fit token budget

Examples:
  cartographer neighbors UserService          # Depth 2 (default)
  cartographer neighbors -d 1 main.py         # Direct connections only
  cartographer neighbors --depth 3 Preprocessor
```

Depth 1 shows direct connections. Depth 2 shows neighbors of neighbors (can be large). Depth 3+ can be very slow on large graphs because the number of nodes grows exponentially with depth.

---

## cartographer path

**Purpose:** Find the shortest path between two nodes in the graph using breadth-first search. Useful for understanding how two parts of the codebase are connected.

```bash
cartographer path [OPTIONS] FROM_NAME TO_NAME

Options:
  --max-depth INT         Maximum search depth (default: 5)
  -m, --max-tokens INT    Compress output to fit token budget

Examples:
  cartographer path "cmd" "config"
  cartographer path "UserController" "UserRepository"
  cartographer path --max-depth 10 "Frontend" "Database"
```

Uses bidirectional BFS (searching from both ends simultaneously) for faster path finding. Fails gracefully if no path exists within the max depth.

---

## cartographer summarize

**Purpose:** Generate a high-level statistical summary of the repository — total nodes, edges, breakdowns by type, top files, largest classes.

```bash
cartographer summarize [OPTIONS]

Options:
  -r, --repo TEXT         Repository name
  -m, --max-tokens INT    Compress output to fit token budget

Examples:
  cartographer summarize
  cartographer summarize -r myproject
  cartographer summarize -m 100
```

Output includes:
- Repository name and path
- Total node and edge counts
- Node breakdown by type (class, function, method, file, variable, interface, enum, etc.)
- Edge breakdown by type (DEFINES, CONTAINS, IMPORTS, DECLARES)
- Top files by entity count
- Largest classes by method count

---

## cartographer architecture

**Purpose:** Display or detect repository architecture — layers, frameworks, patterns, and dependency flows. This is the closest thing to "automated architecture documentation."

```bash
cartographer architecture [OPTIONS]

Options:
  -r, --repo TEXT         Repository name
  --detect                Run architecture detection (required for first use)
  -v, --verbose           Show detailed evidence (examples, signal types)

Examples:
  cartographer architecture --detect
  cartographer architecture --detect -v        # With detailed evidence
  cartographer architecture                     # Show previously detected
  cartographer architecture -r myproject
```

### What gets detected

**Frameworks** — detected from manifest fingerprints and graph structure:
Django, Flask, Rails, Spring Boot, NestJS, Express, FastAPI, Next.js, Laravel, Actix Web, Axum, Gin, Echo, Rocket, Vapor, Phoenix, and more

**Layers** — 12 layer types detected from naming conventions:
Controller, Presentation, API, Business, Data, Middleware, Config, Infrastructure, Migration, Testing, Utility, Deployment

**Architecture patterns** — 6 generic patterns:
- MVC (Model-View-Controller)
- Layered (n-tier)
- Clean Architecture
- Hexagonal (Ports & Adapters)
- Repository Pattern
- Service-Oriented

**Framework-specific patterns** — 9 framework patterns:
Django MTV, Rails MVC, Spring Boot Layered, NestJS Modular, Express MVC, FastAPI Modular, Next.js App Router, Laravel MVC, Actix Web Modular, Axum Modular

**Dependency flow** — layer-to-layer import analysis showing expected vs. unexpected dependency directions

### Verbose output

With `-v`, shows:
- Which files contributed to each layer detection
- Examples of matching entity names
- Signal types and their weights

---

## cartographer embed

**Purpose:** Generate vector embeddings for semantic search. Run this once after indexing to enable `--semantic` flag on `ask`, the `similar` command, and semantic similarity features.

```bash
cartographer embed [OPTIONS]

Options:
  -r, --repo TEXT         Repository name (embed only one repo's nodes)

Examples:
  cartographer embed                # Embed all unembedded nodes
  cartographer embed -r myproject   # Embed only nodes from 'myproject'
```

### What gets embedded

Only these node types get embeddings:
- class, function, method, file, interface, enum, type_alias

Each node is converted to text before embedding:
```
{node_type}: {name}
file: {file_path}
docstring: {docstring if present}
```

The text is passed through `BAAI/bge-small-en-v1.5` to produce a 384-dimensional vector.

### How it works

1. Queries for unembedded nodes matching embeddable types
2. Builds text representations with a progress bar
3. Batch-embeds via fastembed (ONNX-based inference)
4. Serializes vectors as float32 blobs (1536 bytes each)
5. Batch-inserts into the embeddings table
6. Skips already-embedded nodes (incremental — rerunning only embeds new nodes)

---

## cartographer similar

**Purpose:** Find semantically similar nodes using vector embeddings. If you give it an existing node name, it finds nodes with similar embeddings. Otherwise, it treats it as a text query and does semantic search.

```bash
cartographer similar [OPTIONS] TARGET

Options:
  -r, --repo TEXT         Repository name
  -l, --limit INT         Max results (default: 20)

Examples:
  cartographer similar "error handling"            # Text query
  cartographer similar UserService                  # Find similar to a node
  cartographer similar -l 10 "database connection pool"
  cartographer similar -r myproject "config parser"
```

### Similarity computation

Uses numpy-batched cosine similarity — loads all vectors as a `(N, 384)` array and computes dot products in one vectorized operation. This is **280x faster** than a pure Python loop (2,025ms reduced to 7ms for 5,000 vectors).

---

## cartographer git

**Purpose:** Git intelligence commands for understanding code history, authorship, and change patterns.

### git index

Index git history (commits, authors, file changes). Run this before other git commands.

```bash
cartographer git index [OPTIONS]

Options:
  -p, --repo-path TEXT    Path to the git repository
  -r, --repo TEXT         Repository name (for already-indexed repos)
  -n, --max-count INT     Max commits to index (default: all)

Examples:
  cartographer git index -p /path/to/repo
  cartographer git index -n 100          # Only last 100 commits
  cartographer git index                  # Uses first indexed repo
```

Runs `git log --all --reverse` with a 60-second timeout.

### git blame

Show commit history for a file or symbol — who changed it and when.

```bash
cartographer git blame [OPTIONS] TARGET

Options:
  -r, --repo TEXT         Repository name
  -l, --limit INT         Max results (default: 15)

Examples:
  cartographer git blame render.py
  cartographer git blame Preprocessor
  cartographer git blame -l 30 config.py
```

Tries to find history for a specific symbol first, then falls back to file-level history.

### git author

Show an author's contributions — total commits, most-changed files, recent activity.

```bash
cartographer git author [OPTIONS] NAME

Options:
  -r, --repo TEXT         Repository name
  -l, --limit INT         Max results (default: 15)

Examples:
  cartographer git author "Jane Doe"
  cartographer git author -l 30 "John Smith"
```

### git cochange

Find files that change together with a target file — useful for understanding coupling.

```bash
cartographer git cochange [OPTIONS] TARGET

Options:
  -r, --repo TEXT         Repository name
  -l, --limit INT         Max results (default: 15)

Examples:
  cartographer git cochange config.rs
  cartographer git cochange -l 10 settings.py
```

Uses co-occurrence analysis: counts how many commits contain both files, sorted by frequency.

### git why

Find which commit first introduced a symbol or file — answers "why does this exist?"

```bash
cartographer git why [OPTIONS] TARGET

Options:
  -r, --repo TEXT         Repository name

Examples:
  cartographer git why render.rs
  cartographer git why UserService
```

Shows the commit hash, file path, author, date, and commit message.

### git authors

List all authors sorted by commit count — helps identify who knows what.

```bash
cartographer git authors [OPTIONS]

Options:
  -r, --repo TEXT         Repository name
  -l, --limit INT         Max results (default: 20)

Examples:
  cartographer git authors
  cartographer git authors -l 50
```

---

## cartographer mcp

**Purpose:** Start the MCP (Model Context Protocol) server for AI assistant integration. This exposes all Cartographer tools to AI coding assistants like Claude Desktop, Cursor, and OpenCode.

```bash
cartographer mcp [OPTIONS]

Options:
  --db PATH               Database path (default: ~/.cartographer/index.db)

Examples:
  cartographer mcp
  cartographer --db /tmp/my.db mcp
```

### What it exposes

**8 Tools** (callable by the AI assistant):
- `search` — search knowledge graph nodes
- `impact` — find what depends on a target
- `neighbors` — show graph neighbors (BFS)
- `path` — shortest path between nodes
- `summarize` — repository statistics
- `architecture` — detect/retrieve architecture
- `similar` — semantic similarity search
- `ask` — natural language question answering

**3 Resources** (readable by the AI assistant):
- `cartographer://repos` — list all indexed repositories
- `cartographer://repo/{name}` — repository details
- `cartographer://node/{node_id}` — single node details

### Configuration

Claude Desktop / Cursor:
```json
{
  "mcpServers": {
    "cartographer": {
      "command": "cartographer-mcp",
      "args": ["--db", "/path/to/custom.db"]
    }
  }
}
```

The `--db` flag is forwarded to the MCP server and used for all database connections. If omitted, defaults to `~/.cartographer/index.db`.

### Connection Settings

All MCP connections use WAL mode, foreign keys enabled, synchronous=NORMAL, and a 5-second busy timeout.

---

## cartographer version

Show the installed version.

```bash
cartographer version
# cartographer 0.1.0
```
