from __future__ import annotations

import tree_sitter_typescript
from tree_sitter import Language, Node

from cartographer.core.models import CodeLocation, EntityKind, ParsedEntity, Relationship
from cartographer.parser.languages.javascript import JavaScriptParser


class TypeScriptParser(JavaScriptParser):
    def _build_language(self) -> Language:
        return Language(tree_sitter_typescript.language_typescript())

    def _parse_node(self, node: Node, source: bytes, file_path: str) -> ParsedEntity | None:
        if node.type == "interface_declaration":
            return self._extract_interface(node, source, file_path)
        if node.type == "type_alias_declaration":
            return self._extract_type_alias(node, source, file_path)
        if node.type == "enum_declaration":
            return self._extract_enum(node, source, file_path)
        return super()._parse_node(node, source, file_path)

    def _extract_interface(
        self, node: Node, source: bytes, file_path: str
    ) -> ParsedEntity | None:
        name_node = node.child_by_field_name("name")
        if not name_node:
            return None
        name = self._node_text(name_node, source)
        loc = self._location_from_node(node)
        loc["file_path"] = file_path
        meta: dict = {}
        tp = node.child_by_field_name("type_parameters")
        if tp:
            meta["type_parameters"] = self._node_text(tp, source)
        return ParsedEntity(
            kind=EntityKind.INTERFACE,
            name=name,
            location=CodeLocation(**loc),
            metadata=meta,
        )

    def _extract_type_alias(
        self, node: Node, source: bytes, file_path: str
    ) -> ParsedEntity | None:
        name_node = node.child_by_field_name("name")
        if not name_node:
            return None
        name = self._node_text(name_node, source)
        loc = self._location_from_node(node)
        loc["file_path"] = file_path
        meta: dict = {}
        tp = node.child_by_field_name("type_parameters")
        if tp:
            meta["type_parameters"] = self._node_text(tp, source)
        return ParsedEntity(
            kind=EntityKind.TYPE_ALIAS,
            name=name,
            location=CodeLocation(**loc),
            metadata=meta,
        )

    def _extract_enum(
        self, node: Node, source: bytes, file_path: str
    ) -> ParsedEntity | None:
        name_node = node.child_by_field_name("name")
        if not name_node:
            return None
        name = self._node_text(name_node, source)
        loc = self._location_from_node(node)
        loc["file_path"] = file_path
        return ParsedEntity(
            kind=EntityKind.ENUM,
            name=name,
            location=CodeLocation(**loc),
        )

    def _extract_function(self, node: Node, source: bytes, file_path: str) -> ParsedEntity | None:
        name_node = node.child_by_field_name("name")
        name = self._node_text(name_node, source) if name_node else "anonymous"
        loc = self._location_from_node(node)
        loc["file_path"] = file_path
        meta: dict = {}
        tp = node.child_by_field_name("type_parameters")
        if tp:
            meta["type_parameters"] = self._node_text(tp, source)
        relationships: list[Relationship] = []
        self._extract_calls(node, source, relationships)
        return ParsedEntity(
            kind=EntityKind.FUNCTION,
            name=name,
            location=CodeLocation(**loc),
            metadata=meta,
            relationships=relationships,
        )
