from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path

from tree_sitter import Language, Node, Parser

from cartographer.core.models import Language as ProgLang
from cartographer.core.models import ParsedEntity


def _count_error_nodes(node: Node) -> tuple[int, int]:
    error_count = 0
    missing_count = 0
    if not node.children:
        if node.type == "ERROR":
            error_count = 1
        return error_count, missing_count
    for child in node.children:
        if child.type == "ERROR":
            error_count += 1
        if child.is_missing:
            missing_count += 1
        e, m = _count_error_nodes(child)
        error_count += e
        missing_count += m
    return error_count, missing_count


class BaseParser(ABC):
    def __init__(self, language: ProgLang) -> None:
        self._lang = language
        self._parser = Parser(self._build_language())

    @abstractmethod
    def _build_language(self) -> Language: ...

    @property
    def language(self) -> ProgLang:
        return self._lang

    def parse_file(self, path: Path) -> tuple[bytes | None, list[str]]:
        errors: list[str] = []
        try:
            source = path.read_bytes()
            tree = self._parser.parse(source)
            if tree and tree.root_node.has_error:
                error_nodes, missing = _count_error_nodes(tree.root_node)
                if tree.root_node.type == "ERROR":
                    errors.append(f"Parse catastrophic in {path.name}: root is ERROR, {missing} missing")
                elif error_nodes <= 3 and missing == 0:
                    pass
                else:
                    detail = f"{error_nodes} error nodes"
                    if missing:
                        detail += f", {missing} missing"
                    errors.append(f"Parse errors in {path.name}: {detail}")
            return source, errors
        except Exception as e:
            errors.append(f"Failed to parse {path}: {e}")
            return None, errors

    @abstractmethod
    def extract_entities(self, source: bytes, file_path: str) -> list[ParsedEntity]: ...

    def _node_text(self, node: Node, source: bytes) -> str:
        return source[node.start_byte : node.end_byte].decode("utf-8")

    def _location_from_node(self, node: Node) -> dict:
        return {
            "file_path": "",
            "start_line": node.start_point[0] + 1,
            "start_col": node.start_point[1] + 1,
            "end_line": node.end_point[0] + 1,
            "end_col": node.end_point[1] + 1,
        }
