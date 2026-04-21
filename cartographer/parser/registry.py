from __future__ import annotations

from cartographer.core.models import Language as ProgLang
from cartographer.parser.base import BaseParser
from cartographer.parser.languages.c import CParser
from cartographer.parser.languages.cpp import CppParser
from cartographer.parser.languages.csharp import CSharpParser
from cartographer.parser.languages.elixir import ElixirParser
from cartographer.parser.languages.go import GoParser
from cartographer.parser.languages.groovy import GroovyParser
from cartographer.parser.languages.java import JavaParser
from cartographer.parser.languages.javascript import JavaScriptParser
from cartographer.parser.languages.julia import JuliaParser
from cartographer.parser.languages.kotlin import KotlinParser
from cartographer.parser.languages.lua import LuaParser
from cartographer.parser.languages.php import PHPPhpParser
from cartographer.parser.languages.python import PythonParser
from cartographer.parser.languages.ruby import RubyParser
from cartographer.parser.languages.rust import RustParser
from cartographer.parser.languages.scala import ScalaParser
from cartographer.parser.languages.swift import SwiftParser
from cartographer.parser.languages.tsx import TSXParser
from cartographer.parser.languages.typescript import TypeScriptParser
from cartographer.parser.languages.zig import ZigParser

_PARSER_MAP: dict[ProgLang, type[BaseParser]] = {
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
}


def get_parser(language: ProgLang) -> BaseParser | None:
    cls = _PARSER_MAP.get(language)
    return cls(language) if cls else None


def supported_languages() -> list[ProgLang]:
    return list(_PARSER_MAP.keys())
