# Architecture Deep Dive

Cartographer transforms source code repositories into queryable knowledge graphs. This document explains how each engine works and how they fit together.

---

## System Overview

```
Repository (files on disk)
    │
    ▼
┌─────────────────┐
│  Ingestion      │  File discovery, language detection, framework fingerprinting,
│  Engine         │  .gitignore/.cartographerignore support, binary detection
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  Parser Engine  │  20 language parsers (Tree-sitter), entity extraction
│                 │  (classes, functions, methods, interfaces, enums, etc.)
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  Graph Builder  │  SQLite persistence: nodes, edges, directories,
│                 │  manifest metadata, embeddings, git data
└────────┬────────┘
         │
    ┌────┴────┐
    ▼         ▼
┌────────┐  ┌──────────┐
│Retrieval│  │Git       │  Git log parsing, commit/author tracking,
│Engine   │  │Intelligence│ co-change analysis, why-introduced
│         │  │Engine    │
│Search,  │  └──────────┘
│Traversal│
│Impact,  │  ┌──────────────┐
│Path     │  │Architecture  │  Layer detection, pattern matching,
│Summary  │  │Engine        │  dependency flow, framework detection
└────────┘  └──────────────┘
         │           │
         ▼           ▼
     ┌────────┐ ┌──────────────┐
     │Query   │ │Compression   │  Token-aware output compression
     │Planner │ │Engine        │  for LLM context budgets
     │Intent  │ └──────────────┘
     │Detect  │
     │Dispatch│ ┌──────────────┐
     └────────┘ │ MCP Server   │  Model Context Protocol server
                 │              │  exposes 14 tools + 3 resources
                └──────────────┘

┌──────────────┐
│ Embedding    │  fastembed + bge-small-en-v1.5 (384-dim)
│ Engine       │  numpy-batched cosine similarity (280x speedup)
└──────────────┘
```

---

## 1. Ingestion Engine

**File:** `cartographer/ingestion/engine.py`

The ingestion engine orchestrates the entire indexing pipeline from file discovery to graph construction.

### File Discovery

Recursively walks the directory tree using `Path.iterdir()`. Skips:
- **Hidden directories** starting with `.` (`.git`, `.venv`, `.next`, `.nuxt`, etc.)
- **23 blocked directories** (`node_modules`, `__pycache__`, `target`, `build`, `dist`, `vendor`, `Pods`, etc.)
- **Binary files** — two-layer detection: extension blocklist (50+ binary extensions) then null-byte check (reads first 8KB and checks for `\0`)
- **`.cartographerignore` patterns** — loaded from repo root, matched via `fnmatch.fnmatch`. Patterns with `/` match full relative path; patterns without `/` match basename only
- **`.gitignore` patterns** — root `.gitignore` is parsed via the `pathspec` library (gitwildmatch format) and merged with `.cartographerignore` exclusions

### Language Detection

Maps file extensions to languages:

| Extension | Language |
|---|---|
| `.py` | Python |
| `.js`, `.jsx`, `.mjs`, `.cjs` | JavaScript |
| `.ts` | TypeScript |
| `.tsx` | TSX |
| `.go` | Go |
| `.rs` | Rust |
| `.java` | Java |
| `.kt`, `.kts` | Kotlin |
| `.cs` | C# |
| `.php`, `.phtml` | PHP |
| `.rb` | Ruby |
| `.c`, `.h` | C |
| `.cpp`, `.hpp`, `.cc`, `.cxx` | C++ |
| `.swift` | Swift |
| `.scala`, `.sc` | Scala |
| `.ex`, `.exs` | Elixir |
| `.lua` | Lua |
| `.jl` | Julia |
| `.zig` | Zig |
| `.groovy`, `.gvy`, `.gsh` | Groovy |

### Framework Fingerprinting

**File:** `cartographer/ingestion/fingerprint.py`

Detects frameworks by checking for indicator files and parsing config files:

