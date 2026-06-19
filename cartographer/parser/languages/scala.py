from __future__ import annotations

import tree_sitter_scala
from tree_sitter import Language, Node

from cartographer.core.models import CodeLocation, EntityKind, ParsedEntity, Relationship
from cartographer.parser.base import BaseParser


class ScalaParser(BaseParser):
    def _build_language(self) -> Language:
        return Language(tree_sitter_scala.language())

    def extract_entities(self, source: bytes, file_path: str) -> list[ParsedEntity]:
        entities: list[ParsedEntity] = []
        root = self._parser.parse(source).root_node
        for child in root.children:
            entity = self._parse_top(child, source, file_path)
            if entity:
                entities.append(entity)
        return entities

    def _parse_top(self, node: Node, source: bytes, file_path: str) -> ParsedEntity | None:
        if node.type == "class_definition":
            return self._extract_named(node, source, file_path, EntityKind.CLASS)
        if node.type == "object_definition":
            return self._extract_named(node, source, file_path, EntityKind.CLASS)
        if node.type == "trait_definition":
            return self._extract_named(node, source, file_path, EntityKind.INTERFACE)
        if node.type == "enum_definition":
            return self._extract_named(node, source, file_path, EntityKind.ENUM)
        if node.type == "function_definition":
            return self._extract_named(node, source, file_path, EntityKind.FUNCTION)
        if node.type == "val_definition":
            return self._extract_val(node, source, file_path)
        if node.type == "var_definition":
            return self._extract_val(node, source, file_path)
        if node.type == "package_clause":
            return None
        if node.type == "import_statement":
            return None
        return None

    def _extract_named(
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

        if kind in (EntityKind.CLASS, EntityKind.INTERFACE):
            template = None
            for child in node.children:
                if child.type == "template":
                    template = child
                    break
            if template:
                for child in template.children:
                    if child.type == "template_parents":
                        for parent in child.children:
                            if parent.type in ("identifier", "type_identifier", "simple_identifier"):
                                rel_name = self._node_text(parent, source)
                                rel_type = "IMPLEMENTS" if kind == EntityKind.CLASS else "INHERITS"
                                relationships.append(Relationship(
                                    target_name=rel_name,
                                    relationship_type=rel_type,
                                ))

        children: list[ParsedEntity] = []
        if kind in (EntityKind.CLASS, EntityKind.INTERFACE):
            body = node.child_by_field_name("body")
            if body:
                for child in body.children:
                    if child.type == "function_definition":
                        parsed = self._extract_named(child, source, file_path, EntityKind.METHOD)
                        if parsed:
                            children.append(parsed)
                    elif child.type == "val_definition":
                        parsed = self._extract_val(child, source, file_path)
                        if parsed:
                            children.append(parsed)

        return ParsedEntity(
            kind=kind, name=name,
            location=CodeLocation(**loc), children=children,
            relationships=relationships,
        )

    def _extract_val(self, node: Node, source: bytes, file_path: str) -> ParsedEntity | None:
        patterns = node.child_by_field_name("patterns")
        if not patterns:
            return None
        name_node = None
        for c in patterns.children:
            if c.type in ("identifier", "simple_identifier"):
                name_node = c
                break
        if not name_node:
            return None
        name = self._node_text(name_node, source)
        loc = self._location_from_node(node)
        loc["file_path"] = file_path
        return ParsedEntity(
            kind=EntityKind.VARIABLE, name=name,
            location=CodeLocation(**loc),
        )
