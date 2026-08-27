from __future__ import annotations

import json
import logging
import sqlite3
from pathlib import Path

from mcp.server.fastmcp import FastMCP

from cartographer.architecture.engine import detect_architecture, get_architecture
from cartographer.embedding.engine import find_similar, similarity_search
from cartographer.ingestion.engine import index_repository
from cartographer.query.engine import execute_query
from cartographer.retrieval.searcher import search_nodes
from cartographer.retrieval.summarizer import generate_summary
from cartographer.retrieval.traversal import (
    _resolve_target,
    find_path,
    get_neighbors,
    impact_analysis,
)

logger = logging.getLogger(__name__)

DEFAULT_DB = Path.home() / ".cartographer" / "index.db"

_CUSTOM_DB_PATH: Path | None = None
_mcp: FastMCP | None = None


def mcp() -> FastMCP:
    global _mcp
    if _mcp is None:
        _mcp = FastMCP("Cartographer", instructions="""
Cartographer — Repository Intelligence Operating System.

Workflow for LLMs:
1. Call status (or summarize) to check if repo is indexed. If empty, call index with path=".".
2. Use search for keyword lookup, ask for natural language questions, file_summary for compressed file reads (90% token savings vs reading files).
3. Use impact/neighbors/path for dependency analysis.
4. Use architecture for high-level structure, similar for semantic search (requires embed), graph_data for visualization.
5. All tools support --json style structured output via JSON envelope: {"status":"ok","data":{...}}.

Token savings: file_summary ~200 tokens vs 2000 for full file; summarize ~200 vs 60k. Prefer cartographer tools over raw file reads.
""")
    return _mcp


def _db(db_str: str | None) -> Path:
    global _CUSTOM_DB_PATH
    if db_str:
        return Path(db_str)
    if _CUSTOM_DB_PATH is not None:
        return _CUSTOM_DB_PATH
    # Per-project config like CLI: .cartographer/config.json in CWD
    try:
        cfg_path = Path.cwd() / ".cartographer" / "config.json"
        if cfg_path.exists():
            import json as _j
            cfg = _j.loads(cfg_path.read_text())
            cfg_db = cfg.get("dbPath", "")
            if cfg_db:
                p = Path(cfg_db)
                return p if p.is_absolute() else Path.cwd() / cfg_db
            return Path.cwd() / ".cartographer" / "data.db"
    except Exception:
        pass
    # also check CARTOGRAPHER_DB env
    import os as _os
    if _os.environ.get("CARTOGRAPHER_DB"):
        return Path(_os.environ["CARTOGRAPHER_DB"])
    return DEFAULT_DB


def _get_conn(db: str | None = None) -> sqlite3.Connection:
    conn = sqlite3.connect(str(_db(db)))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA cache_size=-8000")
    conn.execute("PRAGMA temp_store=MEMORY")
    conn.execute("PRAGMA busy_timeout=5000")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def _ok(data, hint: str | None = None) -> str:
    payload = {"status": "ok", "data": data}
    if hint:
        payload["hint"] = hint
    return json.dumps(payload, ensure_ascii=False, indent=2)


def _empty(message: str, hint: str | None = None) -> str:
    payload = {"status": "empty", "message": message}
    if hint:
        payload["hint"] = hint
    return json.dumps(payload, ensure_ascii=False, indent=2)


def _error(message: str, hint: str | None = None) -> str:
    payload = {"status": "error", "error": message}
    if hint:
        payload["hint"] = hint
    return json.dumps(payload, ensure_ascii=False, indent=2)


def _clamp(v: int, lo: int, hi: int, default: int) -> int:
    try:
        iv = int(v)
    except Exception:
        return default
    return max(lo, min(iv, hi))


@mcp().resource(
    "cartographer://repos",
    description="List all indexed repositories",
)
def get_repos() -> str:
    conn = _get_conn()
    rows = conn.execute("SELECT id, name, path FROM repositories ORDER BY name").fetchall()
    conn.close()
    if not rows:
        return "No repositories indexed. Run cartographer index first."
    lines = ["Indexed repositories:"]
    for r in rows:
        lines.append(f"  [{r['id']}] {r['name']}  ({r['path']})")
    return "\n".join(lines)


@mcp().resource(
    "cartographer://repo/{name}",
    description="Get repository details and statistics",
)
def get_repo(name: str) -> str:
    conn = _get_conn()
    row = conn.execute(
        "SELECT id, name, path FROM repositories WHERE name = ?", (name,)
    ).fetchone()
    if not row:
        conn.close()
        return f"No repository found: {name}. Try cartographer://repos or list_repos tool."
    node_count = conn.execute(
        "SELECT COUNT(*) FROM nodes WHERE repository_id = ?", (row["id"],)
    ).fetchone()[0]
    edge_count = conn.execute(
        "SELECT COUNT(*) FROM edges WHERE repository_id = ?", (row["id"],)
    ).fetchone()[0]
    embed_count = conn.execute(
        "SELECT COUNT(*) FROM embeddings emb"
        " JOIN nodes n ON emb.node_id = n.id"
        " WHERE n.repository_id = ?",
        (row["id"],),
    ).fetchone()[0]
    conn.close()
    return (
        f"Repository: {row['name']}\n"
        f"  Path: {row['path']}\n"
        f"  Nodes: {node_count}\n"
        f"  Edges: {edge_count}\n"
        f"  Embeddings: {embed_count}"
    )


