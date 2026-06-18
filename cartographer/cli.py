from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

import click

logging.basicConfig(
    level=logging.INFO,
    format="%(message)s",
    stream=sys.stderr,
)

from cartographer.architecture.engine import detect_architecture, get_architecture
from cartographer.compression.engine import build_context_package, compress
from cartographer.core.models import EntityKind
from cartographer.embedding.engine import (
    find_similar,
    generate_embeddings,
    invalidate_cache,
    similarity_search,
)
from cartographer.git.engine import (
    author_impact,
    co_change_analysis,
    get_file_history,
    get_node_history,
    index_commits,
    list_authors,
    why_introduced,
)
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


def _ensure_indexed(db_path: Path) -> bool:
    """Auto-index CWD if DB is empty and CWD is a git repo. Returns True if data is available."""
    from cartographer.storage.connection import get_connection, init_schema
    conn = get_connection(db_path)
    init_schema(conn)
    count = conn.execute("SELECT COUNT(*) FROM repositories").fetchone()[0]
    conn.close()
    if count > 0:
        return True
    cwd = Path.cwd()
    if not (cwd / ".git").is_dir():
        return False
    click.echo("No indexed repos found. Auto-indexing current directory...", err=True)
    result = index_repository(str(cwd), db_path=db_path)
    if result.success:
        manifest = result.manifest
        click.echo(f"Indexed {manifest.total_files} files in {manifest.total_dirs} directories", err=True)
    return bool(result.success)


def _count_entities(parsed_files, kind: EntityKind) -> int:
    total = 0
    for pf in parsed_files:
        for e in pf.entities:
            if e.kind == kind:
                total += 1
            total += sum(1 for c in _walk_children(e) if c.kind == kind)
    return total


def _walk_children(entity):
    for c in entity.children:
        yield c
        yield from _walk_children(c)


@click.group()
@click.option("--db", default=None, help="Path to SQLite database", envvar="CARTOGRAPHER_DB")
@click.pass_context
def main(ctx, db):
    ctx.ensure_object(dict)
    if db:
        ctx.obj["db_path"] = Path(db)
    elif env_db := os.environ.get("CARTOGRAPHER_DB"):
        ctx.obj["db_path"] = Path(env_db)
    else:
        # Check for per-project config in current directory
        proj_cfg = Path.cwd() / ".cartographer" / "config.json"
        if proj_cfg.exists():
            try:
                import json as _json
                cfg = _json.loads(proj_cfg.read_text())
                cfg_db = cfg.get("dbPath", "")
                if cfg_db:
                    p = Path(cfg_db)
                    ctx.obj["db_path"] = p if p.is_absolute() else Path.cwd() / cfg_db
                else:
                    ctx.obj["db_path"] = Path.cwd() / ".cartographer" / "data.db"
                return
            except Exception:
                pass
        ctx.obj["db_path"] = Path.home() / ".cartographer" / "index.db"


@main.command()
@click.argument("path", default=".", type=click.Path(exists=True, file_okay=False))
@click.option("--force", "-f", is_flag=True, help="Re-index even if already indexed")
@click.pass_context
def init(ctx, path, force):
    """Initialize Cartographer for a project. Sets up the database and indexes the repository."""
    db_path = ctx.obj["db_path"]
    from cartographer.storage.connection import get_connection, init_schema

    conn = get_connection(db_path)
    init_schema(conn)
    conn.close()

    resolved = str(Path(path).resolve())
    if not force:
        conn = get_connection(db_path)
        existing = conn.execute(
            "SELECT name FROM repositories WHERE path = ?", (resolved,)
        ).fetchone()
        conn.close()
        if existing:
            click.echo(f"Cartographer is already initialized for '{existing[0]}'")
            click.echo(f"Database: {db_path}")
            click.echo()
            click.echo("To re-index, run:  cartographer index .")
            click.echo("To start fresh:    cartographer init . --force")
            return

    click.echo(f"Initializing Cartographer for {path}...")
    click.echo(f"Database: {db_path}")
    click.echo()

    from cartographer.ingestion.engine import index_repository
    result = index_repository(resolved, db_path=db_path)

    if not result.success:
        for err in result.errors:
            click.echo(f"Error: {err}", err=True)
        if not result.manifest:
            raise click.Abort()

    manifest = result.manifest
    click.echo(f"Indexed {manifest.total_files} files in {manifest.total_dirs} directories")
    click.echo(f"Duration: {result.duration_ms}ms")
    click.echo()

    if result.parsed_files:
        funcs = _count_entities(result.parsed_files, EntityKind.FUNCTION)
        classes = _count_entities(result.parsed_files, EntityKind.CLASS)
        methods = _count_entities(result.parsed_files, EntityKind.METHOD)
        click.echo(f"Entities: {classes} classes, {funcs} functions, {methods} methods")

    click.echo()
    click.echo("Next steps:")
    click.echo("  cartographer embed              Enable semantic search")
    click.echo("  cartographer git index          Index git history")
    click.echo("  cartographer ask <query>        Search the knowledge graph")
    click.echo("  cartographer graph-data -r <name>  Export graph data")


