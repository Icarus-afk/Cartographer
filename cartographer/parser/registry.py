from __future__ import annotations

import logging
import threading

from cartographer.core.models import Language as ProgLang
from cartographer.parser.base import BaseParser

logger = logging.getLogger(__name__)

_PARSER_MAP: dict[ProgLang, type[BaseParser]] | None = None
_THREAD_LOCAL = threading.local()


def _ensure_parsers() -> None:
    global _PARSER_MAP
    if _PARSER_MAP is not None:
        return
    # import each parser in isolation — missing tree-sitter grammar falls back to GenericParser
    from cartographer.parser.languages.generic import GenericParser as _Generic  # always available

    def _try_import(mod: str, cls: str):
        try:
            m = __import__(mod, fromlist=[cls])
            return getattr(m, cls)
        except Exception as exc:
            logger.warning("Parser %s.%s unavailable, falling back to generic: %s", mod, cls, exc)
            return _Generic

    CParser = _try_import("cartographer.parser.languages.c", "CParser")
    CppParser = _try_import("cartographer.parser.languages.cpp", "CppParser")
    CSharpParser = _try_import("cartographer.parser.languages.csharp", "CSharpParser")
    DartParser = _try_import("cartographer.parser.languages.dart", "DartParser")
    ElixirParser = _try_import("cartographer.parser.languages.elixir", "ElixirParser")
    GenericParser = _Generic
    GoParser = _try_import("cartographer.parser.languages.go", "GoParser")
    GroovyParser = _try_import("cartographer.parser.languages.groovy", "GroovyParser")
    JavaParser = _try_import("cartographer.parser.languages.java", "JavaParser")
    JavaScriptParser = _try_import("cartographer.parser.languages.javascript", "JavaScriptParser")
    JuliaParser = _try_import("cartographer.parser.languages.julia", "JuliaParser")
    KotlinParser = _try_import("cartographer.parser.languages.kotlin", "KotlinParser")
    LuaParser = _try_import("cartographer.parser.languages.lua", "LuaParser")
    MarkdownParser = _try_import("cartographer.parser.languages.markdown", "MarkdownParser")
    PHPPhpParser = _try_import("cartographer.parser.languages.php", "PHPPhpParser")
    PythonParser = _try_import("cartographer.parser.languages.python", "PythonParser")
    RubyParser = _try_import("cartographer.parser.languages.ruby", "RubyParser")
    RustParser = _try_import("cartographer.parser.languages.rust", "RustParser")
    ScalaParser = _try_import("cartographer.parser.languages.scala", "ScalaParser")
    SwiftParser = _try_import("cartographer.parser.languages.swift", "SwiftParser")
    TSXParser = _try_import("cartographer.parser.languages.tsx", "TSXParser")
    TypeScriptParser = _try_import("cartographer.parser.languages.typescript", "TypeScriptParser")
    ZigParser = _try_import("cartographer.parser.languages.zig", "ZigParser")
    _PARSER_MAP = {
        ProgLang.PYTHON: PythonParser,
        ProgLang.JAVASCRIPT: JavaScriptParser,
        ProgLang.TYPESCRIPT: TypeScriptParser,
        ProgLang.TSX: TSXParser,
        ProgLang.GO: GoParser,
        ProgLang.RUST: RustParser,
        ProgLang.JAVA: JavaParser,
        ProgLang.KOTLIN: KotlinParser,
        ProgLang.CSHARP: CSharpParser,
        ProgLang.PHP: PHPPhpParser,
        ProgLang.RUBY: RubyParser,
        ProgLang.C: CParser,
        ProgLang.CPP: CppParser,
        ProgLang.SWIFT: SwiftParser,
        ProgLang.SCALA: ScalaParser,
        ProgLang.ELIXIR: ElixirParser,
        ProgLang.LUA: LuaParser,
        ProgLang.JULIA: JuliaParser,
        ProgLang.ZIG: ZigParser,
        ProgLang.GROOVY: GroovyParser,
        ProgLang.DART: DartParser,
        ProgLang.MARKDOWN: MarkdownParser,
        ProgLang.YAML: GenericParser,
        ProgLang.JSON: GenericParser,
        ProgLang.TOML: GenericParser,
        ProgLang.SQL: GenericParser,
        ProgLang.HTML: GenericParser,
        ProgLang.CSS: GenericParser,
        ProgLang.SHELL: GenericParser,
        ProgLang.DOCKERFILE: GenericParser,
        ProgLang.PROTOBUF: GenericParser,
    }


def register_parser(
    language: ProgLang, parser_cls: type, extensions: list[str] | None = None
) -> None:
    _ensure_parsers()
    assert _PARSER_MAP is not None
    _PARSER_MAP[language] = parser_cls
    if extensions:
        from cartographer.core.models import LANGUAGE_EXTENSIONS

        for ext in extensions:
            LANGUAGE_EXTENSIONS[ext] = language
        try:
            from cartographer.ingestion.engine import LANGUAGE_EXTENSIONS as ENG_EXT

            for ext in extensions:
                ENG_EXT[language] = ENG_EXT.get(language, ()) + (ext,)
        except Exception:
            pass
    if hasattr(_THREAD_LOCAL, "parser_cache"):
        _THREAD_LOCAL.parser_cache.pop(language, None)


def get_parser(language: ProgLang) -> BaseParser | None:
    _ensure_parsers()
    cache = getattr(_THREAD_LOCAL, "parser_cache", None)
    if cache is None:
        cache = {}
        _THREAD_LOCAL.parser_cache = cache
    if language in cache:
        return cache[language]
    cls = _PARSER_MAP.get(language)
    if cls is None and language != ProgLang.UNKNOWN:
        try:
            from cartographer.parser.languages.generic import GenericParser

            cls = GenericParser
        except Exception:
            cls = None
    instance = cls(language) if cls else None
    if instance:
        cache[language] = instance
    return instance


def supported_languages() -> list[ProgLang]:
    _ensure_parsers()
    assert _PARSER_MAP is not None
    return list(_PARSER_MAP.keys())
