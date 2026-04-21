from __future__ import annotations

import tree_sitter_java
from tree_sitter import Language, Node

from cartographer.core.models import CodeLocation, EntityKind, ParsedEntity
from cartographer.parser.base import BaseParser


class JavaParser(BaseParser):
    def _build_language(self) -> Language:
        return Language(tree_sitter_java.language())

    def extract_entities(self, source: bytes, file_path: str) -> list[ParsedEntity]:
        entities: list[ParsedEntity] = []
        root = self._parser.parse(source).root_node
        for child in root.children:
            entity = self._parse_declaration(child, source, file_path)
            if entity:
                entities.append(entity)
        return entities

    def _parse_declaration(self, node: Node, source: bytes, file_path: str) -> ParsedEntity | None:
        if node.type == "class_declaration":
            return self._extract_class(node, source, file_path)
        if node.type == "interface_declaration":
            return self._extract_interface(node, source, file_path)
        if node.type == "enum_declaration":
            return self._extract_enum(node, source, file_path)
        if node.type == "annotation_type_declaration":
            return self._extract_annotation(node, source, file_path)
        if node.type == "record_declaration":
            return self._extract_class(node, source, file_path)
        if node.type in ("import_declaration", "package_declaration"):
            return self._extract_module(node, source, file_path)
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

    def _extract_annotation(self, node: Node, source: bytes, file_path: str) -> ParsedEntity | None:
        name_node = node.child_by_field_name("name")
        if not name_node:
            return None
        name = self._node_text(name_node, source)
        loc = self._location_from_node(node)
        loc["file_path"] = file_path
        return ParsedEntity(
            kind=EntityKind.CLASS, name=f"@{name}",
            location=CodeLocation(**loc),
        )

    def _extract_module(self, node: Node, source: bytes, file_path: str) -> ParsedEntity | None:
        loc = self._location_from_node(node)
        loc["file_path"] = file_path
        return ParsedEntity(
            kind=EntityKind.MODULE,
            name=self._node_text(node, source),
            location=CodeLocation(**loc),
        )

    def _extract_body(self, node: Node, source: bytes, file_path: str) -> list[ParsedEntity]:
        body = node.child_by_field_name("body")
        if not body:
            return []
        children: list[ParsedEntity] = []
        for child in body.children:
            if child.type == "method_declaration":
                parsed = self._extract_method(child, source, file_path)
                if parsed:
                    children.append(parsed)
            elif child.type == "field_declaration":
                parsed = self._extract_field(child, source, file_path)
                if parsed:
                    children.append(parsed)
        return children

    def _extract_method(self, node: Node, source: bytes, file_path: str) -> ParsedEntity | None:
        name_node = node.child_by_field_name("name")
        if not name_node:
            return None
        name = self._node_text(name_node, source)
        loc = self._location_from_node(node)
        loc["file_path"] = file_path
        return ParsedEntity(
            kind=EntityKind.METHOD, name=name,
            location=CodeLocation(**loc),
        )

    def _extract_field(self, node: Node, source: bytes, file_path: str) -> ParsedEntity | None:
        declarator = node.child_by_field_name("declarator")
        if not declarator:
            return None
        name_node = declarator.child_by_field_name("name")
        if not name_node:
            return None
        name = self._node_text(name_node, source)
        loc = self._location_from_node(node)
        loc["file_path"] = file_path
        return ParsedEntity(
            kind=EntityKind.VARIABLE, name=name,
            location=CodeLocation(**loc),
        )
