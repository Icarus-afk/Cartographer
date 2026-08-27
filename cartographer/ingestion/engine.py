import logging
import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from cartographer.core.models import IngestionResult, Language, ParsedFile, RepositoryManifest
from cartographer.graph.builder import build_graph
from cartographer.ingestion.discoverer import (
    detect_build_systems,
    detect_languages,
    detect_monorepo,
    detect_package_managers,
    discover_files,
)
from cartographer.ingestion.fingerprint import fingerprint_frameworks
from cartographer.ingestion.references import extract_references
from cartographer.ingestion.schema import extract_schema
from cartographer.parser.registry import get_parser, supported_languages

logger = logging.getLogger(__name__)


def index_repository(
    path: str | Path, db_path: Path | None = None, parse: bool = True
) -> IngestionResult:
    root = Path(path).resolve()
    if not root.is_dir():
        return IngestionResult(
            path=str(root),
            manifest=None,
            success=False,
            errors=[f"Not a directory: {root}"],
        )

    start = time.perf_counter()
    errors: list[str] = []

    try:
        logger.info("Discovering files in %s...", root)
        files = discover_files(root)
        logger.info("Found %d files", len(files))
    except Exception as e:
        return IngestionResult(
            path=str(root),
            manifest=None,
            success=False,
            errors=[f"File discovery failed: {e}"],
        )

    logger.info("Detecting project metadata...")
    lang_counts = detect_languages(files)
    package_managers = detect_package_managers(root)
    build_systems = detect_build_systems(root)
    is_monorepo, mono_tool = detect_monorepo(root)
    frameworks = fingerprint_frameworks(root)

    dirs: set[Path] = set()
    for f in files:
        parent = f.parent
        while parent != root:
            dirs.add(parent)
            parent = parent.parent
    dir_count = len(dirs)

    manifest = RepositoryManifest(
        languages=lang_counts,
        frameworks=frameworks,
        package_managers=package_managers,
        build_systems=build_systems,
        is_monorepo=is_monorepo,
        monorepo_tool=mono_tool,
        total_files=len(files),
        total_dirs=dir_count,
    )

    parsed_files: list[ParsedFile] = []
    references: list[dict] = []
    if parse:
        parsed_files = _parse_repository(files, root, errors)

        if parsed_files:
            try:
                logger.info("Extracting cross-file references...")
                references = extract_references(root, parsed_files, files)
                logger.info("Found %d references", len(references))
            except Exception as e:
                errors.append(f"Reference extraction failed: {e}")

        if parsed_files:
            try:
                logger.info("Extracting schema...")
                extract_schema(parsed_files, files, root)
            except Exception as e:
                errors.append(f"Schema extraction failed: {e}")

        if db_path is None:
            db_path_obj = Path.home() / ".cartographer" / "index.db"
        else:
            db_path_obj = Path(db_path)
        manifest.total_references = len(references)
        try:
            logger.info("Building knowledge graph...")
            stats = build_graph(db_path_obj, str(root), parsed_files, references, manifest)
            manifest.total_files = stats.get("files", len(files))
            logger.info("Graph built: %d nodes, %d edges",
                        stats.get("nodes", 0), stats.get("edges", 0))
        except Exception as e:
            errors.append(f"Graph build failed: {e}")

    elapsed = (time.perf_counter() - start) * 1000

    fatal_errors = [e for e in errors if not (
        e.startswith("Parse ") or e.startswith("Failed to parse")
    )]
    return IngestionResult(
        path=str(root),
        manifest=manifest,
        parsed_files=parsed_files,
        success=len(fatal_errors) == 0,
        errors=errors,
        duration_ms=round(elapsed, 2),
    )



