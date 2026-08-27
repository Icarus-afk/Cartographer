# MCP — AI Assistant Integration

Cartographer is MCP-first (model context protocol). `cartographer-mcp` (stdio) exposes the knowledge graph to Opencode, Claude Desktop, Cursor, VS Code.

## Setup

**Opencode** (`opencode.json` already ships):

```json
{ "mcp": { "cartographer": { "type": "local", "command": ["cartographer-mcp"], "enabled": true } } }
```

**Claude Desktop** (`claude_desktop_config.json`):

```json
{ "mcpServers": { "cartographer": { "command": "cartographer-mcp", "args": [] } } }
```

**Cursor** (same as Claude).

**Manual:**

```bash
cartographer mcp start --verbose
cartographer mcp start --port 8080   # SSE + uvicorn
cartographer mcp stop
```

DB resolution mirrors CLI: `--db` > `$CARTOGRAPHER_DB` > `CWD/.cartographer/config.json` `dbPath` > `CWD/.cartographer/data.db` > `~/.cartographer/index.db`.

## Workflow for LLMs

FastMCP `instructions` tell the model:

> 1) `status()` → if `empty` → `index(path=".")`
> 2) `search` (exact), `ask` (NL), `file_summary` (90% savings)
> 3) `impact/neighbors/path` for deps
> 4) `architecture/similar/graph_data` for structure/semantics

```python
# Example session
status()                              # {"status":"empty","hint":"Run index(path=\".\")"}
index(path=".")                        # {"files":152,"duration_ms":2431}
search(query="UserService", limit=5)   # {"count":5,"results":[{type,name,file_path,score}]}
file_summary(file_path="src/auth/service.py")  # ~200 tokens vs 2000
impact(target="UserService")           # {"count":12,"dependents":[...]}
```

Always prefer `file_summary` over raw `read_file` — saves ~96k tokens / 5-turn session (~$0.48 GPT-4).

## Tools (20) + Resources (3)

| Tool | Params | Returns | When to use |
|---|---|---|---|
| `status` (`doctor`, `health`) | `db?` | `{db_path, exists, counts, repositories[], health[], languages[]}` | **First call** — is repo indexed? |
| `list_repos` | `db?` | `{repos:[{name,path,nodes,edges}],count}` | Discover available repos |
| `ensure_indexed` | `path=".", db?` | `{path,already_indexed,files,duration_ms}` | Idempotent ensure |
| `index` | `path=".", db?` | `{path,files,directories,duration_ms,languages,frameworks}` | Index before query |
| `search` | `query*, repo?, node_type?, limit 1-100, db?` | `{query,count,results:[{id,type,name,file_path,score}], human}` | Exact symbol/file lookup |
| `impact` | `target*, repo?, db?` | `{target,count,dependents:[{id,type,name,file_path,via_edge}]}` | Change risk |
| `neighbors` | `name*, repo?, depth 1-5, db?` | `{node,neighbors:[{type,name,depth}]}` | Local graph |
| `path` | `from_name*, to_name*, max_depth 1-10, db?` | `{from,to,hops,path:[{type,name,depth}]}` | `UserController → Database` |
| `summarize` | `repo?, db?` | `{name,path,total_nodes,total_edges,node_breakdown,edge_breakdown,top_files}` | Repo overview |
| `architecture` | `repo?, detect=false, db?` | `{repository,frameworks,layers,patterns,dependency_flow}` | Layers/patterns |
| `similar` | `target*, repo?, limit 1-100, db?` | `{target,count,results:[{type,name,similarity}]}` | Semantic (needs `embed`) |
| `ask` | `query*, repo?, limit 1-100, max_tokens 0, db?` | `{"answer":string}` (intent: search/explain/impact/path/…) | NL questions |
| `graph_data` | `repo?, limit 1-500, offset 0, dir?, expand_node_id?, db?` | `{total_nodes,total_edges,nodes[],edges[],directories[]}` | Viz |
| `context` | `repo?, top_n 1-50, max_tokens 200-8000, db?` | `{human, data:{summary,architecture,top_nodes}}` | One-call overview for LLM |
| `update_index` | `file_path*, db?` | `{nodes_added,nodes_removed,edges_added,file,language}` | After edit |
| `delete_file` | `file_path*, db?` | `{file,nodes_removed,embeddings_generated}` | After delete |
| `db_info` | `db?` | `{path,size,nodes,edges,embeddings,commits}` | Diagnostics |
| `file_summary` | `file_path*, repo?, db?` | `{file,entities:{class:[...]},imports,depended_on_by}` + `human` | Replace `read_file` |
| `doctor` / `health` | alias of `status` | — | — |

Resources:

- `cartographer://repos` — human list of repos
- `cartographer://repo/{name}` — repo stats
- `cartographer://node/{node_id}` — node details

All tools return `{"status":"ok|empty|error","data":{...},"human":"...","hint":"..."}` (unless `empty`/`error`). Limits clamped, empty `query`/`target` → `error` with example, `search` with no results → `hint: "Try broader query"`; `similar` with no embeddings → `hint: "Run cartographer embed"`.

Per-tool validation (`_clamp`), `tryJson` handling in VS Code (`editors/vscode/src/cartographer.ts` handles both human and JSON).

## VS Code Extension (MCP-first)

`ClientManager` per workspace folder → `McpClient.start("cartographer","mcp","start","--db",dbPath)` with `30s` tool timeout. Fallback `exec(["ask",...])` → parse JSON or human. Features: D3 graph (`graph_data` with `limit/offset/dir/expand`), incremental watch (batched 2s `update_index/delete_file`), multi-root, hover `300ms` + `60s` cache.

## CLI ↔ MCP parity

Every MCP tool maps to a CLI command: `cartographer --json <tool>` uses same validation and `hint`. Use `ensure_indexed` in MCP or `cartographer status || cartographer index .` in shell.

## Troubleshooting (MCP)

- `status` shows `exists:false` → `index(path="CWD")`
- `search` empty → check `repo` name via `list_repos`, try `node_type`
- `similar` empty → run `cartographer embed` in shell first
- DB locked → `storage/connection` has `WAL` + `busy_timeout 5000` + 3× retry
