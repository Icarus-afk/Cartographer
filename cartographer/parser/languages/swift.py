from __future__ import annotations

import tree_sitter_swift
from tree_sitter import Language, Node

from cartographer.core.models import CodeLocation, EntityKind, ParsedEntity
from cartographer.parser.base import BaseParser


class SwiftParser(BaseParser):
    def _build_language(self) -> Language:
        return Language(tree_sitter_swift.language())

    def extract_entities(self, source: bytes, file_path: str) -> list[ParsedEntity]:
        entities: list[ParsedEntity] = []
        root = self._parser.parse(source).root_node
        for child in root.children:
            entity = self._parse_top(child, source, file_path)
            if entity:
                entities.append(entity)
        return entities

    def _parse_top(self, node: Node, source: bytes, file_path: str) -> ParsedEntity | None:
        if node.type == "class_declaration":
            return self._extract_class(node, source, file_path, EntityKind.CLASS)
        if node.type == "struct_declaration":
            return self._extract_class(node, source, file_path, EntityKind.CLASS)
        if node.type == "enum_declaration":
            return self._extract_class(node, source, file_path, EntityKind.ENUM)
        if node.type == "protocol_declaration":
            return self._extract_protocol(node, source, file_path)
        if node.type == "extension_declaration":
            return self._extract_extension(node, source, file_path)
        if node.type == "function_declaration":
            return self._extract_function(node, source, file_path)
        if node.type == "import_declaration":
            return None
        if node.type == "variable_declaration":
            return self._extract_variable(node, source, file_path)
        return None

    def _extract_class(
        self, node: Node, source: bytes, file_path: str, kind: EntityKind
    ) -> ParsedEntity | None:
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
                if child.type == "function_declaration":
                    parsed = self._extract_function(child, source, file_path)
                    if parsed:
                        parsed.kind = EntityKind.METHOD
                        children.append(parsed)
                elif child.type == "variable_declaration":
                    parsed = self._extract_variable(child, source, file_path)
                    if parsed:
                        children.append(parsed)

        return ParsedEntity(
            kind=kind, name=name,
            location=CodeLocation(**loc), children=children,
        )

    def _extract_protocol(self, node: Node, source: bytes, file_path: str) -> ParsedEntity | None:
        name_node = node.child_by_field_name("name")
        if not name_node:
            return None
        name = self._node_text(name_node, source)
        loc = self._location_from_node(node)
        loc["file_path"] = file_path
        return ParsedEntity(
            kind=EntityKind.INTERFACE, name=name,
            location=CodeLocation(**loc),
        )

    def _extract_extension(self, node: Node, source: bytes, file_path: str) -> ParsedEntity | None:
        type_node = node.child_by_field_name("type")
        if not type_node:
            return None
        name = self._node_text(type_node, source)
        loc = self._location_from_node(node)
        loc["file_path"] = file_path

        children: list[ParsedEntity] = []
        body = node.child_by_field_name("body")
        if body:
            for child in body.children:
                if child.type == "function_declaration":
                    parsed = self._extract_function(child, source, file_path)
                    if parsed:
                        parsed.kind = EntityKind.METHOD
                        children.append(parsed)

        return ParsedEntity(
            kind=EntityKind.CLASS, name=f"{name}+",
            location=CodeLocation(**loc), children=children,
        )

    def _extract_function(self, node: Node, source: bytes, file_path: str) -> ParsedEntity | None:
        name_node = node.child_by_field_name("name")
        if not name_node:
            return None
        name = self._node_text(name_node, source)
        loc = self._location_from_node(node)
        loc["file_path"] = file_path
        return ParsedEntity(
            kind=EntityKind.FUNCTION, name=name,
            location=CodeLocation(**loc),
        )

    def _extract_variable(self, node: Node, source: bytes, file_path: str) -> ParsedEntity | None:
        name_node = node.child_by_field_name("name")
        if not name_node:
            return None
        name = self._node_text(name_node, source)
        loc = self._location_from_node(node)
        loc["file_path"] = file_path
        return ParsedEntity(
            kind=EntityKind.VARIABLE, name=name,
            location=CodeLocation(**loc),
        )
