from __future__ import annotations

import tree_sitter_go
from tree_sitter import Language, Node

from cartographer.core.models import CodeLocation, EntityKind, ParsedEntity, Relationship
from cartographer.parser.base import BaseParser


class GoParser(BaseParser):
    def _build_language(self) -> Language:
        return Language(tree_sitter_go.language())

    def extract_entities(self, source: bytes, file_path: str) -> list[ParsedEntity]:
        entities: list[ParsedEntity] = []
        root = self._parser.parse(source).root_node

        for child in root.children:
            result = self._parse_node(child, source, file_path)
            if isinstance(result, list):
                entities.extend(result)
            elif result:
                entities.append(result)

        return entities

    def _parse_node(
        self, node: Node, source: bytes, file_path: str
    ) -> list[ParsedEntity] | ParsedEntity | None:
        if node.type == "function_declaration":
            return self._extract_function(node, source, file_path)
        if node.type == "method_declaration":
            return self._extract_method(node, source, file_path)
        if node.type == "type_declaration":
            return self._extract_type_declaration(node, source, file_path)
        if node.type == "import_declaration":
            return self._extract_import(node, source, file_path)
        if node.type in ("const_declaration", "var_declaration"):
            return self._extract_const_or_var(node, source, file_path)
        return None

    def _extract_function(self, node: Node, source: bytes, file_path: str) -> ParsedEntity | None:
        name_node = node.child_by_field_name("name")
        if not name_node:
            return None
        name = self._node_text(name_node, source)
        loc = self._location_from_node(node)
        loc["file_path"] = file_path
        docstring = self._extract_leading_docstring(node, source)

        meta: dict = {"exported": name[0].isupper() if name else False}

        relationships: list[Relationship] = []
        self._extract_calls(node, source, relationships)

        return ParsedEntity(
            kind=EntityKind.FUNCTION,
            name=name,
            location=CodeLocation(**loc),
            docstring=docstring,
            metadata=meta,
            relationships=relationships,
        )

    def _extract_method(self, node: Node, source: bytes, file_path: str) -> ParsedEntity | None:
        name_node = node.child_by_field_name("name")
        if not name_node:
            return None
        name = self._node_text(name_node, source)
        loc = self._location_from_node(node)
        loc["file_path"] = file_path
        docstring = self._extract_leading_docstring(node, source)

        meta: dict = {"exported": name[0].isupper() if name else False}

        relationships: list[Relationship] = []
        self._extract_calls(node, source, relationships)

        return ParsedEntity(
            kind=EntityKind.METHOD,
            name=name,
            location=CodeLocation(**loc),
            docstring=docstring,
            metadata=meta,
            relationships=relationships,
        )

    def _extract_type_declaration(
        self, node: Node, source: bytes, file_path: str
    ) -> ParsedEntity | None:
        for child in node.children:
            if child.type == "type_spec":
                name_node = child.child_by_field_name("name")
                if not name_node:
                    continue
                name = self._node_text(name_node, source)
                type_node = child.child_by_field_name("type")
                kind = (
                    EntityKind.INTERFACE
                    if type_node and type_node.type == "interface_type"
                    else EntityKind.CLASS
                )
                loc = self._location_from_node(node)
                loc["file_path"] = file_path

                children: list[ParsedEntity] = []
                relationships: list[Relationship] = []
                if type_node and type_node.type == "struct_type":
                    body = type_node.child_by_field_name("body")
                    if body:
                        for field in body.children:
                            if field.type == "field_declaration":
                                field_name = field.child_by_field_name("name")
                                if field_name:
                                    floc = self._location_from_node(field)
                                    floc["file_path"] = file_path
                                    children.append(ParsedEntity(
                                        kind=EntityKind.VARIABLE,
                                        name=self._node_text(field_name, source),
                                        location=CodeLocation(**floc),
                                    ))
                elif type_node and type_node.type == "interface_type":
                    pass

                return ParsedEntity(
                    kind=kind,
                    name=name,
                    location=CodeLocation(**loc),
                    children=children,
                    relationships=relationships,
                )
        return None

    def _extract_const_or_var(
        self, node: Node, source: bytes, file_path: str
    ) -> list[ParsedEntity]:
        kind = EntityKind.CONSTANT if node.type == "const_declaration" else EntityKind.VARIABLE
        entities: list[ParsedEntity] = []
        spec_type = "const_spec" if node.type == "const_declaration" else "var_spec"
        for child in node.children:
            if child.type == spec_type:
                name_node = child.child_by_field_name("name")
                if name_node:
                    loc = self._location_from_node(child)
                    loc["file_path"] = file_path
                    entities.append(ParsedEntity(
                        kind=kind,
                        name=self._node_text(name_node, source),
                        location=CodeLocation(**loc),
                    ))
        return entities

    def _extract_import(self, node: Node, source: bytes, file_path: str) -> ParsedEntity | None:
        loc = self._location_from_node(node)
        loc["file_path"] = file_path
        return ParsedEntity(
            kind=EntityKind.MODULE,
            name=f"import:{self._node_text(node, source)}",
            location=CodeLocation(**loc),
        )
