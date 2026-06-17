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
        _mcp = FastMCP("Cartographer")
    return _mcp


def _db(db_str: str | None) -> Path:
    global _CUSTOM_DB_PATH
    if db_str:
        return Path(db_str)
    if _CUSTOM_DB_PATH is not None:
        return _CUSTOM_DB_PATH
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


@mcp().resource(
    "cartographer://repos",
    description="List all indexed repositories",
)
def get_repos() -> str:
    conn = _get_conn()
    rows = conn.execute("SELECT id, name, path FROM repositories ORDER BY name").fetchall()
    conn.close()
    if not rows:
        return "No repositories indexed."
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
        return f"No repository found: {name}"
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
    conn = _get_conn()
    row = conn.execute(
        """SELECT n.id, n.name, n.node_type, n.file_path, n.metadata_json, r.name as repo
           FROM nodes n
           JOIN repositories r ON n.repository_id = r.id
           WHERE n.id = ?""",
        (int(node_id),),
    ).fetchone()
    conn.close()
    if not row:
        return f"No node with id {node_id}"
    lines = [f"Node [{row['id']}]: {row['name']} ({row['node_type']})"]
    lines.append(f"  Repository: {row['repo']}")
    lines.append(f"  File: {row['file_path'] or '(root)'}")
    if row["metadata_json"]:
        meta = json.loads(row["metadata_json"])
        if meta:
            lines.append(f"  Metadata: {json.dumps(meta, indent=2)}")
    return "\n".join(lines)


@mcp().tool(
    name="search",
    description="Search for nodes (classes, functions, files) by name in the knowledge graph",
)
def search(
    query: str,
    repo: str | None = None,
    node_type: str | None = None,
    limit: int = 20,
    db: str | None = None,
) -> str:
    results = search_nodes(query, _db(db), repo, node_type, limit)
    if not results:
        return "No results found."
    lines = [f"Found {len(results)} result(s):"]
    for r in results:
        lines.append(f"  [{r['type']}] {r['name']}")
        if r.get("file_path"):
            lines.append(f"      {r['file_path']}")
    return "\n".join(lines)


@mcp().tool(
    name="impact",
    description="Analyze what depends on a given file, class, or function",
)
def impact(
    target: str,
    repo: str | None = None,
    db: str | None = None,
) -> str:
    results = impact_analysis(target, _db(db), repo)
    if not results:
        return "No dependents found."
    lines = [f"Impact analysis for '{target}':"]
    by_edge: dict[str, list] = {}
    for r in results:
        by_edge.setdefault(r.get("via_edge", "UNKNOWN"), []).append(r)
    for edge_type, nodes in by_edge.items():
        lines.append(f"  Via {edge_type}:")
        for n in nodes:
            lines.append(f"    [{n['type']}] {n['name']} ({n['file_path']})")
    return "\n".join(lines)


@mcp().tool(
    name="neighbors",
    description="Show neighboring nodes of a class, function, or file in the graph",
)
def neighbors(
    name: str,
    repo: str | None = None,
    depth: int = 2,
    db: str | None = None,
) -> str:
    conn = _get_conn(db)
    node = _resolve_target(conn, name, repo)
    conn.close()

    if not node:
        return f"No node found matching '{name}'."

    results = get_neighbors(node["id"], _db(db), depth)
    lines = [f"Neighbors of [{node['type']}] {node['name']}:"]
    for r in results:
        if r["depth"] == 0:
            continue
        indent = "  " * r["depth"]
        lines.append(f"{indent}[{r['type']}] {r['name']}")
    return "\n".join(lines)


@mcp().tool(
    name="path",
    description="Find the shortest path between two nodes in the knowledge graph",
)
def find_path_between(
    from_name: str,
    to_name: str,
    max_depth: int = 5,
    db: str | None = None,
) -> str:
    results = find_path(from_name, to_name, _db(db), max_depth=max_depth)
    if not results:
        return "No path found."
    lines = [f"Path ({len(results)} hops):"]
    for r in results:
        arrow = " → " if r["depth"] > 0 else "   "
        lines.append(f"  {arrow}[{r['type']}] {r['name']}")
        if r.get("file_path"):
            lines.append(f"      {r['file_path']}")
    return "\n".join(lines)