@mcp().resource(
    "cartographer://node/{node_id}",
    description="Get details of a specific node by ID",
)
def get_node(node_id: str) -> str:
    try:
        nid = int(node_id)
    except ValueError:
        return _error(f"Invalid node_id: {node_id}", "node_id must be an integer")
    conn = _get_conn()
    row = conn.execute(
        """SELECT n.id, n.name, n.node_type, n.file_path, n.metadata_json, r.name as repo
           FROM nodes n
           JOIN repositories r ON n.repository_id = r.id
           WHERE n.id = ?""",
        (nid,),
    ).fetchone()
    conn.close()
    if not row:
        return _error(f"No node with id {node_id}", "Try search to find node ids")
    lines = [f"Node [{row['id']}]: {row['name']} ({row['node_type']})"]
    lines.append(f"  Repository: {row['repo']}")
    lines.append(f"  File: {row['file_path'] or '(root)'}")
    if row["metadata_json"]:
        try:
            meta = json.loads(row["metadata_json"])
            if meta:
                lines.append(f"  Metadata: {json.dumps(meta, indent=2)}")
        except Exception:
            pass
    return "\n".join(lines)


# ── New: status/doctor/health ──

@mcp().tool(
    name="status",
    description="Show indexing status, DB health, and diagnostics. Call this FIRST to check if a repo is indexed. Returns repos, node/edge counts, DB size, languages, and health checks. Use before search/ask if unsure. Example: status() -> check if empty -> then index(path=\".\")",
)
def status_tool(
    db: str | None = None,
) -> str:
    import os
    import importlib.util
    db_path = _db(db)
    data: dict = {"db_path": str(db_path), "exists": db_path.exists()}
    if not db_path.exists():
        return _empty("DB not initialized (no file)", "Run index(path=\".\") to index current repo")
    try:
        size = db_path.stat().st_size
        data["size_bytes"] = size
        data["size_human"] = f"{size/1024/1024:.1f}MB" if size>1024*1024 else f"{size/1024:.1f}KB"
    except Exception:
        pass
    conn = _get_conn(db)
    try:
        repo_count = conn.execute("SELECT COUNT(*) FROM repositories").fetchone()[0]
        node_count = conn.execute("SELECT COUNT(*) FROM nodes").fetchone()[0]
        edge_count = conn.execute("SELECT COUNT(*) FROM edges").fetchone()[0]
        embed_count = conn.execute("SELECT COUNT(*) FROM embeddings").fetchone()[0]
        per_repo = conn.execute("SELECT name, path FROM repositories ORDER BY name").fetchall()
        data.update({
            "repositories": [{"name": r[0], "path": r[1]} for r in per_repo],
            "counts": {"repos": repo_count, "nodes": node_count, "edges": edge_count, "embeddings": embed_count},
            "status": "ok" if repo_count>0 else "empty",
        })
        if repo_count==0:
            data["hint"] = "Run index(path=\".\") to index current repo"
        # health
        checks=[]
        for mod,label in [("tree_sitter","tree-sitter"),("fastembed","fastembed"),("mcp","mcp")]:
            checks.append({"check":label,"ok": importlib.util.find_spec(mod) is not None})
        data["health"]=checks
        try:
            from cartographer.parser.registry import supported_languages
            data["languages"]=[l.value for l in supported_languages()]
        except Exception:
            pass
    finally:
        conn.close()
    return _ok(data, None if data.get("counts",{}).get("repos",0)>0 else "No repos indexed — call index(path=\".\")")


@mcp().tool(
    name="doctor",
    description="Alias for status — diagnose setup and suggest fixes. Use when things seem broken.",
)
def doctor_tool(db: str | None = None) -> str:
    return status_tool(db)


@mcp().tool(
    name="health",
    description="Alias for status — health check for automation.",
)
def health_tool(db: str | None = None) -> str:
    return status_tool(db)


@mcp().tool(
    name="list_repos",
    description="List all indexed repositories (tool version of cartographer://repos). Returns JSON array of {name, path, nodes, edges}. Use to discover available repos before querying.",
)
def list_repos_tool(db: str | None = None) -> str:
    conn = _get_conn(db)
    rows = conn.execute(
        """SELECT r.name, r.path,
                  (SELECT COUNT(*) FROM nodes WHERE repository_id=r.id) as nodes,
                  (SELECT COUNT(*) FROM edges WHERE repository_id=r.id) as edges
           FROM repositories r ORDER BY r.name"""
    ).fetchall()
    conn.close()
    repos=[{"name": r[0], "path": r[1], "nodes": r[2], "edges": r[3]} for r in rows]
    if not repos:
        return _empty("No repositories indexed", "Run index(path=\".\")")
    return _ok({"repos": repos, "count": len(repos)})


