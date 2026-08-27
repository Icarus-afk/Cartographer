from __future__ import annotations

import re
from pathlib import Path

import tree_sitter_python
from tree_sitter import Language

from cartographer.core.models import CodeLocation, EntityKind, ParsedEntity
from cartographer.parser.base import BaseParser

_CLASS_RE = re.compile(r"^\s*(?:class|struct|interface|enum|trait|type)\s+(\w+)", re.MULTILINE)
_FUNC_RE = re.compile(r"^\s*(?:func|function|def|fn|fun|proc)\s+(\w+)\s*\(", re.MULTILINE)
_METHOD_RE = re.compile(r"^\s*(?:public|private|protected|static|\s)*\s*(?:async\s+)?(?:def|function|func|fn)?\s*(\w+)\s*\([^)]*\)\s*(?:\{|:|=>)?", re.MULTILINE)
_IMPORT_RE = re.compile(r"^\s*(?:import|from|require|include|use|using)\s+[^\n]+", re.MULTILINE)
_DART_IMPORT = re.compile(r"^\s*import\s+['\"][^'\"]+['\"]", re.MULTILINE)
_HEADING_RE = re.compile(r"^#{1,6}\s+(.+)$", re.MULTILINE)


class GenericParser(BaseParser):
    def _build_language(self) -> Language:
        return Language(tree_sitter_python.language())

    def parse_file(self, path: Path) -> tuple[bytes | None, list[str]]:
        try:
            source = path.read_bytes()
            return source, []
        except Exception as e:
            return None, [f"Failed to read {path}: {e}"]

    def extract_entities(self, source: bytes, file_path: str) -> list[ParsedEntity]:
        if not source.strip():
            return []
        text = source.decode("utf-8", errors="replace")
        entities: list[ParsedEntity] = []
        seen: set[str] = set()
        lines = text.splitlines()
        line_map: dict[str, int] = {}
        for idx, line in enumerate(lines, start=1):
            for m in _CLASS_RE.finditer(line):
                name = m.group(1)
                if name not in seen:
                    seen.add(name)
                    loc = CodeLocation(file_path=file_path, start_line=idx, start_col=1, end_line=idx, end_col=len(line) + 1)
                    entities.append(ParsedEntity(kind=EntityKind.CLASS, name=name, location=loc))
            for m in _FUNC_RE.finditer(line):
                name = m.group(1)
                if name not in seen:
                    seen.add(name)
                    loc = CodeLocation(file_path=file_path, start_line=idx, start_col=1, end_line=idx, end_col=len(line) + 1)
                    entities.append(ParsedEntity(kind=EntityKind.FUNCTION, name=name, location=loc))

        for idx, line in enumerate(lines, start=1):
            if _IMPORT_RE.match(line) or _DART_IMPORT.match(line):
                loc = CodeLocation(file_path=file_path, start_line=idx, start_col=1, end_line=idx, end_col=len(line) + 1)
                entities.append(ParsedEntity(kind=EntityKind.MODULE, name=f"import:{line.strip()[:120]}", location=loc))

        return entities
