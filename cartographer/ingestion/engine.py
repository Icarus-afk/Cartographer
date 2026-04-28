import time
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
from cartographer.parser.registry import get_parser, supported_languages


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
        files = discover_files(root)
    except Exception as e:
        return IngestionResult(
            path=str(root),
            manifest=None,
            success=False,
            errors=[f"File discovery failed: {e}"],
        )

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
                references = extract_references(root, parsed_files, files)
            except Exception as e:
                errors.append(f"Reference extraction failed: {e}")

        if db_path is None:
            db_path_obj = Path.home() / ".cartographer" / "index.db"
        else:
            db_path_obj = Path(db_path)
        manifest.total_references = len(references)
        try:
            stats = build_graph(db_path_obj, str(root), parsed_files, references, manifest)
            manifest.total_files = stats.get("files", len(files))
        except Exception as e:
            errors.append(f"Graph build failed: {e}")

    elapsed = (time.perf_counter() - start) * 1000

    fatal_errors = [e for e in errors if not e.startswith("Parse errors")]
    return IngestionResult(
        path=str(root),
        manifest=manifest,
        parsed_files=parsed_files,
        success=len(fatal_errors) == 0,
        errors=errors,
        duration_ms=round(elapsed, 2),
    )


def _parse_repository(
    files: list[Path],
    root: Path,
    errors: list[str],
) -> list[ParsedFile]:
    available = supported_languages()
    target_langs = set(available)

    parsers = {}
    for lang in target_langs:
        parser = get_parser(lang)
        if parser:
            parsers[lang] = parser

    parsed_files: list[ParsedFile] = []

    for f in files:
        ext = f.suffix.lower()
        lang = Language.UNKNOWN
        for known_lang, parser in parsers.items():
            if ext in LANGUAGE_EXTENSION_MAP_REVERSE.get(known_lang, ()):
                lang = known_lang
                break

        if lang == Language.UNKNOWN or lang not in parsers:
            continue

        try:
            parser = parsers[lang]
            source, parse_errors = parser.parse_file(f)
            if source:
                entities = parser.extract_entities(source, str(f.relative_to(root)))
                pf = ParsedFile(path=str(f.relative_to(root)), language=lang, entities=entities)
                parsed_files.append(pf)
            errors.extend(parse_errors)
        except Exception as e:
            errors.append(f"Parse error {f}: {e}")

    return parsed_files


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
}

LANGUAGE_EXTENSION_MAP_REVERSE: dict[Language, tuple[str, ...]] = _LANG_EXTENSIONS
