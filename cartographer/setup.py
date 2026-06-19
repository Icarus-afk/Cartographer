from __future__ import annotations

import json
import os
import shutil
import sys
from pathlib import Path


def run_setup(
    db_path: Path | None = None,
    config_path: Path | None = None,
    verbose: bool = False,
) -> dict:
    """Auto-detect AI coding assistants and configure them to use Cartographer's MCP server.

    Returns a dict with keys: configured, skipped, errors.
    """
    result: dict[str, list[dict]] = {"configured": [], "skipped": [], "errors": []}

    bin_path = _find_cartographer_mcp()
    if not bin_path:
        result["errors"].append({
            "tool": "cartographer",
            "error": "cartographer-mcp not found on PATH",
        })
        return result

    detect_args = _build_detect_args(db_path, config_path)

    _try_cursor(bin_path, detect_args, result)
    _try_claude_code(bin_path, detect_args, result)
    _try_opencode(bin_path, detect_args, result)
    _try_windsurf(bin_path, detect_args, result)
    _try_continue(bin_path, detect_args, result)
    _try_cline(bin_path, detect_args, result)
    _try_vscode(bin_path, detect_args, result)

    if verbose:
        _log_result(result)

    return result


def _find_cartographer_mcp() -> str | None:
    """Locate the cartographer-mcp binary on PATH."""
    return shutil.which("cartographer-mcp") or shutil.which("cartographer")


def _build_detect_args(
    db_path: Path | None,
    config_path: Path | None,
) -> list[str]:
    args: list[str] = []
    if db_path:
        args.extend(["--db", str(db_path)])
    return args


def _read_json(path: Path) -> dict | None:
    try:
        if path.suffix == ".jsonc":
            import json as _json
            text = path.read_text()
            text = _strip_jsonc_comments(text)
            return _json.loads(text)
        return json.loads(path.read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        return None


def _strip_jsonc_comments(text: str) -> str:
    import re
    text = re.sub(r"//.*?(\n|$)", "\n", text)
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.DOTALL)
    return text


def _write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + "\n")


def _mcp_entry(args: list[str]) -> dict:
    return {"command": "cartographer-mcp", "args": args}


def _try_cursor(
    bin_path: str,
    detect_args: list[str],
    result: dict,
) -> None:
    paths = [
        Path.home() / ".cursor" / "mcp.json",
    ]
    if sys.platform == "win32":
        paths.append(Path(os.environ.get("APPDATA", "")) / "Cursor" / "mcp.json")

    for path in paths:
        if not path.exists():
            continue
        cfg = _read_json(path) or {}
        mcp = cfg.setdefault("mcpServers", {})
        if "cartographer" in mcp:
            result["skipped"].append({
                "tool": "Cursor",
                "path": str(path),
                "reason": "already configured",
            })
            return
        mcp["cartographer"] = _mcp_entry(detect_args)
        _write_json(path, cfg)
        result["configured"].append({
            "tool": "Cursor",
            "path": str(path),
        })
        return

    result["skipped"].append({
        "tool": "Cursor",
        "path": str(paths[0]),
        "reason": "not found (install Cursor first)",
    })


def _try_claude_code(
    bin_path: str,
    detect_args: list[str],
    result: dict,
) -> None:
    paths = [
        Path.home() / ".claude" / "settings.json",
        Path.home() / "Library" / "Application Support" / "Claude" / "claude_desktop_config.json",
    ]

    for path in paths:
        if not path.exists():
            continue
        cfg = _read_json(path) or {}
        mcp = cfg.setdefault("mcpServers", {})
        if "cartographer" in mcp:
            result["skipped"].append({
                "tool": "Claude Code",
                "path": str(path),
                "reason": "already configured",
            })
            return
        mcp["cartographer"] = _mcp_entry(detect_args)
        _write_json(path, cfg)
        result["configured"].append({
            "tool": "Claude Code",
            "path": str(path),
        })
        return

    result["skipped"].append({
        "tool": "Claude Code",
        "path": str(paths[0]),
        "reason": "not found",
    })


def _try_opencode(
    bin_path: str,
    detect_args: list[str],
    result: dict,
) -> None:
    paths = [
        Path.home() / ".config" / "opencode" / "opencode.jsonc",
        Path.home() / ".config" / "opencode" / "config.jsonc",
        Path.cwd() / "opencode.json",
    ]

    for path in paths:
        if not path.exists():
            continue
        cfg = _read_json(path) or {}
        mcp = cfg.setdefault("mcp", {})
        if "cartographer" in mcp:
            result["skipped"].append({
                "tool": "OpenCode",
                "path": str(path),
                "reason": "already configured",
            })
            return
        mcp["cartographer"] = {
            "type": "local",
            "command": ["cartographer-mcp", *detect_args],
            "enabled": True,
        }
        _write_json(path, cfg)
        result["configured"].append({
            "tool": "OpenCode",
            "path": str(path),
        })
        return

    result["skipped"].append({
        "tool": "OpenCode",
        "path": str(paths[0]),
        "reason": "not found",
    })


