# Architecture Deep Dive

Cartographer is a modular pipeline system that transforms source code repositories into queryable knowledge graphs. This document explains how each component works.

## System Overview

```
Repository (files on disk)
    │
    ▼
┌─────────────────┐
│  Ingestion      │  File discovery, language detection, framework fingerprinting
│  Engine         │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  Parser Engine  │  19 language parsers (Tree-sitter)
│                 │  Entity extraction (classes, functions, methods, etc.)
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  References     │  Cross-file import/reference extraction (regex-based)
│  Extractor      │  Candidate resolution with suffix matching
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  Graph Builder  │  SQLite persistence: nodes, edges, directories
│                 │  Manifest metadata, embeddings, git data
└────────┬────────┘
         │
    ┌────┴────┐
    ▼         ▼
┌────────┐ ┌──────────┐
│Retrieval│ │Git       │ Git log parsing,
│Engine   │ │Intelligence│ commit/author tracking
│         │ │Engine    │
│Search,  │ └──────────┘
│Traversal│
│Impact,  │ ┌──────────────┐
│Path     │ │Architecture  │ Layer detection,
│Summary  │ │Engine        │ pattern matching,
└────────┘ │              │ dependency flow
           └──────────────┘
                    │
           ┌────────┴────────┐
           ▼                 ▼
    ┌──────────┐     ┌──────────────┐
    │Query     │     │Compression   │ Token-aware
    │Planner   │     │Engine        │ output compression
    │Intent    │     │              │
    │Detection │     └──────────────┘
    │Dispatch  │
    └──────────┘

┌──────────────┐
│ Embedding    │  fastembed + bge-small-en-v1.5
│ Engine       │  Semantic search, similarity
└──────────────┘
```

## 1. Ingestion Engine

**File:** `cartographer/ingestion/engine.py`

The ingestion engine orchestrates the entire indexing pipeline:

### File Discovery

Recursively walks the directory tree using `Path.iterdir()`. Collects all files, filters by known extensions, and counts directories.

### Language Detection

Maps file extensions to languages using a `LANGUAGE_EXTENSIONS` dictionary:

```python
LANGUAGE_EXTENSIONS = {
    ".py": Language.PYTHON,
    ".js": Language.JAVASCRIPT,
    ".ts": Language.TYPESCRIPT,
    ".rs": Language.RUST,
    # ... 30+ extensions for 19 languages
}
```

Unknown extensions are skipped silently.

### Framework Fingerprinting

**File:** `cartographer/ingestion/fingerprint.py`

Detects frameworks by checking for indicator files and parsing config:

| Framework | Indicator Files | Detection Method |
|-----------|----------------|------------------|
| Django | `manage.py`, `settings.py`, `requirements.txt` | File + regex on requirements |
| Flask | `requirements.txt` | Regex on requirements |
| Rails | `Gemfile`, `bin/rails` | File existence |
| Spring Boot | `pom.xml`, `build.gradle`, `application.yml` | File existence + XML/parsing |
| Express | `package.json` | Regex on dependencies |
| Next.js | `package.json`, `next.config.js` | Regex on dependencies |
| NestJS | `package.json`, `nest-cli.json` | Regex on dependencies |
| React | `package.json` | Regex on dependencies |
| Vue | `package.json` | Regex on dependencies |
| Laravel | `artisan`, `composer.json` | File existence |
| Actix Web | `Cargo.toml` | Regex on dependencies |
| Axum | `Cargo.toml` | Regex on dependencies |

Fingerprints are stored as JSON in the `manifest_json` column of the `repositories` table.

### Package Manager Detection

Detects files like `package.json` (npm), `Cargo.toml` (cargo), `requirements.txt` (pip), `Gemfile` (bundler), `Pipfile` (pipenv), `Cargo.lock`, `yarn.lock`, `composer.json` (composer).

### Build System Detection

Detects `Makefile`, `CMakeLists.txt`, `Cargo.toml`, `setup.py`, `pyproject.toml`, `build.gradle`, `pom.xml`.

### Monorepo Detection

Detects `lerna.json`, `nx.json`, `turbo.json`, `workspace` entries in `package.json` or `Cargo.toml`.

## 2. Parser Engine

**File:** `cartographer/parser/registry.py`, `cartographer/parser/base.py`, `cartographer/parser/languages/*.py`

### Architecture

The parser engine uses a registry pattern:

```python
_python_parser = PythonParser()
_go_parser = GoParser()
_rust_parser = RustParser()
# ... 19 parsers total

PARSER_MAP: dict[Language, BaseParser] = {
    Language.PYTHON: _python_parser,
    Language.GO: _go_parser,
    # ...
}
```

