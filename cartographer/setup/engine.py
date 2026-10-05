from __future__ import annotations

import json
import os
import platform
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path


def _mcp_command() -> list[str]:
    found = shutil.which("cartographer-mcp")
    if found:
        return [found]
    return ["cartographer-mcp"]


OPENCODE_ENTRY = {"type": "local", "command": _mcp_command(), "enabled": True}


def _stdio_entry() -> dict:
    return {"command": _mcp_command()[0], "args": []}


def _config_paths(project: Path) -> dict[str, Path]:
    home = Path.home()
    system = platform.system()
    if system == "Darwin":
        claude = home / "Library" / "Application Support" / "Claude" / "claude_desktop_config.json"
    elif system == "Windows":
        base = Path(os.environ.get("APPDATA", str(home)))
        claude = base / "Claude" / "claude_desktop_config.json"
    else:
        claude = home / ".config" / "Claude" / "claude_desktop_config.json"
    return {
        "opencode-project": project / "opencode.json",
        "opencode-global": home / ".config" / "opencode" / "opencode.json",
        "claude-desktop": claude,
        "cursor": home / ".cursor" / "mcp.json",
        "windsurf": home / ".codeium" / "windsurf" / "mcp_config.json",
        "vscode-project": project / ".vscode" / "mcp.json",
        "roo-project": project / ".roo" / "mcp.json",
    }


AGENTS = ("opencode", "claude-desktop", "cursor", "windsurf", "vscode", "roo")


def _load_json(path: Path) -> dict:
    try:
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        pass
    return {}


def _write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)


def _merge_opencode(data: dict) -> tuple[dict, bool]:
    mcp = data.get("mcp")
    if not isinstance(mcp, dict):
        mcp = {}
        data["mcp"] = mcp
    before = json.dumps(mcp.get("cartographer"), sort_keys=True)
    mcp["cartographer"] = {"type": "local", "command": _mcp_command(), "enabled": True}
    return data, json.dumps(mcp["cartographer"], sort_keys=True) != before


def _merge_stdio(data: dict, key: str = "mcpServers") -> tuple[dict, bool]:
    servers = data.get(key)
    if not isinstance(servers, dict):
        servers = {}
        data[key] = servers
    before = json.dumps(servers.get("cartographer"), sort_keys=True)
    servers["cartographer"] = _stdio_entry()
    return data, json.dumps(servers["cartographer"], sort_keys=True) != before


def _merge_vscode(data: dict) -> tuple[dict, bool]:
    return _merge_stdio(data, key="servers")


@dataclass
class SetupResult:
    configured: list[str] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    vscode: str = ""
    details: dict = field(default_factory=dict)


def configure_agents(
    project: Path,
    agents: tuple[str, ...] = AGENTS,
    scope: str = "all",
    dry_run: bool = False,
) -> SetupResult:
    result = SetupResult()
    paths = _config_paths(project)
    targets: dict[str, tuple[Path, str]] = {}
    if "opencode" in agents and scope in ("all", "project", "global"):
        if scope in ("all", "project"):
            targets["opencode (project)"] = (paths["opencode-project"], "opencode")
        if scope in ("all", "global"):
            targets["opencode (global)"] = (paths["opencode-global"], "opencode")
    if "claude-desktop" in agents and scope in ("all", "global"):
        targets["claude-desktop"] = (paths["claude-desktop"], "stdio")
    if "cursor" in agents and scope in ("all", "global"):
        targets["cursor"] = (paths["cursor"], "stdio")
    if "windsurf" in agents and scope in ("all", "global"):
        targets["windsurf"] = (paths["windsurf"], "stdio")
    if "vscode" in agents and scope in ("all", "project"):
        targets["vscode (project)"] = (paths["vscode-project"], "vscode")
    if "roo" in agents and scope in ("all", "project"):
        targets["roo (project)"] = (paths["roo-project"], "stdio")
    for label, (path, kind) in targets.items():
        try:
            data = _load_json(path)
            if kind == "opencode":
                data, changed = _merge_opencode(data)
            elif kind == "vscode":
                data, changed = _merge_vscode(data)
            else:
                data, changed = _merge_stdio(data)
            if not dry_run:
                _write_json(path, data)
            result.details[label] = str(path)
            if changed or not path.exists():
                result.configured.append(f"{label}: {path}")
            else:
                result.skipped.append(f"{label} already configured")
        except Exception as e:
            result.errors.append(f"{label}: {e}")
    return result


def find_bundled_vsix() -> Path | None:
    here = Path(__file__).resolve()
    candidates: list[Path] = []
    for parent in [here.parent.parent.parent, Path.cwd()]:
        candidates.extend(sorted(parent.glob("editors/vscode/*.vsix")))
    for c in candidates:
        if c.exists():
            return c
    return None


def install_vscode_extension(
    vsix: Path | None = None, editors: tuple[str, ...] = ("code", "cursor")
) -> str:
    target = vsix or find_bundled_vsix()
    if target is None or not target.exists():
        return "skip: no .vsix found (build with `npx vsce package` in editors/vscode)"
    installed: list[str] = []
    for editor in editors:
        binary = shutil.which(editor)
        if not binary:
            continue
        try:
            proc = subprocess.run(
                [binary, "--install-extension", str(target), "--force"],
                capture_output=True,
                text=True,
                timeout=120,
            )
            if proc.returncode == 0:
                installed.append(editor)
        except Exception:
            continue
    if installed:
        return f"installed via {', '.join(installed)}: {target.name}"
    return "found .vsix but no `code`/`cursor` CLI — install via Extensions view"


def check_setup(project: Path) -> dict:
    paths = _config_paths(project)
    report: dict = {
        "python": sys.version.split()[0],
        "cli": shutil.which("cartographer") or "",
        "mcp": shutil.which("cartographer-mcp") or "",
        "vsix": str(find_bundled_vsix() or ""),
        "editors": {e: bool(shutil.which(e)) for e in ("code", "cursor")},
        "configs": {},
    }
    for label, path in paths.items():
        data = _load_json(path)
        has = False
        if "opencode" in label:
            has = isinstance(data.get("mcp", {}).get("cartographer"), dict)
        elif "vscode" in label:
            has = isinstance(data.get("servers", {}).get("cartographer"), dict)
        else:
            has = isinstance(data.get("mcpServers", {}).get("cartographer"), dict) or isinstance(
                data.get("servers", {}).get("cartographer"), dict
            )
        report["configs"][label] = {
            "path": str(path),
            "exists": path.exists(),
            "configured": bool(has),
        }
    return report


def run_setup(
    project: Path,
    agents: tuple[str, ...] = AGENTS,
    scope: str = "all",
    with_vscode: bool = True,
    with_index: bool = False,
    dry_run: bool = False,
) -> SetupResult:
    result = configure_agents(project, agents=agents, scope=scope, dry_run=dry_run)
    if with_vscode and not dry_run:
        result.vscode = install_vscode_extension()
    elif dry_run:
        result.vscode = "dry-run: vscode install skipped"
    if with_index and not dry_run:
        try:
            from cartographer.ingestion.engine import index_repository

            index_repository(str(project))
        except Exception as e:
            result.errors.append(f"index: {e}")
    return result
