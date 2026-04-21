from __future__ import annotations

import tree_sitter_python
from tree_sitter import Language, Node

from cartographer.core.models import CodeLocation, EntityKind, ParsedEntity
from cartographer.parser.base import BaseParser


class PythonParser(BaseParser):
    def _build_language(self) -> Language:
        return Language(tree_sitter_python.language())

    def extract_entities(self, source: bytes, file_path: str) -> list[ParsedEntity]:
        entities: list[ParsedEntity] = []
        root = self._parser.parse(source).root_node

        for child in root.children:
            entity = self._parse_node(child, source, file_path)
            if entity:
                entities.append(entity)

        return entities

    def _parse_node(self, node: Node, source: bytes, file_path: str) -> ParsedEntity | None:
        node_type = node.type

        if node_type == "function_definition":
            return self._extract_function(node, source, file_path)
        if node_type == "class_definition":
            return self._extract_class(node, source, file_path)
        if node_type == "decorated_definition":
            return self._extract_decorated(node, source, file_path)
        if node_type == "import_statement" or node_type == "import_from_statement":
            return self._extract_import(node, source, file_path)
        if node_type == "module":
            return None

        for child in node.children:
            entity = self._parse_node(child, source, file_path)
            if entity:
                return entity

        return None

    def _extract_function(self, node: Node, source: bytes, file_path: str) -> ParsedEntity | None:
        name_node = node.child_by_field_name("name")
        if not name_node:
            return None
        name = self._node_text(name_node, source)
        body = node.child_by_field_name("body")
        docstring = self._extract_docstring(body, source)

        decorator = ""
        for child in node.children:
            if child.type == "decorator":
                decorator += self._node_text(child, source) + " "

        is_property = "@property" in decorator or "@staticmethod" in decorator

        loc = self._location_from_node(node)
        loc["file_path"] = file_path

        return ParsedEntity(
            kind=EntityKind.FUNCTION if not is_property else EntityKind.METHOD,
            name=name,
            location=CodeLocation(**loc),
            docstring=docstring,
            metadata={
                "decorators": decorator.strip(),
                "parameters": self._extract_params(node, source),
            },
        )

    def _extract_class(self, node: Node, source: bytes, file_path: str) -> ParsedEntity | None:
        name_node = node.child_by_field_name("name")
        if not name_node:
            return None
        name = self._node_text(name_node, source)
        body = node.child_by_field_name("body")
        docstring = self._extract_docstring(body, source)

        bases: list[str] = []
        superclass = node.child_by_field_name("superclass")
        if superclass:
            bases.append(self._node_text(superclass, source))

        loc = self._location_from_node(node)
        loc["file_path"] = file_path

        children: list[ParsedEntity] = []
        if body:
            for child in body.children:
                parsed = self._parse_node(child, source, file_path)
                if parsed:
                    if parsed.kind == EntityKind.FUNCTION:
                        parsed.kind = EntityKind.METHOD
                    children.append(parsed)

        return ParsedEntity(
            kind=EntityKind.CLASS,
            name=name,
            location=CodeLocation(**loc),
            docstring=docstring,
            metadata={"bases": bases},
            children=children,
        )

    def _extract_decorated(self, node: Node, source: bytes, file_path: str) -> ParsedEntity | None:
        for child in node.children:
            if child.type in ("function_definition", "class_definition"):
                return self._parse_node(child, source, file_path)
        return None

    def _extract_import(self, node: Node, source: bytes, file_path: str) -> ParsedEntity | None:
        loc = self._location_from_node(node)
        loc["file_path"] = file_path

        return ParsedEntity(
            kind=EntityKind.MODULE,
            name=f"import:{self._node_text(node, source)}",
            location=CodeLocation(**loc),
        )

    def _extract_docstring(self, body_node: Node | None, source: bytes) -> str | None:
        if not body_node:
            return None
        for child in body_node.children:
            if child.type == "expression_statement":
                expr = child.children[0] if child.children else None
                if expr and expr.type == "string":
                    return self._node_text(expr, source).strip('"').strip("'")
        return None

    def _extract_params(self, node: Node, source: bytes) -> list[str]:
        params = node.child_by_field_name("parameters")
        if not params:
            return []
        return [
            self._node_text(p, source).split(":")[0].strip()
            for p in params.children
            if p.type == "identifier"
        ]