@mcp().tool(
    name="ensure_indexed",
    description="Ensure a repository is indexed, indexing it if needed. Idempotent. Use when unsure if repo is indexed. Returns status and whether indexing was performed. Example: ensure_indexed(path=\"/path/to/repo\")",
)
def ensure_indexed_tool(path: str = ".", db: str | None = None) -> str:
    from pathlib import Path as P
    p = P(path).resolve()
    if not p.is_dir():
        return _error(f"Path is not a directory: {path}", "Provide a valid repo path")
    conn = _get_conn(db)
    row = conn.execute("SELECT id FROM repositories WHERE path = ?", (str(p),)).fetchone()
    conn.close()
    if row:
        return _ok({"path": str(p), "already_indexed": True, "message": "Already indexed"})
    result = index_repository(str(p), db_path=_db(db))
    if not result.success and not result.manifest:
        return _error(f"Indexing failed: {result.errors}", "Check path and permissions")
    return _ok({
        "path": str(p),
        "already_indexed": False,
        "files": result.manifest.total_files if result.manifest else 0,
        "duration_ms": result.duration_ms,
        "errors": result.errors,
    }, hint="Now you can use search/summarize/etc.")


@mcp().tool(
    name="search",
    description="Keyword search for nodes (classes, functions, files) by name. Use for exact symbol lookup. For questions use 'ask'. Params: query (required, e.g. 'UserService'), repo (optional, filter by repo name), node_type (optional, e.g. 'class','function','file'), limit (1-100, default 20). Returns JSON {results:[{id,type,name,file_path,score}]}. Example: search(query=\"UserService\", limit=10)",
)
def search(
    query: str,
    repo: str | None = None,
    node_type: str | None = None,
    limit: int = 20,
    db: str | None = None,
) -> str:
    if not query or not query.strip():
        return _error("query is required and cannot be empty", "Example: search(query=\"UserService\")")
    limit = _clamp(limit, 1, 100, 20)
    try:
        results = search_nodes(query.strip(), _db(db), repo, node_type, limit)
    except Exception as e:
        logger.exception("search failed")
        return _error(f"Search failed: {e}", "Check status() and ensure repo is indexed")
    if not results:
        return _empty(f"No results for '{query}'", "Try broader query, check repo name, or run status() to verify indexing")
    # Return both human and JSON: JSON envelope with human hint
    data={"query":query,"repo":repo,"node_type":node_type,"count":len(results),"results":results}
    human=[f"Found {len(results)} result(s) for '{query}':"]
    for r in results[:5]:
        human.append(f"  [{r['type']}] {r['name']}" + (f" — {r['file_path']}" if r.get("file_path") else ""))
    if len(results)>5:
        human.append(f"  ... and {len(results)-5} more (see JSON data)")
    payload={"status":"ok","human": "\n".join(human),"data": data}
    return json.dumps(payload, ensure_ascii=False, indent=2)


@mcp().tool(
    name="impact",
    description="Analyze what depends on a file, class, or function (reverse dependencies). Use to assess change risk. Params: target (required, file path or symbol name, e.g. 'UserService' or 'src/models.py'), repo (optional). Returns JSON {target, count, dependents:[{id,type,name,file_path,via_edge}]}. Example: impact(target=\"UserService\")",
)
def impact(
    target: str,
    repo: str | None = None,
    db: str | None = None,
) -> str:
    if not target or not target.strip():
        return _error("target is required", "Example: impact(target=\"UserService\")")
    try:
        results = impact_analysis(target.strip(), _db(db), repo)
    except Exception as e:
        return _error(f"Impact failed: {e}")
    if not results:
        return _empty(f"No dependents for '{target}'", "Try search to find exact symbol name, or check file path")
    data={"target":target,"count":len(results),"dependents":results}
    human=[f"Impact for '{target}': {len(results)} dependents"]
    by_edge: dict[str,int]={}
    for r in results:
        by_edge[r.get("via_edge","UNKNOWN")] = by_edge.get(r.get("via_edge","UNKNOWN"),0)+1
    for k,v in sorted(by_edge.items(), key=lambda x:-x[1]):
        human.append(f"  {k}: {v}")
    return json.dumps({"status":"ok","human":"\n".join(human),"data":data}, ensure_ascii=False, indent=2)


@mcp().tool(
    name="neighbors",
    description="Show neighboring nodes of a class/function/file (graph traversal). Params: name (required, symbol or file), repo (optional), depth (1-5, default 2). Returns JSON {node, neighbors}. Example: neighbors(name=\"UserService\", depth=2)",
)
def neighbors(
    name: str,
    repo: str | None = None,
    depth: int = 2,
    db: str | None = None,
) -> str:
    if not name or not name.strip():
        return _error("name is required", "Example: neighbors(name=\"UserService\")")
    depth = _clamp(depth,1,5,2)
    conn = _get_conn(db)
    node = _resolve_target(conn, name.strip(), repo)
    conn.close()

    if not node:
        return _empty(f"No node matching '{name}'", "Try search(query=\"{name}\") to find correct name")

    try:
        results = get_neighbors(node["id"], _db(db), depth)
    except Exception as e:
        return _error(f"Neighbors failed: {e}")
    data={"node":node,"depth":depth,"count":len(results),"neighbors":results}
    human=[f"Neighbors of [{node['type']}] {node['name']}: {len(results)} nodes at depth {depth}"]
    for r in results:
        if r["depth"]==0: continue
        human.append(f"{'  '*r['depth']}[{r['type']}] {r['name']}")
    return json.dumps({"status":"ok","human":"\n".join(human),"data":data}, ensure_ascii=False, indent=2)