@main.command()
@click.argument("path", default=".", type=click.Path(exists=True, file_okay=False))
@click.pass_context
def index(ctx, path):
    """Index a repository into the knowledge graph."""
    db_path = ctx.obj["db_path"]
    result = index_repository(path, db_path=db_path)

    if not result.success:
        for err in result.errors:
            click.echo(f"Error: {err}", err=True)
        if not result.manifest:
            raise click.Abort()

    manifest = result.manifest
    click.echo(f"Indexed {manifest.total_files} files in {manifest.total_dirs} directories")
    click.echo(f"Duration: {result.duration_ms}ms")

    if manifest.languages:
        active = {
            k: v
            for k, v in sorted(manifest.languages.items(), key=lambda x: -x[1])
            if k.value != "unknown" and v > 0
        }
        if active:
            parts = (f"{k.value}: {v}" for k, v in active.items())
            click.echo(f"Languages: {', '.join(parts)}")

    if manifest.frameworks:
        click.echo("Frameworks:")
        for fw in manifest.frameworks:
            confidence_pct = round(fw.confidence * 100)
            click.echo(f"  - {fw.name} ({confidence_pct}% confidence)")

    if manifest.package_managers:
        click.echo(f"Package Managers: {', '.join(manifest.package_managers)}")

    if manifest.build_systems:
        click.echo(f"Build Systems: {', '.join(manifest.build_systems)}")

    if manifest.is_monorepo:
        click.echo(f"Monorepo: yes ({manifest.monorepo_tool})")

    if result.parsed_files:
        funcs = _count_entities(result.parsed_files, EntityKind.FUNCTION)
        classes = _count_entities(result.parsed_files, EntityKind.CLASS)
        methods = _count_entities(result.parsed_files, EntityKind.METHOD)
        click.echo(f"Entities: {len(result.parsed_files)} files parsed, "
                    f"{classes} classes, {funcs} functions, {methods} methods")
        if manifest.total_references:
            click.echo(f"References: {manifest.total_references} cross-file imports")

    if result.errors:
        for err in result.errors:
            click.echo(f"Warning: {err}", err=True)

    click.echo()
    click.echo("Next: run 'cartographer embed' and 'cartographer git index' for full features")


@main.command()
@click.argument("query")
@click.option("--type", "-t", "node_type", help="Filter by node type")
@click.option("--repo", "-r", help="Filter by repository name")
@click.option("--limit", "-l", default=20, help="Max results")
@click.option("--semantic", "-s", is_flag=True, help="Use semantic (embedding) search")
@click.option("--max-tokens", "-m", default=0, type=int, help="Compress output to fit token budget")
@click.pass_context
def ask(ctx, query, node_type, repo, limit, semantic, max_tokens):
    """Search the knowledge graph."""
    _ensure_indexed(ctx.obj["db_path"])
    if semantic:
        results = similarity_search(ctx.obj["db_path"], query, limit, repo)
        if not results:
            click.echo("No semantic results found. Run 'cartographer embed' first.")
            return
        click.echo(f"Found {len(results)} semantic result(s):")
        for r in results:
            type_label = r["type"].ljust(12)
            score = r["similarity"]
            click.echo(f"  [{type_label}] {r['name']}  (score: {score})")
            if r["file_path"]:
                click.echo(f"           {r['file_path']}")
        return

    results = search_nodes(query, ctx.obj["db_path"], repo, node_type, limit)

    if not results:
        click.echo("No results found.")
        return

    if max_tokens:
        click.echo(compress(results, max_tokens, "nodes"))
    else:
        click.echo(f"Found {len(results)} result(s):")
        for r in results:
            type_label = r["type"].ljust(12)
            click.echo(f"  [{type_label}] {r['name']}")
            if r["file_path"]:
                click.echo(f"           {r['file_path']}")
        click.echo("  (use 'cartographer impact <id>' for impact analysis)")


@main.command()
@click.argument("target")
@click.option("--repo", "-r", help="Repository name")
@click.option("--max-tokens", "-m", default=0, type=int, help="Compress output to fit token budget")
@click.pass_context
def impact(ctx, target, repo, max_tokens):
    """Analyze what depends on a given file or symbol."""
    _ensure_indexed(ctx.obj["db_path"])
    results = impact_analysis(target, ctx.obj["db_path"], repo)

    if not results:
        click.echo("No dependents found.")
        return

    if max_tokens:
        click.echo(compress(results, max_tokens, "impact"))
        return

    click.echo(f"Impact analysis for '{target}':")
    by_edge: dict[str, list] = {}
    for r in results:
        edge = r.get("via_edge", "UNKNOWN")
        by_edge.setdefault(edge, []).append(r)

    for edge_type, nodes in by_edge.items():
        click.echo(f"  Via {edge_type}:")
        for n in nodes:
            click.echo(f"    [{n['type']}] {n['name']} ({n['file_path']})")


@main.command()
@click.argument("name")
@click.option("--repo", "-r", help="Repository name")
@click.option("--depth", "-d", default=2, help="Traversal depth")
@click.option("--max-tokens", "-m", default=0, type=int, help="Compress output to fit token budget")
@click.pass_context
def neighbors(ctx, name, repo, depth, max_tokens):
    """Show neighbors of a node in the graph."""
    _ensure_indexed(ctx.obj["db_path"])
    from cartographer.storage.connection import get_connection

    conn = get_connection(ctx.obj["db_path"])
    node = _resolve_target(conn, name, repo)
    conn.close()

    if not node:
        click.echo(f"No node found matching '{name}'.")
        return

    click.echo(f"Neighbors of [{node['type']}] {node['name']}:")
    results = get_neighbors(node["id"], ctx.obj["db_path"], depth)

    if max_tokens:
        click.echo(compress(results, max_tokens, "nodes"))
        return

    for r in results:
        if r["depth"] == 0:
            continue
        indent = "  " * r["depth"]
        click.echo(f"{indent}[{r['type']}] {r['name']}")


