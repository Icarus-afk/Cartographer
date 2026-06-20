from __future__ import annotations

import tree_sitter_c_sharp
from tree_sitter import Language, Node

from cartographer.core.models import CodeLocation, EntityKind, ParsedEntity, Relationship
from cartographer.parser.base import BaseParser


class CSharpParser(BaseParser):
    def _build_language(self) -> Language:
        return Language(tree_sitter_c_sharp.language())

    def extract_entities(self, source: bytes, file_path: str) -> list[ParsedEntity]:
        entities: list[ParsedEntity] = []
        root = self._parser.parse(source).root_node
        for child in root.children:
            entity = self._parse_top(child, source, file_path)
            if entity:
                entities.append(entity)
        return entities

    def _parse_top(self, node: Node, source: bytes, file_path: str) -> ParsedEntity | None:
        if node.type == "namespace_declaration":
            return self._extract_namespace(node, source, file_path)
        if node.type == "class_declaration":
            return self._extract_class(node, source, file_path)
        if node.type == "struct_declaration":
            return self._extract_class(node, source, file_path)
        if node.type == "interface_declaration":
            return self._extract_interface(node, source, file_path)
        if node.type == "enum_declaration":
            return self._extract_enum(node, source, file_path)
        if node.type == "record_declaration":
            return self._extract_class(node, source, file_path)
        if node.type in ("using_directive", "global_attribute"):
            return None
        return None

    def _extract_namespace(self, node: Node, source: bytes, file_path: str) -> ParsedEntity | None:
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
                parsed = self._parse_top(child, source, file_path)
                if parsed:
                    children.append(parsed)

        return ParsedEntity(
            kind=EntityKind.MODULE, name=name,
            location=CodeLocation(**loc), children=children,
        )

    def _extract_base_types(self, node: Node, source: bytes) -> list[str]:
        base_list = node.child_by_field_name("base_list")
        if not base_list:
            return []
        types: list[str] = []
        for child in base_list.children:
            if child.type in ("simple_name", "qualified_name", "generic_name"):
                types.append(self._node_text(child, source))
        return types

    def _extract_class(self, node: Node, source: bytes, file_path: str) -> ParsedEntity | None:
        name_node = node.child_by_field_name("name")
        if not name_node:
            return None
        name = self._node_text(name_node, source)
        loc = self._location_from_node(node)
        loc["file_path"] = file_path
        children = self._extract_members(node, source, file_path)
        base_types = self._extract_base_types(node, source)
        relationships = [
            Relationship(target_name=t, relationship_type="INHERITS")
            for t in base_types
        ]
        return ParsedEntity(
            kind=EntityKind.CLASS, name=name,
            location=CodeLocation(**loc), children=children,
            relationships=relationships,
        )

    def _extract_interface(self, node: Node, source: bytes, file_path: str) -> ParsedEntity | None:
        name_node = node.child_by_field_name("name")
        if not name_node:
            return None
        name = self._node_text(name_node, source)
        loc = self._location_from_node(node)
        loc["file_path"] = file_path
        base_types = self._extract_base_types(node, source)
        relationships = [
            Relationship(target_name=t, relationship_type="INHERITS")
            for t in base_types
        ]

        children: list[ParsedEntity] = []
        body = node.child_by_field_name("body")
        if body:
            for child in body.children:
                if child.type == "method_declaration":
                    parsed = self._extract_method(child, source, file_path)
                    if parsed:
                        children.append(parsed)
                elif child.type == "property_declaration":
                    parsed = self._extract_property(child, source, file_path)
                    if parsed:
                        children.append(parsed)

        return ParsedEntity(
            kind=EntityKind.INTERFACE, name=name,
            location=CodeLocation(**loc),
            children=children,
            relationships=relationships,
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

    def _extract_members(self, node: Node, source: bytes, file_path: str) -> list[ParsedEntity]:
        body = node.child_by_field_name("body")
        if not body:
            return []
        children: list[ParsedEntity] = []
        for child in body.children:
            if child.type == "method_declaration":
                parsed = self._extract_method(child, source, file_path)
                if parsed:
                    children.append(parsed)
            elif child.type == "property_declaration":
                parsed = self._extract_property(child, source, file_path)
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
        docstring = self._extract_leading_docstring(node, source)

        relationships: list[Relationship] = []
        self._extract_calls(node, source, relationships)

        return ParsedEntity(
            kind=EntityKind.METHOD, name=name,
            location=CodeLocation(**loc),
            docstring=docstring,
            relationships=relationships,
        )

    def _extract_property(self, node: Node, source: bytes, file_path: str) -> ParsedEntity | None:
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

    def _extract_field(self, node: Node, source: bytes, file_path: str) -> ParsedEntity | None:
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