@mcp().tool(
    name="summarize",
    description="Generate a summary of the repository from the knowledge graph",
)
def summarize(
    repo: str | None = None,
    db: str | None = None,
) -> str:
    summary = generate_summary(_db(db), repo)
    if not summary:
        return "No repository found. Run 'cartographer index' first."
    lines = [
        f"Repository: {summary['name']}",
        f"Path: {summary['path']}",
        f"Total nodes: {summary['total_nodes']}",
        f"Total edges: {summary['total_edges']}",
        "",
        "Node breakdown:",
    ]
    for ntype, count in summary.get("node_breakdown", {}).items():
        lines.append(f"  {ntype}: {count}")
    lines.append("")
    lines.append("Edge breakdown:")
    for etype, count in summary.get("edge_breakdown", {}).items():
        lines.append(f"  {etype}: {count}")
    return "\n".join(lines)


@mcp().tool(
    name="architecture",
    description="Detect or retrieve the architecture layers and patterns of the repository",
)
def architecture(
    repo: str | None = None,
    detect: bool = False,
    db: str | None = None,
) -> str:
    if detect:
        result = detect_architecture(_db(db), repo)
        if "error" in result:
            return result["error"]
        lines = [f"Architecture for {result['repository']}:", ""]
        if result.get("frameworks"):
            lines.append("Detected frameworks:")
            for fw in result["frameworks"]:
                pct = round(fw["confidence"] * 100)
                lines.append(f"  {fw['name']} ({pct}% confidence)")
            lines.append("")
        if result["layers"]:
            lines.append("Layers:")
            for layer_name, info in result["layers"].items():
                pct = round(info["confidence"] * 100)
                lines.append(f"  {info['description']} ({pct}% confidence, "
                             f"{info['entity_count']} entities)")
        if result["patterns"]:
            lines.append("")
            lines.append("Architecture patterns:")
            for p in result["patterns"]:
                pct = round(p["confidence"] * 100)
                lines.append(f"  {p['name']} ({pct}% confidence)")
        return "\n".join(lines)

    result = get_architecture(_db(db), repo)
    if "error" in result:
        return result["error"]
    if not result["layers"]:
        return "No architecture data. Run with detect=True first."
    lines = [f"Architecture for {result['repository']}:"]
    for layer in result["layers"]:
        lines.append(f"  {layer['name']}: {layer['description']}")
    return "\n".join(lines)


@mcp().tool(
    name="similar",
    description="Find semantically similar nodes using vector embeddings",
)
def similar(
    target: str,
    repo: str | None = None,
    limit: int = 20,
    db: str | None = None,
) -> str:
    db_path = _db(db)
    conn = _get_conn(db)
    node = _resolve_target(conn, target, repo)
    conn.close()

    if node:
        results = find_similar(db_path, node["id"], limit)
    else:
        results = similarity_search(db_path, target, limit, repo)

    if not results:
        return "No similar nodes found. Run 'cartographer embed' first."
    lines = [f"Similar to '{target}':"]
    for r in results:
        lines.append(f"  [{r['type']}] {r['name']}  (score: {r['similarity']})")
        if r.get("file_path"):
            lines.append(f"      {r['file_path']}")
    return "\n".join(lines)


@mcp().tool(
    name="ask",
    description="Ask a natural language question about the repository",
)
def ask(
    query: str,
    repo: str | None = None,
    limit: int = 20,
    max_tokens: int = 0,
    db: str | None = None,
) -> str:
    result = execute_query(query, _db(db), repo, limit, max_tokens)
    return result


