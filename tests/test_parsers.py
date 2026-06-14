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


def test_gitignore_loading():
    import tempfile

    from cartographer.ingestion.discoverer import _load_gitignore_spec

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        gitignore = root / ".gitignore"
        gitignore.write_text("*.pyc\nbuild/\n.env\n")
        spec = _load_gitignore_spec(root)
        assert spec is not None
        assert spec.match_file("foo.pyc")
        assert spec.match_file("build/output.o")
        assert spec.match_file(".env")
        assert not spec.match_file("src/main.py")
        assert not spec.match_file("README.md")


def test_discover_with_gitignore():
    import tempfile

    from cartographer.ingestion.discoverer import discover_files

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "main.py").write_text("x = 1\n")
        (root / "build").mkdir()
        (root / "build" / "output.o").write_bytes(b"\x00\x01")
        (root / ".gitignore").write_text("build/\n")

        files = discover_files(root)
        paths = [str(f.relative_to(root)) for f in files]
        assert "main.py" in paths
        assert all("build" not in p for p in paths)


def test_typescript_generic_function():
    parser = get_parser(Language.TYPESCRIPT)
    code = b"function identity<T>(x: T): T { return x; }\n"
    entities = parser.extract_entities(code, "test.ts")
    assert len(entities) == 1
    assert entities[0].kind.value == "function"
    assert entities[0].name == "identity"
    assert entities[0].metadata.get("type_parameters") == "<T>"


def test_typescript_interface():
    parser = get_parser(Language.TYPESCRIPT)
    code = b"interface Props {\n  name: string;\n  age?: number;\n}\n"
    entities = parser.extract_entities(code, "test.ts")
    assert len(entities) == 1
    assert entities[0].kind.value == "interface"
    assert entities[0].name == "Props"


def test_typescript_generic_interface():
    parser = get_parser(Language.TYPESCRIPT)
    code = b"interface Response<T> {\n  data: T;\n  status: number;\n}\n"
    entities = parser.extract_entities(code, "test.ts")
    assert len(entities) == 1
    assert entities[0].kind.value == "interface"
    assert entities[0].name == "Response"
    assert entities[0].metadata.get("type_parameters") == "<T>"


def test_typescript_type_alias():
    parser = get_parser(Language.TYPESCRIPT)
    code = b"type UserID = string;\n"
    entities = parser.extract_entities(code, "test.ts")
    assert len(entities) == 1
    assert entities[0].kind.value == "type_alias"
    assert entities[0].name == "UserID"


def test_typescript_type_alias_generic():
    parser = get_parser(Language.TYPESCRIPT)
    code = b"type Result<T> = { success: boolean; data: T };\n"
    entities = parser.extract_entities(code, "test.ts")
    assert len(entities) == 1
    assert entities[0].kind.value == "type_alias"
    assert entities[0].name == "Result"
    assert entities[0].metadata.get("type_parameters") == "<T>"


def test_typescript_enum():
    parser = get_parser(Language.TYPESCRIPT)
    code = b"enum Color { Red, Green, Blue }\n"
    entities = parser.extract_entities(code, "test.ts")
    assert len(entities) == 1
    assert entities[0].kind.value == "enum"
    assert entities[0].name == "Color"


def test_typescript_default_export_function():
    parser = get_parser(Language.TYPESCRIPT)
    code = b"export default function() { return 42; }\n"
    entities = parser.extract_entities(code, "test.ts")
    assert len(entities) == 1
    assert entities[0].kind.value == "function"
    assert entities[0].name == "default"


def test_typescript_const_arrow_function():
    parser = get_parser(Language.TYPESCRIPT)
    code = b"const handler = (x: number) => x * 2;\n"
    entities = parser.extract_entities(code, "test.ts")
    assert len(entities) == 1
    assert entities[0].kind.value == "function"
    assert entities[0].name == "handler"


def test_typescript_const_arrow_generic():
    parser = get_parser(Language.TYPESCRIPT)
    code = b"const wrap = <T>(x: T) => x;\n"
    entities = parser.extract_entities(code, "test.ts")
    assert len(entities) == 1
    assert entities[0].kind.value == "function"
    assert entities[0].name == "wrap"


def test_tsx_jsx_element():
    parser = get_parser(Language.TSX)
    code = b"const App = () => <div>Hello</div>;\n"
    entities = parser.extract_entities(code, "test.tsx")
    assert len(entities) >= 1
    assert entities[0].kind.value == "function"
    assert entities[0].name == "App"


def test_tsx_jsx_self_closing():
    parser = get_parser(Language.TSX)
    code = b"function render() { return <Button label=\"Click\" />; }\n"
    entities = parser.extract_entities(code, "test.tsx")
    assert len(entities) >= 1
    assert entities[0].kind.value == "function"
    assert entities[0].name == "render"


def test_typescript_react_fc_component():
    parser = get_parser(Language.TSX)
    code = b"const Header: React.FC<{ title: string }> = ({ title }) => <h1>{title}</h1>;\n"
    entities = parser.extract_entities(code, "test.tsx")
    assert len(entities) >= 1
    assert entities[0].kind.value == "function"
    assert entities[0].name == "Header"


def test_typescript_export_default_generic():
    parser = get_parser(Language.TYPESCRIPT)
    code = b"export default function identity<T>(x: T): T { return x; }\n"
    entities = parser.extract_entities(code, "test.ts")
    assert len(entities) == 1
    assert entities[0].kind.value == "function"
    assert entities[0].name == "identity"
    assert entities[0].metadata.get("type_parameters") == "<T>"
