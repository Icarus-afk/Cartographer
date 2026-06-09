from pathlib import Path

import pytest

from cartographer.core.models import Language
from cartographer.parser.base import BaseParser
from cartographer.parser.registry import get_parser, supported_languages

LANGUAGE_SNIPPETS: dict[Language, tuple[str, str, list[str]]] = {
    Language.PYTHON: (
        "test.py",
        "class Foo:\n    def bar(self):\n        pass\ndef baz():\n    pass\n",
        ["class", "function"],
    ),
    Language.JAVASCRIPT: (
        "test.js",
        "function foo() {}\nclass Bar {}\nconst x = 1;\n",
        ["function", "class", "constant"],
    ),
    Language.TYPESCRIPT: (
        "test.ts",
        "function foo(): void {}\nclass Bar {}\nconst x: number = 1;\n",
        ["function", "class", "constant"],
    ),
    Language.TSX: (
        "test.tsx",
        "function foo(): void {}\nclass Bar {}\nconst x: number = 1;\n",
        ["function", "class", "constant"],
    ),
    Language.GO: (
        "test.go",
        "package main\nfunc foo() {}\ntype Bar struct{}\n",
        ["function"],
    ),
    Language.RUST: (
        "test.rs",
        "fn foo() {}\nstruct Bar {}\n",
        ["function"],
    ),
    Language.JAVA: (
        "test.java",
        "class Foo {}\ninterface Bar {}\n",
        ["class", "interface"],
    ),
    Language.RUBY: (
        "test.rb",
        "def foo; end\nclass Bar; end\n",
        ["function", "class"],
    ),
}


def test_supported_languages_returns_all():
    langs = supported_languages()
    assert len(langs) >= 18
    assert Language.PYTHON in langs
    assert Language.JAVASCRIPT in langs


@pytest.mark.parametrize("lang", supported_languages())
def test_all_parsers_construct(lang):
    parser = get_parser(lang)
    assert parser is not None
    assert isinstance(parser, BaseParser)
    assert parser.language == lang


@pytest.mark.parametrize(
    ["lang", "filename", "code", "expected_types"],
    [(k, *v) for k, v in LANGUAGE_SNIPPETS.items()],
    ids=list(LANGUAGE_SNIPPETS.keys()),
)
def test_parse_snippets(lang, filename, code, expected_types):
    parser = get_parser(lang)
    assert parser is not None

    source = code.encode("utf-8")
    entities = parser.extract_entities(source, filename)

    found_types = [e.kind.value for e in entities]
    for t in expected_types:
        assert t in found_types, (
            f"Expected {t} in {found_types} for {lang}"
        )


def test_all_parsers_handle_empty_source():
    for lang in supported_languages():
        parser = get_parser(lang)
        entities = parser.extract_entities(b"", "empty.txt")
        assert entities == [], f"{lang} returned entities for empty source"


BINARY_FILES = [
    b"\x89PNG\r\n\x1a\n",
    b"\xff\xd8\xff\xe0",
    b"\x00\x00\x00\x00",
]


def _check_skip():
    from cartographer.ingestion.discoverer import BINARY_EXTENSIONS, _is_binary

    assert ".pyc" in BINARY_EXTENSIONS
    assert ".class" in BINARY_EXTENSIONS

    for data in BINARY_FILES:
        import tempfile
        with tempfile.NamedTemporaryFile(delete=False) as f:
            f.write(data)
            p = Path(f.name)
        assert _is_binary(p), f"Binary check failed for {data[:4]}"
        p.unlink()


IGNORE_PATTERNS_TEST = [
    ("*.pyc", "foo.pyc", True),
    ("*.pyc", "foo.py", False),
    ("build/*", "build/output.o", True),
    ("build/*", "src/main.py", False),
    ("node_modules/*", "node_modules/express/index.js", True),
]


def test_ignore_pattern_matching():
    from cartographer.ingestion.discoverer import _matches_pattern

    for pattern, name, expected in IGNORE_PATTERNS_TEST:
        result = _matches_pattern(name, [pattern])
        assert result == expected, (
            f"Pattern {pattern!r} on {name!r}: expected {expected}, got {result}"
        )