_LANG_EXTENSIONS: dict[Language, tuple[str, ...]] = {
    Language.PYTHON: (".py",),
    Language.JAVASCRIPT: (".js", ".jsx", ".mjs", ".cjs"),
    Language.TYPESCRIPT: (".ts",),
    Language.TSX: (".tsx",),
    Language.GO: (".go",),
    Language.RUST: (".rs",),
    Language.JAVA: (".java",),
    Language.KOTLIN: (".kt", ".kts"),
    Language.CSHARP: (".cs",),
    Language.PHP: (".php", ".phtml"),
    Language.RUBY: (".rb",),
    Language.C: (".c", ".h"),
    Language.CPP: (".cpp", ".hpp", ".cc", ".cxx"),
    Language.SWIFT: (".swift",),
    Language.SCALA: (".scala", ".sc"),
    Language.ELIXIR: (".ex", ".exs"),
    Language.LUA: (".lua",),
    Language.JULIA: (".jl",),
    Language.ZIG: (".zig",),
    Language.GROOVY: (".groovy", ".gvy", ".gsh"),
    Language.DART: (".dart",),
    Language.MARKDOWN: (".md", ".markdown", ".mdx"),
    Language.YAML: (".yaml", ".yml"),
    Language.JSON: (".json",),
    Language.TOML: (".toml",),
    Language.SQL: (".sql",),
    Language.HTML: (".html", ".htm"),
    Language.CSS: (".css", ".scss", ".less"),
    Language.SHELL: (".sh", ".bash", ".zsh", ".fish"),
    Language.DOCKERFILE: (".dockerfile",),
    Language.PROTOBUF: (".proto",),
}

LANGUAGE_EXTENSIONS: dict[Language, tuple[str, ...]] = _LANG_EXTENSIONS


def _detect_lang_for_file(f: Path, ext_map: dict[Language, tuple[str, ...]]) -> Language:
    ext = f.suffix.lower()
    for known_lang, exts in ext_map.items():
        if ext in exts:
            return known_lang
    name = f.name
    lower_name = name.lower()
    if lower_name == "dockerfile" or lower_name.startswith("dockerfile."):
        return Language.DOCKERFILE
    if lower_name in ("makefile", "gnumakefile"):
        return Language.SHELL
    if ext in (".yaml", ".yml"):
        return Language.YAML
    if not ext and lower_name.endswith(".md"):
        return Language.MARKDOWN
    from cartographer.core.models import LANGUAGE_EXTENSIONS as CORE_EXT

    return CORE_EXT.get(ext, Language.UNKNOWN)


def _parse_single_file(
    args: tuple[Path, Path, dict[Language, tuple[str, ...]]],
) -> tuple[ParsedFile | None, list[str]]:
    f, root, ext_map = args
    lang = _detect_lang_for_file(f, ext_map)
    if lang == Language.UNKNOWN:
        from cartographer.core.models import LANGUAGE_EXTENSIONS as CORE_EXT

        lang = CORE_EXT.get(f.suffix.lower(), Language.UNKNOWN)
        if lang == Language.UNKNOWN:
            try:
                from cartographer.parser.languages.generic import GenericParser

                lang = Language.UNKNOWN
                parser = GenericParser(lang)
                source, parse_errors = parser.parse_file(f)
                if source:
                    entities = parser.extract_entities(source, str(f.relative_to(root)))
                    pf = ParsedFile(path=str(f.relative_to(root)), language=lang, entities=entities)
                    return pf, parse_errors
                return None, parse_errors
            except Exception:
                return None, []
        if lang == Language.UNKNOWN:
            return None, []
    parser = get_parser(lang)
    if not parser:
        try:
            from cartographer.parser.languages.generic import GenericParser

            parser = GenericParser(lang)
        except Exception:
            return None, []
    try:
        source, parse_errors = parser.parse_file(f)
        if source:
            entities = parser.extract_entities(source, str(f.relative_to(root)))
            pf = ParsedFile(path=str(f.relative_to(root)), language=lang, entities=entities)
            return pf, parse_errors
        return None, parse_errors
    except Exception as e:
        return None, [f"Parse error {f}: {e}"]


