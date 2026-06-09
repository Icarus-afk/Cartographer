from cartographer.query.engine import classify_intent


def test_classify_architecture():
    result = classify_intent("what is the architecture")
    assert result["type"] == "architecture"
    assert result["category"] == "architecture"

    result = classify_intent("layers")
    assert result["type"] == "architecture"


def test_classify_summarize():
    result = classify_intent("what is this project")
    assert result["type"] == "summarize"

    result = classify_intent("overview")
    assert result["type"] == "summarize"

    result = classify_intent("summarize this")
    assert result["type"] == "summarize"


def test_classify_explain():
    result = classify_intent("explain Preprocessor")
    assert result["type"] == "explain"
    assert "Preprocessor" in result["targets"]

    result = classify_intent("what is Flask")
    assert result["type"] == "explain"
    assert "Flask" in result["targets"]


def test_classify_impact():
    result = classify_intent("what depends on render.py")
    assert result["type"] == "impact"


def test_classify_path():
    result = classify_intent("path between cmd and config")
    assert result["type"] == "path"
    assert "cmd" in result["targets"]

    result = classify_intent("relationship")
    assert result["type"] == "path"


def test_classify_git():
    result = classify_intent("who wrote render.rs")
    assert result["type"] == "git_blame"

    result = classify_intent("authors")
    assert result["type"] == "git_blame"

    result = classify_intent("why was this introduced")
    assert result["type"] == "git_why"

    result = classify_intent("co-change")
    assert result["type"] == "git_cochange"


def test_classify_search_fallback():
    result = classify_intent("find the book module")
    assert result["type"] == "search"