def _try_windsurf(
    bin_path: str,
    detect_args: list[str],
    result: dict,
) -> None:
    paths = [
        Path.home() / ".config" / "windsurf" / "mcp_config.json",
        Path.home() / ".windsurf" / "mcp_config.json",
    ]

    for path in paths:
        if not path.exists():
            continue
        cfg = _read_json(path) or {}
        mcp = cfg.setdefault("mcpServers", {})
        if "cartographer" in mcp:
            result["skipped"].append({
                "tool": "Windsurf",
                "path": str(path),
                "reason": "already configured",
            })
            return
        mcp["cartographer"] = _mcp_entry(detect_args)
        _write_json(path, cfg)
        result["configured"].append({
            "tool": "Windsurf",
            "path": str(path),
        })
        return

    result["skipped"].append({
        "tool": "Windsurf",
        "path": str(paths[0]),
        "reason": "not found",
    })


def _try_continue(
    bin_path: str,
    detect_args: list[str],
    result: dict,
) -> None:
    paths = [
        Path.home() / ".continue" / "config.json",
    ]

    for path in paths:
        if not path.exists():
            continue
        cfg = _read_json(path) or {}
        mcp = cfg.setdefault("mcpServers", {})
        if "cartographer" in mcp:
            result["skipped"].append({
                "tool": "Continue",
                "path": str(path),
                "reason": "already configured",
            })
            return
        mcp["cartographer"] = _mcp_entry(detect_args)
        _write_json(path, cfg)
        result["configured"].append({
            "tool": "Continue",
            "path": str(path),
        })
        return

    result["skipped"].append({
        "tool": "Continue",
        "path": str(paths[0]),
        "reason": "not found",
    })


def _try_cline(
    bin_path: str,
    detect_args: list[str],
    result: dict,
) -> None:
    paths = [
        Path.home() / ".config" / "cline" / "mcp_config.json",
        Path.home() / ".vscode" / "cline" / "mcp_config.json",
    ]

    for path in paths:
        if not path.exists():
            continue
        cfg = _read_json(path) or {}
        mcp = cfg.setdefault("mcpServers", {})
        if "cartographer" in mcp:
            result["skipped"].append({
                "tool": "Cline",
                "path": str(path),
                "reason": "already configured",
            })
            return
        mcp["cartographer"] = _mcp_entry(detect_args)
        _write_json(path, cfg)
        result["configured"].append({
            "tool": "Cline",
            "path": str(path),
        })
        return

    result["skipped"].append({
        "tool": "Cline",
        "path": str(paths[0]),
        "reason": "not found",
    })


def _try_vscode(
    bin_path: str,
    detect_args: list[str],
    result: dict,
) -> None:
    paths = []
    if sys.platform == "linux":
        paths.append(Path.home() / ".config" / "Code" / "User" / "settings.json")
    elif sys.platform == "darwin":
        paths.append(
            Path.home() / "Library" / "Application Support" / "Code" / "User" / "settings.json"
        )
    elif sys.platform == "win32":
        paths.append(
            Path(os.environ.get("APPDATA", "")) / "Code" / "User" / "settings.json"
        )

    for path in paths:
        if not path.exists():
            continue
        cfg = _read_json(path) or {}
        mcp = cfg.setdefault("mcp", {}).setdefault("servers", {})
        if "cartographer" in mcp:
            result["skipped"].append({
                "tool": "VS Code",
                "path": str(path),
                "reason": "already configured",
            })
            return
        mcp["cartographer"] = {
            "command": ["cartographer-mcp", *detect_args],
        }
        _write_json(path, cfg)
        result["configured"].append({
            "tool": "VS Code",
            "path": str(path),
        })
        return

    result["skipped"].append({
        "tool": "VS Code",
        "path": str(paths[0]) if paths else "N/A",
        "reason": "not found",
    })


def _log_result(result: dict) -> None:
    if result["configured"]:
        print("Configured:")
        for entry in result["configured"]:
            print(f"  {entry['tool']}: {entry['path']}")
    if result["skipped"]:
        print("Skipped:")
        for entry in result["skipped"]:
            print(f"  {entry['tool']}: {entry['reason']}")
    if result["errors"]:
        print("Errors:")
        for entry in result["errors"]:
            print(f"  {entry['tool']}: {entry['error']}")