def _parse_repository(
    files: list[Path],
    root: Path,
    errors: list[str],
) -> list[ParsedFile]:
    supported = set(supported_languages())
    ext_map = {lang: exts for lang, exts in LANGUAGE_EXTENSIONS.items()
               if lang in supported}

    work = [(f, root, ext_map) for f in files]
    parsed_files: list[ParsedFile] = []
    total = len(work)

    # ThreadPoolExecutor avoids forking N processes that peg all CPU cores.
    # IO-bound file reads benefit from more threads; tree-sitter parsing in C releases the GIL.
    max_workers = min(os.cpu_count() or 4, 8)
    logger.info("Parsing %d files with %d workers...", total, max_workers)

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(_parse_single_file, args): args for args in work}
        done = 0
        for future in as_completed(futures):
            done += 1
            if done % max(1, total // 10) == 0 or done == total:
                logger.info("  parsed %d/%d files...", done, total)
            try:
                pf, parse_errors = future.result()
                if pf:
                    parsed_files.append(pf)
                errors.extend(parse_errors)
            except Exception as e:
                errors.append(f"Parse worker failed: {e}")

    logger.info("Parsing complete: %d/%d files parsed", len(parsed_files), total)
    parsed_files.sort(key=lambda pf: pf.path)
    return parsed_files


def update_index(
    path: str | Path,
    db_path: Path | None = None,
) -> dict:
    """Incrementally re-index a single file after changes.

    Re-parses the file, updates the graph, and re-embeds changed nodes.
    Returns stats about what changed.
    """
    root = Path(path).resolve()
    if not root.exists():
        return {"error": f"Path does not exist: {root}"}

    from cartographer.embedding.engine import generate_embeddings
    from cartographer.graph.builder import update_file_in_graph

    if db_path is None:
        db_path = Path.home() / ".cartographer" / "index.db"
    else:
        db_path = Path(db_path)

    from cartographer.storage.connection import get_connection, init_schema
    conn = get_connection(db_path)
    init_schema(conn)
    root_str = str(root)
    repo_row = conn.execute(
        "SELECT id, path FROM repositories WHERE ? = path OR ? LIKE path || '/%'",
        (root_str, root_str),
    ).fetchone()
    # If multiple repos match (nested), pick the longest path prefix
    if not repo_row:
        rows = conn.execute(
            "SELECT id, path FROM repositories ORDER BY LENGTH(path) DESC"
        ).fetchall()
        for row in rows:
            if root_str.startswith(row[1] + "/") or root_str == row[1]:
                repo_row = row
                break
    conn.close()

    if not repo_row:
        return {"error": "Repository not indexed. Run 'cartographer index' first."}

    repo_path = repo_row[1]
    rel_path = str(root.relative_to(repo_path)) if root.is_file() else ""

    if not root.is_file():
        return {"error": f"Not a file: {root}"}

    from cartographer.core.models import LANGUAGE_EXTENSIONS

    lang = _detect_lang_for_file(root, {k: tuple(v) for k, v in LANGUAGE_EXTENSIONS.items() if isinstance(v, str) or True})
    # fallback using core map directly
    if lang == Language.UNKNOWN:
        lang = LANGUAGE_EXTENSIONS.get(root.suffix.lower(), Language.UNKNOWN)
        if root.name.lower() == "dockerfile" or root.name.lower().startswith("dockerfile."):
            lang = Language.DOCKERFILE
    if lang == Language.UNKNOWN:
        try:
            from cartographer.parser.languages.generic import GenericParser

            parser_tmp = GenericParser(lang)
            source_tmp, _ = parser_tmp.parse_file(root)
            if source_tmp is not None:
                lang = Language.UNKNOWN
            else:
                return {"error": f"Unsupported file type: {root.suffix}"}
        except Exception:
            return {"error": f"Unsupported file type: {root.suffix}"}

    parser = get_parser(lang)
    if not parser:
        try:
            from cartographer.parser.languages.generic import GenericParser

            parser = GenericParser(lang)
        except Exception:
            return {"error": f"No parser for {lang.value}"}

    source, parse_errors = parser.parse_file(root)
    if not source:
        return {"error": f"Failed to parse {root}", "parse_errors": parse_errors}

    entities = parser.extract_entities(source, rel_path)
    parsed_file = ParsedFile(path=rel_path, language=lang, entities=entities)

    stats = update_file_in_graph(Path(db_path), repo_path, parsed_file)

    # Re-embed the changed nodes
    embed_count = 0
    if stats.get("nodes_added", 0) > 0:
        new_count, _ = generate_embeddings(Path(db_path))
        embed_count = new_count

    return {
        **stats,
        "file": rel_path,
        "language": lang.value,
        "embeddings_generated": embed_count,
        "parse_errors": parse_errors,
    }
