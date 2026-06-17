"""Real-repo benchmark: indexes repos from test/repos/, measures performance,
runs architecture detection, generates embeddings, tests queries.

Usage:
    python -m tests.benchmark                  # full run
    python -m tests.benchmark --quick           # single repo
    python -m tests.benchmark --repo flask      # specific repo
    python -m tests.benchmark --output results.json  # save results as JSON
    python -m tests.benchmark --skip-embed      # skip embedding & queries
"""

import argparse
import json
import sqlite3
import sys
import time
from pathlib import Path

REPOS_DIR = Path(__file__).resolve().parent.parent / "test" / "repos"

REPO_QUERIES = {
    "flask": [
        ("How do I define URL routes", ["route", "Route"]),
        ("How to handle HTTP requests", ["Request", "Response"]),
        ("How to render HTML templates", ["template", "Template"]),
    ],
    "django": [
        ("How to define database models", ["Model"]),
        ("How to configure URL routing", ["URLResolver", "URLPattern", "url"]),
        ("How does user authentication work", ["auth", "authenticate"]),
    ],
    "fastapi": [
        ("How to create REST API endpoints", ["APIRouter", "router", "route"]),
        ("How does dependency injection work", ["Depends", "depend"]),
        ("How to validate request body data", ["Body", "validate", "model"]),
    ],
    "gin": [
        ("How to define HTTP routes", ["route", "Handler", "Engine"]),
        ("How to use middleware functions", ["middleware", "Middleware", "Use"]),
        ("How to access request context", ["Context", "context"]),
    ],
    "react": [
        ("How to use React hooks for state", ["useState", "UseState", "hook"]),
        ("How to handle component side effects", ["useEffect", "UseEffect"]),
        ("How does React render components", ["render", "Render", "ReactDOM"]),
    ],
    "redis": [
        ("How does Redis handle string commands", ["set", "get", "string"]),
        ("How does Redis allocate memory", ["zmalloc", "malloc", "alloc"]),
        ("How does the event loop work", ["ae", "event", "EventLoop"]),
    ],
    "tokio": [
        ("How to spawn async tasks", ["spawn", "task", "JoinHandle"]),
        ("How to use TCP networking", ["TcpListener", "TcpStream"]),
        ("How to create the async runtime", ["Runtime", "runtime"]),
    ],
    "serde": [
        ("How to serialize data structures", ["Serialize", "serialize"]),
        ("How to implement custom deserialization", ["Deserialize", "deserialize"]),
        ("How does the derive macro work", ["derive", "Derive"]),
    ],
    "hugo": [
        ("How to build a Hugo site", ["Site", "site", "build"]),
        ("How to render page templates", ["Page", "template", "render"]),
        ("How to configure Hugo", ["config", "Config"]),
    ],
    "spring-boot": [
        ("How to create a REST controller", ["Controller", "RestController"]),
        ("How does auto-configuration work", ["AutoConfiguration", "auto"]),
        ("How to inject dependencies", ["Autowired", "Inject", "bean"]),
    ],
    "junit5": [
        ("How to write a JUnit test", ["Test", "test"]),
        ("How to use parameterized tests", ["Parameterized", "parameterized"]),
        ("How to assert test results", ["Assert", "assert"]),
    ],
    "json": [
        ("How to parse JSON from string", ["parse", "json", "from"]),
        ("How to create JSON objects", ["object", "json", "object_t"]),
        ("How to access JSON values", ["value", "json", "get"]),
    ],
    "jansson": [
        ("How to create JSON objects", ["json_object", "json_string"]),
        ("How to parse JSON text", ["json_load", "load", "parse"]),
        ("How to serialize JSON to string", ["json_dump", "dump"]),
    ],
    "Humanizer": [
        ("How to convert numbers to words", ["ToWords", "Number", "words"]),
        ("How to format byte sizes", ["ByteSize", "byte"]),
        ("How to humanize dates", ["Date", "time", "humanize"]),
    ],
    "kotlinx.coroutines": [
        ("How to launch coroutines", ["launch", "async", "coroutine"]),
        ("How to collect data from Flow", ["Flow", "collect", "flow"]),
        ("How to handle coroutine cancellation", ["cancel", "cancellation"]),
    ],
    "cats": [
        ("How to use Functor type class", ["Functor", "functor"]),
        ("How to use Monad for sequencing", ["Monad", "monad", "flatMap"]),
        ("How to use effect types", ["IO", "Sync", "effect"]),
    ],
    "rspec-core": [
        ("How to define test examples", ["Example", "example"]),
        ("How to use before and after hooks", ["Hook", "before", "after"]),
        ("How to configure RSpec", ["config", "configure"]),
    ],
    "monolog": [
        ("How to create a Monolog logger", ["Logger", "logger"]),
        ("How to add log handlers", ["Handler", "handler"]),
        ("How to set log levels", ["Level", "level"]),
    ],
    "chalk": [
        ("How to style terminal text", ["Chalk", "color", "style"]),
        ("How to use ANSI colors", ["ansi", "color", "style"]),
        ("How to apply formatting", ["style", "format", "String"]),
    ],
    "plug": [
        ("How to define a connection", ["Conn", "conn"]),
        ("How to route HTTP requests", ["Router", "router"]),
        ("How to handle plug errors", ["exception", "error", "Exception"]),
    ],
    "luassert": [
        ("How to assert values in tests", ["assert", "assertion"]),
        ("How to spy on function calls", ["spy", "Spy"]),
        ("How to mock functions", ["mock", "Mock"]),
    ],
    "mdbook": [
        ("How to configure mdbook", ["Config", "config"]),
        ("How to implement a renderer", ["Renderer", "renderer"]),
        ("How to write a preprocessor", ["Preprocessor", "preprocess"]),
    ],
}

