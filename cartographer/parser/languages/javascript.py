from __future__ import annotations

import tree_sitter_javascript
from tree_sitter import Language, Node

from cartographer.core.models import CodeLocation, EntityKind, ParsedEntity
from cartographer.parser.base import BaseParser


class JavaScriptParser(BaseParser):
    def _build_language(self) -> Language:
        return Language(tree_sitter_javascript.language())

    def extract_entities(self, source: bytes, file_path: str) -> list[ParsedEntity]:
        entities: list[ParsedEntity] = []
        root = self._parser.parse(source).root_node

        for child in root.children:
            entity = self._parse_node(child, source, file_path)
            if entity:
                entities.append(entity)

        return entities

    def _parse_node(self, node: Node, source: bytes, file_path: str) -> ParsedEntity | None:
        if node.type == "function_declaration":
            return self._extract_function(node, source, file_path)
        if node.type == "class_declaration":
            return self._extract_class(node, source, file_path)
        if node.type == "arrow_function":
            return self._extract_arrow_function(node, source, file_path)
        if node.type == "variable_declaration":
            return self._extract_variable_declaration(node, source, file_path)
        if node.type == "export_statement":
            return self._extract_export(node, source, file_path)
        if node.type == "lexical_declaration":
            return self._extract_lexical_declaration(node, source, file_path)
        return None

    def _extract_function(self, node: Node, source: bytes, file_path: str) -> ParsedEntity | None:
        name_node = node.child_by_field_name("name")
        if not name_node:
            return None
        name = self._node_text(name_node, source)
        loc = self._location_from_node(node)
        loc["file_path"] = file_path
        return ParsedEntity(
            kind=EntityKind.FUNCTION,
            name=name,
            location=CodeLocation(**loc),
        )

    def _extract_class(self, node: Node, source: bytes, file_path: str) -> ParsedEntity | None:
        name_node = node.child_by_field_name("name")
        if not name_node:
            return None
        name = self._node_text(name_node, source)
        loc = self._location_from_node(node)
        loc["file_path"] = file_path

        children: list[ParsedEntity] = []
        body = node.child_by_field_name("body")
        if body:
            for child in body.children:
                parsed = self._parse_class_member(child, source, file_path)
                if parsed:
                    children.append(parsed)

        return ParsedEntity(
            kind=EntityKind.CLASS,
            name=name,
            location=CodeLocation(**loc),
            children=children,
        )

    def _parse_class_member(self, node: Node, source: bytes, file_path: str) -> ParsedEntity | None:
        if node.type == "method_definition":
            name_node = node.child_by_field_name("name")
            if not name_node:
                return None
            name = self._node_text(name_node, source)
            loc = self._location_from_node(node)
            loc["file_path"] = file_path
            return ParsedEntity(
                kind=EntityKind.METHOD,
                name=name,
                location=CodeLocation(**loc),
            )
        return None

    def _extract_arrow_function(
        self, node: Node, source: bytes, file_path: str
    ) -> ParsedEntity | None:
        loc = self._location_from_node(node)
        loc["file_path"] = file_path
        return ParsedEntity(
            kind=EntityKind.FUNCTION,
            name="<anonymous>",
            location=CodeLocation(**loc),
        )

    def _extract_variable_declaration(
        self, node: Node, source: bytes, file_path: str
    ) -> ParsedEntity | None:
        entities: list[ParsedEntity] = []
        for child in node.children:
            if child.type == "variable_declarator":
                name_node = child.child_by_field_name("name")
                if name_node:
                    entities.append(self._make_variable(name_node, source, file_path))
        return entities[0] if entities else None

    def _extract_lexical_declaration(
        self, node: Node, source: bytes, file_path: str
    ) -> ParsedEntity | None:
        for child in node.children:
            if child.type == "variable_declarator":
                name_node = child.child_by_field_name("name")
                if name_node:
                    return self._make_variable(name_node, source, file_path)
        return None

    def _make_variable(self, name_node: Node, source: bytes, file_path: str) -> ParsedEntity:
        name = self._node_text(name_node, source)
        loc = self._location_from_node(name_node)
        loc["file_path"] = file_path
        return ParsedEntity(
            kind=EntityKind.CONSTANT,
            name=name,
            location=CodeLocation(**loc),
        )

    def _extract_export(self, node: Node, source: bytes, file_path: str) -> ParsedEntity | None:
        for child in node.children:
            parsed = self._parse_node(child, source, file_path)
            if parsed:
                return parsed
        return None