@mcp().tool(
    name="path",
    description="Find the shortest path between two nodes. Params: from_name, to_name (required), max_depth (1-10, default 5), repo/db optional. Returns JSON {path:[{id,type,name,file_path,depth}]}. Example: path(from_name=\"UserController\", to_name=\"Database\")",
)
def find_path_between(
    from_name: str,
    to_name: str,
    max_depth: int = 5,
    db: str | None = None,
) -> str:
    if not from_name or not to_name:
        return _error("from_name and to_name are required")
    max_depth=_clamp(max_depth,1,10,5)
    try:
        results = find_path(from_name.strip(), to_name.strip(), _db(db), max_depth=max_depth)
    except Exception as e:
        return _error(f"Path failed: {e}")
    if not results:
        return _empty(f"No path between '{from_name}' and '{to_name}'", "Verify names via search; try larger max_depth")
    data={"from":from_name,"to":to_name,"max_depth":max_depth,"hops":len(results),"path":results}
    human=[f"Path {len(results)} hops from '{from_name}' to '{to_name}':"]
    for r in results:
        arrow=" → " if r["depth"]>0 else "   "
        human.append(f"  {arrow}[{r['type']}] {r['name']}" + (f" — {r['file_path']}" if r.get("file_path") else ""))
    return json.dumps({"status":"ok","human":"\n".join(human),"data":data}, ensure_ascii=False, indent=2)


@mcp().tool(
    name="summarize",
    description="Generate a repository summary (nodes, edges, breakdown). Params: repo (optional, defaults to largest repo), db optional. Returns JSON {name, path, total_nodes, total_edges, node_breakdown, edge_breakdown, top_files}. Use for repo overview before diving deeper. Example: summarize(repo=\"my-repo\")",
)
def summarize(
    repo: str | None = None,
    db: str | None = None,
) -> str:
    try:
        summary = generate_summary(_db(db), repo)
    except Exception as e:
        return _error(f"Summarize failed: {e}")
    if not summary:
        return _empty("No repository found", "Run index(path=\".\") first; check status()")
    return _ok(summary, hint="Use search/file_summary for details; architecture for layers")


@mcp().tool(
    name="architecture",
    description="Detect or retrieve architecture layers and patterns. Params: repo (optional), detect (bool, default false — set true to re-detect and write to DB), db optional. Returns JSON {repository, frameworks, layers, patterns, dependency_flow}. Example: architecture(detect=true)",
)
def architecture(
    repo: str | None = None,
    detect: bool = False,
    db: str | None = None,
) -> str:
    try:
        if detect:
            result = detect_architecture(_db(db), repo)
            if "error" in result:
                return _error(result["error"], "Run index() first")
            return _ok(result)
        result = get_architecture(_db(db), repo)
        if "error" in result:
            return _error(result["error"], "Run architecture(detect=true) to detect")
        if not result.get("layers"):
            return _empty("No architecture data", "Run architecture(detect=true)")
        return _ok(result)
    except Exception as e:
        return _error(f"Architecture failed: {e}")


@mcp().tool(
    name="similar",
    description="Find semantically similar nodes using vector embeddings. Requires `embed` first (via CLI `cartographer embed`). Params: target (symbol or free text), repo, limit (1-100). Returns JSON {target, results:[{id,type,name,file_path,similarity}]}. Example: similar(target=\"auth middleware\", limit=10)",
)
def similar(
    target: str,
    repo: str | None = None,
    limit: int = 20,
    db: str | None = None,
) -> str:
    if not target or not target.strip():
        return _error("target is required")
    limit=_clamp(limit,1,100,20)
    db_path = _db(db)
    conn = _get_conn(db)
    node = _resolve_target(conn, target.strip(), repo)
    conn.close()

    try:
        if node:
            results = find_similar(db_path, node["id"], limit)
        else:
            results = similarity_search(db_path, target.strip(), limit, repo)
    except Exception as e:
        return _error(f"Similar failed: {e}")

    if not results:
        return _empty(f"No similar nodes for '{target}'", "Run `cartographer embed` first (CLI) or try keyword search")
    data={"target":target,"count":len(results),"results":results}
    human=[f"Similar to '{target}': {len(results)} results"]
    for r in results[:3]:
        human.append(f"  [{r['type']}] {r['name']} (score {r.get('similarity','?')})")
    return json.dumps({"status":"ok","human":"\n".join(human),"data":data}, ensure_ascii=False, indent=2)


@mcp().tool(
    name="ask",
    description="Ask a natural language question about the repository (intent-aware). Handles: 'what is architecture', 'explain X', 'what depends on X', 'summarize', etc. Params: query (required, e.g. 'explain UserService'), repo, limit (1-100), max_tokens (0=no limit). Returns answer string. Example: ask(query=\"What does UserService do?\")",
)
def ask(
    query: str,
    repo: str | None = None,
    limit: int = 20,
    max_tokens: int = 0,
    db: str | None = None,
) -> str:
    if not query or not query.strip():
        return _error("query is required", "Example: ask(query=\"What is the architecture?\")")
    limit=_clamp(limit,1,100,20)
    max_tokens=max(0, int(max_tokens) if isinstance(max_tokens,int) else 0)
    try:
        result = execute_query(query.strip(), _db(db), repo, limit, max_tokens)
        # execute_query returns string; wrap in JSON envelope for LLM
        return _ok({"query":query,"answer":result})
    except Exception as e:
        return _error(f"Ask failed: {e}")


