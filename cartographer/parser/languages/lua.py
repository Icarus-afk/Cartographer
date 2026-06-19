from __future__ import annotations

import tree_sitter_lua
from tree_sitter import Language, Node

from cartographer.core.models import CodeLocation, EntityKind, ParsedEntity, Relationship
from cartographer.parser.base import BaseParser


class LuaParser(BaseParser):
    def _build_language(self) -> Language:
        return Language(tree_sitter_lua.language())

    def extract_entities(self, source: bytes, file_path: str) -> list[ParsedEntity]:
        entities: list[ParsedEntity] = []
        root = self._parser.parse(source).root_node
        for child in root.children:
            entity = self._parse_top(child, source, file_path)
            if entity:
                entities.append(entity)
        return entities

    def _parse_top(self, node: Node, source: bytes, file_path: str) -> ParsedEntity | None:
        if node.type == "function_declaration":
            return self._extract_function(node, source, file_path)
        if node.type == "function_call":
            return None
        if node.type == "local_function_declaration":
            return self._extract_local_function(node, source, file_path)
        if node.type == "local_variable_declaration":
            return None
        if node.type == "assignment_statement":
            return None
        return None

    def _extract_function(self, node: Node, source: bytes, file_path: str) -> ParsedEntity | None:
        name_node = node.child_by_field_name("name")
        if not name_node:
            return None
        name = self._node_text(name_node, source)
        loc = self._location_from_node(node)
        loc["file_path"] = file_path

        relationships: list[Relationship] = []
        self._extract_calls(node, source, relationships)

        return ParsedEntity(
            kind=EntityKind.FUNCTION, name=name,
            location=CodeLocation(**loc),
            relationships=relationships,
        )

    def _extract_local_function(
        self, node: Node, source: bytes, file_path: str
    ) -> ParsedEntity | None:
        name_node = node.child_by_field_name("name")
        if not name_node:
            return None
        name = "local " + self._node_text(name_node, source)
        loc = self._location_from_node(node)
        loc["file_path"] = file_path

        relationships: list[Relationship] = []
        self._extract_calls(node, source, relationships)

        return ParsedEntity(
            kind=EntityKind.FUNCTION, name=name,
            location=CodeLocation(**loc),
            relationships=relationships,
        )