Each parser extends `BaseParser` and implements `parse(file_path, source_bytes)` which returns a list of `ParsedFile` objects containing `ParsedEntity` trees.

### Entity Types

| EntityKind | Description | Examples |
|------------|-------------|----------|
| `FILE` | Source file | `main.py`, `app.js` |
| `CLASS` | Class definition | `UserService`, `ConfigManager` |
| `FUNCTION` | Function definition | `get_user()`, `validate_input` |
| `METHOD` | Method within a class | `__init__`, `save()` |
| `INTERFACE` | Interface/protocol/trait | `IUserRepository`, `Serializable` |
| `ENUM` | Enumeration | `Color.RED`, `Status.ACTIVE` |
| `VARIABLE` | Module-level variable | `DEFAULT_TIMEOUT`, `APP_CONFIG` |
| `CONSTANT` | Named constant | `MAX_RETRIES`, `PI` |
| `MODULE` | Module/namespace | Python module, Rust `mod` |

### Parser Implementations

19 parsers using Tree-sitter 0.25.x:

| Language | File | Grammar Package | Key Features |
|----------|------|----------------|--------------|
| Python | `python.py` | `tree-sitter-python` | classes, functions, decorators |
| JavaScript | `javascript.py` | `tree-sitter-javascript` | classes, functions, exports |
| TypeScript | `typescript.py` | `tree-sitter-typescript` | interfaces, enums, generics |
| Go | `go.py` | `tree-sitter-go` | structs, interfaces, methods |
| Rust | `rust.py` | `tree-sitter-rust` | structs, traits, impl blocks, enums |
| Java | `java.py` | `tree-sitter-java` | classes, interfaces, methods |
| Kotlin | `kotlin.py` | `tree-sitter-kotlin` | classes, interfaces, functions |
| C# | `csharp.py` | `tree-sitter-csharp` | classes, interfaces, methods |
| PHP | `php.py` | `tree-sitter-php` | classes, interfaces, traits |
| Ruby | `ruby.py` | `tree-sitter-ruby` | classes, modules, methods |
| C | `c.py` | `tree-sitter-c` | functions, structs, enums |
| C++ | `cpp.py` | `tree-sitter-cpp` | classes, functions, templates |
| Swift | `swift.py` | `tree-sitter-swift` | classes, structs, protocols |
| Scala | `scala.py` | `tree-sitter-scala` | classes, objects, traits |
| Elixir | `elixir.py` | `tree-sitter-elixir` | modules, functions (positional children) |
| Lua | `lua.py` | `tree-sitter-lua` | functions, tables |
| Julia | `julia.py` | `tree-sitter-julia` | structs, functions, abstract types |
| Zig | `zig.py` | `tree-sitter-zig` | structs, functions, enums |
| Groovy | `groovy.py` | `tree-sitter-groovy` | classes, interfaces, methods |

### Elixir Parser Note

The Elixir Tree-sitter grammar (0.3.5) uses positional children instead of named fields for `call` nodes. The parser uses `child[0]` for the identifier, `child[1]` for arguments, and `child[2]` for the do-block.

## 3. Reference Extraction

**File:** `cartographer/ingestion/references.py`

### Import Patterns

Extracts cross-file references using regex patterns for each language:

```python
IMPORT_PATTERNS = {
    Language.PYTHON: [
        (r'^\s*import\s+(\S+)', 1),
        (r'^\s*from\s+(\S+)\s+import', 1),
    ],
    Language.JAVASCRIPT: [
        (r"(?:import|require)\s*\(?['\"]([^'\"]+)['\"]", 1),
        (r"from\s+['\"]([^'\"]+)['\"]", 1),
    ],
    Language.RUST: [
        (r'^\s*use\s+(\S[^;]*)', 1),
        (r'^\s*extern\s+crate\s+(\S+)', 1),
    ],
    # ... 19 languages
}
```

### Candidate Resolution

The `_candidates_for_import` function resolves import strings to actual file paths using a multi-step fallback chain:

1. **Exact match** — import string matches file path exactly
2. **Suffix match** — file path ends with import string (converting dots to path separators)
3. **Case-insensitive suffix** — lowercase version of suffix match
4. **Last-part fallback** — for multi-segment imports, tries just the last segment as a suffix
5. **Module indicator fallback** — checks for `__init__.py`, `mod.rs`, `init.lua`

### Rust-Specific Resolution

Rust imports use `::` separators. The resolver handles:

- `crate::foo` → `src/foo.rs`
- `super::foo` → `../foo.rs`
- `self::foo` → `./foo.rs`
- External crate names are stripped for path matching (e.g., `mdbook::config` → `config`)

## 4. Graph Builder

**File:** `cartographer/graph/builder.py`

### Schema

The graph is stored in SQLite with these tables:

```
repositories (id, path, name, indexed_at, manifest_json)
nodes        (id, repository_id, node_type, name, file_path, metadata_json)
edges        (id, repository_id, source_node_id, target_node_id, edge_type, metadata_json)
embeddings   (id, node_id, model, vector)
architecture (id, repository_id, layer, pattern, description)
commits      (id, repository_id, hash, author, message, committed_at)
commit_files (id, commit_id, file_path, change_type)
commit_authors (id, repository_id, name, email, commit_count)
```

### Indexes

```sql
CREATE INDEX idx_nodes_repo_type ON nodes(repository_id, node_type);
CREATE INDEX idx_nodes_file_path ON nodes(file_path);
CREATE INDEX idx_edges_repo_type ON edges(repository_id, edge_type);
CREATE INDEX idx_edges_source ON edges(source_node_id);
CREATE INDEX idx_edges_target ON edges(target_node_id);
```

### Edge Types

| Edge Type | Description |
|-----------|-------------|
| `CONTAINS` | Directory/file/entity containment |
| `DEFINES` | Class/function/interface definition |
| `DECLARES` | Variable/constant declaration |
| `IMPORTS` | Cross-file import/reference |

### Graph Construction

The builder processes each parsed file:

1. Creates directory nodes for each path segment
2. Creates CONTAINS edges from parent to child
3. Creates file nodes with language metadata
4. Processes entities recursively with DEFINES/DECLARES edges
5. Creates IMPORTS edges from reference resolution

## 5. Retrieval Engine

**File:** `cartographer/retrieval/`

### Search (`searcher.py`)

Basic text search using SQL `LIKE`:

```sql
SELECT n.id, n.node_type, n.name, n.file_path, r.name, r.path
FROM nodes n
JOIN repositories r ON n.repository_id = r.id
WHERE n.name LIKE '%query%'
ORDER BY
    CASE WHEN n.name = 'query' THEN 0
         WHEN n.name LIKE 'query%' THEN 1
         ELSE 2
    END
LIMIT 20
```

Results ordered by exact match → prefix match → substring match.

### Traversal (`traversal.py`)

**Neighbors** — BFS traversal from a starting node, collecting all connected nodes up to a configurable depth. Uses `SELECT source_node_id, target_node_id FROM edges WHERE source_node_id = ? OR target_node_id = ?`.

**Impact Analysis** — Reverse graph traversal finding all nodes that point to the target via IMPORTS, DEFINES, or CONTAINS edges. Groups results by edge type.

**Path Finding** — BFS from start to target node, with max depth limit. Returns the first (shortest) path found.

### Summarizer (`summarizer.py`)

Aggregates statistics from the graph:

- Total nodes and edges
- Node type breakdown
- Edge type breakdown
- Top files by entity count
- Top classes by method count

## 6. Architecture Engine

**File:** `cartographer/architecture/engine.py`

### Detection Pipeline

1. **Framework detection** — Reads `manifest_json` from the database (fingerprint data from indexing). Falls back to graph-only detection (directory/file name heuristics) for old databases.

2. **Evidence collection** — Scores all nodes against 5 signal types:
   - Class/naming: suffix/prefix matching against `CLASS_SUFFIX_RULES` (50 rules)
   - Function naming: same rules with 0.8x weight
   - File naming: keyword matching against `FILE_NAME_RULES` (32 rules)
   - Directory naming: exact match against `DIRECTORY_NAME_RULES` (60 rules)
   - Framework files: framework-specific patterns (70+ rules across 9 frameworks)

3. **Layer aggregation** — Combines evidence into confidence scores per layer:
   ```
   confidence = (avg_weight × 0.4 + max_weight × 0.6) × min(entity_count / 3, 1.0)
   ```

4. **Dependency flow** — Analyzes IMPORTS edges between files in different layers. Detects expected vs. unexpected dependency directions.

5. **Pattern detection** — Matches detected layer sets against 6 architecture patterns and 9 framework-specific patterns.

### Layer Types