| Framework | Detection Method |
|---|---|
| Django | `manage.py`, `settings.py`, `django` in `requirements.txt` |
| Flask | `flask` in `requirements.txt` |
| FastAPI | `fastapi` in `requirements.txt` or imports |
| Rails | `Gemfile`, `bin/rails` |
| Spring Boot | `pom.xml`, `build.gradle`, `application.yml` |
| Express | `express` in `package.json` dependencies |
| Next.js | `next` in `package.json`, `next.config.js` |
| NestJS | `nest` in `package.json`, `nest-cli.json` |
| React | `react` in `package.json` |
| Vue | `vue` in `package.json` |
| Laravel | `artisan` file, `composer.json` |
| Actix Web | `actix-web` in `Cargo.toml` |
| Axum | `axum` in `Cargo.toml` |
| Gin | `gin` in `go.mod` |
| Echo | `echo` in `go.mod` |
| Rocket | `rocket` in `Cargo.toml` |
| Vapor | `vapor` in `Package.swift` |
| Phoenix | `phoenix` in `mix.exs` |

Each fingerprint includes a confidence score (0.0–1.0). Fingerprints are stored as JSON in the `manifest_json` column of the `repositories` table.

### Package Manager Detection

Detects files like `package.json` (npm), `Cargo.toml` (cargo), `requirements.txt` (pip), `Gemfile` (bundler), `Pipfile` (pipenv), `Cargo.lock`, `yarn.lock`, `composer.json` (composer).

### Build System Detection

Detects `Makefile`, `CMakeLists.txt`, `Cargo.toml`, `setup.py`, `pyproject.toml`, `build.gradle`, `pom.xml`.

### Monorepo Detection

Detects `lerna.json`, `nx.json`, `turbo.json`, `workspace` entries in `package.json` or `Cargo.toml` (pnpm, npm, yarn workspaces).

---

## 2. Parser Engine

**File:** `cartographer/parser/registry.py`, `cartographer/parser/base.py`, `cartographer/parser/languages/*.py`

### Architecture

The parser engine uses a registry pattern — each language has its own parser class that extends `BaseParser` and implements `parse(file_path, source_bytes)` returning a list of `ParsedEntity` trees. All 20 tree-sitter language bindings are imported lazily on first use via `_ensure_parsers()`, and parser instances are cached in `_PARSER_CACHE` (constructed once per language).

```
BaseParser (abstract)
 ├── PythonParser
 ├── JavaScriptParser (+ value-aware extraction, export handling)
 │    ├── TypeScriptParser (+ interfaces, type aliases, enums, generics)
 │    │    └── TSXParser (+ JSX element extraction)
 ├── GoParser
 ├── RustParser
 ├── ...
 └── GroovyParser (20 total)
```

### Entity Types

| EntityKind | Description | Examples |
|---|---|---|
| `FILE` | Source file | `main.py`, `app.js` |
| `CLASS` | Class definition | `UserService`, `ConfigManager` |
| `FUNCTION` | Function definition | `get_user()`, `validate_input` |
| `METHOD` | Method within a class | `__init__`, `save()` |
| `INTERFACE` | Interface/protocol/trait | `IUserRepository`, `Serializable` |
| `TYPE_ALIAS` | Type alias | `Response<T>`, `UserID` |
| `ENUM` | Enumeration | `Color.RED`, `Status.ACTIVE` |
| `VARIABLE` | Module-level variable | `DEFAULT_TIMEOUT`, `APP_CONFIG` |
| `CONSTANT` | Named constant | `MAX_RETRIES`, `PI` |
| `MODULE` | Module/namespace | Python module, Rust `mod` |

### JavaScript Parser (`javascript.py`)

Dispatches top-level children to specialized extractors:

| Node Type | Extracted As | Notes |
|---|---|---|
| `function_declaration` | FUNCTION | Standard function |
| `function_expression` | FUNCTION | Anonymous/assigned |
| `arrow_function` | FUNCTION | Named `<anonymous>` if unnamed |
| `class_declaration` | CLASS | With children |
| `variable_declaration` (var) | CONSTANT | Module-level var |
| `lexical_declaration` (const/let) | CONSTANT or FUNCTION | **Value-aware**: promotes to FUNCTION if value is arrow/function |
| `export_statement` | delegates | Wraps inner declaration |