@mcp().tool(
    name="graph_data",
    description="Export graph data as JSON for visualization. Supports pagination and filtering. Params: repo, limit (1-500), offset (pagination), dir (filter by directory prefix e.g. 'src/'), expand_node_id (expand neighbors of node). Returns JSON {nodes, edges, total_nodes, total_edges, directories}. Example: graph_data(limit=80, dir=\"src/\")",
)
def graph_data(
    repo: str | None = None,
    limit: int = 80,
    offset: int = 0,
    dir: str | None = None,
    expand_node_id: int | None = None,
    db: str | None = None,
) -> str:
    import json as _json
    limit=_clamp(limit,1,500,80)
    offset=max(0, int(offset) if isinstance(offset,int) else 0)
    conn = _get_conn(db)

    if repo:
        row = conn.execute(
            "SELECT id FROM repositories WHERE name = ?", (repo,)
        ).fetchone()
    else:
        row = conn.execute(
            "SELECT id FROM repositories ORDER BY id DESC LIMIT 1"
        ).fetchone()

    if not row:
        conn.close()
        return _error("Repository not found", "Run status() or list_repos() to see available repos")

    repo_id = row[0]

    type_counts = dict(conn.execute(
        """SELECT node_type, COUNT(*) as cnt FROM nodes
           WHERE repository_id = ? GROUP BY node_type ORDER BY cnt DESC""",
        (repo_id,),
    ).fetchall())

    all_ids: list[int] = []

    if expand_node_id is not None:
        try:
            expand_node_id=int(expand_node_id)
        except Exception:
            conn.close()
            return _error("expand_node_id must be integer")
        all_ids = _graph_expand_node(conn, repo_id, expand_node_id, limit)

    else:
        all_ids = _graph_hub_nodes(conn, repo_id, limit, offset, dir)

    if not all_ids:
        conn.close()
        empty = {"nodes": [], "edges": [],
                 "total_nodes": 0, "total_edges": 0, "node_types": type_counts}
        return _ok(empty)

    ph = ",".join("?" for _ in all_ids)
    nodes_list = conn.execute(
        f"SELECT id, name, node_type, file_path FROM nodes WHERE id IN ({ph}) ORDER BY id",
        (*all_ids,),
    ).fetchall()

    edges = conn.execute(
        f"""SELECT source_node_id, target_node_id, edge_type FROM edges
            WHERE repository_id = ?
            AND source_node_id IN ({ph})
            AND target_node_id IN ({ph})
            ORDER BY source_node_id, target_node_id""",
        (repo_id, *all_ids, *all_ids),
    ).fetchall()

    total_nodes = conn.execute(
        "SELECT COUNT(*) FROM nodes WHERE repository_id = ?", (repo_id,)
    ).fetchone()[0]
    total_edges = conn.execute(
        "SELECT COUNT(*) FROM edges WHERE repository_id = ?", (repo_id,)
    ).fetchone()[0]

    dir_rows = conn.execute(
        """SELECT
            CASE WHEN INSTR(SUBSTR(file_path, 1, LENGTH(file_path) - 1), '/') > 0
                 THEN SUBSTR(file_path, 1, LENGTH(file_path) - 1 -
                      INSTR(SUBSTR(file_path, 1, LENGTH(file_path) - 1), '/'))
                 ELSE '/' END as dir,
            COUNT(*) as cnt
        FROM nodes
        WHERE repository_id = ? AND node_type != 'directory' AND file_path IS NOT NULL
        GROUP BY dir
        ORDER BY cnt DESC""",
        (repo_id,),
    ).fetchall()
    dirs = [(r[0], r[1]) for r in dir_rows]

    conn.close()
    data={
        "total_nodes": total_nodes,
        "total_edges": total_edges,
        "node_types": type_counts,
        "nodes": [{"id": n[0], "name": n[1], "type": n[2], "file_path": n[3]} for n in nodes_list],
        "edges": [{"source": e[0], "target": e[1], "type": e[2]} for e in edges],
        "directories": [{"path": p, "count": c} for p, c in dirs],
    }
    return _ok(data)


def _graph_expand_node(
    conn: sqlite3.Connection, repo_id: int, node_id: int, limit: int,
) -> list[int]:
    ids: list[int] = [node_id]
    rows = conn.execute(
        """SELECT DISTINCT
               CASE WHEN e.source_node_id = ? THEN e.target_node_id
                    ELSE e.source_node_id END as neighbor_id
           FROM edges e
           WHERE e.repository_id = ?
           AND (e.source_node_id = ? OR e.target_node_id = ?)
           LIMIT ?""",
        (node_id, repo_id, node_id, node_id, limit - 1),
    ).fetchall()
    for r in rows:
        if r[0] not in ids and len(ids) < limit:
            ids.append(r[0])
    return ids


