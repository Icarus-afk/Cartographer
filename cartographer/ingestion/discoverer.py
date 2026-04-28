from __future__ import annotations

import fnmatch
from pathlib import Path

from cartographer.core.models import LANGUAGE_EXTENSIONS, Language

IGNORED_DIRS = {
    ".git", "__pycache__", "node_modules", ".venv", "venv",
    "env", ".env", ".eggs", "dist", "build", "target",
    ".idea", ".vscode", ".DS_Store", ".next", ".nuxt",
    "vendor", "third_party", ".tox", ".mypy_cache", ".pytest_cache",
    ".ruff_cache", "site-packages", ".git-rewrite", ".terraform",
    "Pods", ".build", "cmake-build-debug", "cmake-build-release",
}

BINARY_EXTENSIONS = {
    ".pyc", ".pyo", ".so", ".dll", ".dylib", ".o", ".obj", ".lib",
    ".a", ".class", ".jar", ".war", ".ear", ".dex", ".apk",
    ".png", ".jpg", ".jpeg", ".gif", ".bmp", ".ico", ".svg",
    ".ttf", ".otf", ".woff", ".woff2", ".eot",
    ".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx",
    ".zip", ".tar", ".gz", ".bz2", ".xz", ".7z", ".rar",
    ".mp3", ".mp4", ".avi", ".mov", ".wmv", ".flv",
    ".woff2", ".eot", ".wasm",
}

CARTOGRAPHER_IGNORE = ".cartographerignore"


def _load_ignore_patterns(root: Path) -> list[str]:
    patterns: list[str] = []
    ignore_file = root / CARTOGRAPHER_IGNORE
    if ignore_file.exists():
        try:
            for line in ignore_file.read_text().splitlines():
                line = line.strip()
                if line and not line.startswith("#"):
                    patterns.append(line)
        except Exception:
            pass
    return patterns


def _is_binary(path: Path) -> bool:
    if path.suffix.lower() in BINARY_EXTENSIONS:
        return True
    try:
        with open(path, "rb") as f:
            head = f.read(8192)
        return b"\0" in head
    except Exception:
        return True


def _matches_pattern(name: str, patterns: list[str]) -> bool:
    for pat in patterns:
        if fnmatch.fnmatch(name, pat):
            return True
        if "/" not in pat:
            if fnmatch.fnmatch(name.split("/")[-1], pat):
                return True
    return False


def discover_files(
    root: Path,
    ignore_patterns: list[str] | None = None,
) -> list[Path]:
    if ignore_patterns is None:
        ignore_patterns = _load_ignore_patterns(root)
    return _walk(root, ignore_patterns)


def _walk(root: Path, ignore_patterns: list[str]) -> list[Path]:
    files: list[Path] = []
    try:
        entries = list(root.iterdir())
    except PermissionError:
        return files

    for entry in entries:
        name = entry.name

        if name.startswith(".") or name in IGNORED_DIRS:
            continue
        if _matches_pattern(name, ignore_patterns):
            continue

        try:
            if entry.is_file():
                if not _is_binary(entry):
                    files.append(entry)
            elif entry.is_dir():
                files.extend(_walk(entry, ignore_patterns))
        except PermissionError:
            continue

    return files


def detect_languages(files: list[Path]) -> dict[Language, int]:
    counts: dict[Language, int] = {}
    for f in files:
        ext = f.suffix.lower()
        lang = LANGUAGE_EXTENSIONS.get(ext, Language.UNKNOWN)
        counts[lang] = counts.get(lang, 0) + 1
    return counts


def detect_package_managers(root: Path) -> list[str]:
    indicators: list[tuple[str, str]] = [
        ("package.json", "npm"),
        ("yarn.lock", "yarn"),
        ("pnpm-lock.yaml", "pnpm"),
        ("Pipfile", "pipenv"),
        ("poetry.lock", "poetry"),
        ("requirements.txt", "pip"),
        ("Cargo.toml", "cargo"),
        ("go.mod", "go-modules"),
        ("Cargo.lock", "cargo"),
        ("Gemfile", "bundler"),
        ("composer.json", "composer"),
        ("build.gradle", "gradle"),
        ("pom.xml", "maven"),
        ("Package.swift", "swift-pm"),
        ("pubspec.yaml", "pub"),
        ("mix.exs", "mix"),
        ("rebar.config", "rebar3"),
    ]
    managers: list[str] = []
    for indicator, name in indicators:
        if (root / indicator).exists():
            managers.append(name)
    return managers


def detect_build_systems(root: Path) -> list[str]:
    indicators: list[tuple[str, str]] = [
        ("Makefile", "make"),
        ("CMakeLists.txt", "cmake"),
        ("meson.build", "meson"),
        ("BUILD", "bazel"),
        ("BUILD.bazel", "bazel"),
        ("justfile", "just"),
        ("Taskfile.yml", "taskfile"),
        ("noxfile.py", "nox"),
        ("invoke.yaml", "invoke"),
        ("Rakefile", "rake"),
    ]
    systems: list[str] = []
    for indicator, name in indicators:
        if (root / indicator).exists():
            systems.append(name)
    return systems


def detect_monorepo(root: Path) -> tuple[bool, str | None]:
    if (root / "pnpm-workspace.yaml").exists():
        return True, "pnpm"
    if (root / "lerna.json").exists():
        return True, "lerna"
    if (root / "nx.json").exists():
        return True, "nx"
    if (root / "rush.json").exists():
        return True, "rush"
    if (root / "turborepo.json").exists():
        return True, "turbo"
    if (root / "package.json").exists():
        import json as j

        try:
            pkg = j.loads((root / "package.json").read_text())
            if "workspaces" in pkg:
                return True, "npm-workspaces"
        except Exception:
            pass
    return False, None