# Baseline expectations from the actual test/repos/ snapshots.
# These are real-world repos, but shallow-cloned at specific tags/commits,
# so file/node counts reflect the actual snapshot, not full history.
EXPECTED = {
    "flask": {"files": 80, "min_nodes": 800, "min_edges": 1000},
    "gin": {"files": 99, "min_nodes": 1200, "min_edges": 1200},
    "mdbook": {"files": 109, "min_nodes": 800, "min_edges": 1000},
    "plug": {"files": 77, "min_nodes": 80, "min_edges": 100},
    "luassert": {"files": 39, "min_nodes": 100, "min_edges": 100},
    "chalk": {"files": 13, "min_nodes": 40, "min_edges": 30},
    "json": {"files": 499, "min_nodes": 1500, "min_edges": 1500},
    "junit5": {"files": 1911, "min_nodes": 12000, "min_edges": 14000},
    "Humanizer": {"files": 469, "min_nodes": 4000, "min_edges": 4000},
    "monolog": {"files": 216, "min_nodes": 1400, "min_edges": 1400},
    "rspec-core": {"files": 223, "min_nodes": 200, "min_edges": 300},
    "cats": {"files": 836, "min_nodes": 7000, "min_edges": 7000},
    "jansson": {"files": 51, "min_nodes": 400, "min_edges": 400},
    "kotlinx.coroutines": {"files": 1104, "min_nodes": 2000, "min_edges": 2000},
    "serde": {"files": 208, "min_nodes": 2000, "min_edges": 2000},
    "tokio": {"files": 784, "min_nodes": 9000, "min_edges": 10000},
    "redis": {"files": 866, "min_nodes": 8000, "min_edges": 10000},
    "fastapi": {"files": 944, "min_nodes": 5000, "min_edges": 7000},
    "hugo": {"files": 929, "min_nodes": 8000, "min_edges": 8000},
    "django": {"files": 2356, "min_nodes": 35000, "min_edges": 60000},
    "react": {"files": 4588, "min_nodes": 20000, "min_edges": 20000},
    "spring-boot": {"files": 8790, "min_nodes": 50000, "min_edges": 50000},
}


def _fmt(ms: float) -> str:
    return f"{ms:.0f}"


def _index_repo(repo_name: str, repo_path: Path, db_path: Path) -> dict:
    from cartographer.ingestion.engine import index_repository

    start = time.perf_counter()
    result = index_repository(str(repo_path), db_path=str(db_path))
    elapsed = (time.perf_counter() - start) * 1000

    conn = sqlite3.connect(str(db_path))
    nodes = conn.execute("SELECT COUNT(*) FROM nodes").fetchone()[0]
    edges = conn.execute("SELECT COUNT(*) FROM edges").fetchone()[0]
    conn.close()

    return {
        "name": repo_name,
        "files": result.manifest.total_files if result.manifest else 0,
        "dirs": result.manifest.total_dirs if result.manifest else 0,
        "duration_ms": round(elapsed),
        "nodes": nodes,
        "edges": edges,
        "success": result.success,
        "errors": result.errors,
    }


def _embed_repo(repo_name: str, db_path: Path) -> dict:
    from cartographer.embedding.engine import generate_embeddings

    start = time.perf_counter()
    new_count, existing_count = generate_embeddings(db_path, repo_name)
    elapsed = (time.perf_counter() - start) * 1000
    return {
        "new": new_count,
        "existing": existing_count,
        "duration_ms": round(elapsed),
    }