**Value-aware extraction:** If a `variable_declarator`'s value is an arrow function or class, the entity kind is promoted — so `const handler = () => {}` becomes a FUNCTION, not a CONSTANT.

**Export handling:** `export default function()` without a name falls back to name `"default"`.

### TypeScript Parser (`typescript.py`)

Extends JavaScriptParser with TypeScript-specific nodes:

| Node Type | Extracted As | Metadata |
|---|---|---|
| `interface_declaration` | INTERFACE | `{"type_parameters": "<T>"}` |
| `type_alias_declaration` | TYPE_ALIAS | `{"type_parameters": "<T>"}` |
| `enum_declaration` | ENUM | — |

Generic type parameters (`<T>`, `<K, V>`) are captured in metadata for interfaces and type aliases.

### TSX Parser (`tsx.py`)

Extends TypeScriptParser with JSX handling. Captures top-level JSX expressions:

| Node Type | Extracted As | Example |
|---|---|---|
| `expression_statement` → `jsx_element` | CONSTANT (tag name) | `<App />` at module root |
| `expression_statement` → `jsx_self_closing_element` | CONSTANT (tag name) | `<Header />` at module root |

### All 20 Parsers

| Parser | File | Tree-sitter Grammar |
|---|---|---|
| PythonParser | `languages/python.py` | `tree-sitter-python` |
| JavaScriptParser | `languages/javascript.py` | `tree-sitter-javascript` |
| TypeScriptParser | `languages/typescript.py` | `tree-sitter-typescript` (language_typescript) |
| TSXParser | `languages/tsx.py` | `tree-sitter-typescript` (language_tsx) |
| GoParser | `languages/go.py` | `tree-sitter-go` |
| RustParser | `languages/rust.py` | `tree-sitter-rust` |
| JavaParser | `languages/java.py` | `tree-sitter-java` |
| KotlinParser | `languages/kotlin.py` | `tree-sitter-kotlin` |
| CSharpParser | `languages/csharp.py` | `tree-sitter-c-sharp` |
| PHPPhpParser | `languages/php.py` | `tree-sitter-php` |
| RubyParser | `languages/ruby.py` | `tree-sitter-ruby` |
| CParser | `languages/c.py` | `tree-sitter-c` |
| CppParser | `languages/cpp.py` | `tree-sitter-cpp` |
| SwiftParser | `languages/swift.py` | `tree-sitter-swift` |
| ScalaParser | `languages/scala.py` | `tree-sitter-scala` |
| ElixirParser | `languages/elixir.py` | `tree-sitter-elixir` |
| LuaParser | `languages/lua.py` | `tree-sitter-lua` |
| JuliaParser | `languages/julia.py` | `tree-sitter-julia` |
| ZigParser | `languages/zig.py` | `tree-sitter-zig` |
| GroovyParser | `languages/groovy.py` | `tree-sitter-groovy` |

### Relationship Extraction

Each parser extracts these relationship types from the AST:

| Relationship | Description | Extracted By |
|---|---|---|
| `CALLS` | Function/method calls | All 20 parsers (via `_extract_calls`) |
| `INHERITS` | Class/struct inheritance | Python, JS, TS, Java, C#, Kotlin, Swift, Scala, Rust, Ruby, PHP, Groovy |
| `IMPLEMENTS` | Interface/protocol implementation | Java, C#, Kotlin, Scala, Rust, Elixir, PHP, Groovy |
| `DECORATES` | Decorator relationships | Python |

### Docstring Extraction

Leading comments are extracted as docstrings for these languages:

| Language | Comment Style | Example |
|---|---|---|
| Python | Triple-quoted strings | `"""Module docstring"""` |
| Java | Javadoc | `/** ... */` |
| C# | XML doc | `/// ...` |
| Go | Line comments | `// ...` |
| Rust | Doc comments | `/// ...` or `//! ...` |

