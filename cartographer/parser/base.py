from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path

from tree_sitter import Language, Node, Parser

from cartographer.core.models import Language as ProgLang
from cartographer.core.models import ParsedEntity


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
                errors.append(f"Parse errors in {path}")
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
