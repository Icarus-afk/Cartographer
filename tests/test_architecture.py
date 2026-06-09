from cartographer.architecture.engine import (
    CLASS_SUFFIX_RULES,
    DIRECTORY_NAME_RULES,
    FILE_NAME_RULES,
    _normalize_layer,
    _score_directory,
    _score_file_name,
    _score_name,
)


def test_normalize_layer():
    assert _normalize_layer("models") == "data"
    assert _normalize_layer("service") == "business"
    assert _normalize_layer("routes") == "controller"
    assert _normalize_layer("unknown") == "unknown"


def test_score_name_class_suffix():
    rules = CLASS_SUFFIX_RULES
    results = _score_name("UserController", rules)
    matching = [r for r in results if r[0] == "controller"]
    assert len(matching) >= 1

    results = _score_name("UserService", rules)
    matching = [r for r in results if r[0] == "business"]
    assert len(matching) >= 1

    results = _score_name("UserRepository", rules)
    matching = [r for r in results if r[0] == "data"]
    assert len(matching) >= 1


def test_score_name_class_prefix():
    rules = [("abstract", "utility", 0.3)]
    results = _score_name("AbstractFactory", rules)
    matching = [r for r in results if r[0] == "utility"]
    assert len(matching) >= 1


def test_score_file_name():
    rules = FILE_NAME_RULES
    results = _score_file_name("user_controller.py", rules)
    matching = [r for r in results if r[0] == "controller"]
    assert len(matching) >= 1

    results = _score_file_name("test_helpers.py", rules)
    assert any(r[0] == "testing" for r in results)
    assert any(r[0] == "utility" for r in results)


def test_score_directory():
    rules = DIRECTORY_NAME_RULES
    results = _score_directory("controllers", rules)
    assert any(r[0] == "controller" for r in results)

    results = _score_directory("tests", rules)
    assert any(r[0] == "testing" for r in results)