### Metadata Extraction

Parsers attach metadata to entities for richer analysis:

| Language | Entity | Metadata |
|---|---|---|
| Python | Functions | `decorators`, `parameters` |
| TypeScript | Interfaces, Functions | `type_parameters` |
| Rust | Functions | `public`, `return_type` |
| Java | Methods | `modifiers` (public, private, protected, static, final) |
| Go | Functions, Methods | `exported` (uppercase = exported) |

### Elixir Parser Note

The Elixir Tree-sitter grammar (0.3.5) uses positional children instead of named fields for `call` nodes. The parser uses `child[0]` for the identifier, `child[1]` for arguments, and `child[2]` for the do-block.

---

## 3. Reference Extraction

**File:** `cartographer/ingestion/references.py`

Extracts cross-file import/reference statements using regex patterns, then resolves them to actual file paths.

### Import Patterns

Each language has regex patterns for its import syntax:

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
    # ... 20 languages
}
```

### Candidate Resolution

The `_candidates_for_import` function resolves import strings to actual file paths using a multi-step fallback chain:

1. **Exact match** — import string matches file path exactly
2. **Suffix match** — file path ends with import string (converting dots to path separators, e.g., `os.path` → `os/path`)
3. **Case-insensitive suffix** — lowercase version of suffix match
4. **Last-part fallback** — for multi-segment imports, tries just the last segment
5. **Module indicator fallback** — checks for `__init__.py`, `mod.rs`, `index.ts`

### Rust-Specific Resolution

Rust imports use `::` separators:
- `crate::foo` → `src/foo.rs`
- `super::foo` → `../foo.rs`
- `self::foo` → `./foo.rs`
- External crate names are stripped (e.g., `mdbook::config` → `config`)

---

## 4. Graph Builder

**File:** `cartographer/graph/builder.py`

### Schema

The graph is stored in SQLite with these tables:

```sql
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
CREATE INDEX idx_nodes_name ON nodes(name);
CREATE INDEX idx_commits_hash ON commits(repository_id, hash);
CREATE INDEX idx_commit_files_commit ON commit_files(commit_id);
```

### Edge Types

| Edge Type | Description |
|---|---|
| `CONTAINS` | Directory/file/entity containment |
| `DEFINES` | Class/function/interface definition |
| `DECLARES` | Variable/constant declaration |
| `IMPORTS` | Cross-file import/reference |

### Graph Construction Process

The builder processes each parsed file:
1. Creates directory nodes for each path segment
2. Creates CONTAINS edges from parent to child
3. Creates file nodes with language metadata
4. Processes entities recursively with DEFINES/DECLARES edges
5. Creates IMPORTS edges from reference resolution
6. Deduplicates entities to prevent duplicate nodes

---

## 5. Retrieval Engine

**File:** `cartographer/retrieval/`

### Search (`searcher.py`)

Basic text search using SQL `LIKE` with `%query%` wildcards. Results ordered by exact match → prefix match → substring match.

Supports optional filters by `node_type` and `repo_name`.

### Traversal (`traversal.py`)

**Neighbors** — BFS traversal from a starting node, collecting all connected nodes up to a configurable depth. Uses `SELECT source_node_id, target_node_id FROM edges WHERE source_node_id = ? OR target_node_id = ?`.

**Impact Analysis** — Reverse graph traversal finding all nodes that point to the target via IMPORTS, DEFINES, or CONTAINS edges. Groups results by edge type.

**Path Finding** — Bidirectional BFS from start to target node with a max depth limit. Alternates between forward and backward search frontiers. Returns the shortest path.

### Summarizer (`summarizer.py`)

Aggregates statistics from the graph:
- Total nodes and edges
- Node type breakdown
- Edge type breakdown
- Top files by entity count
- Top classes by method count

---

## 6. Architecture Engine

**File:** `cartographer/architecture/engine.py`

### Detection Pipeline

1. **Framework detection** — reads `manifest_json` from the database (fingerprint data from indexing). Falls back to graph-only detection for old databases.

2. **Evidence collection** — scores all nodes against 5 signal types:
   - Class naming (1.0x weight) — suffix/prefix matching against 50 rules
   - Function naming (0.8x weight) — same rules
   - File naming (1.0x weight) — keyword matching against 32 rules
   - Directory naming (1.0x weight) — exact match against 60 rules
   - Framework files (1.0x weight) — 70+ framework-specific patterns

3. **Layer aggregation** — combines evidence into confidence scores per layer:
   ```
   confidence = (avg_weight × 0.4 + max_weight × 0.6) × min(entity_count / 3, 1.0)
   ```

4. **Dependency flow** — analyzes IMPORTS edges between files in different layers. Detects expected vs. unexpected dependency directions.

5. **Pattern detection** — matches detected layer sets against 6 architecture patterns and 9 framework-specific patterns.

### Layer Types

| Layer | Detection Signals |
|---|---|
| Controller | `*Controller`, `routes/`, `handlers/` |
| Presentation | `views/`, `templates/`, `components/` |
| API | `api/`, `graphql/`, `grpc/` |
| Business | `*Service`, `*Manager`, `services/` |
| Data | `*Repository`, `*DAO`, `models/` |
| Middleware | `middleware/`, `filters/` |
| Config | `*Config`, `config/`, `settings/` |
| Infrastructure | `infrastructure/`, `*Adapter`, `*Client` |
| Migration | `migrations/`, `alembic/` |
| Testing | `tests/`, `*Test`, `*Spec` |
| Utility | `utils/`, `helpers/`, `common/` |
| Deployment | `Dockerfile`, CI/CD configs |

### Architecture Patterns

| Pattern | Required Layers |
|---|---|
| MVC | controller, presentation, data |
| Layered (n-tier) | presentation, business, data |
| Clean Architecture | business, infrastructure, api |
| Hexagonal (Ports & Adapters) | business, infrastructure, api |
| Repository Pattern | data |
| Service-Oriented | api, business |

---

## 7. Embedding Engine

**File:** `cartographer/embedding/engine.py`

### Model

- **Model:** `BAAI/bge-small-en-v1.5` (general-purpose embedding model)
- **Dimensions:** 384
- **Library:** `fastembed` (efficient ONNX-based inference)
- **Singleton:** model cached globally (loaded once, reused across commands)

### Embeddable Node Types

```
class, function, method, file, interface, enum, type_alias
```

All 7 types include `type_alias` (TypeScript type aliases, etc.).

### Text Construction

Each node is converted to text before embedding:
```
{node_type}: {name}
file: {file_path}
docstring: {docstring if present}
```

### Pipeline (`generate_embeddings`)

1. Queries for unembedded nodes (uses `NOT IN (SELECT node_id FROM embeddings)`)
2. Builds text representations (with progress bar)
3. Batch-embeds via `model.embed(texts)` (with progress bar)
4. Serializes vectors as float32 blobs (384 × 4 = 1536 bytes each)
5. Batch-inserts into embeddings table (with progress bar)
6. Skips already-embedded nodes (incremental — safe to rerun)

### Similarity Search (`similarity_search`)

Uses **numpy-batched cosine similarity**:

```python
vectors = np.frombuffer(all_blobs, dtype=np.float32).reshape(N, 384)
norms = np.linalg.norm(vectors, axis=1)
dot = vectors @ query_vec
scores = dot / (norms * np.linalg.norm(query_vec))
top_indices = np.argpartition(-scores, top_k)[:top_k]
```

This is **280x faster** than the original Python loop:
- 5,000 vectors: **7ms** vs 2,025ms

### Find Similar (`find_similar`)

Same batch approach but uses an existing node's embedding vector as the query. Excludes the source node from results.

---

## 8. Git Intelligence Engine

**File:** `cartographer/git/engine.py`

### Commit Indexing

Runs `git log --all --reverse --format=FORMAT --date=unix` with a 60-second timeout. Parses output to extract commits, authors, and file changes.

### Co-Change Analysis

Counts how often pairs of files appear in the same commit. Co-change frequency = number of commits where both files changed together. Returns sorted results.

### Why-Introduced

Uses `git log --diff-filter=A --follow --format=%H` to find the commit that first introduced a file or symbol.

---

## 9. Compression Engine

**File:** `cartographer/compression/engine.py`

### Token Estimation

```
estimate_tokens(text) → len(text) // 4
```

### Strategies

| Strategy | Input | Method |
|---|---|---|
| `compress_nodes` | List of node dicts | Groups by type when >10, shows counts + top files, truncates lines |
| `compress_impact` | Impact analysis results | Groups by edge type, shows counts per group |
| `compress_path` | Path results | Shows all hops, truncates long paths |
| `compress_summary` | Summary dict | Condenses to top types/files, truncates |

### Auto-Dispatch

The `compress()` function automatically selects the best strategy based on input structure.

---

## 10. Query Planner

**File:** `cartographer/query/engine.py`

Uses priority-based regex rules to classify queries into 9 intents:

| Intent | Priority Keywords | Retrieval Method |
|---|---|---|
| `architecture` | architecture, layers, structure, pattern | `detect_architecture` |
| `summarize` | overview, summarize, high-level | `generate_summary` |
| `explain` | explain, what is, describe | `search_nodes` + `impact_analysis` |
| `impact` | impact, depends, breaks, affect | `impact_analysis` |
| `path` | path, between, connect, relationship | `find_path` (BFS) |
| `git_blame` | who, wrote, authored, changed | Git blame/history |
| `git_why` | why, introduced, added | Why-introduced analysis |
| `git_cochange` | cochange, changes with | Co-change analysis |
| `search` | (fallback) | `search_nodes` |

Architecture and summarize keywords get the highest priority (10) to avoid being misclassified as `explain` or `impact`.

---

## 11. MCP Server

**File:** `cartographer/mcp/server.py`

### Protocol

Uses **Model Context Protocol** (MCP SDK 1.27.2) with FastMCP on stdio transport. No HTTP, no auth — local only.

### Resources (3)

| URI | Description | Returns |
|---|---|---|
| `cartographer://repos` | List all indexed repositories | IDs, names, paths |
| `cartographer://repo/{name}` | Repository details + counts | Nodes, edges, embeddings |
| `cartographer://node/{node_id}` | Single node with metadata | Name, type, file, metadata JSON |

