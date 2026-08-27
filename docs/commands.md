# CLI Reference

Every command supports global flags before the subcommand: `--db PATH` (`$CARTOGRAPHER_DB`), `--json` (JSON envelope), `--verbose/-v`, `--quiet/-q`, `-h/--help`. JSON shape is always `{"status":"ok|empty|error","data":{...},"hint":"..."}` — use `--json` for LLM/automation.

Limits are clamped (`limit 1-100`, `depth 1-5`, `max_depth 1-10`, `graph_data limit 1-500`) and empty query returns `[]`.

## `cartographer status` / `doctor` / `health`

Health + indexing check — call first.

```bash
cartographer status
cartographer --json status
```

Output: `db_path, exists, size_bytes, counts {repos,nodes,edges,embeddings}, repositories[], health[{check,ok}], languages[]`. If `repos==0` → `hint: "Run index(path=\".\")"`.

`doctor` and `health` are aliases.

## `cartographer init [path] [--force]`

Init project DB + index. Warns if already indexed (`init . --force` to re-index).

```bash
cartographer init . --force
```

## `cartographer index [path]`

Index repo (idempotent). Parses, extracts references/schema, builds graph (chunked 1000, WAL retry).

```bash
cartographer index .
cartographer --json index /path/to/repo
```

JSON:

```json
{"status":"ok","path":"/abs/path","files":152,"directories":24,"duration_ms":2431,"languages":{"python":89},"frameworks":[{"name":"Django","confidence":0.98}],"entities":{"files_parsed":152,"classes":52}}
```

## `cartographer ask <query> [-t type] [-r repo] [-l 1-100] [-s] [-m max_tokens]`

Keyword search (for NL use `query`). Type priority (`controller/service/class/interface` higher), `name LIKE %query%`, scored by `name + type + ref_count + depth`.

```bash
cartographer ask "UserService" -t class --limit 5
cartographer --json ask "UserService" --limit 5
cartographer ask --semantic "auth middleware"   # needs embed
```

JSON: `{"status":"ok|empty","query","mode":"keyword|semantic","count":5,"results":[{id,type,name,file_path,score}],"hint":null}`

## `cartographer query <text> [-r repo] [-l 1-100] [-m max_tokens] [-v]`

Natural-language router (9 intents: `architecture|summarize|explain|impact|path|search|git_blame|git_why|git_cochange`). Delegates to `summarize/explain/impact/path/architecture/search`.

```bash
cartographer query "what is the architecture?" 
cartographer --json query "explain Preprocessor" --limit 10
```

## `cartographer impact <target> [-r repo] [-m max_tokens]`

Reverse deps (transitive `target_id` walk).

```bash
cartographer impact UserService
cartographer --json impact src/auth/service.py
```

JSON: `{"status":"ok","target","count":12,"dependents":[{id,type,name,file_path,via_edge}], "hint":null}`. Hint if empty: `try search`.

## `cartographer neighbors <name> [-r repo] [-d 1-5] [-m max_tokens]`

Graph traversal (DFS).

```bash
cartographer neighbors UserService -d 2
cartographer --json neighbors UserService --depth 2
```

JSON: `{"status":"ok","node":{id,type,name},"depth":2,"count":20,"neighbors":[...]}`

## `cartographer path <from> <to> [--max-depth 1-10] [-r repo] [-m max_tokens]`

BFS shortest path.

```bash
cartographer path UserController Database
cartographer --json path UserController Database --max-depth 5
```

JSON: `{"status":"ok|empty","from","to","hops":4,"path":[{id,type,name,file_path,depth}]}`

## `cartographer summarize [-r repo] [-m max_tokens]`

Repo overview: `total_nodes/edges`, `node_breakdown` / `edge_breakdown`, `top_files`, `top_classes`.

```bash
cartographer summarize
cartographer --json summarize
```

JSON: `{"status":"ok","summary":{name,path,total_nodes,total_edges,node_breakdown,edge_breakdown,top_files}}`

## `cartographer context [--top-n 10] [--max-tokens 1500] [-r repo]`

Compressed context package (`build_context_package`) for LLMs.

```bash
cartographer context --top-n 20 --max-tokens 1500
cartographer --json context --top-n 20   # JSON {summary,architecture,top_nodes}
```

## `cartographer architecture [--detect] [--verbose] [-r repo]`

Detect caches to `architecture` table. `--detect` writes, without reads cached. Shows `frameworks` (`django/rails/spring_boot/flutter/dart/...`), `layers` (`controller/business/data/...`), `patterns` (`MVC/layered/clean/hexagonal/repository`), `dependency_flow`, `domains`.

```bash
cartographer architecture --detect --verbose
cartographer --json architecture --detect
```

## `cartographer embed [-r repo]`

Generate `bge-small-en-v1.5` 384-d embeddings (chunked 500, batch 256, 3× retry, valid-blob filter, `parallelism 0`). Idempotent.

```bash
cartographer embed
cartographer --json embed
```

## `cartographer similar <target> [-r repo] [-l 1-100]`

Hybrid semantic search (cosine + `+0.1*overlap` when top <0.35, filter <0.15). Requires `embed`.

```bash
cartographer similar "error handling middleware"
cartographer --json similar "auth middleware" --limit 10
```

## `cartographer file-summary <path> [-r repo]`

~200 tokens vs 2000 for full file: entities by type, `IMPORTS`, `DEPENDED_ON_BY`, `INHERITS`.

```bash
cartographer file-summary src/auth/service.py
```

## `cartographer graph-data [-r repo] [-l 80] [-o offset] [-d dir] [--expand-node-id N]`

JSON for viz (always JSON, even without `--json`).

```bash
cartographer graph-data --limit 80 --dir src/ --expand-node-id 123
```

Returns `{total_nodes,total_edges,node_types,nodes[],edges[],directories[]}`. Hubs via `degree` CTE (`hub_count=max(5,limit/8)`), pagination `offset`, `dir` filter.

## `cartographer watch [path] [-v]`

Incremental `update_index`/`delete_file` on save/rename/delete (all 31 langs + `Dockerfile/Makefile`). Needs `watchdog`. VS Code does this automatically.

```bash
cartographer watch .
```

## `cartographer update-index <file>`

Single-file re-parse + `update_file_in_graph` + `generate_embeddings` for changed nodes.

```bash
cartographer update-index src/main.py
```

## `cartographer delete-file <file>`

Delete `nodes`/`edges`/`embeddings` for file.

```bash
cartographer delete-file src/removed.py
```

## `cartographer git *`

```bash
cartographer git index --repo-path . --max-count 500
cartographer git blame Preprocessor
cartographer git why src/main.py
cartographer git cochange src/config.py
cartographer git author "Jane Doe"
cartographer git authors --limit 20
```

## `cartographer repo list` / `repo remove <name> [--yes]`

Multi-repo DB management.

## `cartographer db info` / `db vacuum`

`db info` shows `size, repos, nodes, edges, embeddings, commits, per-repo`; `vacuum` reclaims space.

## `cartographer mcp start [--db PATH] [--port N] [--verbose] [--log-file PATH]`

MCP stdio (default) or SSE (`--port`). Uses `mcp` `FastMCP`, pid file `~/.cartographer/mcp.pid`.

## `cartographer version`

```bash
cartographer --json version  # {"status":"ok","version":"0.1.0"}
```

## Common patterns

```bash
# LLM: check, index, search
cartographer --json status || cartographer --json index . && cartographer --json ask "UserService"

# Watch + embeddings
cartographer index . && cartographer embed && cartographer architecture --detect
```
