from __future__ import annotations

import re
from pathlib import Path

import tree_sitter_python
from tree_sitter import Language

from cartographer.core.models import CodeLocation, EntityKind, ParsedEntity
from cartographer.parser.base import BaseParser

_CLASS_RE = re.compile(
    r"^\s*(?:(?:abstract|sealed|open|data|public|private|protected)\s+)*"
    r"(?:class|struct|interface|enum|trait|type|module|defmodule|defprotocol|defimpl|object|protocol|record)\s+(\w+)",
    re.MULTILINE,
)
_FUNC_RE = re.compile(
    r"^\s*(?:(?:public|private|protected|static|async|open|override)\s+)*"
    r"(?:func|function|def|defp|defmacro|defn|fn|fun|proc|procedure|priv\s+fn|pub\s+fn)\s+(\w+)\s*\(",
    re.MULTILINE,
)
# fallback for language where func keyword is optional but has parens (e.g. Elixir defp)
_FUNC_FALLBACK_RE = re.compile(r"^\s*(?:defp|def|fn)\s+(\w+)(?:\s*\(|\s+do)", re.MULTILINE)
_METHOD_RE = re.compile(r"^\s*(?:public|private|protected|static|\s)*\s*(?:async\s+)?(?:def|function|func|fn)?\s*(\w+)\s*\([^)]*\)\s*(?:\{|:|=>)?", re.MULTILINE)
_IMPORT_RE = re.compile(r"^\s*(?:import|from|require|include|use|using|alias|export)\s+[^\n]+", re.MULTILINE)
_DART_IMPORT = re.compile(r"^\s*import\s+['\"][^'\"]+['\"]", re.MULTILINE)
_HEADING_RE = re.compile(r"^#{1,6}\s+(.+)$", re.MULTILINE)
# Elixir specific
_ELIXIR_MODULE_RE = re.compile(r"^\s*defmodule\s+([\w\.]+)\s+do", re.MULTILINE)
_ELIXIR_FUNC_RE = re.compile(r"^\s*def(?:p|macro)?\s+(\w+)\s*(?:\(|do)", re.MULTILINE)


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
        for idx, line in enumerate(lines, start=1):
            # Elixir defmodule has dotted names — take last segment as class name
            for m in _ELIXIR_MODULE_RE.finditer(line):
                full = m.group(1)
                name = full.split(".")[-1]
                if name not in seen:
                    seen.add(name)
                    loc = CodeLocation(file_path=file_path, start_line=idx, start_col=1, end_line=idx, end_col=len(line) + 1)
                    entities.append(ParsedEntity(kind=EntityKind.CLASS, name=name, location=loc, metadata={"full_name": full}))
            for m in _CLASS_RE.finditer(line):
                name = m.group(1)
                if name not in seen:
                    seen.add(name)
                    loc = CodeLocation(file_path=file_path, start_line=idx, start_col=1, end_line=idx, end_col=len(line) + 1)
                    entities.append(ParsedEntity(kind=EntityKind.CLASS, name=name, location=loc))
            for m in _FUNC_RE.finditer(line):
                name = m.group(1)
                if name not in seen and name not in {"if", "for", "while", "switch", "catch", "when", "case"}:
                    seen.add(name)
                    loc = CodeLocation(file_path=file_path, start_line=idx, start_col=1, end_line=idx, end_col=len(line) + 1)
                    entities.append(ParsedEntity(kind=EntityKind.FUNCTION, name=name, location=loc))
            # fallback for Elixir defp without parens
            if ".ex" in file_path or "elixir" in file_path.lower():
                for m in _ELIXIR_FUNC_RE.finditer(line):
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
