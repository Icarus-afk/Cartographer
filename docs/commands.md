# Command Reference

This document covers every Cartographer command, option, and example.

## Global Options

Every command supports these global options:

```
--db PATH     Path to SQLite database (default: ~/.cartographer/index.db)
              Also settable via CARTOGRAPHER_DB environment variable
```

## cartographer index

Index a repository into the knowledge graph. This is the first command you run.

```bash
cartographer index [PATH]

# Examples
cartographer index .
cartographer index /path/to/repo
cartographer --db /tmp/my.db index ./my-project
```

The indexer:

1. Discovers all files via recursive directory walk
2. Detects languages by file extension
3. Parses each file with the appropriate Tree-sitter parser
4. Extracts entities (classes, functions, methods, variables, interfaces, enums, constants)
5. Extracts cross-file references/imports using regex patterns
6. Detects package managers, build systems, and frameworks
7. Builds the graph (nodes + edges) in SQLite
8. Persists manifest metadata (frameworks, languages, reference count)

**Performance notes:**

- Indexing is I/O bound for large repos (reading files)
- Memory scales with total entity count, not file size
- Tree-sitter parsers are loaded lazily per language
- Cross-reference resolution is O(imports × candidate files) in worst case

## cartographer ask

Search the knowledge graph for symbols matching a text query.

```bash
cartographer ask [OPTIONS] QUERY

Options:
  -t, --type TEXT     Filter by node type (class, function, file, etc.)
  -r, --repo TEXT     Filter by repository name
  -l, --limit INT     Max results (default: 20)
  -s, --semantic      Use semantic (embedding) search instead of text
  -m, --max-tokens INT  Compress output to fit token budget

Examples:
  # Basic text search
  cartographer ask "UserService"

  # Filter by type
  cartographer ask --type class "User"

  # Limit results
  cartographer ask --limit 5 "handler"

  # Semantic search (requires embeddings)
  cartographer ask --semantic "error handling middleware"

  # Compressed output for LLM context
  cartographer ask -m 200 "Preprocessor"
```

**Text search** uses SQL `LIKE` with `%query%` wildcards. Results are sorted by relevance (exact match first, then prefix match, then substring).

**Semantic search** compares the query embedding against all stored embeddings using cosine similarity.

## cartographer query

Natural language query with automatic intent detection. This wraps multiple retrieval strategies behind a single interface.

```bash
cartographer query [OPTIONS] QUERY_STR

Options:
  -r, --repo TEXT         Filter by repository name
  -l, --limit INT         Max results per step (default: 20)
  -m, --max-tokens INT    Compress output to fit token budget
  -v, --verbose           Show detailed reasoning

Examples:
  # Architecture
  cartographer query "what is the architecture"
  cartographer query "how is this project organized"

  # Explanation
  cartographer query "explain Preprocessor"
  cartographer query "what is the UserService class"

  # Impact analysis
  cartographer query "what depends on config.py"
  cartographer query "impact of the auth module"

  # Path finding
  cartographer query "path between cmd and config"
  cartographer query "how are the CLI and API connected"

  # Summary
  cartographer query "summarize this project"
  cartographer query "overview"

  # Search (fallback when no intent is detected)
  cartographer query "find the database connection pool"

  # Compressed for LLM context
  cartographer query -m 200 "explain Preprocessor"
```

### Intent Detection

The query planner classifies queries into these types:

| Intent | Example Queries | Strategy |
|--------|----------------|----------|
| `architecture` | "architecture", "layers", "patterns" | Runs architecture detection |
| `summarize` | "overview", "summarize", "what is this" | Generates repo summary |
| `explain` | "explain X", "what is X" | Searches nodes + impact |
| `impact` | "what depends on X", "impact" | Impact analysis |
| `path` | "path between X and Y", "relationship" | Path finding |
| `git_blame` | "who wrote X", "blame X" | Git history |
| `git_why` | "why was X introduced" | Why-introduced analysis |
| `git_cochange` | "what changes with X" | Co-change analysis |
| `search` | (fallback) | Basic text search |

Architecture and summary queries take highest priority to avoid false matches from catch-all explain patterns.

## cartographer impact

Analyze what depends on (imports, extends, or otherwise references) a given file or symbol.

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

Results are grouped by edge type (IMPORTS, DEFINES, CONTAINS) so you can see which files directly import the target vs. which contain it.

## cartographer neighbors

Show nodes connected to a given node in the graph.

```bash
cartographer neighbors [OPTIONS] NAME

Options:
  -r, --repo TEXT         Repository name
  -d, --depth INT         Traversal depth (default: 2, beware: grows exponentially)
  -m, --max-tokens INT    Compress output to fit token budget

Examples:
  cartographer neighbors UserService
  cartographer neighbors -d 1 main.py
  cartographer neighbors --depth 3 Preprocessor
```

Depth 1 shows direct connections. Depth 2 shows neighbors of neighbors. Depth 3+ can be very slow on large graphs.

## cartographer path

Find the shortest path between two nodes in the graph.

```bash
cartographer path [OPTIONS] FROM_NAME TO_NAME

Options:
  --max-depth INT         Maximum search depth (default: 5)
  -m, --max-tokens INT    Compress output to fit token budget

Examples:
  cartographer path "cmd" "config"
  cartographer path "UserController" "UserRepository"
```

Uses BFS (breadth-first search) to find the shortest path. Fails gracefully if no path exists within the max depth.

