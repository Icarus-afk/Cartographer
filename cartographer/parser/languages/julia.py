from __future__ import annotations

import tree_sitter_julia
from tree_sitter import Language, Node

from cartographer.core.models import CodeLocation, EntityKind, ParsedEntity, Relationship
from cartographer.parser.base import BaseParser


class JuliaParser(BaseParser):
    def _build_language(self) -> Language:
        return Language(tree_sitter_julia.language())

    def extract_entities(self, source: bytes, file_path: str) -> list[ParsedEntity]:
        entities: list[ParsedEntity] = []
        root = self._parser.parse(source).root_node
        for child in root.children:
            entity = self._parse_top(child, source, file_path)
            if entity:
                entities.append(entity)
        return entities

    def _parse_top(self, node: Node, source: bytes, file_path: str) -> ParsedEntity | None:
        if node.type == "function_definition":
            return self._extract_function(node, source, file_path)
        if node.type == "struct_definition":
            return self._extract_struct(node, source, file_path)
        if node.type == "abstract_struct_definition":
            return self._extract_struct(node, source, file_path)
        if node.type == "primitive_struct_definition":
            return self._extract_struct(node, source, file_path)
        if node.type == "module_definition":
            return self._extract_module(node, source, file_path)
        if node.type == "macro_definition":
            return self._extract_macro(node, source, file_path)
        if node.type in ("import_statement", "using_statement", "export_statement"):
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

    def _extract_struct(self, node: Node, source: bytes, file_path: str) -> ParsedEntity | None:
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
                if child.type in ("function_definition", "call_expression"):
                    continue

        return ParsedEntity(
            kind=EntityKind.CLASS, name=name,
            location=CodeLocation(**loc), children=children,
        )

    def _extract_module(self, node: Node, source: bytes, file_path: str) -> ParsedEntity | None:
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

    def _extract_macro(self, node: Node, source: bytes, file_path: str) -> ParsedEntity | None:
        name_node = node.child_by_field_name("name")
        if not name_node:
            return None
        name = "macro " + self._node_text(name_node, source)
        loc = self._location_from_node(node)
        loc["file_path"] = file_path

        relationships: list[Relationship] = []
        self._extract_calls(node, source, relationships)

        return ParsedEntity(
            kind=EntityKind.FUNCTION, name=name,
            location=CodeLocation(**loc),
            relationships=relationships,
        )