@mcp().tool(
    name="graph_data",
    description="Export graph data as JSON for visualization. Returns nodes, edges, and stats.",
)
def graph_data(
    repo: str | None = None,
    limit: int = 80,
    db: str | None = None,
) -> str:
    import json
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
        return json.dumps({"error": "Repository not found"})

    repo_id = row[0]

    type_counts = dict(conn.execute(
        """SELECT node_type, COUNT(*) as cnt FROM nodes
           WHERE repository_id = ? GROUP BY node_type ORDER BY cnt DESC""",
        (repo_id,),
    ).fetchall())

    hub_count = max(5, limit // 8)
    seeds = conn.execute(
        """SELECT n.id, n.name, n.node_type, n.file_path
           FROM nodes n
           WHERE n.repository_id = ?
           ORDER BY (SELECT COUNT(*) FROM edges WHERE repository_id = ?
                     AND (source_node_id = n.id OR target_node_id = n.id)) DESC, RANDOM()
           LIMIT ?""",
        (repo_id, repo_id, hub_count),
    ).fetchall()

    seed_ids = [s[0] for s in seeds]
    all_ids: list[int] = list(seed_ids)
    if seed_ids:
        seed_ph = ",".join("?" for _ in seed_ids)
        rows = conn.execute(
            f"""SELECT DISTINCT n.id FROM nodes n
                JOIN edges e ON (e.source_node_id = n.id OR e.target_node_id = n.id)
                WHERE n.repository_id = ?
                AND (e.source_node_id IN ({seed_ph}) OR e.target_node_id IN ({seed_ph}))""",
            (repo_id, *seed_ids, *seed_ids),
        ).fetchall()
        for r in rows:
            if r[0] not in all_ids and len(all_ids) < limit:
                all_ids.append(r[0])

    if all_ids and len(all_ids) < limit:
        ph = ",".join("?" for _ in all_ids)
        remaining = conn.execute(
            f"""SELECT n.id FROM nodes n
                WHERE n.repository_id = ? AND n.id NOT IN ({ph})
                ORDER BY (SELECT COUNT(*) FROM edges WHERE repository_id = ?
                          AND (source_node_id = n.id OR target_node_id = n.id)) DESC
                LIMIT ?""",
            (repo_id, *all_ids, repo_id, limit - len(all_ids)),
        ).fetchall()
        for r in remaining:
            all_ids.append(r[0])

    final_ids = all_ids[:limit]
    if not final_ids:
        conn.close()
        return json.dumps({"nodes": [], "edges": []})

    ph = ",".join("?" for _ in final_ids)
    nodes_list = conn.execute(
        f"SELECT id, name, node_type, file_path FROM nodes WHERE id IN ({ph})",
        (*final_ids,),
    ).fetchall()

    edges = conn.execute(
        f"""SELECT source_node_id, target_node_id, edge_type FROM edges
            WHERE repository_id = ?
            AND source_node_id IN ({ph})
            AND target_node_id IN ({ph})""",
        (repo_id, *final_ids, *final_ids),
    ).fetchall()

    total_nodes = conn.execute(
        "SELECT COUNT(*) FROM nodes WHERE repository_id = ?", (repo_id,)
    ).fetchone()[0]
    total_edges = conn.execute(
        "SELECT COUNT(*) FROM edges WHERE repository_id = ?", (repo_id,)
    ).fetchone()[0]

    conn.close()
    return json.dumps({
        "total_nodes": total_nodes,
        "total_edges": total_edges,
        "node_types": type_counts,
        "nodes": [{"id": n[0], "name": n[1], "type": n[2], "file_path": n[3]} for n in nodes_list],
        "edges": [{"source": e[0], "target": e[1], "type": e[2]} for e in edges],
    })


@mcp().tool(
    name="index",
    description="Index a repository. Run this before querying a new repo.",
)
def index_repo(
    path: str = ".",
    db: str | None = None,
) -> str:
    result = index_repository(path, db_path=_db(db))
    if not result.success:
        lines = [f"Indexing failed for {path}:"]
        lines.extend(f"  Error: {e}" for e in result.errors)
        return "\n".join(lines)
    manifest = result.manifest
    lines = [
        f"Indexed {manifest.total_files} files in {manifest.total_dirs} directories",
        f"Duration: {result.duration_ms}ms",
    ]
    if manifest.languages:
        active = {
            k: v for k, v in sorted(manifest.languages.items(), key=lambda x: -x[1])
            if k.value != "unknown" and v > 0
        }
        if active:
            lines.append("Languages: " + ", ".join(f"{k.value}: {v}" for k, v in active.items()))
    return "\n".join(lines)


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
