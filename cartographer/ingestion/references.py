from __future__ import annotations

import re
from pathlib import Path
from typing import Any

IMPORT_PATTERNS: dict[str, list[tuple[str, re.Pattern, int]]] = {}


def _compile(pat: str) -> re.Pattern:
    return re.compile(pat)


IMPORT_PATTERNS["python"] = [
    ("direct", _compile(r"^\s*import\s+(\S+)"), 1),
    ("from", _compile(r"^\s*from\s+(\S+)\s+import"), 1),
    ("alias", _compile(r"^\s*import\s+(\S+)\s+as\s+\S+"), 1),
]

IMPORT_PATTERNS["javascript"] = [
    ("es6_import", _compile(r"""import\s+(?:\S+\s+from\s+)?['"]([^'"]+)['"]"""), 1),
    ("es6_dynamic", _compile(r"""import\s*\(\s*['"]([^'"]+)['"]"""), 1),
    ("require", _compile(r"""(?:require|require\.resolve)\s*\(\s*['"]([^'"]+)['"]"""), 1),
]

IMPORT_PATTERNS["typescript"] = IMPORT_PATTERNS["javascript"]
IMPORT_PATTERNS["tsx"] = IMPORT_PATTERNS["javascript"]

IMPORT_PATTERNS["go"] = [
    ("direct", _compile(r'"([^"]+)"'), 1),
]
GO_IMPORT_BLOCK = re.compile(r"import\s*\((.*?)\)", re.DOTALL)
GO_IMPORT_LINE = re.compile(r'^\s*import\s+"([^"]+)"')

IMPORT_PATTERNS["rust"] = [
    ("use", _compile(r"^\s*use\s+([^;{]+)"), 1),
    ("extern_crate", _compile(r"^\s*extern\s+crate\s+(\S+)"), 1),
]

IMPORT_PATTERNS["java"] = [
    ("import", _compile(r"^\s*import\s+(?:static\s+)?(\S+)\s*;"), 1),
]

IMPORT_PATTERNS["kotlin"] = [
    ("import", _compile(r"^\s*import\s+(\S+)"), 1),
]

IMPORT_PATTERNS["csharp"] = [
    ("using_static", _compile(r"^\s*using\s+(?:static\s+)?(\S+)\s*;"), 1),
]

_INC = r"(?:require|include|require_once|include_once)"

IMPORT_PATTERNS["php"] = [
    ("use", _compile(r"^\s*use\s+([^;]+)"), 1),
    ("require", _compile(_INC + r"\s*\(\s*['\"]([^'\"]+)['\"]"), 1),
    ("require_noparen", _compile(_INC + r"\s+['\"]([^'\"]+)['\"]"), 1),
]

IMPORT_PATTERNS["ruby"] = [
    ("require", _compile(r"""^\s*require\s+['"]([^'"]+)['"]"""), 1),
    ("require_relative", _compile(r"""^\s*require_relative\s+['"]([^'"]+)['"]"""), 1),
    ("load", _compile(r"""^\s*load\s+['"]([^'"]+)['"]"""), 1),
]

IMPORT_PATTERNS["c"] = [
    ("include", _compile(r'#\s*include\s+"([^"]+)"'), 1),
    ("include_sys", _compile(r'#\s*include\s+<([^>]+)>'), 1),
]

IMPORT_PATTERNS["cpp"] = IMPORT_PATTERNS["c"]

IMPORT_PATTERNS["swift"] = [
    ("import", _compile(r"^\s*import\s+(?:\w+\s+)?(\S+)"), 1),
]

IMPORT_PATTERNS["scala"] = [
    ("import", _compile(r"^\s*import\s+(\S+)"), 1),
]

IMPORT_PATTERNS["elixir"] = [
    ("use", _compile(r"^\s*use\s+(\S+)"), 1),
    ("alias", _compile(r"^\s*alias\s+(\S+)"), 1),
    ("import_module", _compile(r"^\s*import\s+(\S+)"), 1),
    ("require_module", _compile(r"^\s*require\s+(\S+)"), 1),
]

IMPORT_PATTERNS["lua"] = [
    ("require", _compile(r"""require\s*\(\s*['"]([^'"]+)['"]"""), 1),
    ("require_noparen", _compile(r"""require\s+['"]([^'"]+)['"]"""), 1),
]

IMPORT_PATTERNS["julia"] = [
    ("using", _compile(r"^\s*using\s+(\S+)"), 1),
    ("import_export", _compile(r"^\s*import\s+(\S+)"), 1),
]

IMPORT_PATTERNS["zig"] = [
    ("import", _compile(r'@import\s*\(\s*"([^"]+)"'), 1),
]

