from __future__ import annotations

import sqlite3
from pathlib import Path

from mcp.server.fastmcp import FastMCP

from cartographer.architecture.engine import detect_architecture, get_architecture
from cartographer.embedding.engine import find_similar, similarity_search
from cartographer.query.engine import execute_query
from cartographer.retrieval.searcher import search_nodes
from cartographer.retrieval.summarizer import generate_summary
from cartographer.retrieval.traversal import (
    _resolve_target,
    find_path,
    get_neighbors,
    impact_analysis,
)

DEFAULT_DB = Path.home() / ".cartographer" / "index.db"

mcp = FastMCP("Cartographer")


def _db(db_str: str | None) -> Path:
    return Path(db_str) if db_str else DEFAULT_DB


@mcp.tool(
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


@mcp.tool(
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


@mcp.tool(
    name="neighbors",
    description="Show neighboring nodes of a class, function, or file in the graph",
)
def neighbors(
    name: str,
    repo: str | None = None,
    depth: int = 2,
    db: str | None = None,
) -> str:
    conn = sqlite3.connect(str(_db(db)))
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


@mcp.tool(
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


@mcp.tool(
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


@mcp.tool(
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


@mcp.tool(
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
    conn = sqlite3.connect(str(db_path))
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


@mcp.tool(
    name="ask",
    description="Ask a natural language question about the repository",
)
def ask(
    query: str,
    repo: str | None = None,
    limit: int = 20,
    db: str | None = None,
) -> str:
    result = execute_query(query, _db(db), repo, limit)
    return result


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
