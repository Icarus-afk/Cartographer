from __future__ import annotations

import tree_sitter_javascript
from tree_sitter import Language, Node

from cartographer.core.models import CodeLocation, EntityKind, ParsedEntity, Relationship
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
        if node.type in ("function_declaration", "function_expression"):
            return self._extract_function(node, source, file_path)
        if node.type == "generator_function_declaration":
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
        name = self._node_text(name_node, source) if name_node else "anonymous"
        loc = self._location_from_node(node)
        loc["file_path"] = file_path
        relationships: list[Relationship] = []
        self._extract_calls(node, source, relationships)
        return ParsedEntity(
            kind=EntityKind.FUNCTION,
            name=name,
            location=CodeLocation(**loc),
            relationships=relationships,
        )

    def _extract_class(self, node: Node, source: bytes, file_path: str) -> ParsedEntity | None:
        name_node = node.child_by_field_name("name")
        if not name_node:
            return None
        name = self._node_text(name_node, source)
        loc = self._location_from_node(node)
        loc["file_path"] = file_path

        relationships: list[Relationship] = []
        superclass = node.child_by_field_name("superclass")
        if superclass:
            rel_name = self._node_text(superclass, source)
            relationships.append(Relationship(
                target_name=rel_name,
                relationship_type="INHERITS",
            ))

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
            relationships=relationships,
        )

    def _parse_class_member(self, node: Node, source: bytes, file_path: str) -> ParsedEntity | None:
        if node.type == "method_definition":
            name_node = node.child_by_field_name("name")
            if not name_node:
                return None
            name = self._node_text(name_node, source)
            loc = self._location_from_node(node)
            loc["file_path"] = file_path
            relationships: list[Relationship] = []
            self._extract_calls(node, source, relationships)
            return ParsedEntity(
                kind=EntityKind.METHOD,
                name=name,
                location=CodeLocation(**loc),
                relationships=relationships,
            )
        return None

    def _extract_arrow_function(
        self, node: Node, source: bytes, file_path: str
    ) -> ParsedEntity | None:
        loc = self._location_from_node(node)
        loc["file_path"] = file_path
        relationships: list[Relationship] = []
        self._extract_calls(node, source, relationships)
        return ParsedEntity(
            kind=EntityKind.FUNCTION,
            name="<anonymous>",
            location=CodeLocation(**loc),
            relationships=relationships,
        )

    def _extract_variable_declaration(
        self, node: Node, source: bytes, file_path: str
    ) -> ParsedEntity | None:
        for child in node.children:
            if child.type == "variable_declarator":
                entity = self._from_declarator(child, source, file_path)
                if entity:
                    return entity
        return None

    def _extract_lexical_declaration(
        self, node: Node, source: bytes, file_path: str
    ) -> ParsedEntity | None:
        for child in node.children:
            if child.type == "variable_declarator":
                entity = self._from_declarator(child, source, file_path)
                if entity:
                    return entity
        return None

    def _from_declarator(
        self, node: Node, source: bytes, file_path: str
    ) -> ParsedEntity | None:
        name_node = node.child_by_field_name("name")
        if not name_node:
            return None
        name = self._node_text(name_node, source)
        value_node = node.child_by_field_name("value")
        kind: EntityKind = EntityKind.CONSTANT
        if value_node and value_node.type == "arrow_function":
            kind = EntityKind.FUNCTION
        elif value_node and value_node.type == "function":
            kind = EntityKind.FUNCTION
        elif value_node and value_node.type == "class":
            kind = EntityKind.CLASS
        loc = self._location_from_node(name_node)
        loc["file_path"] = file_path
        return ParsedEntity(
            kind=kind,
            name=name,
            location=CodeLocation(**loc),
        )

    def _extract_export(self, node: Node, source: bytes, file_path: str) -> ParsedEntity | None:
        for child in node.children:
            parsed = self._parse_node(child, source, file_path)
            if parsed:
                if parsed.name == "anonymous":
                    parsed.name = "default"
                return parsed
        return None