IMPORT_PATTERNS["groovy"] = [
    ("import", _compile(r"^\s*import\s+(?:static\s+)?(\S+)"), 1),
]

FILE_EXTENSIONS: dict[str, list[str]] = {
    "python": [".py"],
    "javascript": [".js", ".jsx", ".mjs", ".cjs"],
    "typescript": [".ts", ".tsx"],
    "tsx": [".tsx", ".ts"],
    "go": [".go"],
    "rust": [".rs"],
    "java": [".java"],
    "kotlin": [".kt", ".kts"],
    "csharp": [".cs"],
    "php": [".php", ".phtml"],
    "ruby": [".rb"],
    "c": [".c", ".h"],
    "cpp": [".cpp", ".hpp", ".cc", ".cxx"],
    "swift": [".swift"],
    "scala": [".scala", ".sc"],
    "elixir": [".ex", ".exs"],
    "lua": [".lua"],
    "julia": [".jl"],
    "zig": [".zig"],
    "groovy": [".groovy", ".gvy", ".gsh"],
}

MODULE_INDICATORS: dict[str, list[str]] = {
    "python": ["__init__.py"],
    "javascript": ["index.js", "index.jsx", "index.mjs", "index.cjs"],
    "typescript": ["index.ts", "index.tsx"],
    "tsx": ["index.tsx", "index.ts"],
    "go": [],
    "rust": ["mod.rs"],
    "java": [],
    "kotlin": [],
    "csharp": [],
    "php": [],
    "ruby": [],
    "c": [],
    "cpp": [],
    "swift": [],
    "scala": [],
    "elixir": [],
    "lua": [],
    "julia": [],
    "zig": [],
    "groovy": [],
}


def _dotted_to_path(dotted: str) -> str:
    return dotted.replace(".", "/")


def _find_all_crate_roots(source_dir: str) -> list[str]:
    """Return likely crate root dirs based on source_dir segments."""
    parts = source_dir.split("/")
    results: list[str] = []
    for i in range(1, len(parts) + 1):
        results.append("/".join(parts[:i]))
    return results


def _extract_imports(source_bytes: bytes, language: str) -> list[str]:
    text = source_bytes.decode("utf-8", errors="replace")
    lines = text.split("\n")
    imports: list[str] = []

    if language == "go":
        for block_match in GO_IMPORT_BLOCK.finditer(text):
            inner = block_match.group(1)
            for inner_line in inner.split("\n"):
                m = re.search(r'"([^"]+)"', inner_line)
                if m:
                    imports.append(m.group(1))
        for line in lines:
            m = GO_IMPORT_LINE.match(line)
            if m:
                imports.append(m.group(1))
        return imports

    patterns = IMPORT_PATTERNS.get(language, [])
    for line in lines:
        for _name, pat, group_idx in patterns:
            for m in pat.finditer(line):
                val = m.group(group_idx).strip()
                if val:
                    imports.append(val)
    return imports