@main.command()
@click.option("--repo", "-r", help="Repository name")
@click.option("--max-tokens", "-m", default=0, type=int, help="Compress output to fit token budget")
@click.pass_context
def summarize(ctx, repo, max_tokens):
    """Generate repository summary from the knowledge graph."""
    _ensure_indexed(ctx.obj["db_path"])
    summary = generate_summary(ctx.obj["db_path"], repo)

    if not summary:
        click.echo("No repository found. Run 'cartographer index' first.")
        return

    if max_tokens:
        click.echo(compress(summary, max_tokens, "summary"))
        return

    click.echo(f"Repository: {summary['name']}")
    click.echo(f"Path: {summary['path']}")
    click.echo(f"Total nodes: {summary['total_nodes']}")
    click.echo(f"Total edges: {summary['total_edges']}")
    click.echo()
    click.echo("Node breakdown:")
    for ntype, count in summary["node_breakdown"].items():
        click.echo(f"  {ntype}: {count}")
    click.echo()
    click.echo("Edge breakdown:")
    for etype, count in summary["edge_breakdown"].items():
        click.echo(f"  {etype}: {count}")
    if summary["top_files"]:
        click.echo()
        click.echo("Top files by entity count:")
        for f in summary["top_files"]:
            click.echo(f"  {f['name']} ({f['entities']} entities)")
    if summary["top_classes"]:
        click.echo()
        click.echo("Largest classes:")
        for c in summary["top_classes"]:
            click.echo(f"  {c['name']} ({c['methods']} methods)")


@main.command()
@click.option("--repo", "-r", help="Repository name")
@click.option("--max-tokens", "-m", default=1500, type=int, help="Token budget")
@click.option("--top-n", default=10, type=int, help="Number of key nodes to include")
@click.pass_context
def context(ctx, repo, max_tokens, top_n):
    """Generate a structured context package (graph + architecture + key nodes)."""
    _ensure_indexed(ctx.obj["db_path"])
    summary = generate_summary(ctx.obj["db_path"], repo)
    if not summary:
        click.echo("No repository found. Run 'cartographer index' first.")
        return

    arch = None
    try:
        arch = get_architecture(ctx.obj["db_path"], repo)
        if "error" in arch:
            arch = None
    except Exception:
        pass

    top_nodes = None
    try:
        results = search_nodes("", ctx.obj["db_path"], repo, limit=top_n)
        if results:
            top_nodes = results
    except Exception:
        pass

    result = build_context_package(summary, arch, top_nodes, max_tokens)
    click.echo(result)


@main.command()
@click.argument("from_name")
@click.argument("to_name")
@click.option("--max-depth", default=5)
@click.option("--max-tokens", "-m", default=0, type=int, help="Compress output to fit token budget")
@click.pass_context
def path(ctx, from_name, to_name, max_depth, max_tokens):
    """Find path between two nodes."""
    _ensure_indexed(ctx.obj["db_path"])
    results = find_path(from_name, to_name, ctx.obj["db_path"], max_depth=max_depth)

    if not results:
        click.echo("No path found.")
        return

    if max_tokens:
        click.echo(compress(results, max_tokens, "path"))
        return

    click.echo(f"Path ({len(results)} hops):")
    for r in results:
        arrow = " → " if r["depth"] > 0 else "   "
        click.echo(f"  {arrow}[{r['type']}] {r['name']}")
        if r["file_path"]:
            click.echo(f"      {r['file_path']}")


@main.command()
@click.option("--repo", "-r", help="Repository name")
@click.pass_context
def embed(ctx, repo):
    """Generate vector embeddings for semantic search."""
    click.echo("Embedding...")
    try:
        new_count, skip_count = generate_embeddings(ctx.obj["db_path"], repo)
        if new_count:
            click.echo(f"Embedded {new_count} nodes.")
        else:
            click.echo("All nodes already embedded.")
        if skip_count:
            click.echo(f"Skipped {skip_count} already-embedded nodes.")
    except Exception as e:
        click.echo(f"Embedding failed: {e}", err=True)


@main.command()
@click.argument("target")
@click.option("--repo", "-r", help="Repository name")
@click.option("--limit", "-l", default=20, help="Max results")
@click.pass_context
def similar(ctx, target, repo, limit):
    """Find semantically similar nodes."""
    _ensure_indexed(ctx.obj["db_path"])
    from cartographer.storage.connection import get_connection

    conn = get_connection(ctx.obj["db_path"])
    node = _resolve_target(conn, target, repo)
    conn.close()

    if node:
        results = find_similar(ctx.obj["db_path"], node["id"], limit)
    else:
        results = similarity_search(ctx.obj["db_path"], target, limit, repo)

    if not results:
        click.echo("No similar nodes found. Run 'cartographer embed' first.")
        return

    click.echo(f"Similar to '{target}':")
    for r in results:
        type_label = r["type"].ljust(12)
        score = r["similarity"]
        click.echo(f"  [{type_label}] {r['name']}  (score: {score})")
        if r["file_path"]:
            click.echo(f"           {r['file_path']}")


