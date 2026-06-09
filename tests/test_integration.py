import tempfile
from pathlib import Path

from cartographer.core.models import Language
from cartographer.ingestion.discoverer import discover_files
from cartographer.ingestion.engine import index_repository

_SAMPLE_REPO: dict[str, str | dict] = {
    "hello.py": (
        "def greet(name):\n"
        "    return f'Hello {name}'\n"
        "\n"
        "class Greeter:\n"
        "    def __init__(self):\n"
        "        pass\n"
    ),
    "main.js": "function main() {\n  console.log('hello')\n}\n",
    "utils.ts": "export function util(): void {}\n",
    "README.md": "# Test\n",
    ".git": {},  # should be skipped
    "__pycache__": {},  # should be skipped
    "node_modules/react": {},  # should be skipped
}


def _create_repo(tmpdir: Path, structure: dict[str, str | dict]) -> Path:
    for name, content in structure.items():
        path = tmpdir / name
        if isinstance(content, dict):
            path.mkdir(parents=True, exist_ok=True)
            _create_repo(path, content)
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content)
    return tmpdir


def test_discover_files_skips_dotdirs_and_ignored():
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        _create_repo(root, _SAMPLE_REPO)

        files = discover_files(root)
        paths = [str(f.relative_to(root)) for f in files]

        assert "hello.py" in paths
        assert "main.js" in paths
        assert "utils.ts" in paths
        assert "README.md" in paths

        assert ".git" not in paths
        assert "__pycache__" not in paths
        assert "node_modules/react" not in paths
        assert "node_modules" not in " ".join(paths)


def test_discover_files_respects_cartographerignore():
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        _create_repo(root, _SAMPLE_REPO)
        (root / ".cartographerignore").write_text("*.md\n")

        files = discover_files(root)
        paths = [str(f.relative_to(root)) for f in files]

        assert "hello.py" in paths
        assert "README.md" not in paths


def test_index_repository_basic():
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        _create_repo(root, _SAMPLE_REPO)

        db_path = Path(td) / "test.db"
        result = index_repository(root, db_path=db_path)

        assert result.success
        assert result.manifest is not None
        assert result.manifest.total_files >= 3
        assert result.manifest.total_dirs >= 0
        assert result.duration_ms > 0
        assert len(result.parsed_files) >= 3

        langs = result.manifest.languages
        assert langs.get(Language.PYTHON, 0) >= 1
        assert langs.get(Language.JAVASCRIPT, 0) >= 1


def test_index_repository_graph_persisted():
    import sqlite3

    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        _create_repo(root, _SAMPLE_REPO)

        db_path = Path(td) / "test.db"
        result = index_repository(root, db_path=db_path)

        assert result.success

        conn = sqlite3.connect(str(db_path))
        repos = conn.execute("SELECT COUNT(*) FROM repositories").fetchone()[0]
        nodes = conn.execute("SELECT COUNT(*) FROM nodes").fetchone()[0]
        edges = conn.execute("SELECT COUNT(*) FROM edges").fetchone()[0]

        assert repos >= 1
        assert nodes >= 1
        assert edges >= 0

        conn.close()


def test_index_repository_with_parse_errors():
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        (root / "bad.py").write_text("def broken(\n")
        (root / "good.py").write_text("x = 1\n")

        db_path = Path(td) / "test.db"
        result = index_repository(root, db_path=db_path)

        assert result.success
        assert len(result.errors) > 0
        assert any("Parse" in e for e in result.errors)


def test_index_repository_on_directory():
    with tempfile.TemporaryDirectory() as td:
        result = index_repository(td)
        assert result.success
        assert result.manifest is not None
        assert result.manifest.total_files == 0


def test_index_repository_on_file_returns_error():
    with tempfile.NamedTemporaryFile(suffix=".py") as f:
        result = index_repository(f.name)
        assert not result.success
        assert result.manifest is None
