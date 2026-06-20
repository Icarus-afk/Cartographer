from __future__ import annotations

import tree_sitter_lua
from tree_sitter import Language, Node

from cartographer.core.models import CodeLocation, EntityKind, ParsedEntity, Relationship
from cartographer.parser.base import BaseParser


class LuaParser(BaseParser):
    def _build_language(self) -> Language:
        return Language(tree_sitter_lua.language())

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
        if node.type == "local_function_declaration":
            return self._extract_local_function(node, source, file_path)
        if node.type == "local_variable_declaration":
            return self._extract_local_variable(node, source, file_path)
        if node.type == "assignment_statement":
            return self._extract_assignment(node, source, file_path)
        if node.type == "function_call":
            return self._extract_function_call(node, source, file_path)
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

    def _extract_local_function(
        self, node: Node, source: bytes, file_path: str
    ) -> ParsedEntity | None:
        name_node = node.child_by_field_name("name")
        if not name_node:
            return None
        name = "local " + self._node_text(name_node, source)
        loc = self._location_from_node(node)
        loc["file_path"] = file_path

        relationships: list[Relationship] = []
        self._extract_calls(node, source, relationships)

        return ParsedEntity(
            kind=EntityKind.FUNCTION, name=name,
            location=CodeLocation(**loc),
            relationships=relationships,
        )

    def _extract_local_variable(
        self, node: Node, source: bytes, file_path: str
    ) -> ParsedEntity | None:
        for child in node.children:
            if child.type == "variable_declaration":
                name_node = child.child_by_field_name("name")
                if name_node:
                    name = self._node_text(name_node, source)
                    loc = self._location_from_node(child)
                    loc["file_path"] = file_path
                    return ParsedEntity(
                        kind=EntityKind.VARIABLE, name=name,
                        location=CodeLocation(**loc),
                    )
        return None

    def _extract_assignment(
        self, node: Node, source: bytes, file_path: str
    ) -> ParsedEntity | None:
        for child in node.children:
            if child.type == "assignment_statement":
                var_node = child.child_by_field_name("name")
                if var_node:
                    name = self._node_text(var_node, source)
                    loc = self._location_from_node(child)
                    loc["file_path"] = file_path
                    return ParsedEntity(
                        kind=EntityKind.VARIABLE, name=name,
                        location=CodeLocation(**loc),
                    )
        return None

    def _extract_function_call(
        self, node: Node, source: bytes, file_path: str
    ) -> ParsedEntity | None:
        func_node = node.child_by_field_name("name")
        if not func_node:
            return None
        name = self._node_text(func_node, source)

        if name == "require":
            arg = node.child_by_field_name("arguments")
            if arg and arg.children:
                module_name = self._node_text(arg.children[0], source).strip('"').strip("'")
                loc = self._location_from_node(node)
                loc["file_path"] = file_path
                return ParsedEntity(
                    kind=EntityKind.MODULE,
                    name=f"import:{module_name}",
                    location=CodeLocation(**loc),
                )
        return None