@main.command()
@click.option("--repo", "-r", help="Repository name")
@click.option("--detect", is_flag=True, help="Run architecture detection")
@click.option("--verbose", "-v", is_flag=True, help="Show detailed evidence")
@click.pass_context
def architecture(ctx, repo, detect, verbose):
    """Show or detect repository architecture."""
    _ensure_indexed(ctx.obj["db_path"])
    if detect:
        click.echo("Detecting architecture...")
        result = detect_architecture(ctx.obj["db_path"], repo)
        if "error" in result:
            click.echo(result["error"])
            return

        click.echo(f"Architecture for {result['repository']}:")
        click.echo()

        if result.get("frameworks"):
            click.echo("Detected frameworks:")
            for fw in result["frameworks"]:
                pct = round(fw["confidence"] * 100)
                click.echo(f"  {fw['name']} ({pct}% confidence)")
            click.echo()

        if result["layers"]:
            click.echo("Layers:")
            for layer_name, info in result["layers"].items():
                pct = round(info["confidence"] * 100)
                types_str = ", ".join(
                    f"{k}: {v}" for k, v in info.get("evidence_types", {}).items()
                )
                click.echo(f"  {info['description']} ({pct}% confidence, "
                           f"{info['entity_count']} entities)")
                click.echo(f"    signals: {types_str}")
                if verbose and info.get("examples"):
                    for ex in info["examples"][:5]:
                        click.echo(f"    - {ex}")
            click.echo()

        if result["patterns"]:
            click.echo("Architecture patterns:")
            for p in result["patterns"]:
                pct = round(p["confidence"] * 100)
                click.echo(f"  {p['name']} ({pct}% confidence)")
                click.echo(f"    {p['description']}")
                if p.get("missing_layers"):
                    click.echo(f"    missing: {', '.join(p['missing_layers'])}")
            click.echo()

        if result.get("framework_patterns"):
            click.echo("Framework-specific patterns:")
            for fp in result["framework_patterns"]:
                pct = round(fp["confidence"] * 100)
                click.echo(f"  {fp['name']} ({pct}% confidence)")
                click.echo(f"    {fp['description']}")
            click.echo()

        if result.get("dependency_flow"):
            click.echo("Dependency flow:")
            for df in result["dependency_flow"]:
                label = "expected" if df.get("expected") else "unexpected"
                if df.get("expected") is None:
                    label = "observed"
                click.echo(f"  {df['direction']} ({df['forward']}f/{df['reverse']}r) [{label}]")
                click.echo(f"    {df['description']}")
            click.echo()

        if result.get("domains"):
            click.echo("Service domains:")
            for d in result["domains"]:
                pct = round(d["confidence"] * 100)
                click.echo(f"  {d['name']} ({pct}% confidence, {d['file_count']} files)")
                click.echo(f"    layers: {', '.join(f'{k}: {v}' for k, v in d.get('layer_counts', {}).items())}")
            click.echo()

        if not result["layers"] and not result["patterns"]:
            click.echo("  No clear architecture patterns detected.")
        return

    result = get_architecture(ctx.obj["db_path"], repo)
    if "error" in result:
        click.echo(result["error"])
        return

    if not result["layers"] and not result["patterns"] and not result.get("framework_patterns"):
        click.echo("No architecture data. Run 'cartographer architecture --detect' first.")
        return

    click.echo(f"Architecture for {result['repository']}:")
    if result["layers"]:
        click.echo()
        click.echo("Layers:")
        for layer in result["layers"]:
            click.echo(f"  {layer['name']}: {layer['description']}")
    if result["patterns"]:
        click.echo()
        click.echo("Patterns:")
        for pattern in result["patterns"]:
            click.echo(f"  {pattern['name']}: {pattern['description']}")
    if result.get("framework_patterns"):
        click.echo()
        click.echo("Framework patterns:")
        for fp in result["framework_patterns"]:
            click.echo(f"  {fp['name']}: {fp['description']}")


@main.command()
def version():
    """Show Cartographer version."""
    try:
        from importlib.metadata import version as _v
        v = _v("cartographer")
    except Exception:
        v = "0.1.0"
    click.echo(f"cartographer {v}")


@main.command()
@click.argument("query_str")
@click.option("--repo", "-r", help="Repository name")
@click.option("--limit", "-l", default=20, help="Max results per step")
@click.option("--max-tokens", "-m", default=0, type=int, help="Compress output to fit token budget")
@click.option("--verbose", "-v", is_flag=True, help="Show detailed reasoning")
@click.pass_context
def query(ctx, query_str, repo, limit, max_tokens, verbose):
    """Ask a natural language question about the repository."""
    _ensure_indexed(ctx.obj["db_path"])
    try:
        result = execute_query(query_str, ctx.obj["db_path"], repo, limit, max_tokens)
        click.echo(result)
    except Exception as e:
        click.echo(f"Query failed: {e}", err=True)


# ── mcp commands ────────────────────────────────────────────────────────────────

MCP_PID_FILE = Path.home() / ".cartographer" / "mcp.pid"


@main.group()
def mcp():
    """MCP server commands for AI assistant integration."""
    pass


@mcp.command()
@click.option("--db", default=None, help="Database path", envvar="CARTOGRAPHER_DB")
@click.option("--port", default=None, type=int, help="Run as SSE server on port (e.g. 8080)")
@click.option("--verbose", is_flag=True, help="Show server logs on stderr")
@click.option("--log-file", default=None, help="Write logs to file", type=click.Path())
def start(db, port, verbose, log_file):
    """Start the MCP server for AI assistant integration.

    Runs a Model Context Protocol server that exposes Cartographer's
    knowledge graph as tools for AI assistants (Claude Desktop, Cursor, etc.).

    Configure your AI assistant client to use the 'cartographer-mcp' entry point:

    \b
    Claude Desktop (claude_desktop_config.json):
    {
      "mcpServers": {
        "cartographer": {
          "command": "cartographer-mcp",
          "args": []
        }
      }
    }

    \b
    Cursor:
    {
      "mcpServers": {
        "cartographer": {
          "command": "cartographer-mcp",
          "args": []
        }
      }
    }
    """
    MCP_PID_FILE.parent.mkdir(parents=True, exist_ok=True)

    if MCP_PID_FILE.exists():
        try:
            pid = int(MCP_PID_FILE.read_text().strip())
            os.kill(pid, 0)
            click.echo(f"MCP server already running (PID {pid})", err=True)
            return
        except (OSError, ValueError):
            MCP_PID_FILE.unlink(missing_ok=True)

    MCP_PID_FILE.write_text(str(os.getpid()))

    if verbose or log_file:
        logger = logging.getLogger("cartographer.mcp")
        logger.setLevel(logging.INFO)
        if log_file:
            handler = logging.FileHandler(log_file)
        else:
            handler = logging.StreamHandler(sys.stderr)
        handler.setFormatter(logging.Formatter(
            "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
        ))
        logger.addHandler(handler)

    from cartographer.mcp.server import main as mcp_main
    db_path = Path(db) if db else None
    try:
        click.echo(f"MCP server starting (PID {os.getpid()})", err=True)
        mcp_main(db_path, port=port)
    finally:
        MCP_PID_FILE.unlink(missing_ok=True)


