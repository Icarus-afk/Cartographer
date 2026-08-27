# Troubleshooting

## Quick check

```bash
cartographer status --verbose
cartographer --json status
cartographer doctor
```

Shows `db_path, size, counts, repositories[], health[tree_sitter/fastembed/mcp], languages[31]`. If `repos==0` → `index`.

## Common issues

### No results / empty search

```bash
cartographer --json ask "MyClass"  # {"status":"empty","hint":"Try broader query"}
cartographer status                # is repo indexed?
cartographer repo list
cartographer --json search --help
```

- Check `repo` name: `list_repos` / `cartographer repo list` → pass `-r RepoName`.
- Try broader `query` or `node_type` filter (`-t class`).
- Empty `query` → `[]` by design (guard).

### Similar returns empty

- Needs `cartographer embed` first (generates 384-d `bge-small-en-v1.5` embeddings, chunked 500, retry 3×).
- Check `cartographer --json db info` → `embeddings: 0` → run `embed`.
- If model download fails → `CARTOGRAPHER_EMBEDDING_MODEL` env or check network/token.

### DB locked / busy

Storage uses `WAL` + `busy_timeout 5000` + 3× retry (`10s` timeout). If still:

```bash
cartographer db vacuum
lsof ~/.cartographer/index.db
# close other `cartographer watch` / `cartographer mcp start` if needed
```

Graph `build_graph` also retries `0.2*(attempt+1)`.

### Large repo / OOM

- Parser: `1MiB` truncate warning (`Parse warning: large file`), `2MiB` hard cap, `10MiB` skip (`Parse skipped large file`), `30s` per-file timeout → generic fallback.
- Discovery: `10MiB` skip, `b"\x00"` binary check, symlink loop guard.
- Embeddings: chunked `500`, valid-blob filter, `>100k` warning; search clamps `limit 1-100`.

```bash
# reduce scope via .cartographerignore or .gitignore
echo "node_modules/" >> .cartographerignore
cartographer index . --verbose
```

### Parse errors

```
Parse errors in foo.py: 2 error nodes
Parse warning: large file ...
Parse skipped binary file image.png
```

Single file never kills indexing (`per-file isolation` in `ThreadPool`). Check `cartographer --json index .` → `errors[]`.

Missing grammar (e.g. `tree_sitter_xyz` not installed) → `GenericParser` regex fallback, check `cartographer status` → `languages`.

### MCP not connecting

```bash
cartographer mcp start --verbose --db /tmp/test.db
# VS Code: check output channel "Cartographer"
# Opencode: check opencode.json → { "mcp": { "cartographer": { "command": ["cartographer-mcp"] } } }
# Claude Desktop: claude_desktop_config.json
```

DB path mirrors CLI: `--db` > `$CARTOGRAPHER_DB` > `CWD/.cartographer/config.json` → `.cartographer/data.db`. Verify with `cartographer --json status` vs `MCP status()`.

VS Code `ClientManager` tries MCP then CLI fallback; check `McpClient` `30s` timeout.

### Wrong repo returned

`search_nodes` defaults to `CWD/path` exact else largest `COUNT(nodes)`. Pass `-r` / `repo` param explicitly:

```bash
cartographer --json ask "Foo" --repo MyRepo
# MCP: search(query="Foo", repo="MyRepo")
```

### Git features say no history

```bash
cartographer git index --repo-path .
cartographer git blame src/main.py
```

Requires `cartographer git index` first; stores `commits/commit_files/commit_authors`.

### Port already in use

```bash
cartographer mcp stop
cat ~/.cartographer/mcp.pid
cartographer mcp start --port 8080
```

## Doctor output

```
Health:
  ✓ tree_sitter
  ✓ fastembed
  ✗ mcp
Parsers: 31 languages
```

`✗` → `pip install mcp` / `fastembed` / `tree-sitter-*`.

## Still stuck?

1. `cartographer --json status` → paste JSON
2. `cartographer --json index . --verbose` (or MCP `status` → `index`)
3. Check `~/.cartographer/index.db` size + `db_info`
4. File issue with `cartographer version` + `python --version`.
