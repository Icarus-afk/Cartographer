import json

from cartographer.setup.engine import check_setup, configure_agents


def test_configure_opencode_project(tmp_path):
    result = configure_agents(tmp_path, agents=("opencode",), scope="project", dry_run=False)
    cfg = json.loads((tmp_path / "opencode.json").read_text())
    assert cfg["mcp"]["cartographer"]["command"][0].endswith("cartographer-mcp")
    assert cfg["mcp"]["cartographer"]["enabled"] is True
    assert result.configured


def test_configure_stdio_agents_idempotent(tmp_path, monkeypatch):
    monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)
    result = configure_agents(
        tmp_path, agents=("cursor", "vscode", "roo"), scope="all", dry_run=False
    )
    assert result.configured
    second = configure_agents(
        tmp_path, agents=("cursor", "vscode", "roo"), scope="all", dry_run=False
    )
    assert not second.errors
    cursor_cfg = json.loads((tmp_path / ".cursor" / "mcp.json").read_text())
    assert "cartographer" in cursor_cfg["mcpServers"]
    vscode_cfg = json.loads((tmp_path / ".vscode" / "mcp.json").read_text())
    assert "cartographer" in vscode_cfg["servers"]


def test_dry_run_writes_nothing(tmp_path, monkeypatch):
    monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)
    configure_agents(tmp_path, agents=("cursor",), scope="all", dry_run=True)
    assert not (tmp_path / ".cursor" / "mcp.json").exists()


def test_check_setup_reports(tmp_path, monkeypatch):
    monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)
    report = check_setup(tmp_path)
    assert "configs" in report
    assert "cursor" in report["configs"]
    assert "cli" in report