@mcp.command()
def stop():
    """Stop a running MCP server."""
    if not MCP_PID_FILE.exists():
        click.echo("No MCP server running (PID file not found)", err=True)
        return
    try:
        pid = int(MCP_PID_FILE.read_text().strip())
        os.kill(pid, 15)
        MCP_PID_FILE.unlink(missing_ok=True)
        click.echo(f"Stopped MCP server (PID {pid})", err=True)
    except ProcessLookupError:
        MCP_PID_FILE.unlink(missing_ok=True)
        click.echo("MCP server was not running (stale PID file cleaned up)", err=True)
    except (OSError, ValueError) as e:
        click.echo(f"Failed to stop MCP server: {e}", err=True)


# ── git commands ──────────────────────────────────────────────────────────────


@main.group()
def git():
    """Git intelligence commands."""


@git.command("index")
@click.option("--repo-path", "-p", default=None, help="Repository path")
@click.option("--repo", "-r", default=None, help="Repository name")
@click.option("--max-count", "-n", default=0, type=int, help="Max commits to index")
@click.pass_context
def git_index(ctx, repo_path, repo, max_count):
    """Index git history (commits, authors, change patterns)."""
    if not repo_path:
        row = _get_repo(ctx)
        if not row:
            click.echo("No repository found. Specify --repo-path or index a repo first.")
            return
        repo_path = row[0]

    click.echo("Indexing git history...")
    result = index_commits(repo_path, ctx.obj["db_path"], max_count)
    if "error" in result:
        click.echo(result["error"])
        return
    click.echo(f"Indexed {result['commits_indexed']} commits, "
               f"{result['authors_found']} authors found.")


@git.command("blame")
@click.argument("target")
@click.option("--repo", "-r", default=None, help="Repository name")
@click.option("--limit", "-l", default=15, type=int)
@click.pass_context
def git_blame(ctx, target, repo, limit):
    """Show commit history for a file or symbol."""
    history = get_node_history(ctx.obj["db_path"], target, repo_name=repo, limit=limit)
    if not history:
        history = get_file_history(ctx.obj["db_path"], target, repo_name=repo, limit=limit)
    if not history:
        click.echo("No history found. Run 'cartographer git index' first.")
        return

    click.echo(f"History for '{target}':")
    for entry in history:
        short_hash = entry["hash"][:8]
        date = entry["committed_at"][:10]
        msg = entry["message"].split("\n")[0]
        click.echo(f"  {short_hash} {date} {entry['author']}")
        click.echo(f"      {entry['change_type']}  {msg}")


@git.command("author")
@click.argument("name")
@click.option("--repo", "-r", default=None, help="Repository name")
@click.option("--limit", "-l", default=15, type=int)
@click.pass_context
def git_author(ctx, name, repo, limit):
    """Show an author's contributions."""
    result = author_impact(ctx.obj["db_path"], name, repo_name=repo, limit=limit)
    if "error" in result:
        click.echo(result["error"])
        return

    click.echo(f"Author: {result['author']} ({result.get('email', 'no email')})")
    click.echo(f"Total commits: {result['total_commits']}")
    click.echo()
    if result["top_files"]:
        click.echo("Most changed files:")
        for f in result["top_files"][:10]:
            click.echo(f"  {f['file_path']} ({f['changes']} changes)")
    click.echo()
    click.echo("Recent commits:")
    for c in result["commits"][:limit]:
        short_hash = c["hash"][:8]
        date = c["committed_at"][:10]
        click.echo(f"  {short_hash} {date} {c['change_type']}  {c['file']}")
        msg = c["message"].split("\n")[0]
        click.echo(f"      {msg}")


@git.command("cochange")
@click.argument("target")
@click.option("--repo", "-r", default=None, help="Repository name")
@click.option("--limit", "-l", default=15, type=int)
@click.pass_context
def git_cochange(ctx, target, repo, limit):
    """Show files that change together with target."""
    results = co_change_analysis(ctx.obj["db_path"], target, repo_name=repo, limit=limit)
    if not results:
        click.echo("No co-change data found. Run 'cartographer git index' first.")
        return

    click.echo(f"Files that co-change with '{target}':")
    for r in results:
        click.echo(f"  {r['file_path']} ({r['co_occurrences']} times)")


@git.command("why")
@click.argument("target")
@click.option("--repo", "-r", default=None, help="Repository name")
@click.pass_context
def git_why(ctx, target, repo):
    """Find which commit introduced a symbol or file."""
    result = why_introduced(ctx.obj["db_path"], target, repo_name=repo)
    if not result:
        click.echo("No information found.")
        return

    short_hash = result["introduced_in"][:8]
    click.echo(f"'{target}' was introduced in commit {short_hash}")
    click.echo(f"  File: {result['file_path']}")
    click.echo(f"  Author: {result['by']}")
    click.echo(f"  Date: {result['committed_at']}")
    click.echo(f"  Message: {result['message']}")