def _run_queries(repo_name: str, db_path: Path, queries: list) -> list:
    from cartographer.embedding.engine import similarity_search
    from cartographer.retrieval.searcher import search_nodes

    results = []
    for query, expected_kws in queries:
        s_start = time.perf_counter()
        s_results = similarity_search(db_path, query, limit=5, repo_name=repo_name)
        s_time = (time.perf_counter() - s_start) * 1000
        s_top1 = s_results[0]["name"] if s_results else None
        s_top1_score = s_results[0]["similarity"] if s_results else 0
        s_relevant = bool(
            s_results
            and any(
                any(kw.lower() in r.get("name", "").lower() for kw in expected_kws)
                for r in s_results[:5]
            )
        )

        k_start = time.perf_counter()
        k_results = search_nodes(query, str(db_path), repo_name=repo_name, limit=5)
        k_time = (time.perf_counter() - k_start) * 1000
        k_top1 = k_results[0]["name"] if k_results else None
        k_relevant = bool(
            k_results
            and any(
                any(kw.lower() in r.get("name", "").lower() for kw in expected_kws)
                for r in k_results[:5]
            )
        )

        results.append(
            {
                "query": query,
                "s_top1": s_top1,
                "s_score": s_top1_score,
                "s_relevant": s_relevant,
                "s_ms": round(s_time, 1),
                "k_top1": k_top1,
                "k_relevant": k_relevant,
                "k_ms": round(k_time, 1),
            }
        )
    return results


def _detect_architecture(repo_name: str, db_path: Path) -> dict:
    from cartographer.architecture.engine import detect_architecture

    arch = detect_architecture(str(db_path), repo_name)
    return arch


def _search(repo_name: str, db_path: Path, query: str) -> list:
    from cartographer.retrieval.searcher import search_nodes

    out = search_nodes(query, str(db_path), repo_name=repo_name)
    return out


def _verify(stats: dict, expected: dict) -> list[str]:
    issues = []
    if stats["files"] < expected["files"] * 0.8:
        issues.append(
            f"  File count {stats['files']} < 80% of expected {expected['files']}"
        )
    if stats["nodes"] < expected["min_nodes"]:
        issues.append(
            f"  Node count {stats['nodes']} < min {expected['min_nodes']}"
        )
    if stats["edges"] < expected["min_edges"]:
        issues.append(
            f"  Edge count {stats['edges']} < min {expected['min_edges']}"
        )
    if not stats["success"]:
        issues.append(f"  Index did not complete successfully")
    return issues


def _measure_source(repo_path: Path, repo_name: str) -> dict:
    total_chars = 0
    total_bytes = 0
    file_count = 0
    exts: dict[str, int] = {}
    for f in repo_path.rglob("*"):
        if not f.is_file() or f.name.startswith("."):
            continue
        try:
            b = f.read_bytes()
            total_bytes += len(b)
            total_chars += len(b.decode("utf-8", errors="replace"))
            file_count += 1
            ext = f.suffix.lower() or "(no ext)"
            exts[ext] = exts.get(ext, 0) + 1
        except (OSError, UnicodeDecodeError):
            pass
    return {
        "repo": repo_name,
        "files": file_count,
        "chars": total_chars,
        "bytes": total_bytes,
        "tokens_est": total_chars // 3,
        "extensions": exts,
    }


def _run_benchmark(repo_name: str, repo_path: Path, tmpdir: Path, skip_embed: bool = False) -> dict:
    db_path = tmpdir / f"{repo_name}.db"
    print(f"  Indexing...", end=" ", flush=True)
    stats = _index_repo(repo_name, repo_path, db_path)
    print(f"{stats['duration_ms']}ms, {stats['nodes']} nodes, {stats['edges']} edges")

    catastrophic = [e for e in stats["errors"] if "catastrophic" in e]
    moderate = [e for e in stats["errors"] if "catastrophic" not in e]
    for err in catastrophic:
        print(f"    Parse catastrophic: {err}")
    if moderate:
        print(f"    Parse warnings: {len(stats['errors'])} files with errors")

    expected = EXPECTED.get(repo_name, {})
    issues = _verify(stats, expected)
    for i in issues:
        print(f"    {i}")
    stats["issues"] = issues

    if stats["success"]:
        source = _measure_source(repo_path, repo_name)
        stats["source"] = source
        print(f"  Source: {source['chars']:,} chars, ~{source['tokens_est']:,} tokens")

        print(f"  Architecture detection...", end=" ", flush=True)
        arch = _detect_architecture(repo_name, db_path)
        layer_names = set(arch.get("layers", {}).keys())
        pattern_names = {p["name"] for p in arch.get("patterns", [])}
        stats["architecture"] = {"layers": len(layer_names), "patterns": len(pattern_names)}
        print(f"{len(layer_names)} layers, {len(pattern_names)} patterns")

        print(f"  Search ('class' query)...", end=" ", flush=True)
        results = _search(repo_name, db_path, "class")
        stats["search_results"] = len(results)
        print(f"{len(results)} results")

        if not skip_embed:
            embed = _embed_repo(repo_name, db_path)
            stats["embed_ms"] = embed["duration_ms"]
            stats["embed_nodes"] = embed["new"]
            print(f"  Embedding... {embed['new']} nodes in {embed['duration_ms']}ms")

            queries = REPO_QUERIES.get(repo_name, [])
            if queries:
                q_results = _run_queries(repo_name, db_path, queries)
                q_passed = sum(1 for q in q_results if q["s_relevant"])
                stats["queries"] = {"total": len(queries), "passed": q_passed, "results": q_results}
                for q in q_results:
                    sym = "✓" if q["s_relevant"] else "✗"
                    print(f"    {sym} \"{q['query']}\" -> {q['s_top1']} ({q['s_score']:.2f}) [{q['s_ms']}ms]" if q["s_top1"]
                          else f"    {sym} \"{q['query']}\" -> no results [{q['s_ms']}ms]")

    return stats


