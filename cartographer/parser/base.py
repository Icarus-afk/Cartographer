from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path

from tree_sitter import Language, Node, Parser

from cartographer.core.models import Language as ProgLang
from cartographer.core.models import ParsedEntity, Relationship


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


MAX_FILE_SIZE = 1024 * 1024  # 1 MiB — larger files are truncated with warning
MAX_SOURCE_BYTES = 2 * 1024 * 1024  # hard cap for tree-sitter


class BaseParser(ABC):
    def __init__(self, language: ProgLang) -> None:
        self._lang = language
        try:
            self._parser = Parser(self._build_language())
        except Exception as exc:  # graceful fallback if tree-sitter language missing
            import logging

            logging.getLogger(__name__).warning("Parser init failed for %s: %s", language, exc)
            self._parser = None  # type: ignore[assignment]

    @abstractmethod
    def _build_language(self) -> Language: ...

    @property
    def language(self) -> ProgLang:
        return self._lang

    def parse_file(self, path: Path) -> tuple[bytes | None, list[str]]:
        errors: list[str] = []
        try:
            try:
                size = path.stat().st_size
            except Exception:
                size = 0
            if size > MAX_FILE_SIZE:
                errors.append(f"Parse warning: large file ({size} bytes) in {path.name}: truncated to {MAX_FILE_SIZE}")
            source = path.read_bytes()
            if len(source) > MAX_SOURCE_BYTES:
                errors.append(f"Parse warning: file exceeds hard cap ({len(source)} bytes) in {path.name}")
                source = source[:MAX_SOURCE_BYTES]
            # quick binary check
            if b"\x00" in source[:8192]:
                errors.append(f"Parse skipped binary file {path.name}")
                return None, errors
            if self._parser is None:
                return source, errors
            try:
                tree = self._parser.parse(source)
            except Exception as exc:
                errors.append(f"Tree-sitter crash in {path.name}: {exc}")
                return source, errors
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

    def _extract_calls(self, node: Node, source: bytes, relationships: list[Relationship]) -> None:
        call_types = {"call", "call_expression", "method_invocation"}
        if node.type in call_types:
            func = node.child_by_field_name("function") or node.child_by_field_name("name")
            if func:
                name = self._node_text(func, source)
                if "." not in name and " " not in name and "(" not in name:
                    is_dup = any(
                        r.target_name == name and r.relationship_type == "CALLS"
                        for r in relationships
                    )
                    if not is_dup:
                        relationships.append(Relationship(
                            target_name=name,
                            relationship_type="CALLS",
                        ))
        for child in node.children:
            self._extract_calls(child, source, relationships)

    def _node_text(self, node: Node, source: bytes) -> str:
        try:
            return source[node.start_byte : node.end_byte].decode("utf-8", errors="replace")
        except Exception:
            return source[node.start_byte : node.end_byte].decode("utf-8", errors="ignore")

    def _location_from_node(self, node: Node) -> dict:
        return {
            "file_path": "",
            "start_line": node.start_point[0] + 1,
            "start_col": node.start_point[1] + 1,
            "end_line": node.end_point[0] + 1,
            "end_col": node.end_point[1] + 1,
        }

    def _extract_leading_docstring(self, node: Node, source: bytes) -> str | None:
        prev = node.prev_sibling
        if not prev:
            return None
        if prev.type == "comment":
            text = self._node_text(prev, source)
            if text.startswith("///") or text.startswith("//!"):
                return text[3:].strip()
            if text.startswith("/**") and text.endswith("*/"):
                return text[3:-3].strip()
            if text.startswith("//"):
                return text[2:].strip()
        if prev.type == "documentation_comment":
            return self._node_text(prev, source).strip()
        return None