@git.command("authors")
@click.option("--repo", "-r", default=None, help="Repository name")
@click.option("--limit", "-l", default=20, type=int)
@click.pass_context
def git_authors(ctx, repo, limit):
    """List all authors sorted by commit count."""
    authors = list_authors(ctx.obj["db_path"], repo_name=repo, limit=limit)
    if not authors:
        click.echo("No authors found. Run 'cartographer git index' first.")
        return

    click.echo("Authors (by commit count):")
    for a in authors:
        click.echo(f"  {a['name']} <{a['email']}> — {a['commit_count']} commits")


@main.command(name="graph-data")
@click.option("--repo", "-r", help="Repository name")
@click.option("--limit", "-l", default=80, help="Max nodes to sample")
@click.option("--offset", "-o", default=0, help="Skip N hub groups for pagination")
@click.option("--dir", "-d", "dir_filter", default=None, help="Filter by directory prefix")
@click.option("--expand-node-id", type=int, default=None,
              help="Expand neighbors of a specific node ID")
@click.pass_context
def graph_data(ctx, repo, limit, offset, dir_filter, expand_node_id):
    """Output graph data as JSON for the VS Code extension."""
    import json

    from cartographer.storage.connection import get_connection
    conn = get_connection(ctx.obj["db_path"])

    if repo:
        row = conn.execute("SELECT id FROM repositories WHERE name = ?", (repo,)).fetchone()
    else:
        row = conn.execute("SELECT id FROM repositories ORDER BY id DESC LIMIT 1").fetchone()

    if not row:
        click.echo(json.dumps({"error": "Repository not found"}))
        return

    repo_id = row[0]

    type_counts = dict(conn.execute(
        "SELECT node_type, COUNT(*) as cnt FROM nodes"
        " WHERE repository_id = ? GROUP BY node_type ORDER BY cnt DESC",
        (repo_id,),
    ).fetchall())

    all_ids: list[int] = []

    if expand_node_id is not None:
        all_ids = [expand_node_id]
        rows = conn.execute(
            """SELECT DISTINCT
                   CASE WHEN e.source_node_id = ? THEN e.target_node_id
                        ELSE e.source_node_id END
               FROM edges e
               WHERE e.repository_id = ?
               AND (e.source_node_id = ? OR e.target_node_id = ?)
               LIMIT ?""",
            (expand_node_id, repo_id, expand_node_id, expand_node_id, limit - 1),
        ).fetchall()
        for r in rows:
            if r[0] not in all_ids and len(all_ids) < limit:
                all_ids.append(r[0])
    else:
        base_where = "WHERE n.repository_id = ?"
        base_params: list = [repo_id]
        if dir_filter:
            base_where += " AND n.file_path LIKE ?"
            base_params.append(dir_filter + "%")

        hub_count = max(5, limit // 8)
        seeds = conn.execute(
            f"""SELECT n.id FROM nodes n
                {base_where}
                ORDER BY (SELECT COUNT(*) FROM edges e
                          WHERE e.repository_id = ?
                          AND (e.source_node_id = n.id OR e.target_node_id = n.id)) DESC, RANDOM()
                LIMIT ? OFFSET ?""",
            (*base_params, repo_id, hub_count, offset),
        ).fetchall()

        all_ids = [s[0] for s in seeds]
        if seeds:
            seed_ph = ",".join("?" for _ in seeds)
            rows = conn.execute(
                f"""SELECT DISTINCT n.id FROM nodes n
                    JOIN edges e ON (e.source_node_id = n.id OR e.target_node_id = n.id)
                    WHERE n.repository_id = ?
                    AND (e.source_node_id IN ({seed_ph}) OR e.target_node_id IN ({seed_ph}))
                    AND n.id NOT IN ({seed_ph})
                    LIMIT ?""",
                (repo_id, *[s[0] for s in seeds], *[s[0] for s in seeds], limit - len(all_ids)),
            ).fetchall()
            for r in rows:
                if r[0] not in all_ids and len(all_ids) < limit:
                    all_ids.append(r[0])

        if all_ids and len(all_ids) < limit:
            ph = ",".join("?" for _ in all_ids)
            remaining = conn.execute(
                f"""SELECT n.id FROM nodes n
                    {base_where} AND n.id NOT IN ({ph})
                    ORDER BY (SELECT COUNT(*) FROM edges e
                              WHERE e.repository_id = ?
                              AND (e.source_node_id = n.id OR e.target_node_id = n.id)) DESC
                    LIMIT ?""",
                (*base_params, *all_ids, repo_id, limit - len(all_ids)),
            ).fetchall()
            for r in remaining:
                all_ids.append(r[0])

    final_ids = all_ids[:limit]
    if not final_ids:
        conn.close()
        empty = {"nodes": [], "edges": [], "total_nodes": 0, "total_edges": 0, "node_types": type_counts}
        click.echo(json.dumps(empty))
        return

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

    dir_rows = conn.execute(
        "SELECT file_path FROM nodes WHERE repository_id = ?"
        " AND node_type != 'directory' AND file_path IS NOT NULL",
        (repo_id,),
    ).fetchall()
    dir_counts: dict[str, int] = {}
    for (fp,) in dir_rows:
        d = fp.rsplit("/", 1)[0] if "/" in fp else "/"
        dir_counts[d] = dir_counts.get(d, 0) + 1

    conn.close()
    click.echo(json.dumps({
        "total_nodes": total_nodes,
        "total_edges": total_edges,
        "node_types": type_counts,
        "nodes": [{"id": n[0], "name": n[1], "type": n[2], "file_path": n[3]} for n in nodes_list],
        "edges": [{"source": e[0], "target": e[1], "type": e[2]} for e in edges],
        "directories": [{"path": p, "count": c}
                for p, c in sorted(dir_counts.items(), key=lambda x: -x[1])],
    }))


# ── watch command ────────────────────────────────────────────────────────────


@main.command()
@click.argument("path", default=".", type=click.Path(exists=True, file_okay=False))
@click.option("--verbose", "-v", is_flag=True, help="Show detailed change info")
@click.pass_context
def watch(ctx, path, verbose):
    """Watch a repository for file changes and auto-update the graph.

    Incrementally re-indexes and re-embeds files as they are modified,
    created, or deleted. Uses watchdog for filesystem monitoring.
    """
    db_path = ctx.obj["db_path"]
    from cartographer.storage.connection import get_connection
    _ensure_indexed(db_path)
    try:
        from watchdog.events import FileSystemEventHandler
        from watchdog.observers import Observer
    except ImportError:
        click.echo("Watch mode requires watchdog: pip install watchdog", err=True)
        raise click.Abort()

    from cartographer.ingestion.engine import update_index

    resolved = str(Path(path).resolve())

    conn = get_connection(db_path)
    repo_row = conn.execute(
        "SELECT id, name FROM repositories WHERE path = ?", (resolved,),
    ).fetchone()
    conn.close()

    if not repo_row:
        click.echo(f"Repository not found at {resolved}. Run 'cartographer index' first.")
        return

    repo_name = repo_row[1]
    _db_path = db_path
    _resolved = resolved

    class ChangeHandler(FileSystemEventHandler):
        def on_modified(self, event):
            if event.is_directory:
                return
            self._handle(event.src_path, "modified")

        def on_created(self, event):
            if event.is_directory:
                return
            self._handle(event.src_path, "created")

        def on_deleted(self, event):
            if event.is_directory:
                return
            self._handle(event.src_path, "deleted", is_deletion=True)

        def on_moved(self, event):
            if event.is_directory:
                return
            self._handle(event.dest_path, "moved")

        @staticmethod
        def _handle(file_path: str, change_type: str, is_deletion: bool = False):
            if not file_path.endswith((".py", ".js", ".ts", ".tsx", ".go", ".rs",
                                       ".java", ".kt", ".cs", ".php", ".rb",
                                       ".c", ".cpp", ".h", ".swift", ".scala",
                                       ".ex", ".lua", ".jl", ".zig", ".groovy")):
                return
            try:
                rel = str(Path(file_path).relative_to(_resolved))
            except ValueError:
                return

            if is_deletion:
                from cartographer.graph.builder import delete_file_from_graph
                conn = get_connection(_db_path)
                repo = conn.execute(
                    "SELECT id FROM repositories WHERE path = ?", (_resolved,),
                ).fetchone()
                if repo:
                    removed = delete_file_from_graph(conn, repo[0], rel)
                    conn.commit()
                    conn.close()
                    if removed:
                        click.echo(f"  deleted: {rel} ({removed} nodes removed)")
                return

            click.echo(f"  {change_type}: {rel}", err=True)
            result = update_index(file_path, db_path=_db_path)
            if verbose and result.get("parse_errors"):
                for e in result["parse_errors"]:
                    click.echo(f"    warning: {e}", err=True)
            nodes = result.get("nodes_added", 0)
            if nodes:
                click.echo(f"    graph: {result.get('nodes_removed', 0)} removed, "
                           f"{nodes} added", err=True)

    handler = ChangeHandler()
    observer = Observer()
    observer.schedule(handler, resolved, recursive=True)
    observer.start()
    click.echo(f"Watching {repo_name} for changes... (Ctrl+C to stop)")
    try:
        while observer.is_alive():
            observer.join(1)
    except KeyboardInterrupt:
        observer.stop()
    observer.join()


# ── repo management ──────────────────────────────────────────────────────────


@main.group()
def repo():
    """Manage indexed repositories."""


@repo.command("list")
@click.pass_context
def repo_list(ctx):
    """List all indexed repositories."""
    from cartographer.storage.connection import get_connection
    conn = get_connection(ctx.obj["db_path"])
    rows = conn.execute(
        """SELECT r.name, r.path,
                  (SELECT COUNT(*) FROM nodes WHERE repository_id = r.id) as node_count,
                  (SELECT COUNT(*) FROM edges WHERE repository_id = r.id) as edge_count
           FROM repositories r ORDER BY r.name"""
    ).fetchall()
    conn.close()
    if not rows:
        click.echo("No repositories indexed.")
        return
    click.echo(f"{'Name':<20} {'Nodes':<8} {'Edges':<8} Path")
    click.echo("-" * 80)
    for name, path, nodes, edges in rows:
        click.echo(f"{name:<20} {nodes:<8} {edges:<8} {path}")


@repo.command("remove")
@click.argument("name")
@click.option("--yes", "-y", is_flag=True, help="Skip confirmation")
@click.pass_context
def repo_remove(ctx, name, yes):
    """Remove a repository and all its data from the database."""
    from cartographer.storage.connection import get_connection
    conn = get_connection(ctx.obj["db_path"])

    row = conn.execute("SELECT id, path FROM repositories WHERE name = ?", (name,)).fetchone()
    if not row:
        click.echo(f"No repository found: {name}")
        return

    repo_id, repo_path = row
    total_nodes = conn.execute(
        "SELECT COUNT(*) FROM nodes WHERE repository_id = ?", (repo_id,)
    ).fetchone()[0]
    total_edges = conn.execute(
        "SELECT COUNT(*) FROM edges WHERE repository_id = ?", (repo_id,)
    ).fetchone()[0]

    if not yes:
        click.confirm(
            f"Remove '{name}' ({repo_path}) with {total_nodes} nodes"
            f" and {total_edges} edges?",
            abort=True,
        )

    conn.execute("DELETE FROM commit_authors WHERE repository_id = ?", (repo_id,))
    conn.execute(
        "DELETE FROM commit_files WHERE commit_id IN"
        " (SELECT id FROM commits WHERE repository_id = ?)",
        (repo_id,),
    )
    conn.execute("DELETE FROM commits WHERE repository_id = ?", (repo_id,))
    conn.execute("DELETE FROM architecture WHERE repository_id = ?", (repo_id,))
    invalidate_cache(ctx.obj["db_path"], name)
    conn.execute(
        "DELETE FROM embeddings WHERE node_id IN"
        " (SELECT id FROM nodes WHERE repository_id = ?)",
        (repo_id,),
    )
    conn.execute("DELETE FROM edges WHERE repository_id = ?", (repo_id,))
    conn.execute("DELETE FROM nodes WHERE repository_id = ?", (repo_id,))
    conn.execute("DELETE FROM repositories WHERE id = ?", (repo_id,))
    conn.commit()
    conn.close()

    click.echo(
        f"Removed '{name}' ({total_nodes} nodes, {total_edges} edges)"
    )


# ── db management ────────────────────────────────────────────────────────────


@main.group()
def db():
    """Manage the Cartographer database."""


@db.command("vacuum")
@click.pass_context
def db_vacuum(ctx):
    """Reclaim storage space by running VACUUM on the database."""
    from cartographer.storage.connection import get_connection
    db_path = ctx.obj["db_path"]

    before = db_path.stat().st_size if db_path.exists() else 0
    conn = get_connection(db_path)
    conn.execute("VACUUM")
    conn.close()
    after = db_path.stat().st_size

    saved = before - after
    if saved > 0:
        click.echo(
            f"Database shrunk: {_fmt_size(before)} → {_fmt_size(after)}"
            f" (saved {_fmt_size(saved)})"
        )
    else:
        click.echo(f"Database size: {_fmt_size(after)} (no savings)")


@db.command("info")
@click.pass_context
def db_info(ctx):
    """Show database statistics."""
    from cartographer.storage.connection import get_connection
    db_path = ctx.obj["db_path"]

    if not db_path.exists():
        click.echo("Database does not exist yet. Run 'cartographer init' first.")
        return

    size = db_path.stat().st_size
    conn = get_connection(db_path)

    repo_count = conn.execute("SELECT COUNT(*) FROM repositories").fetchone()[0]
    node_count = conn.execute("SELECT COUNT(*) FROM nodes").fetchone()[0]
    edge_count = conn.execute("SELECT COUNT(*) FROM edges").fetchone()[0]
    embed_count = conn.execute("SELECT COUNT(*) FROM embeddings").fetchone()[0]
    commit_count = conn.execute("SELECT COUNT(*) FROM commits").fetchone()[0]

    # Per-repo breakdown
    per_repo = conn.execute(
        """SELECT r.name,
                  (SELECT COUNT(*) FROM nodes WHERE repository_id = r.id) as nodes,
                  (SELECT COUNT(*) FROM edges WHERE repository_id = r.id) as edges
           FROM repositories r ORDER BY nodes DESC"""
    ).fetchall()

    conn.close()

    click.echo(f"Database: {db_path}")
    click.echo(f"Size: {_fmt_size(size)}")
    click.echo(f"Repositories: {repo_count}")
    click.echo(f"Total nodes: {node_count}")
    click.echo(f"Total edges: {edge_count}")
    click.echo(f"Embeddings: {embed_count}")
    click.echo(f"Commits: {commit_count}")
    if per_repo:
        click.echo()
        click.echo(f"{'Repository':<20} {'Nodes':<8} {'Edges':<8}")
        click.echo("-" * 40)
        for name, n, e in per_repo:
            click.echo(f"{name:<20} {n:<8} {e:<8}")


def _fmt_size(bytes_: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if bytes_ < 1024:
            return f"{bytes_:.1f}{unit}"
        bytes_ /= 1024
    return f"{bytes_:.1f}TB"


# ── update-index command ─────────────────────────────────────────────────────


@main.command()
@click.argument("file_path", type=click.Path(exists=True))
@click.pass_context
def update_index(ctx, file_path):
    """Incrementally re-index a single file after changes.

    Re-parses the file, updates the graph, and re-embeds changed nodes.
    """
    from cartographer.ingestion.engine import update_index as _update_index
    result = _update_index(file_path, db_path=ctx.obj["db_path"])
    click.echo(json.dumps(result))


# ── delete-file command ─────────────────────────────────────────────────────


@main.command()
@click.argument("file_path", type=click.Path(exists=False))
@click.pass_context
def delete_file(ctx, file_path):
    """Remove a deleted file from the graph and re-embed.

    Deletes all nodes belonging to the file and re-embeds remaining nodes.
    """
    from pathlib import Path as _Path
    from cartographer.graph.builder import delete_file_from_graph
    from cartographer.embedding.engine import generate_embeddings
    from cartographer.storage.connection import get_connection, init_schema

    db_path = ctx.obj["db_path"]
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
        click.echo(json.dumps({"error": "Repository not found for path"}))
        return

    repo_id, repo_path = repo_row[0], repo_row[1]
    rel_path = str(root.relative_to(repo_path))
    removed = delete_file_from_graph(conn, repo_id, rel_path)
    conn.commit()
    conn.close()

    embed_count = 0
    if removed > 0:
        new_count, _ = generate_embeddings(db_path)
        embed_count = new_count

    click.echo(json.dumps({"nodes_removed": removed, "embeddings_generated": embed_count}))


def _get_repo(ctx) -> tuple[str, str] | None:
    from cartographer.storage.connection import get_connection
    conn = get_connection(ctx.obj["db_path"])
    row = conn.execute("SELECT path, name FROM repositories LIMIT 1").fetchone()
    conn.close()
    return row
