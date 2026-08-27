from __future__ import annotations

import re
from pathlib import Path

import tree_sitter_python
from tree_sitter import Language as TS_Language

from cartographer.core.models import CodeLocation, EntityKind, ParsedEntity
from cartographer.core.models import Language as ProgLang
from cartographer.parser.base import BaseParser

_DART_CLASS = re.compile(r"^\s*(?:abstract\s+)?(?:class|mixin|extension|enum)\s+(\w+)", re.MULTILINE)
_DART_FUNC = re.compile(r"^\s*(?:Future<[^>]+>|[A-Za-z_][\w<>,\s]*)\s+(\w+)\s*\([^)]*\)\s*(?:async)?\s*\{", re.MULTILINE)
_DART_METHOD = re.compile(r"^\s*(?:@\w+\s*)*\s*(?:static\s+)?(?:Future<[^>]+>|[A-Za-z_][\w<>]*)\s+(\w+)\s*\(", re.MULTILINE)
_DART_IMPORT = re.compile(r"^\s*import\s+['\"]([^'\"]+)['\"]", re.MULTILINE)
_DART_PART = re.compile(r"^\s*part\s+['\"]([^'\"]+)['\"]", re.MULTILINE)


class DartParser(BaseParser):
    def _build_language(self) -> TS_Language:
        return TS_Language(tree_sitter_python.language())

    def __init__(self, language: ProgLang) -> None:
        super().__init__(language)
        self._tree_parser = None
        self._use_tree = False
        try:
            import tree_sitter_dart  # type: ignore
            from tree_sitter import Language, Parser

            self._tree_parser = Parser(Language(tree_sitter_dart.language()))
            self._use_tree = True
        except Exception:
            self._use_tree = False

    def parse_file(self, path: Path) -> tuple[bytes | None, list[str]]:
        try:
            source = path.read_bytes()
            return source, []
        except Exception as e:
            return None, [f"Failed to read {path}: {e}"]

    def extract_entities(self, source: bytes, file_path: str) -> list[ParsedEntity]:
        if not source.strip():
            return []
        if self._use_tree and self._tree_parser is not None:
            try:
                return self._extract_tree(source, file_path)
            except Exception:
                pass
        return self._extract_regex(source, file_path)

    def _extract_tree(self, source: bytes, file_path: str) -> list[ParsedEntity]:
        from cartographer.core.models import CodeLocation as CL

        entities: list[ParsedEntity] = []
        root = self._tree_parser.parse(source).root_node

        def _node_text(n) -> str:
            return source[n.start_byte : n.end_byte].decode("utf-8", errors="replace")

        def visit(node):
            t = node.type
            if t in ("class_definition", "mixin_declaration", "extension_declaration", "enum_declaration"):
                name_node = node.child_by_field_name("name")
                if name_node:
                    name = _node_text(name_node)
                    loc = CL(file_path=file_path, start_line=node.start_point[0] + 1, start_col=node.start_point[1] + 1, end_line=node.end_point[0] + 1, end_col=node.end_point[1] + 1)
                    kind = EntityKind.ENUM if t == "enum_declaration" else EntityKind.CLASS
                    entities.append(ParsedEntity(kind=kind, name=name, location=loc))
            elif t in ("function_signature", "function_body", "method_signature"):
                name_node = node.child_by_field_name("name")
                if name_node:
                    name = _node_text(name_node)
                    loc = CL(file_path=file_path, start_line=node.start_point[0] + 1, start_col=node.start_point[1] + 1, end_line=node.end_point[0] + 1, end_col=node.end_point[1] + 1)
                    entities.append(ParsedEntity(kind=EntityKind.FUNCTION, name=name, location=loc))
            elif t == "import_specification":
                loc = CL(file_path=file_path, start_line=node.start_point[0] + 1, start_col=node.start_point[1] + 1, end_line=node.end_point[0] + 1, end_col=node.end_point[1] + 1)
                entities.append(ParsedEntity(kind=EntityKind.MODULE, name=f"import:{_node_text(node)[:120]}", location=loc))
            for child in node.children:
                visit(child)

        visit(root)
        if not entities:
            return self._extract_regex(source, file_path)
        return entities

    def _extract_regex(self, source: bytes, file_path: str) -> list[ParsedEntity]:
        text = source.decode("utf-8", errors="replace")
        entities: list[ParsedEntity] = []
        seen: set[str] = set()
        for idx, line in enumerate(text.splitlines(), start=1):
            m = _DART_CLASS.search(line)
            if m:
                name = m.group(1)
                if name not in seen:
                    seen.add(name)
                    loc = CodeLocation(file_path=file_path, start_line=idx, start_col=1, end_line=idx, end_col=len(line) + 1)
                    kind = EntityKind.ENUM if "enum" in line else EntityKind.CLASS
                    entities.append(ParsedEntity(kind=kind, name=name, location=loc))
            mi = _DART_IMPORT.search(line)
            if mi:
                loc = CodeLocation(file_path=file_path, start_line=idx, start_col=1, end_line=idx, end_col=len(line) + 1)
                entities.append(ParsedEntity(kind=EntityKind.MODULE, name=f"import:{mi.group(1)}", location=loc))
            else:
                mp = _DART_PART.search(line)
                if mp:
                    loc = CodeLocation(file_path=file_path, start_line=idx, start_col=1, end_line=idx, end_col=len(line) + 1)
                    entities.append(ParsedEntity(kind=EntityKind.MODULE, name=f"import:{mp.group(1)}", location=loc))
        for idx, line in enumerate(text.splitlines(), start=1):
            m = _DART_FUNC.search(line)
            if m:
                name = m.group(1)
                if name not in seen and name not in {"if", "for", "while", "switch", "catch"}:
                    seen.add(name)
                    loc = CodeLocation(file_path=file_path, start_line=idx, start_col=1, end_line=idx, end_col=len(line) + 1)
                    entities.append(ParsedEntity(kind=EntityKind.FUNCTION, name=name, location=loc))
        return entities
