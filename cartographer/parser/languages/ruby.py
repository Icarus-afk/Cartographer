from __future__ import annotations

import tree_sitter_ruby
from tree_sitter import Language, Node

from cartographer.core.models import CodeLocation, EntityKind, ParsedEntity, Relationship
from cartographer.parser.base import BaseParser


class RubyParser(BaseParser):
    def _build_language(self) -> Language:
        return Language(tree_sitter_ruby.language())

    def extract_entities(self, source: bytes, file_path: str) -> list[ParsedEntity]:
        entities: list[ParsedEntity] = []
        root = self._parser.parse(source).root_node
        for child in root.children:
            entity = self._parse_top(child, source, file_path)
            if entity:
                entities.append(entity)
        return entities

    def _parse_top(self, node: Node, source: bytes, file_path: str) -> ParsedEntity | None:
        if node.type == "class":
            return self._extract_class(node, source, file_path)
        if node.type == "module":
            return self._extract_module(node, source, file_path)
        if node.type == "method":
            return self._extract_method(node, source, file_path, EntityKind.FUNCTION)
        if node.type == "singleton_method":
            return self._extract_singleton_method(node, source, file_path)
        if node.type == "call":
            return None
        return None

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
                if child.type == "method":
                    parsed = self._extract_method(child, source, file_path, EntityKind.METHOD)
                    if parsed:
                        children.append(parsed)
                elif child.type == "singleton_method":
                    parsed = self._extract_singleton_method(child, source, file_path)
                    if parsed:
                        children.append(parsed)

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
                if child.type == "class":
                    parsed = self._extract_class(child, source, file_path)
                    if parsed:
                        children.append(parsed)
                elif child.type == "module":
                    parsed = self._extract_module(child, source, file_path)
                    if parsed:
                        children.append(parsed)
                elif child.type == "method":
                    parsed = self._extract_method(child, source, file_path, EntityKind.METHOD)
                    if parsed:
                        children.append(parsed)

        return ParsedEntity(
            kind=EntityKind.MODULE, name=name,
            location=CodeLocation(**loc), children=children,
        )

    def _extract_method(
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

    def _extract_singleton_method(
        self, node: Node, source: bytes, file_path: str
    ) -> ParsedEntity | None:
        name_node = node.child_by_field_name("name")
        if not name_node:
            return None
        name = "self." + self._node_text(name_node, source)
        loc = self._location_from_node(node)
        loc["file_path"] = file_path
        relationships: list[Relationship] = []
        self._extract_calls(node, source, relationships)
        return ParsedEntity(
            kind=EntityKind.METHOD, name=name,
            location=CodeLocation(**loc),
            relationships=relationships,
        )
