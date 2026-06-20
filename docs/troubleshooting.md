# Troubleshooting

Common issues when using Cartographer and how to fix them.

---

## Installation

### `cartographer: command not found`

```bash
# Make sure you installed the package
pip install -e /path/to/cartographer

# Check pip installed it
pip list | grep cartographer

# Try running directly
python -m cartographer version
```

### `ModuleNotFoundError: No module named 'tree_sitter'`

Tree-sitter is installed as a dependency, but the pip package name may differ on your system:

```bash
pip install tree-sitter>=0.23,<1.0
```

### `Permission denied` when installing

```bash
# Install in user space instead of system-wide
pip install --user -e .

# Or use a virtual environment
python -m venv .venv
source .venv/bin/activate
pip install -e .
```

---

## Indexing

### `No module named 'tree_sitter_LANGUAGE'`

Tree-sitter grammar packages are loaded per-language. If you see this, the language-specific grammar hasn't been installed:

```bash
pip install tree-sitter-python tree-sitter-go tree-sitter-rust
# ... repeat for each language you need
```

The parser registry should auto-download grammars on demand. If it doesn't, installing manually fixes it.

### Slow indexing on large repositories

Cartographer parses source files in parallel across CPU cores using `ProcessPoolExecutor`. For repos with 10,000+ files:

- Indexing is **I/O bound** — an SSD helps significantly
- Watch for repositories that include generated files or vendored dependencies
- Consider adding patterns to `.cartographerignore` for directories you want to skip
- Indexing time is proportional to total entity count rather than file count

### `Warning: Failed to parse file X`

This is normal — some files may use syntax features not yet supported by the Tree-sitter grammar (e.g., very new language features, or unusual syntax). Parse errors are treated as warnings, not fatal. The rest of the repository is still indexed successfully.

### No entities found for a file

If a file is counted in "X files indexed" but shows 0 entities:

1. The language might not be supported (check the languages list in the output)
2. The file might be empty or contain only comments
3. The Tree-sitter grammar might have parsing issues for that specific file

### `Fatal: No parsers available`

No parsers could be loaded. Check that tree-sitter grammars are installed:

```bash
python -c "from tree_sitter import Language; print('tree-sitter OK')"
python -c "import tree_sitter_python as tsp; lang = tsp.language(); print('Python parser OK')"
```

### Files I don't want are being indexed

Use `.cartographerignore` in the repo root to skip specific files or directories:

```
# .cartographerignore
test/repos/*
vendor/*
*.pyc
build/
```

You can also use `.gitignore` — Cartographer respects root `.gitignore` patterns automatically.

---

## Search and Queries

### `No results found` even though the symbol exists

1. Check the database path: `cartographer --db /path/to/db ask "symbol"`
2. Make sure the repository was indexed: `cartographer summarize`
3. Try a partial match: `cartographer ask "part_of_name"`
4. Check the file was parsed by looking at the indexing output

### Semantic search returns no results

```bash
# You need to generate embeddings first
cartographer embed

# If that returns 0, the model needs to download
# First run downloads ~33MB model
# Check network connectivity if it hangs

# You can configure which model to use via env vars
export CARTOGRAPHER_EMBEDDING_MODEL=BAAI/bge-small-en-v1.5
export CARTOGRAPHER_EMBEDDING_BATCH_SIZE=256
```

### Query planner gives wrong intent

If `cartographer query "something"` runs the wrong analysis strategy:

- Be more specific: use "architecture" instead of "what is the architecture"
- Use the explicit command: `cartographer architecture --detect` instead of `query`
- Use verbose mode to see what intent was detected: `cartographer query -v "your question"`
- The intent detection is keyword-based — overly vague queries fall back to plain search

---

## Architecture Detection

### No layers detected

Architecture detection requires a minimum signal strength. If no layers are found:

- The repo might be too small (fewer than 10-20 files)
- File/directory naming might not follow conventional patterns
- Run with `--verbose` to see raw evidence: `cartographer architecture --detect -v`

### Framework not detected

Framework detection relies on fingerprinting during indexing:

1. Check that the framework's indicator files exist in the repository
2. Re-index to update fingerprints: `cartographer index /path/to/repo`
3. Framework detection uses file existence and regex matching on config files

### False positive framework

A framework might be falsely detected if:

