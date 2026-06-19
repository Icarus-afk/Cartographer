from __future__ import annotations

import tree_sitter_kotlin
from tree_sitter import Language, Node

from cartographer.core.models import CodeLocation, EntityKind, ParsedEntity, Relationship
from cartographer.parser.base import BaseParser


class KotlinParser(BaseParser):
    def _build_language(self) -> Language:
        return Language(tree_sitter_kotlin.language())

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
            return self._extract_class_or_interface(node, source, file_path)
        if node.type == "object_declaration":
            return self._extract_object(node, source, file_path)
        if node.type == "fun_declaration":
            return self._extract_function(node, source, file_path, EntityKind.FUNCTION)
        if node.type == "property_declaration":
            return self._extract_property(node, source, file_path)
        if node.type == "type_alias":
            return self._extract_type_alias(node, source, file_path)
        if node.type == "import_list":
            return None
        return None

    def _extract_class_or_interface(
        self, node: Node, source: bytes, file_path: str
    ) -> ParsedEntity | None:
        name_node = node.child_by_field_name("name")
        if not name_node:
            return None
        name = self._node_text(name_node, source)

        modifier_types = ("interface", "data", "sealed", "abstract", "open", "inner")
        modifiers = [c.type for c in node.children if c.type in modifier_types]
        kind = EntityKind.INTERFACE if "interface" in modifiers else EntityKind.CLASS

        loc = self._location_from_node(node)
        loc["file_path"] = file_path

        relationships: list[Relationship] = []
        for child in node.children:
            if child.type == "delegation_specification":
                type_ref = child.child_by_field_name("type")
                if type_ref:
                    rel_name = self._node_text(type_ref, source)
                    rel_type = "IMPLEMENTS" if kind == EntityKind.CLASS else "INHERITS"
                    relationships.append(Relationship(
                        target_name=rel_name,
                        relationship_type=rel_type,
                    ))

        body = node.child_by_field_name("body")
        children: list[ParsedEntity] = []
        if body:
            for child in body.children:
                if child.type == "fun_declaration":
                    parsed = self._extract_function(child, source, file_path, EntityKind.METHOD)
                    if parsed:
                        children.append(parsed)
                elif child.type == "property_declaration":
                    parsed = self._extract_property(child, source, file_path)
                    if parsed:
                        children.append(parsed)

        return ParsedEntity(
            kind=kind, name=name,
            location=CodeLocation(**loc), children=children,
            relationships=relationships,
        )

    def _extract_object(self, node: Node, source: bytes, file_path: str) -> ParsedEntity | None:
        name_node = node.child_by_field_name("name")
        name = self._node_text(name_node, source) if name_node else "<companion>"
        loc = self._location_from_node(node)
        loc["file_path"] = file_path
        return ParsedEntity(
            kind=EntityKind.CLASS, name=name,
            location=CodeLocation(**loc),
        )

    def _extract_function(
        self, node: Node, source: bytes, file_path: str, kind: EntityKind
    ) -> ParsedEntity | None:
        name_node = node.child_by_field_name("name")
        if not name_node:
            return None
        name = self._node_text(name_node, source)
        loc = self._location_from_node(node)
        loc["file_path"] = file_path
        relationships: list[Relationship] = []
        self._extract_calls(node, source, relationships)
        return ParsedEntity(
            kind=kind, name=name,
            location=CodeLocation(**loc),
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

    def _extract_type_alias(self, node: Node, source: bytes, file_path: str) -> ParsedEntity | None:
        name_node = node.child_by_field_name("name")
        if not name_node:
            return None
        name = self._node_text(name_node, source)
        loc = self._location_from_node(node)
        loc["file_path"] = file_path
        return ParsedEntity(
            kind=EntityKind.CONSTANT, name=name,
            location=CodeLocation(**loc),
        )
