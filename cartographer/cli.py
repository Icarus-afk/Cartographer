from __future__ import annotations

from pathlib import Path

import click

from cartographer.architecture.engine import detect_architecture, get_architecture
from cartographer.compression.engine import compress
from cartographer.core.models import EntityKind
from cartographer.embedding.engine import find_similar, generate_embeddings, similarity_search
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
    ctx.obj["db_path"] = Path(db) if db else Path.home() / ".cartographer" / "index.db"


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
@click.argument("from_name")
@click.argument("to_name")
@click.option("--max-depth", default=5)
@click.option("--max-tokens", "-m", default=0, type=int, help="Compress output to fit token budget")
@click.pass_context
def path(ctx, from_name, to_name, max_depth, max_tokens):
    """Find path between two nodes."""
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
    count = generate_embeddings(ctx.obj["db_path"], repo)
    click.echo(f"Embedded {count} nodes.")
    if count == 0:
        click.echo("All nodes already embedded (run with a new repo to embed).")


@main.command()
@click.argument("target")
@click.option("--repo", "-r", help="Repository name")
@click.option("--limit", "-l", default=20, help="Max results")
@click.pass_context
def similar(ctx, target, repo, limit):
    """Find semantically similar nodes."""
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
    result = execute_query(query_str, ctx.obj["db_path"], repo, limit, max_tokens)
    click.echo(result)


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


def _get_repo(ctx) -> tuple[str, str] | None:
    from cartographer.storage.connection import get_connection
    conn = get_connection(ctx.obj["db_path"])
    row = conn.execute("SELECT path, name FROM repositories LIMIT 1").fetchone()
    conn.close()
    return row