- A config file like `requirements.txt` mentions it but it's not actually used
- Directory names incidentally match (e.g., a `routes/` directory that's not Express)

This is by design — the system favors false positives over false negatives. You can check confidence scores to gauge reliability.

---

## Git Commands

### `git index` times out

The default 60-second timeout for `git log` may not be enough for repos with 10,000+ commits:

```bash
# Index only the most recent commits
cartographer git index -n 1000

# Or use a smaller time range
```

### `No history found` even after `git index`

1. Make sure the correct repo path was used: `cartographer git index -p /path/to/repo`
2. Verify commits were indexed (the output shows how many commits and authors)
3. Check the symbol exists in the graph: `cartographer ask "symbol"`

### `failed to run git` errors

Cartographer needs `git` available on the PATH. Verify:

```bash
which git
git --version
```

---

## Database

### Database file not found

Default location is `~/.cartographer/index.db`. If using a custom path:

```bash
# Check if it exists
ls -la /path/to/your/index.db

# Set the env var
export CARTOGRAPHER_DB=/path/to/your/index.db

# Or use --db on every command
```

### Corrupted database

If you see `sqlite3.DatabaseError` or "database disk image is malformed":

```bash
# Delete and re-index
rm ~/.cartographer/index.db
cartographer index /path/to/repo
```

### Database size

The database size depends on entity count. Rough estimate:
- ~310 bytes per node (node + edges + metadata)
- Embeddings add ~1.5KB per entity (384 floats × 4 bytes)

To reduce size:
- Exclude vendored or generated directories from indexing (use `.cartographerignore`)
- Only embed the entity types you need (class, function, method, file, interface, enum)

---

## Embeddings

### Model download hangs

The `BAAI/bge-small-en-v1.5` model is downloaded from HuggingFace on first use (~33MB):

```bash
# Optionally configure the embedding model and batch size
export CARTOGRAPHER_EMBEDDING_MODEL=BAAI/bge-small-en-v1.5
export CARTOGRAPHER_EMBEDDING_BATCH_SIZE=256
```

If downloads are slow, check your network connection. The model only downloads once and is cached.

### Out of memory

The embedding model requires ~500MB RAM for inference. The similarity search loads all vectors into memory. For very large repos (>10,000 embeddable nodes, ~15MB of vectors), memory usage may be significant.

### Embedding quality

The `bge-small-en-v1.5` model is a lightweight general-purpose embedding model. For domain-specific code, results may be noisy. Consider:

- Re-indexing after code changes
- Using more specific search terms
- Combining semantic search with text search for better precision

---

## OpenCode Integration

### Tool not found by OpenCode

1. Check the tool configuration syntax in `opencode.json` or `~/.config/opencode/config.jsonc`
2. Verify the `cartographer` command works standalone
3. Check that the `args` parameter matches how OpenCode passes arguments

### MCP Server not connecting

If using the MCP server (`cartographer mcp`):

1. Make sure the server starts without errors
2. Check that your AI assistant is configured to connect to a local MCP server
3. Verify the `cartographer-mcp` command is on your PATH
4. If a stale PID file exists, remove it: `rm ~/.cartographer/mcp.pid`
5. `notifications/initialized` must be sent without a JSON-RPC `id` field (the VS Code extension does this correctly since v0.1.0)

### Graph shows 0 nodes in VS Code extension

If the interactive graph visualization shows "Showing 0 of N nodes":

1. **Entity type button clicked**: When opening the graph via the entity tree's inline "Graph" button, the entity type is extracted from the tree item. Make sure the entity type is recognized (directory, file, class, function, method, constant, interface, etc.)
2. **MCP fallback**: If the MCP connection fails, the extension falls back to CLI. Check the "Cartographer" output channel (`Ctrl+Shift+U`, select "Cartographer") for "MCP start failed" messages
3. **Database path**: Verify the database contains indexed data with `Cartographer: Database Info` command
4. **Reload window**: After installing a new version, use `Developer: Reload Window` to pick up changes

### Graph panel shows blank or loading indefinitely

If the graph panel opens but shows a blank screen or the loading spinner never goes away:

1. **MCP timeout**: The VS Code extension has a 15-second timeout on graph data requests. If MCP hangs, it falls back to CLI automatically. Check the output channel for "MCP graph_data failed, falling back" messages
2. **Large repository**: For repos with 50K+ nodes, the graph data query may be slow. The default limit is 400 nodes — increase or decrease via `.cartographer/config.json`:
   ```json
   {"graphLimit": 200}
   ```
3. **CLI fallback**: Test that CLI works directly: `cartographer graph-data -l 100`. If this works, the issue is MCP-related
4. **Deterministic layout**: Graph nodes are selected by degree-weighted hub sampling, ordered by node ID. The same project will always show the same nodes

### Extension: "[object Object]s Graph" title

If the graph panel title shows `[object Object]s Graph` instead of "Function Graph" etc., the entity type was not properly extracted from the tree view item. This was fixed in v0.1.0 — update the extension and reload VS Code.

### Output too long for LLM context

Use `--max-tokens` / `-m` to limit output:

```jsonc
{
  "command": "cartographer query -m 1500 --db /path/to/index.db",
}
```

### Slow response in OpenCode

The first query after a period of inactivity is slower due to SQLite cold cache. Subsequent queries are faster. Consider:

- Using `-m` to limit output
- Limiting traversal depth with `--depth 1`
- Using specific queries instead of broad ones
