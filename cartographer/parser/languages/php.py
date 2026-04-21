from __future__ import annotations

import tree_sitter_php
from tree_sitter import Language, Node

from cartographer.core.models import CodeLocation, EntityKind, ParsedEntity
from cartographer.parser.base import BaseParser


class PHPPhpParser(BaseParser):
    def _build_language(self) -> Language:
        return Language(tree_sitter_php.language_php())

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
            return self._extract_class(node, source, file_path)
        if node.type == "interface_declaration":
            return self._extract_interface(node, source, file_path)
        if node.type == "trait_declaration":
            return self._extract_trait(node, source, file_path)
        if node.type == "enum_declaration":
            return self._extract_enum(node, source, file_path)
        if node.type == "function_definition":
            return self._extract_function(node, source, file_path)
        if node.type == "anonymous_function":
            return None
        if node.type in ("namespace_definition", "namespace_use_declaration"):
            return None
        if node.type == "text":
            return None
        return None

    def _extract_class(self, node: Node, source: bytes, file_path: str) -> ParsedEntity | None:
        name_node = node.child_by_field_name("name")
        if not name_node:
            return None
        name = self._node_text(name_node, source)
        loc = self._location_from_node(node)
        loc["file_path"] = file_path
        children = self._extract_body(node, source, file_path)
        return ParsedEntity(
            kind=EntityKind.CLASS, name=name,
            location=CodeLocation(**loc), children=children,
        )

    def _extract_interface(self, node: Node, source: bytes, file_path: str) -> ParsedEntity | None:
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

    def _extract_trait(self, node: Node, source: bytes, file_path: str) -> ParsedEntity | None:
        name_node = node.child_by_field_name("name")
        if not name_node:
            return None
        name = self._node_text(name_node, source)
        loc = self._location_from_node(node)
        loc["file_path"] = file_path
        return ParsedEntity(
            kind=EntityKind.CLASS, name=f"trait {name}",
            location=CodeLocation(**loc),
        )

    def _extract_enum(self, node: Node, source: bytes, file_path: str) -> ParsedEntity | None:
        name_node = node.child_by_field_name("name")
        if not name_node:
            return None
        name = self._node_text(name_node, source)
        loc = self._location_from_node(node)
        loc["file_path"] = file_path
        return ParsedEntity(
            kind=EntityKind.ENUM, name=name,
            location=CodeLocation(**loc),
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

    def _extract_body(self, node: Node, source: bytes, file_path: str) -> list[ParsedEntity]:
        body = node.child_by_field_name("body")
        if not body:
            return []
        children: list[ParsedEntity] = []
        for child in body.children:
            if child.type == "method_declaration":
                name_node = child.child_by_field_name("name")
                if not name_node:
                    continue
                name = self._node_text(name_node, source)
                mloc = self._location_from_node(child)
                mloc["file_path"] = file_path
                children.append(ParsedEntity(
                    kind=EntityKind.METHOD, name=name,
                    location=CodeLocation(**mloc),
                ))
        return children