def main():
    parser = argparse.ArgumentParser(description="Cartographer benchmark")
    parser.add_argument("--quick", action="store_true", help="Run on first repo only")
    parser.add_argument("--repo", type=str, default=None, help="Run on specific repo")
    parser.add_argument("--output", type=str, default=None, help="Save results as JSON")
    parser.add_argument("--skip-embed", action="store_true", help="Skip embedding and queries")
    args = parser.parse_args()

    repos = sorted(
        (d.name, d)
        for d in REPOS_DIR.iterdir()
        if d.is_dir() and not d.name.startswith(".")
    )

    if args.repo:
        repos = [(n, p) for n, p in repos if n == args.repo]
        if not repos:
            print(f"Repo '{args.repo}' not found in test/repos/")
            sys.exit(1)

    if args.quick:
        repos = repos[:1]

    import tempfile

    with tempfile.TemporaryDirectory() as td:
        tmpdir = Path(td)
        all_stats = []
        failed = 0

        for name, path in repos:
            print(f"\n{'='*60}")
            print(f"  {name}")
            print(f"{'='*60}")
            stats = _run_benchmark(name, path, tmpdir, skip_embed=args.skip_embed)
            all_stats.append(stats)
            if stats["issues"]:
                failed += 1

        passed = len(all_stats) - failed
        total = len(all_stats)
        print(f"\n{'='*60}")
        print(f"  Results: {passed}/{total} passed")
        if failed:
            print(f"  {failed} failed")
        print(f"{'='*60}")

        if total > 0:
            avg_ms = sum(s["duration_ms"] for s in all_stats) / total
            total_nodes = sum(s["nodes"] for s in all_stats)
            total_edges = sum(s["edges"] for s in all_stats)
            total_files = sum(s["files"] for s in all_stats)
            total_time = sum(s["duration_ms"] for s in all_stats)
            total_embed_ms = sum(s.get("embed_ms", 0) for s in all_stats)
            total_queries = sum(s.get("queries", {}).get("total", 0) for s in all_stats)
            total_q_passed = sum(s.get("queries", {}).get("passed", 0) for s in all_stats)
            total_chars = sum(s.get("source", {}).get("chars", 0) for s in all_stats)
            total_tokens = sum(s.get("source", {}).get("tokens_est", 0) for s in all_stats)
            total_bytes = sum(s.get("source", {}).get("bytes", 0) for s in all_stats)
            print(f"  Total files: {total_files}")
            print(f"  Total time: {total_time}ms  (embed: {total_embed_ms}ms)")
            print(f"  Total nodes: {total_nodes}")
            print(f"  Total edges: {total_edges}")
            print(f"  Search queries: {total_q_passed}/{total_queries} relevant")
            print(f"  Total source: {total_chars:,} chars, ~{total_tokens:,} tokens, {total_bytes/1024/1024:.1f}MB")
            print(f"  Avg time/repo: {avg_ms:.0f}ms")
            if total_time > 0:
                print(
                    f"  Throughput: {total_files / (total_time / 1000):.1f} files/s"
                )

        if args.output:
            out = {
                "repos": all_stats,
                "summary": {
                    "passed": passed,
                    "total": total,
                    "total_files": total_files,
                    "total_nodes": total_nodes,
                    "total_edges": total_edges,
                    "total_time_ms": total_time,
                    "total_embed_ms": total_embed_ms,
                    "total_chars": total_chars,
                    "total_tokens_est": total_tokens,
                    "total_bytes": total_bytes,
                    "queries_passed": total_q_passed,
                    "queries_total": total_queries,
                },
            }
            outpath = Path(args.output)
            with open(outpath, "w") as f:
                json.dump(out, f, indent=2, default=str)
            print(f"\nResults saved to {outpath}")

        sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
