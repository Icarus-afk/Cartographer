from __future__ import annotations

import tree_sitter_cpp
from tree_sitter import Language, Node

from cartographer.core.models import CodeLocation, EntityKind, ParsedEntity
from cartographer.parser.languages.c import CParser


class CppParser(CParser):
    def _build_language(self) -> Language:
        return Language(tree_sitter_cpp.language())

    def _parse_top(self, node: Node, source: bytes, file_path: str) -> ParsedEntity | None:
        if node.type == "class_specifier":
            return self._extract_class(node, source, file_path)
        if node.type == "namespace_definition":
            return self._extract_namespace(node, source, file_path)
        if node.type == "template_declaration":
            return self._extract_template(node, source, file_path)
        if node.type == "concept_definition":
            return self._extract_concept(node, source, file_path)
        return super()._parse_top(node, source, file_path)

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
                if child.type == "function_definition":
                    parsed = self._extract_function(child, source, file_path)
                    if parsed:
                        parsed.kind = EntityKind.METHOD
                        children.append(parsed)
                elif child.type == "field_declaration":
                    for f in child.children:
                        if f.type == "field_identifier":
                            floc = self._location_from_node(f)
                            floc["file_path"] = file_path
                            children.append(ParsedEntity(
                                kind=EntityKind.VARIABLE,
                                name=self._node_text(f, source),
                                location=CodeLocation(**floc),
                            ))

        return ParsedEntity(
            kind=EntityKind.CLASS, name=name,
            location=CodeLocation(**loc), children=children,
        )

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

    def _extract_template(self, node: Node, source: bytes, file_path: str) -> ParsedEntity | None:
        for child in node.children:
            if child.type in ("class_specifier", "function_definition"):
                return self._parse_top(child, source, file_path)
        return None

    def _extract_concept(self, node: Node, source: bytes, file_path: str) -> ParsedEntity | None:
        name_node = node.child_by_field_name("name")
        if not name_node:
            return None
        name = self._node_text(name_node, source)
        loc = self._location_from_node(node)
        loc["file_path"] = file_path
        return ParsedEntity(
            kind=EntityKind.INTERFACE, name=f"concept {name}",
            location=CodeLocation(**loc),
        )
