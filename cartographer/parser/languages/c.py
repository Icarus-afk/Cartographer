from __future__ import annotations

import tree_sitter_c
from tree_sitter import Language, Node

from cartographer.core.models import CodeLocation, EntityKind, ParsedEntity
from cartographer.parser.base import BaseParser


class CParser(BaseParser):
    def _build_language(self) -> Language:
        return Language(tree_sitter_c.language())

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
        if node.type == "struct_specifier":
            return self._extract_struct(node, source, file_path)
        if node.type == "enum_specifier":
            return self._extract_enum(node, source, file_path)
        if node.type == "union_specifier":
            return self._extract_struct(node, source, file_path)
        if node.type == "declaration":
            return self._extract_declaration(node, source, file_path)
        if node.type in ("preproc_include", "preproc_def", "comment"):
            return None
        return None

    def _extract_function(self, node: Node, source: bytes, file_path: str) -> ParsedEntity | None:
        declarator = node.child_by_field_name("declarator")
        if not declarator:
            return None
        name_node = (
            declarator.child_by_field_name("declarator")
            or declarator.child_by_field_name("name")
        )
        if not name_node:
            return None
        name = self._node_text(name_node, source)
        loc = self._location_from_node(node)
        loc["file_path"] = file_path
        return ParsedEntity(
            kind=EntityKind.FUNCTION, name=name,
            location=CodeLocation(**loc),
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
                if child.type == "field_declaration":
                    for field in child.children:
                        if field.type == "field_identifier":
                            floc = self._location_from_node(field)
                            floc["file_path"] = file_path
                            children.append(ParsedEntity(
                                kind=EntityKind.VARIABLE,
                                name=self._node_text(field, source),
                                location=CodeLocation(**floc),
                            ))
        return ParsedEntity(
            kind=EntityKind.CLASS, name=name,
            location=CodeLocation(**loc), children=children,
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

    def _extract_declaration(
        self, node: Node, source: bytes, file_path: str
    ) -> ParsedEntity | None:
        for child in node.children:
            if child.type == "identifier":
                name = self._node_text(child, source)
                if name.isupper():
                    loc = self._location_from_node(node)
                    loc["file_path"] = file_path
                    return ParsedEntity(
                        kind=EntityKind.CONSTANT, name=name,
                        location=CodeLocation(**loc),
                    )
        return None
