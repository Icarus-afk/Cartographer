from __future__ import annotations

import tree_sitter_zig
from tree_sitter import Language, Node

from cartographer.core.models import CodeLocation, EntityKind, ParsedEntity
from cartographer.parser.base import BaseParser


class ZigParser(BaseParser):
    def _build_language(self) -> Language:
        return Language(tree_sitter_zig.language())

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
        if node.type == "struct_declaration":
            return self._extract_container(node, source, file_path, EntityKind.CLASS)
        if node.type == "union_declaration":
            return self._extract_container(node, source, file_path, EntityKind.CLASS)
        if node.type == "enum_declaration":
            return self._extract_container(node, source, file_path, EntityKind.ENUM)
        if node.type == "error_set_declaration":
            return self._extract_container(node, source, file_path, EntityKind.ENUM)
        if node.type == "variable_declaration":
            return self._extract_variable(node, source, file_path)
        if node.type == "test_declaration":
            loc = self._location_from_node(node)
            loc["file_path"] = file_path
            return ParsedEntity(
                kind=EntityKind.FUNCTION, name="<test>",
                location=CodeLocation(**loc),
            )
        # containers inside containers (pub const, etc)
        if node.type in ("container_member", "declaration_member"):
            for child in node.children:
                parsed = self._parse_top(child, source, file_path)
                if parsed:
                    return parsed
        return None

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

    def _extract_container(
        self, node: Node, source: bytes, file_path: str, kind: EntityKind
    ) -> ParsedEntity | None:
        name_node = node.child_by_field_name("name")
        if not name_node:
            return None
        name = self._node_text(name_node, source)
        loc = self._location_from_node(node)
        loc["file_path"] = file_path

        children: list[ParsedEntity] = []
        body = None
        for c in node.children:
            if c.type == "struct_declaration_body":
                body = c
                break
        if body:
            for member in body.children:
                if member.type == "container_member":
                    for sub in member.children:
                        parsed = self._parse_top(sub, source, file_path)
                        if parsed:
                            children.append(parsed)
                elif member.type == "function_declaration":
                    parsed = self._extract_function(member, source, file_path)
                    if parsed:
                        parsed.kind = EntityKind.METHOD
                        children.append(parsed)

        return ParsedEntity(
            kind=kind, name=name,
            location=CodeLocation(**loc), children=children,
        )

    def _extract_variable(self, node: Node, source: bytes, file_path: str) -> ParsedEntity | None:
        name_node = node.child_by_field_name("name")
        if not name_node:
            return None
        name = self._node_text(name_node, source)
        loc = self._location_from_node(node)
        loc["file_path"] = file_path
        kind = EntityKind.CONSTANT if name.isupper() else EntityKind.VARIABLE
        return ParsedEntity(
            kind=kind, name=name,
            location=CodeLocation(**loc),
        )