def _candidates_for_import(
    import_str: str,
    source_lang: str,
    source_dir: str,
    all_files: set[str],
    ext_map: dict[str, list[str]],
) -> set[str]:
    candidates: set[str] = set()
    exts = ext_map.get(source_lang, [".py"])
    mod_indicators = MODULE_INDICATORS.get(source_lang, [])
    possible_paths = []

    if import_str.startswith("."):
        resolved_dir = source_dir
        dots = 0
        while dots < len(import_str) and import_str[dots] == ".":
            dots += 1
        for _ in range(dots - 1):
            if resolved_dir:
                resolved_dir = "/".join(resolved_dir.split("/")[:-1])
        rest = import_str[dots:]
        if rest:
            rest = rest.replace(".", "/")
            base = f"{resolved_dir}/{rest}" if resolved_dir else rest
            possible_paths.append(base)
        else:
            if resolved_dir:
                possible_paths.append(resolved_dir)
    elif source_lang == "rust":
        if import_str.startswith("crate::"):
            rest = import_str[7:].replace("::", "/")
            possible_paths.append(f"src/{rest}")
            possible_paths.append(rest)
        elif import_str.startswith("super::"):
            rest = import_str[7:].replace("::", "/")
            possible_paths.append(rest)
        elif import_str.startswith("self::"):
            rest = import_str[6:].replace("::", "/")
            possible_paths.append(rest)
        else:
            path_like = import_str.replace("::", "/")
            possible_paths.append(path_like)
            segments = path_like.split("/", 1)
            if len(segments) >= 2:
                possible_paths.append(segments[1])
                module_parts = segments[1].split("/")
                for i in range(1, len(module_parts)):
                    possible_paths.append("/".join(module_parts[:i]))
            possible_paths.append(f"src/{path_like}")
            for crate_dir in _find_all_crate_roots(source_dir):
                module_part = segments[1] if len(segments) >= 2 else path_like
                possible_paths.append(f"{crate_dir}/src/{module_part}")
                module_segments = module_part.split("/")
                for i in range(1, len(module_segments)):
                    possible_paths.append(f"{crate_dir}/src/{'/'.join(module_segments[:i])}")
                for crate_rel in ("src",):
                    for candidate_dir in _find_all_crate_roots(source_dir):
                        possible_paths.append(f"{candidate_dir}/{crate_rel}/{path_like}")
    else:
        possible_paths.append(import_str)
        dotted_path = _dotted_to_path(import_str)
        if dotted_path != import_str:
            possible_paths.append(dotted_path)

    for base in possible_paths:
        base = base.strip("/")
        for ext in exts:
            candidate = f"{base}{ext}"
            if candidate in all_files:
                candidates.add(candidate)
            else:
                suffix = f"/{base}{ext}"
                for f in all_files:
                    if f.endswith(suffix):
                        candidates.add(f)
                if not candidates:
                    lower_suffix = suffix.lower()
                    for f in all_files:
                        if f.lower().endswith(lower_suffix):
                            candidates.add(f)
            if not candidates and "/" in base:
                last_part = base.rsplit("/", 1)[-1]
                last_candidate = f"{last_part}{ext}"
                if last_candidate in all_files:
                    candidates.add(last_candidate)
                else:
                    last_suffix = f"/{last_part}{ext}"
                    for f in all_files:
                        if f.endswith(last_suffix):
                            candidates.add(f)
                    if not candidates:
                        lower_last = last_suffix.lower()
                        for f in all_files:
                            if f.lower().endswith(lower_last):
                                candidates.add(f)

        for indicator in mod_indicators:
            candidate = f"{base}/{indicator}"
            if candidate in all_files:
                candidates.add(candidate)
            else:
                suffix = f"/{base}/{indicator}"
                for f in all_files:
                    if f.endswith(suffix):
                        candidates.add(f)
                if not candidates:
                    lower_suffix = suffix.lower()
                    for f in all_files:
                        if f.lower().endswith(lower_suffix):
                            candidates.add(f)

        if base in all_files:
            candidates.add(base)
        elif not candidates:
            lower_base = base.lower()
            for f in all_files:
                if f.lower() == lower_base:
                    candidates.add(f)
        if not candidates and "/" not in base and "." not in base:
            for indicator in mod_indicators:
                dir_candidate = f"{base}/{indicator}"
                if dir_candidate in all_files:
                    candidates.add(dir_candidate)
                else:
                    dir_suffix = f"/{dir_candidate}"
                    for f in all_files:
                        if f.endswith(dir_suffix):
                            candidates.add(f)

    return candidates


def extract_references(
    root: Path,
    parsed_files: list,
    all_file_paths: list[Path],
) -> list[dict[str, Any]]:
    all_rel = set()
    for pf in parsed_files:
        all_rel.add(pf.path)

    ext_map: dict[str, list[str]] = {}
    for pf in parsed_files:
        lang_key = pf.language.value if hasattr(pf.language, "value") else str(pf.language)
        if lang_key not in ext_map:
            ext_map[lang_key] = FILE_EXTENSIONS.get(lang_key, [])
    for lang_name, exts in FILE_EXTENSIONS.items():
        if lang_name not in ext_map:
            ext_map[lang_name] = exts

    file_to_lang: dict[str, str] = {}
    for pf in parsed_files:
        lang_key = pf.language.value if hasattr(pf.language, "value") else str(pf.language)
        file_to_lang[pf.path] = lang_key

    file_to_bytes: dict[str, bytes] = {}
    for f in all_file_paths:
        rel = str(f.relative_to(root))
        if rel in file_to_lang:
            try:
                file_to_bytes[rel] = f.read_bytes()
            except Exception:
                pass

    references: list[dict[str, Any]] = []

    for source_rel, source_bytes in file_to_bytes.items():
        source_lang = file_to_lang.get(source_rel, "")
        if not source_lang or source_lang not in IMPORT_PATTERNS:
            continue

        imp_imports = _extract_imports(source_bytes, source_lang)
        source_dir = str(Path(source_rel).parent) if "/" in source_rel else ""

        for imp in imp_imports:
            targets = _candidates_for_import(imp, source_lang, source_dir, all_rel, ext_map)
            for target in targets:
                references.append({
                    "source": source_rel,
                    "target": target,
                    "type": "IMPORTS",
                    "import_text": imp,
                })

    return references
