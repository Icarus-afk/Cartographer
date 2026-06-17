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
        ("How to handle form submissions", ["form", "Form"]),
        ("How to set up error handlers", ["error", "Error"]),
        ("How to manage user sessions", ["session", "Session"]),
        ("How to create JSON API responses", ["json", "JSON", "jsonify"]),
        ("How to handle file uploads", ["upload", "Upload", "file"]),
        ("How to run background tasks", ["App", "run", "background"]),
        ("How to log application messages", ["log", "Log", "logger"]),
    ],
    "django": [
        ("How to define database models", ["Model"]),
        ("How to configure URL routing", ["URLResolver", "URLPattern", "url"]),
        ("How does user authentication work", ["auth", "authenticate"]),
        ("How to create database migrations", ["migration", "Migration"]),
        ("How to use Django admin interface", ["Admin", "admin"]),
        ("How to handle file storage", ["Storage", "File", "storage"]),
        ("How to write custom management commands", ["Command", "BaseCommand"]),
        ("How to validate form data", ["Form", "form", "clean"]),
        ("How to use template tags", ["tag", "Tag", "template"]),
        ("How to configure database settings", ["Database", "database"]),
    ],
    "fastapi": [
        ("How to create REST API endpoints", ["APIRouter", "router", "route"]),
        ("How does dependency injection work", ["Depends", "depend"]),
        ("How to validate request body data", ["Body", "validate", "model"]),
        ("How to handle WebSocket connections", ["WebSocket", "websocket"]),
        ("How to add authentication to routes", ["Security", "security", "auth"]),
        ("How to serve static files", ["Static", "static", "file"]),
        ("How to configure CORS middleware", ["CORS", "cors", "middleware"]),
        ("How to document API endpoints", ["OpenAPI", "doc", "Schema"]),
        ("How to handle file uploads", ["Upload", "File", "upload"]),
        ("How to set up background tasks", ["Background", "background", "task"]),
    ],
    "gin": [
        ("How to define HTTP routes", ["route", "Handler", "Engine"]),
        ("How to use middleware functions", ["middleware", "Middleware", "Use"]),
        ("How to access request context", ["Context", "context"]),
        ("How to validate request parameters", ["ShouldBind", "valid", "bind"]),
        ("How to serve static assets", ["Static", "static", "FileSystem"]),
        ("How to handle JSON requests", ["JSON", "json"]),
        ("How to group related routes", ["Group", "RouterGroup"]),
        ("How to handle HTTP errors gracefully", ["Error", "Abort", "AbortWithStatus"]),
        ("How to set custom response headers", ["Header", "Response"]),
        ("How to run tests with test HTTP server", ["TestHTTP", "httptest", "NewRecorder"]),
    ],
    "react": [
        ("How to use React hooks for state", ["useState", "UseState", "hook"]),
        ("How to handle component side effects", ["useEffect", "UseEffect"]),
        ("How does React render components", ["render", "Render", "ReactDOM"]),
        ("How to optimize component performance", ["memo", "Memo", "useMemo"]),
        ("How to manage global state", ["Context", "Provider", "context"]),
        ("How to handle form inputs", ["input", "Input", "onChange"]),
        ("How to create refs to DOM elements", ["ref", "Ref", "useRef"]),
        ("How to handle keyboard events", ["Keyboard", "keyboard", "onKey"]),
        ("How to implement error boundaries", ["ErrorBoundary", "componentDidCatch"]),
        ("How to test React components", ["Test", "render", "act"]),
    ],
    "redis": [
        ("How does Redis handle string commands", ["set", "get", "string"]),
        ("How does Redis allocate memory", ["zmalloc", "malloc", "alloc"]),
        ("How does the event loop work", ["ae", "event", "EventLoop"]),
        ("How does Redis persist data to disk", ["rdb", "aof", "save", "persist"]),
        ("How does Redis handle hash data structures", ["hash", "Hash", "hset"]),
        ("How does Redis manage client connections", ["client", "Client", "networking"]),
        ("How does Redis implement sorted sets", ["zskiplist", "zset", "ZSet"]),
        ("How does Redis handle replication", ["replication", "Replication", "replica"]),
        ("How does Redis manage pub/sub messaging", ["pubsub", "PubSub", "publish"]),
        ("How does Redis implement transactions", ["transaction", "multi", "MULTI"]),
    ],
    "tokio": [
        ("How to spawn async tasks", ["spawn", "task", "JoinHandle"]),
        ("How to use TCP networking", ["TcpListener", "TcpStream"]),
        ("How to create the async runtime", ["Runtime", "runtime"]),
        ("How to use async I/O with files", ["File", "AsyncRead", "AsyncWrite"]),
        ("How to create UDP sockets", ["UdpSocket", "Udp"]),
        ("How to synchronize tasks with mutex", ["Mutex", "mutex", "Lock"]),
        ("How to use channels for communication", ["channel", "Channel", "Sender"]),
        ("How to handle timeouts and delays", ["timeout", "Timeout", "sleep"]),
        ("How to spawn blocking tasks", ["spawn_blocking", "blocking", "block"]),
        ("How to use async signals", ["Signal", "signal", "CtrlC"]),
    ],
    "serde": [
        ("How to serialize data structures", ["Serialize", "serialize"]),
        ("How to implement custom deserialization", ["Deserialize", "deserialize"]),
        ("How does the derive macro work", ["derive", "Derive"]),
        ("How to serialize to JSON format", ["json", "JSON", "to_writer"]),
        ("How to handle optional fields", ["Option", "skip", "default"]),
        ("How to rename fields during serialization", ["rename", "Rename", "rename_all"]),
        ("How to serialize enum variants", ["enum", "Enum", "variant"]),
        ("How to flatten nested structures", ["flatten", "Flatten"]),
        ("How to handle untagged enums", ["untagged", "Untagged", "tag"]),
        ("How to use serde with YAML", ["yaml", "YAML"]),
    ],
    "hugo": [
        ("How to build a Hugo site", ["Site", "site", "build"]),
        ("How to render page templates", ["Page", "template", "render"]),
        ("How to configure Hugo", ["config", "Config"]),
        ("How to create custom shortcodes", ["Shortcode", "shortcode"]),
        ("How to organize content sections", ["Section", "section", "content"]),
        ("How to implement multilingual sites", ["multilingual", "Multilingual", "lang"]),
        ("How to use Hugo themes", ["Theme", "theme"]),
        ("How to generate categorized taxonomies", ["Taxonomy", "taxonomy", "tag"]),
        ("How to build sitemaps", ["Sitemap", "sitemap"]),
        ("How to create RSS feeds", ["RSS", "rss", "feed"]),
    ],
    "spring-boot": [
        ("How to create a REST controller", ["Controller", "RestController"]),
        ("How does auto-configuration work", ["AutoConfiguration", "auto"]),
        ("How to inject dependencies", ["Autowired", "Inject", "bean"]),
        ("How to create database repositories", ["Repository", "repository"]),
        ("How to configure application properties", ["Property", "property", "properties"]),
        ("How to handle exceptions globally", ["ExceptionHandler", "ControllerAdvice"]),
        ("How to use Spring Data JPA", ["JPA", "Entity", "entity"]),
        ("How to configure security", ["Security", "security", "WebSecurity"]),
        ("How to create scheduled tasks", ["Scheduled", "scheduler", "Scheduling"]),
        ("How to use WebFlux for reactive apps", ["WebFlux", "Reactive", "react"]),
    ],
    "junit5": [
        ("How to write a JUnit test", ["Test", "test"]),
        ("How to use parameterized tests", ["Parameterized", "parameterized"]),
        ("How to assert test results", ["Assert", "assert"]),
        ("How to use lifecycle hooks", ["Before", "After", "BeforeEach"]),
        ("How to write nested test classes", ["Nested", "nested"]),
        ("How to repeat tests multiple times", ["Repeated", "repeated", "RepeatedTest"]),
        ("How to handle test timeouts", ["Timeout", "timeout"]),
        ("How to conditionally disable tests", ["Disabled", "disabled", "condition"]),
        ("How to use extension model", ["Extension", "extend"]),
        ("How to write dynamic tests", ["Dynamic", "dynamic", "TestFactory"]),
    ],
    "json": [
        ("How to parse JSON from string", ["parse", "json", "from"]),
        ("How to create JSON objects", ["object", "json", "object_t"]),
        ("How to access JSON values", ["value", "json", "get"]),
        ("How to validate JSON documents", ["valid", "Valid", "check"]),
        ("How to merge two JSON objects", ["merge", "Merge", "object"]),
        ("How to convert JSON to pretty formatted string", ["pretty", "Pretty", "format"]),
        ("How to compare JSON objects", ["equal", "Equal", "compare"]),
        ("How to patch JSON documents", ["patch", "Patch", "merge_patch"]),
        ("How to work with JSON arrays", ["array", "Array"]),
        ("How to serialize JSON arrays", ["array", "Array", "append"]),
    ],
    "jansson": [
        ("How to create JSON objects", ["json_object", "json_string"]),
        ("How to parse JSON text", ["json_load", "load", "parse"]),
        ("How to serialize JSON to string", ["json_dump", "dump"]),
        ("How to create JSON arrays", ["json_array", "array"]),
        ("How to check JSON type", ["json_type", "type", "typeof"]),
        ("How to pack values into JSON", ["json_pack", "pack"]),
        ("How to unpack JSON into values", ["json_unpack", "unpack"]),
        ("How to increment reference counts", ["json_incref", "incref", "refcount"]),
        ("How to iterate over JSON objects", ["json_object_iter", "iter"]),
        ("How to encode JSON with sorting", ["json_dumps", "encode", "sort"]),
    ],
    "Humanizer": [
        ("How to convert numbers to words", ["ToWords", "Number", "words"]),
        ("How to format byte sizes", ["ByteSize", "byte"]),
        ("How to humanize dates", ["Date", "time", "humanize"]),
        ("How to pluralize English words", ["Pluralize", "plural"]),
        ("How to convert strings to title case", ["Title", "title", "ToTitle"]),
        ("How to format time spans", ["TimeSpan", "time", "span"]),
        ("How to truncate long text", ["Truncate", "truncat"]),
        ("How to romanize numbers", ["Roman", "roman", "ToRoman"]),
        ("How to format collections", ["Collection", "collection"]),
        ("How to convert casing styles", ["Casing", "casing", "PascalCase"]),
    ],
    "kotlinx.coroutines": [
        ("How to launch coroutines", ["launch", "async", "coroutine"]),
        ("How to collect data from Flow", ["Flow", "collect", "flow"]),
        ("How to handle coroutine cancellation", ["cancel", "cancellation"]),
        ("How to use coroutine channels", ["Channel", "channel", "Send"]),
        ("How to wait for multiple coroutines", ["await", "async", "join"]),
        ("How to handle coroutine exceptions", ["exception", "Exception", "Supervisor"]),
        ("How to use coroutine dispatchers", ["Dispatchers", "dispatcher"]),
        ("How to create a coroutine scope", ["CoroutineScope", "scope"]),
        ("How to use mutex with coroutines", ["Mutex", "mutex"]),
        ("How to combine multiple flows", ["combine", "Combine", "zip"]),
    ],
    "cats": [
        ("How to use Functor type class", ["Functor", "functor"]),
        ("How to use Monad for sequencing", ["Monad", "monad", "flatMap"]),
        ("How to use effect types", ["IO", "Sync", "effect"]),
        ("How to use Applicative functor", ["Applicative", "applicative"]),
        ("How to traverse collections", ["Traverse", "traverse"]),
        ("How to use Semigroup for combining", ["Semigroup", "semigroup"]),
        ("How to use Monoid for default values", ["Monoid", "monoid"]),
        ("How to use Either for error handling", ["Either", "either"]),
        ("How to use Option for nullable values", ["Option", "option"]),
        ("How to use Validated for error accumulation", ["Validated", "validated"]),
    ],
    "rspec-core": [
        ("How to define test examples", ["Example", "example"]),
        ("How to use before and after hooks", ["Hook", "before", "after"]),
        ("How to configure RSpec", ["config", "configure"]),
        ("How to define shared examples", ["shared", "Shared", "shared_examples"]),
        ("How to use let and let bang", ["let", "Let"]),
        ("How to set up test metadata", ["metadata", "Metadata"]),
        ("How to filter tests by tags", ["filter", "Filter", "tag"]),
        ("How to mock method calls", ["allow", "receive", "mock"]),
        ("How to test for exceptions", ["raise", "exception", "Error"]),
        ("How to define subject under test", ["subject", "Subject"]),
    ],
    "monolog": [
        ("How to create a Monolog logger", ["Logger", "logger"]),
        ("How to add log handlers", ["Handler", "handler"]),
        ("How to set log levels", ["Level", "level"]),
        ("How to format log output", ["Formatter", "formatter"]),
        ("How to filter log messages", ["Filter", "filter"]),
        ("How to write logs to files", ["StreamHandler", "stream", "file"]),
        ("How to send logs via email", ["Mail", "mail", "SwiftMailer"]),
        ("How to log to Slack", ["Slack", "slack", "webhook"]),
        ("How to add contextual data", ["Processor", "processor", "context"]),
        ("How to set up log channels", ["Channel", "channel"]),
    ],
    "chalk": [
        ("How to style terminal text", ["Chalk", "color", "style"]),
        ("How to use ANSI colors", ["ansi", "color", "style"]),
        ("How to apply formatting", ["style", "format", "String"]),
        ("How to add background colors", ["background", "bg", "bgColor"]),
        ("How to make text bold", ["bold", "Bold"]),
        ("How to underline text", ["underline", "Underline"]),
        ("How to chain multiple styles", ["chain", "Chalk", "pipe"]),
        ("How to create color gradients", ["gradient", "Gradient"]),
        ("How to detect color support", ["color", "Color", "level", "support"]),
        ("How to strip ANSI codes from text", ["strip", "Strip"]),
    ],
    "plug": [
        ("How to define a connection", ["Conn", "conn"]),
        ("How to route HTTP requests", ["Router", "router"]),
        ("How to handle plug errors", ["exception", "error", "Exception"]),
        ("How to send HTTP responses", ["send", "Send", "resp"]),
        ("How to parse request parameters", ["params", "Params", "fetch"]),
        ("How to work with request cookies", ["cookie", "Cookie"]),
        ("How to set response headers", ["header", "Header", "put"]),
        ("How to halt request processing", ["halt", "Halt"]),
        ("How to create custom plugs", ["Plug", "call"]),
        ("How to build WebSocket support", ["WebSocket", "websocket"]),
    ],
    "luassert": [
        ("How to assert values in tests", ["assert", "assertion"]),
        ("How to spy on function calls", ["spy", "Spy"]),
        ("How to mock functions", ["mock", "Mock"]),
        ("How to stub method behavior", ["stub", "Stub"]),
        ("How to match error messages", ["error", "Error", "match"]),
        ("How to assert table contents", ["table", "Table", "assert"]),
        ("How to assert boolean conditions", ["True", "False", "boolean"]),
        ("How to assert approximate equality", ["approximate", "approx"]),
        ("How to set up teardown hooks", ["teardown", "Teardown", "after"]),
        ("How to assert function throws", ["throws", "error", "has_error"]),
    ],
    "mdbook": [
        ("How to configure mdbook", ["Config", "config"]),
        ("How to implement a renderer", ["Renderer", "renderer"]),
        ("How to write a preprocessor", ["Preprocessor", "preprocess"]),
        ("How to customize the book theme", ["Theme", "theme", "custom"]),
        ("How to add search functionality", ["Search", "search"]),
        ("How to parse markdown chapters", ["Chapter", "chapter"]),
        ("How to build a summary file", ["Summary", "summary"]),
        ("How to handle multiple languages", ["language", "Language", "multi"]),
        ("How to add custom CSS", ["CSS", "css", "style"]),
        ("How to generate EPUB output", ["EPUB", "epub"]),
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
        def _match_kws(r: dict, kws: list[str]) -> bool:
            text = (r.get("name", "") + " " + r.get("file_path", "")).lower()
            return any(kw.lower() in text for kw in kws)

        s_relevant = bool(
            s_results
            and (
                s_top1_score > 0.7
                or any(_match_kws(r, expected_kws) for r in s_results[:5])
            )
        )

        k_start = time.perf_counter()
        k_results = search_nodes(query, str(db_path), repo_name=repo_name, limit=5)
        k_time = (time.perf_counter() - k_start) * 1000
        k_top1 = k_results[0]["name"] if k_results else None
        k_relevant = bool(
            k_results
            and any(_match_kws(r, expected_kws) for r in k_results[:5])
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
        issues.append("  Index did not complete successfully")
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
    print("  Indexing...", end=" ", flush=True)
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

        print("  Architecture detection...", end=" ", flush=True)
        arch = _detect_architecture(repo_name, db_path)
        layer_names = set(arch.get("layers", {}).keys())
        pattern_names = {p["name"] for p in arch.get("patterns", [])}
        stats["architecture"] = {"layers": len(layer_names), "patterns": len(pattern_names)}
        print(f"{len(layer_names)} layers, {len(pattern_names)} patterns")

        print("  Search ('class' query)...", end=" ", flush=True)
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