### Tools (8)

| Tool | Parameters | Description |
|---|---|---|
| `search` | query, repo?, node_type?, limit?, db? | Search graph nodes by name |
| `impact` | target, repo?, db? | What depends on target |
| `neighbors` | name, repo?, depth?, db? | BFS graph neighbors |
| `path` | from_name, to_name, max_depth?, db? | Shortest path BFS |
| `summarize` | repo?, db? | Repository statistics |
| `architecture` | repo?, detect?, db? | Detect/retrieve architecture |
| `similar` | target, repo?, limit?, db? | Semantic similarity |
| `ask` | query, repo?, limit?, db? | Natural language Q&A |

All tools return plain text formatted for LLM consumption.

---

## Database

### Location

Default: `~/.cartographer/index.db`. Configurable via `--db` flag or `CARTOGRAPHER_DB` environment variable.

### Storage

- SQLite with WAL (Write-Ahead Log) mode for concurrent reads
- Foreign keys enabled for referential integrity
- JSON metadata columns for flexible schema evolution
- Binary vector blobs for embeddings (384 floats × 4 bytes = 1536 bytes per vector)

### Performance

| Operation | Complexity | Bottleneck |
|---|---|---|
| Indexing | O(files × entities) | I/O (file reads) |
| Text search | O(nodes) | SQL LIKE scan |
| Traversal | O(edges^depth) | BFS on adjacency |
| Impact | O(edges) | Reverse edge scan |
| Architecture | O(nodes + edges) | Evidence scoring |
