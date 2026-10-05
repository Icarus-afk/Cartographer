import json
import tempfile
from pathlib import Path

from click.testing import CliRunner

from cartographer.cli import main
from cartographer.graph.paging import hub_page_size, next_offset
from cartographer.ingestion.engine import index_repository


def _seed_repo(root: Path) -> None:
    for i in range(6):
        root.joinpath(f"mod{i}.py").write_text(
            f"import mod{(i + 1) % 6}\n"
            f"CONST_{i} = {i}\n"
            f"def func{i}(x):\n"
            f"    return mod{(i + 1) % 6}.func{(i + 1) % 6}(x)\n"
            f"class Cls{i}:\n"
            f"    def method{i}(self):\n"
            f"        return func{i}(1)\n"
        )


def _page(db: str, limit: int, offset: int) -> dict:
    args = ["--db", db, "--json", "graph-data", "-l", str(limit), "-o", str(offset)]
    r = CliRunner().invoke(main, args)
    assert r.exit_code == 0, r.output
    return json.loads(r.output)


def test_hub_page_size_matches_backend():
    assert hub_page_size(80) == 10
    assert hub_page_size(500) == 62
    assert next_offset(0, 80) == 10
    assert next_offset(10, 80) == 20


def test_cursor_chain_terminates_and_covers():
    with tempfile.TemporaryDirectory() as td:
        root = Path(td) / "repo"
        root.mkdir()
        _seed_repo(root)
        db = str(Path(td) / "t.db")
        assert index_repository(str(root), db_path=Path(db)).success

        limit = 6
        seen: set = set()
        offset = 0
        pages = 0
        last: dict = {}
        while True:
            d = _page(db, limit, offset)
            assert "next_offset" in d and "has_more" in d
            for n in d["nodes"]:
                seen.add(n["id"])
            pages += 1
            last = d
            assert pages < 50, "pagination did not terminate"
            if not d["has_more"]:
                break
            assert d["next_offset"] != offset
            offset = d["next_offset"]
        assert pages > 1, "expected more than one page"
        assert len(seen) >= last["total_nodes"] * 0.9
