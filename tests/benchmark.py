"""Real-repo benchmark: indexes 14 repos from test/repos/, measures performance,
runs architecture detection, and verifies results against documented baselines.

Usage:
    python -m tests.benchmark                 # full run
    python -m tests.benchmark --quick          # single repo
    python -m tests.benchmark --repo flask     # specific repo
"""

import argparse
import sqlite3
import sys
import time
from pathlib import Path

REPOS_DIR = Path(__file__).resolve().parent.parent / "test" / "repos"

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


def _run_benchmark(repo_name: str, repo_path: Path, tmpdir: Path) -> dict:
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
        print(f"  Architecture detection...", end=" ", flush=True)
        arch = _detect_architecture(repo_name, db_path)
        layer_names = set(arch.get("layers", {}).keys())
        pattern_names = {p["name"] for p in arch.get("patterns", [])}
        print(f"{len(layer_names)} layers, {len(pattern_names)} patterns")

        print(f"  Search ('class' query)...", end=" ", flush=True)
        results = _search(repo_name, db_path, "class")
        print(f"{len(results)} results")

    return stats


def main():
    parser = argparse.ArgumentParser(description="Cartographer benchmark")
    parser.add_argument("--quick", action="store_true", help="Run on first repo only")
    parser.add_argument("--repo", type=str, default=None, help="Run on specific repo")
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
            stats = _run_benchmark(name, path, tmpdir)
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
            print(f"  Total files: {total_files}")
            print(f"  Total time: {total_time}ms")
            print(f"  Total nodes: {total_nodes}")
            print(f"  Total edges: {total_edges}")
            print(f"  Avg time/repo: {avg_ms:.0f}ms")
            if total_time > 0:
                print(
                    f"  Throughput: {total_files / (total_time / 1000):.1f} files/s"
                )

        sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