def _graph_hub_nodes(
    conn: sqlite3.Connection, repo_id: int, limit: int, offset: int,
    dir_filter: str | None,
) -> list[int]:
    dir_clause = ""
    dir_params: list = []
    if dir_filter:
        dir_clause = "AND n.file_path LIKE ?"
        dir_params.append(dir_filter + "%")

    hub_count = max(5, limit // 8)
    seeds = conn.execute(
        f"""WITH degree AS (
                SELECT n.id as nid, COUNT(e.rowid) as deg
                FROM nodes n
                LEFT JOIN edges e ON e.repository_id = n.repository_id
                    AND (e.source_node_id = n.id OR e.target_node_id = n.id)
                WHERE n.repository_id = ? {dir_clause}
                GROUP BY n.id
            )
            SELECT nid FROM degree
            ORDER BY deg DESC, nid
            LIMIT ? OFFSET ?""",
        (repo_id, *dir_params, hub_count, offset),
    ).fetchall()

    all_ids: list[int] = [s[0] for s in seeds]
    if seeds:
        seed_ph = ",".join("?" for _ in seeds)
        rows = conn.execute(
            f"""SELECT DISTINCT n.id FROM nodes n
                JOIN edges e ON (e.source_node_id = n.id OR e.target_node_id = n.id)
                WHERE n.repository_id = ?
                AND (e.source_node_id IN ({seed_ph}) OR e.target_node_id IN ({seed_ph}))
                AND n.id NOT IN ({seed_ph})
                ORDER BY n.id
                LIMIT ?""",
            (repo_id, *[s[0] for s in seeds], *[s[0] for s in seeds], *[s[0] for s in seeds], limit - len(all_ids)),
        ).fetchall()
        for r in rows:
            if r[0] not in all_ids and len(all_ids) < limit:
                all_ids.append(r[0])

    if all_ids and len(all_ids) < limit:
        ph = ",".join("?" for _ in all_ids)
        remaining = conn.execute(
            f"""WITH degree AS (
                    SELECT n.id as nid, COUNT(e.rowid) as deg
                    FROM nodes n
                    LEFT JOIN edges e ON e.repository_id = n.repository_id
                        AND (e.source_node_id = n.id OR e.target_node_id = n.id)
                    WHERE n.repository_id = ? {dir_clause}
                        AND n.id NOT IN ({ph})
                    GROUP BY n.id
                )
                SELECT nid FROM degree
                ORDER BY deg DESC, nid
                LIMIT ?""",
            (repo_id, *dir_params, *all_ids, limit - len(all_ids)),
        ).fetchall()
        for r in remaining:
            all_ids.append(r[0])

    return all_ids[:limit]


@mcp().tool(
    name="index",
    description="Index a repository. Run before querying a new repo. Idempotent — safe to call multiple times. Params: path (default '.'), db (optional). Returns JSON {files, directories, duration_ms}. Example: index(path=\"/path/to/repo\") or index(path=\".\")",
)
def index_repo(
    path: str = ".",
    db: str | None = None,
) -> str:
    if not path:
        path="."
    try:
        result = index_repository(path, db_path=_db(db))
    except Exception as e:
        return _error(f"Indexing failed: {e}")
    if not result.success:
        return _error(f"Indexing failed for {path}: {result.errors}", "Check path exists and is readable")
    manifest = result.manifest
    data={
        "path": str(Path(path).resolve()),
        "files": manifest.total_files if manifest else 0,
        "directories": manifest.total_dirs if manifest else 0,
        "duration_ms": result.duration_ms,
        "languages": {k.value: v for k,v in (manifest.languages or {}).items() if v>0} if manifest else {},
        "frameworks": [{"name": fw.name, "confidence": fw.confidence} for fw in (manifest.frameworks or [])],
        "errors": result.errors,
    }
    return _ok(data, hint="Use summarize() or status() to verify")


@mcp().tool(
    name="context",
    description="Generate a structured context package (graph + architecture + key nodes) — LLM-optimized. Params: repo, top_n (default 10), max_tokens (1500), db. Returns compressed text plus JSON. Use for giving LLM a repo overview in one call. Example: context(top_n=20)",
)
def context_package(
    repo: str | None = None,
    top_n: int = 10,
    max_tokens: int = 1500,
    db: str | None = None,
) -> str:
    from cartographer.compression.engine import build_context_package
    from cartographer.retrieval.summarizer import generate_summary

    top_n=_clamp(top_n,1,50,10)
    max_tokens=max(200, min(max_tokens, 8000)) if isinstance(max_tokens,int) else 1500
    db_path = _db(db)
    summary = generate_summary(db_path, repo)
    if not summary:
        return _empty("No repository found", "Run index(path=\".\") first")

    arch = None
    try:
        arch_result = get_architecture(db_path, repo)
        if "error" not in arch_result:
            arch = arch_result
    except Exception:
        pass

    top_nodes = None
    try:
        nodes = search_nodes("", db_path, repo, limit=top_n)
        if nodes:
            top_nodes = nodes
    except Exception:
        pass

    result = build_context_package(summary, arch, top_nodes, max_tokens)
    # also return structured JSON for LLM parsing
    data={"summary":summary,"architecture":arch,"top_nodes":top_nodes,"compressed":result}
    return json.dumps({"status":"ok","human":result,"data":data}, ensure_ascii=False, indent=2)


@mcp().tool(
    name="update_index",
    description="Incrementally re-index a single file after changes. Params: file_path (required, absolute or repo-relative), db optional. Use after editing a file instead of full re-index. Example: update_index(file_path=\"src/main.py\")",
)
def update_index_tool(
    file_path: str,
    db: str | None = None,
) -> str:
    if not file_path:
        return _error("file_path is required")
    from cartographer.ingestion.engine import update_index
    try:
        result = update_index(file_path, db_path=_db(db))
    except Exception as e:
        return _error(f"update_index failed: {e}")
    if "error" in result:
        return _error(result["error"], "Ensure repo is indexed and path exists")
    return _ok(result)


@mcp().tool(
    name="delete_file",
    description="Remove a deleted file from the graph and re-embed. Params: file_path (required), db optional. Example: delete_file(file_path=\"src/removed.py\")",
)
def delete_file_tool(
    file_path: str,
    db: str | None = None,
) -> str:
    if not file_path:
        return _error("file_path is required")
    from pathlib import Path as _Path

    from cartographer.embedding.engine import generate_embeddings
    from cartographer.graph.builder import delete_file_from_graph
    from cartographer.storage.connection import get_connection, init_schema

    db_path = _db(db)
    root = _Path(file_path).resolve()
    conn = get_connection(db_path)
    init_schema(conn)

    root_str = str(root)
    repo_row = conn.execute(
        "SELECT id, path FROM repositories WHERE ? = path OR ? LIKE path || '/%'",
        (root_str, root_str),
    ).fetchone()
    if not repo_row:
        rows = conn.execute(
            "SELECT id, path FROM repositories ORDER BY LENGTH(path) DESC"
        ).fetchall()
        for row in rows:
            if root_str.startswith(row[1] + "/") or root_str == row[1]:
                repo_row = row
                break

    if not repo_row:
        conn.close()
        return _error("Repository not found for path", "Check status() and ensure file is inside indexed repo")

    repo_id, repo_path = repo_row[0], repo_row[1]
    try:
        rel_path = str(root.relative_to(repo_path))
    except ValueError:
        conn.close()
        return _error("File is not inside any indexed repo")

    removed = delete_file_from_graph(conn, repo_id, rel_path)
    conn.commit()
    conn.close()

    embed_count = 0
    if removed > 0:
        try:
            new_count, _ = generate_embeddings(db_path)
            embed_count = new_count
        except Exception:
            pass

    return _ok({"file": rel_path, "nodes_removed": removed, "embeddings_generated": embed_count})


@mcp().tool(
    name="db_info",
    description="Return statistics about the database (size, counts). No params required. Use for diagnostics.",
)
def db_info_tool(
    db: str | None = None,
) -> str:
    import os
    db_path = _db(db)
    conn = _get_conn(db)
    try:
        repo_count = conn.execute("SELECT COUNT(*) FROM repositories").fetchone()[0]
        node_count = conn.execute("SELECT COUNT(*) FROM nodes").fetchone()[0]
        edge_count = conn.execute("SELECT COUNT(*) FROM edges").fetchone()[0]
        embed_count = conn.execute("SELECT COUNT(*) FROM embeddings").fetchone()[0]
        commit_count = conn.execute("SELECT COUNT(*) FROM commits").fetchone()[0]
    except Exception as e:
        conn.close()
        return _error(f"db_info failed: {e}")
    finally:
        try:
            conn.close()
        except Exception:
            pass
    size = os.path.getsize(db_path) if db_path.exists() else 0
    data={
        "path": str(db_path),
        "size": size,
        "size_human": f"{size/1024:.1f}KB" if size<1024*1024 else f"{size/1024/1024:.1f}MB",
        "repositories": repo_count,
        "nodes": node_count,
        "edges": edge_count,
        "embeddings": embed_count,
        "commits": commit_count,
    }
    return _ok(data)


@mcp().tool(
    name="file_summary",
    description="Compressed file summary for agents — replaces reading the full file. Returns entities, imports, exports, and relationships in ~200 tokens instead of ~2000. Params: file_path (required, e.g. 'src/main.py'), repo (optional), db optional. Saves 90% tokens. Example: file_summary(file_path=\"src/auth/service.py\")",
)
def file_summary_tool(
    file_path: str,
    repo: str | None = None,
    db: str | None = None,
) -> str:
    if not file_path:
        return _error("file_path is required", "Example: file_summary(file_path=\"src/main.py\")")
    import os as _os
    conn = _get_conn(db)

    if repo:
        repo_row = conn.execute(
            "SELECT id, path FROM repositories WHERE name = ?", (repo,)
        ).fetchone()
    else:
        repo_row = conn.execute(
            "SELECT id, path FROM repositories ORDER BY id DESC LIMIT 1"
        ).fetchone()

    if not repo_row:
        conn.close()
        return _error("No repository found", "Run index(path=\".\") first")

    repo_id, repo_path = repo_row[0], repo_row[1]

    fpath = file_path
    # try exact file_path, then basename
    row = conn.execute(
        "SELECT id, name, node_type, metadata_json FROM nodes WHERE repository_id = ? AND file_path = ? AND node_type = 'file'",
        (repo_id, fpath),
    ).fetchone()

    if not row:
        # try relative to repo
        try:
            rel = str(Path(fpath).resolve().relative_to(repo_path)) if Path(fpath).is_absolute() else fpath
            row = conn.execute(
                "SELECT id, name, node_type, metadata_json FROM nodes WHERE repository_id = ? AND file_path = ? AND node_type = 'file'",
                (repo_id, rel),
            ).fetchone()
            if row:
                fpath=rel
        except Exception:
            pass

    if not row:
        basename = _os.path.basename(fpath)
        row = conn.execute(
            "SELECT id, name, node_type, metadata_json FROM nodes WHERE repository_id = ? AND name = ? AND node_type = 'file' LIMIT 1",
            (repo_id, basename),
        ).fetchone()

    if not row:
        conn.close()
        return _error(f"File not found in graph: {file_path}", "Check file path; try search(query=\"{basename}\") or ensure file is indexed")

    file_node_id = row[0]

    entities = conn.execute(
        """SELECT n.name, n.node_type, n.metadata_json
           FROM nodes n
           JOIN edges e ON e.source_node_id = ?
           WHERE e.repository_id = ? AND e.target_node_id = n.id
           AND e.edge_type IN ('DEFINES', 'DECLARES')
           ORDER BY n.node_type, n.name""",
        (file_node_id, repo_id),
    ).fetchall()

    imports = conn.execute(
        """SELECT t.name, t.file_path FROM edges e
           JOIN nodes t ON e.target_node_id = t.id
           WHERE e.repository_id = ? AND e.source_node_id = ? AND e.edge_type = 'IMPORTS'""",
        (repo_id, file_node_id),
    ).fetchall()

    dependents = conn.execute(
        """SELECT s.name, s.file_path FROM edges e
           JOIN nodes s ON e.source_node_id = s.id
           WHERE e.repository_id = ? AND e.target_node_id = ? AND e.edge_type = 'IMPORTS'""",
        (repo_id, file_node_id),
    ).fetchall()

    calls = conn.execute(
        """SELECT s.name, t.name FROM edges e
           JOIN nodes s ON e.source_node_id = s.id
           JOIN nodes t ON e.target_node_id = t.id
           WHERE e.repository_id = ?
           AND (e.source_node_id IN (SELECT id FROM nodes WHERE file_path = ?)
                OR e.target_node_id IN (SELECT id FROM nodes WHERE file_path = ?))
           AND e.edge_type = 'CALLS'
           LIMIT 20""",
        (repo_id, fpath, fpath),
    ).fetchall()

    inherits = conn.execute(
        """SELECT s.name, t.name FROM edges e
           JOIN nodes s ON e.source_node_id = s.id
           JOIN nodes t ON e.target_node_id = t.id
           WHERE e.repository_id = ?
           AND e.source_node_id IN (SELECT id FROM nodes WHERE file_path = ?)
           AND e.edge_type IN ('INHERITS', 'IMPLEMENTS')""",
        (repo_id, fpath),
    ).fetchall()

    conn.close()

    by_type: dict[str, list[str]] = {}
    for e in entities:
        etype = e[1]
        ename = e[0]
        by_type.setdefault(etype, []).append(ename)

    # Build both human and JSON
    lines = [f"FILE: {fpath}"]
    human_parts=[]
    json_data={
        "file": fpath,
        "entities": {k: v for k,v in by_type.items()},
        "imports": [{"name": i[0], "file": i[1]} for i in imports],
        "depended_on_by": [{"name": d[0], "file": d[1]} for d in dependents],
        "inherits": [{"from": s, "to": t} for s,t in inherits],
        "calls": [{"from": s, "to": t} for s,t in calls],
    }
    for etype in ["class", "interface", "function", "method", "enum", "constant", "variable"]:
        names = by_type.get(etype, [])
        if names:
            lines.append(f"  {etype.upper()}S({len(names)}): {', '.join(names[:15])}")
    if imports:
        imp_names = [i[0] for i in imports[:10]]
        lines.append(f"  IMPORTS: {', '.join(imp_names)}")
    if dependents:
        dep_names = [d[0] for d in dependents[:10]]
        lines.append(f"  DEPENDED_ON_BY: {', '.join(dep_names)}")
    if inherits:
        rels = [f"{s} -> {t}" for s, t in inherits[:5]]
        lines.append(f"  INHERITS/IMPLEMENTS: {', '.join(rels)}")
    if calls:
        call_pairs = [f"{s}()" for s, t in calls[:8]]
        lines.append(f"  CALLS: {', '.join(call_pairs)}")
    # Token savings note
    lines.append("  (use 90% fewer tokens than reading full file)")

    return json.dumps({"status":"ok","human":"\n".join(lines),"data":json_data}, ensure_ascii=False, indent=2)


def main(db_path: Path | None = None, port: int | None = None) -> None:
    global _CUSTOM_DB_PATH
    if db_path is not None:
        _CUSTOM_DB_PATH = db_path
    from cartographer.storage.connection import init_schema
    conn = _get_conn()
    init_schema(conn)
    conn.close()
    if port:
        try:
            import uvicorn
        except ImportError:
            print("--port requires uvicorn: pip install uvicorn", file=__import__("sys").stderr)
            raise
        uvicorn.run(mcp().sse_app(), host="127.0.0.1", port=port)
    else:
        mcp().run()


if __name__ == "__main__":
    main()

