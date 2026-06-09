from cartographer.compression.engine import (
    compress,
    compress_impact,
    compress_nodes,
    compress_path,
    compress_summary,
    estimate_tokens,
)


def test_estimate_tokens():
    assert estimate_tokens("hello") == 1
    assert estimate_tokens("a" * 100) == 25


def test_compress_nodes_empty():
    assert compress_nodes([]) == "No results."


def test_compress_nodes_list():
    nodes = [
        {"type": "function", "name": "foo", "file_path": "lib/foo.py"},
        {"type": "class", "name": "Bar", "file_path": "lib/bar.py"},
    ]
    result = compress_nodes(nodes)
    assert "foo" in result
    assert "Bar" in result
    assert "lib/foo.py" in result


def test_compress_nodes_grouped():
    nodes = [{"type": "function", "name": f"f{i}", "file_path": f"lib/{i}.py"} for i in range(20)]
    result = compress_nodes(nodes, max_tokens=80)
    assert "function: 20" in result
    assert "Files:" in result


def test_compress_impact():
    results = [
        {"type": "function", "name": "caller", "file_path": "lib/caller.py", "via_edge": "IMPORTS"},
        {"type": "class", "name": "User", "file_path": "lib/user.py", "via_edge": "IMPORTS"},
    ]
    result = compress_impact(results)
    assert "2 dependents" in result
    assert "IMPORTS" in result


def test_compress_path():
    path = [
        {"type": "directory", "name": "src", "depth": 0},
        {"type": "file", "name": "main.rs", "file_path": "src/main.rs", "depth": 1},
    ]
    result = compress_path(path)
    assert "2 hops" in result
    assert "main.rs" in result


def test_compress_summary():
    summary = {
        "name": "test-repo",
        "path": "/test",
        "total_nodes": 100,
        "total_edges": 50,
        "node_breakdown": {"function": 30, "class": 20},
        "edge_breakdown": {"DEFINES": 30, "IMPORTS": 20},
        "top_files": [{"name": "main.py", "entities": 10}],
        "top_classes": [{"name": "Foo", "methods": 5}],
    }
    result = compress_summary(summary)
    assert "test-repo" in result
    assert "function: 30" in result
    assert "main.py" in result
    assert "Foo" in result


def test_compress_dispatch():
    nodes = [{"type": "function", "name": "foo", "file_path": "lib/foo.py"}]
    result = compress(nodes, 200, "nodes")
    assert "foo" in result

    result = compress("raw string", 200, "unknown")
    assert "raw string" in result