| Layer | Description | Detection Signals |
|-------|-------------|-------------------|
| Controller | Request handling | `*Controller`, `routes/`, `handlers/` |
| Presentation | UI/views | `views/`, `templates/`, `components/` |
| API | External interfaces | `api/`, `graphql/`, `grpc/` |
| Business | Business logic | `*Service`, `*Manager`, `services/` |
| Data | Data access/persistence | `*Repository`, `*DAO`, `models/` |
| Middleware | Request filtering | `middleware/`, `filters/` |
| Config | Configuration | `*Config`, `config/`, `settings/` |
| Infrastructure | External integrations | `infrastructure/`, `*Adapter`, `*Client` |
| Migration | Database migrations | `migrations/`, `alembic/` |
| Testing | Tests | `tests/`, `*Test`, `*Spec` |
| Utility | Helpers/utilities | `utils/`, `helpers/`, `common/` |

### Architecture Patterns

| Pattern | Required Layers | Confidence |
|---------|----------------|------------|
| MVC | controller, presentation, data | >50% match |
| Layered | presentation, business, data | >50% match |
| Clean | business, infrastructure, api | >50% match |
| Hexagonal | business, infrastructure, api | >50% match |
| Repository | data | ≥1 layer |
| Service-Oriented | api, business | >50% match |

## 7. Embedding Engine

**File:** `cartographer/embedding/engine.py`

Uses `fastembed` with `BAAI/bge-small-en-v1.5` model (384-dimensional vectors).

### Embedding

Only embeddable node types: `class`, `function`, `method`, `file`, `interface`, `enum`.

Node text for embedding:

```
{node_type}: {name}
file: {file_path}
docstring: {docstring}
```

### Similarity Search

Compares query embedding against all stored embeddings using cosine similarity. Loads all vectors into memory and computes similarity in pure Python — suitable for up to ~10,000 nodes.

### Find Similar

Finds nodes with similar embeddings to a given node. Excludes the source node from results.

## 8. Git Intelligence Engine

**File:** `cartographer/git/engine.py`

### Commit Indexing

Runs `git log --all --reverse --format=FORMAT --date=unix` with a 60-second timeout. Parses the output to extract commits, authors, and file changes.

### Co-Change Analysis

Counts how often pairs of files appear in the same commit. Co-change frequency = number of commits where both files changed together.

### Why-Introduced

Uses `git log --diff-filter=A --follow --format=%H` to find the commit that first introduced a file or symbol.

## 9. Compression Engine

**File:** `cartographer/compression/engine.py`

### Token Estimation

```
estimate_tokens(text) → len(text) // 4
```

### Strategies

| Strategy | Input | Method |
|----------|-------|--------|
| `compress_nodes` | List of node dicts | Groups by type when >10, shows counts + top files, truncates lines to budget |
| `compress_impact` | Impact analysis results | Groups by edge type, shows counts per group |
| `compress_path` | Path results | Shows all hops, truncates long paths |
| `compress_summary` | Summary dict | Condenses to top types/files, truncates |

## 10. Query Planner

**File:** `cartographer/query/engine.py`

### Intent Classification

Uses priority-based regex rules to classify queries:

```python
INTENT_RULES = [
    ("architecture", "architecture", [
        (10, r"\barchitecture\b"),
        (10, r"\blayers?\b"),
    ]),
    ("summarize", "summarize", [
        (10, r"\boverview\b"),
        (10, r"\bsummarize\b"),
    ]),
    # ... 9 intent types with priority scores
]
```

Architecture/summarize keywords get priority (10) over explain/impact (5) to avoid false matches. Targets are extracted from captured regex groups.

### Dispatch

Each intent type maps to a build function that calls the appropriate retrieval method:

| Intent | Function | Retrieval Method |
|--------|----------|-----------------|
| `architecture` | `_build_architecture` | `detect_architecture` |
| `summarize` | `_build_summarize` | `generate_summary` |
| `explain` | `_build_explain` | `search_nodes` + `impact_analysis` |
| `impact` | `_build_impact` | `impact_analysis` |
| `path` | `_build_path` | `find_path` |
| `search` | `_build_search` | `search_nodes` |

## Database

### Location

Default: `~/.cartographer/index.db`

Configurable via `--db` flag or `CARTOGRAPHER_DB` environment variable.

### Storage

- SQLite with WAL (Write-Ahead Log) mode for concurrent reads
- Foreign keys enabled for referential integrity
- JSON metadata columns for flexible schema evolution
- Binary vector blobs for embeddings (384 floats × 4 bytes = 1536 bytes per vector)

### Performance

| Operation | Complexity | Bottleneck |
|-----------|------------|------------|
| Indexing | O(files × entities) | I/O (file reads) |
| Text search | O(nodes) | SQL LIKE scan |
| Traversal | O(edges^depth) | BFS on adjacency |
| Impact | O(edges) | Reverse edge scan |
| Architecture | O(nodes + edges) | Evidence scoring |