## cartographer summarize

Generate a high-level summary of the repository.

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
- Node breakdown by type (class, function, method, file, etc.)
- Edge breakdown by type (DEFINES, DECLARES, CONTAINS, IMPORTS)
- Top files by entity count
- Largest classes by method count

## cartographer architecture

Detect or display repository architecture.

```bash
cartographer architecture [OPTIONS]

Options:
  -r, --repo TEXT         Repository name
  --detect                Run architecture detection
  -v, --verbose           Show detailed evidence

Examples:
  # Detect and display
  cartographer architecture --detect

  # With detailed evidence
  cartographer architecture --detect -v

  # Show previously detected architecture
  cartographer architecture
```

### What is detected

**Frameworks** — Detected from manifest fingerprints and graph structure:
Django, Flask, Rails, Spring Boot, NestJS, Express, FastAPI, Next.js, Laravel, Actix Web, Axum

**Layers** — 12 layer types detected from naming conventions:
Controller, Presentation, API, Business, Data, Middleware, Config, Infrastructure, Migration, Testing, Utility, Migration

**Architecture patterns** — 6 generic patterns:
Model-View-Controller (MVC), Layered (n-tier), Clean Architecture, Hexagonal (Ports & Adapters), Repository Pattern, Service-Oriented

**Framework-specific patterns** — 9 framework patterns:
Django MTV, Rails MVC, Spring Boot Layered, NestJS Modular, Express MVC, FastAPI Modular, Next.js App Router, Laravel MVC, Actix Web Modular, Axum Modular

**Dependency flow** — Layer-to-layer import analysis showing expected vs. unexpected dependencies.

### Detection signals

| Signal | Weight | Description |
|--------|--------|-------------|
| Class naming | 1.0 | Class/interface suffix analysis (e.g., `UserController` → Controller) |
| Function naming | 0.8 | Function naming patterns |
| File naming | 1.0 | File name keyword matching (e.g., `routes.py` → Controller) |
| Directory naming | 1.0 | Directory name matching (e.g., `controllers/` → Controller) |
| Framework files | 1.0 | Framework-specific conventions (e.g., `models.py`, `admin.py`) |

## cartographer embed

Generate vector embeddings for semantic search.

```bash
cartographer embed [OPTIONS]

Options:
  -r, --repo TEXT         Repository name

Examples:
  cartographer embed
  cartographer embed -r myproject
```

Embeds all class, function, method, file, interface, and enum nodes using `BAAI/bge-small-en-v1.5` (384-dimensional vectors).

On first run, downloads the model (approx. 33MB). The model is cached locally for subsequent runs.

Only embeds nodes that don't already have embeddings (incremental).

## cartographer similar

Find semantically similar nodes.

```bash
cartographer similar [OPTIONS] TARGET

Options:
  -r, --repo TEXT         Repository name
  -l, --limit INT         Max results (default: 20)

Examples:
  cartographer similar "error handling"
  cartographer similar UserService
  cartographer similar -l 10 "database connection pool"
```

If the target matches a node name, finds nodes with similar embeddings. Otherwise, treats the target as a text query and does semantic search.

## cartographer git

Git intelligence commands for understanding code history.

### git index

Index git history (commits, authors, change patterns).

```bash
cartographer git index [OPTIONS]

Options:
  -p, --repo-path TEXT    Path to the git repository
  -r, --repo TEXT         Repository name (for already-indexed repos)
  -n, --max-count INT     Max commits to index (default: all)

Examples:
  cartographer git index -p /path/to/repo
  cartographer git index -n 100
```

Runs `git log` with a 60-second timeout. Stores commits, authors, and file-change records.

### git blame

Show commit history for a file or symbol.

```bash
cartographer git blame [OPTIONS] TARGET

Options:
  -r, --repo TEXT         Repository name
  -l, --limit INT         Max results (default: 15)

Examples:
  cartographer git blame render.py
  cartographer git blame Preprocessor
```

Tries to find history for a specific symbol first, then falls back to file history.

### git author

Show an author's contributions.

```bash
cartographer git author [OPTIONS] NAME

Options:
  -r, --repo TEXT         Repository name
  -l, --limit INT         Max results (default: 15)

Examples:
  cartographer git author "Jane Doe"
  cartographer git author -l 30 "John Smith"
```

Shows total commits, most-changed files, and recent commits by the author.

### git cochange

Find files that change together with a target file.

```bash
cartographer git cochange [OPTIONS] TARGET

Options:
  -r, --repo TEXT         Repository name
  -l, --limit INT         Max results (default: 15)

Examples:
  cartographer git cochange config.rs
  cartographer git cochange -l 10 settings.py
```

Uses co-occurrence analysis on commit data to find files frequently changed in the same commits.

### git why

Find which commit introduced a symbol or file.

```bash
cartographer git why [OPTIONS] TARGET

Options:
  -r, --repo TEXT         Repository name

Examples:
  cartographer git why render.rs
  cartographer git why UserService
```

Shows the commit hash, file path, author, date, and commit message that first introduced the target.

### git authors

List all authors sorted by commit count.

```bash
cartographer git authors [OPTIONS]

Options:
  -r, --repo TEXT         Repository name
  -l, --limit INT         Max results (default: 20)

Examples:
  cartographer git authors
  cartographer git authors -l 50
```

## cartographer version

Display the installed version.

```bash
cartographer version
# cartographer 0.1.0
```
