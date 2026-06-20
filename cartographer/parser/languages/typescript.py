from __future__ import annotations

import tree_sitter_typescript
from tree_sitter import Language, Node

from cartographer.core.models import CodeLocation, EntityKind, ParsedEntity, Relationship
from cartographer.parser.languages.javascript import JavaScriptParser


class TypeScriptParser(JavaScriptParser):
    def _build_language(self) -> Language:
        return Language(tree_sitter_typescript.language_typescript())

    def _parse_node(self, node: Node, source: bytes, file_path: str) -> ParsedEntity | None:
        if node.type == "interface_declaration":
            return self._extract_interface(node, source, file_path)
        if node.type == "type_alias_declaration":
            return self._extract_type_alias(node, source, file_path)
        if node.type == "enum_declaration":
            return self._extract_enum(node, source, file_path)
        return super()._parse_node(node, source, file_path)

    def _extract_interface(
        self, node: Node, source: bytes, file_path: str
    ) -> ParsedEntity | None:
        name_node = node.child_by_field_name("name")
        if not name_node:
            return None
        name = self._node_text(name_node, source)
        loc = self._location_from_node(node)
        loc["file_path"] = file_path
        meta: dict = {}
        tp = node.child_by_field_name("type_parameters")
        if tp:
            meta["type_parameters"] = self._node_text(tp, source)

        relationships: list[Relationship] = []
        for child in node.children:
            if child.type == "extends_type_clause":
                self._add_inherits(child, source, relationships)

        children: list[ParsedEntity] = []
        body = node.child_by_field_name("body")
        if body:
            for child in body.children:
                if child.type == "method_signature":
                    method_name = child.child_by_field_name("name")
                    if method_name:
                        mloc = self._location_from_node(child)
                        mloc["file_path"] = file_path
                        children.append(ParsedEntity(
                            kind=EntityKind.METHOD,
                            name=self._node_text(method_name, source),
                            location=CodeLocation(**mloc),
                        ))
                elif child.type == "property_signature":
                    prop_name = child.child_by_field_name("name")
                    if prop_name:
                        ploc = self._location_from_node(child)
                        ploc["file_path"] = file_path
                        children.append(ParsedEntity(
                            kind=EntityKind.VARIABLE,
                            name=self._node_text(prop_name, source),
                            location=CodeLocation(**ploc),
                        ))

        return ParsedEntity(
            kind=EntityKind.INTERFACE,
            name=name,
            location=CodeLocation(**loc),
            metadata=meta,
            children=children,
            relationships=relationships,
        )

    def _extract_type_alias(
        self, node: Node, source: bytes, file_path: str
    ) -> ParsedEntity | None:
        name_node = node.child_by_field_name("name")
        if not name_node:
            return None
        name = self._node_text(name_node, source)
        loc = self._location_from_node(node)
        loc["file_path"] = file_path
        meta: dict = {}
        tp = node.child_by_field_name("type_parameters")
        if tp:
            meta["type_parameters"] = self._node_text(tp, source)
        return ParsedEntity(
            kind=EntityKind.TYPE_ALIAS,
            name=name,
            location=CodeLocation(**loc),
            metadata=meta,
        )

    def _extract_enum(
        self, node: Node, source: bytes, file_path: str
    ) -> ParsedEntity | None:
        name_node = node.child_by_field_name("name")
        if not name_node:
            return None
        name = self._node_text(name_node, source)
        loc = self._location_from_node(node)
        loc["file_path"] = file_path
        return ParsedEntity(
            kind=EntityKind.ENUM,
            name=name,
            location=CodeLocation(**loc),
        )

    def _extract_class(self, node: Node, source: bytes, file_path: str) -> ParsedEntity | None:
        entity = super()._extract_class(node, source, file_path)
        if entity:
            for child in node.children:
                if child.type == "class_heritage":
                    self._add_inherits(child, source, entity.relationships)
        return entity

    def _add_inherits(self, node: Node, source: bytes, rels: list[Relationship]) -> None:
        if node.type in ("type_identifier", "identifier"):
            rels.append(Relationship(
                target_name=self._node_text(node, source),
                relationship_type="INHERITS",
            ))
        for child in node.children:
            self._add_inherits(child, source, rels)

    def _extract_function(self, node: Node, source: bytes, file_path: str) -> ParsedEntity | None:
        name_node = node.child_by_field_name("name")
        name = self._node_text(name_node, source) if name_node else "anonymous"
        loc = self._location_from_node(node)
        loc["file_path"] = file_path
        meta: dict = {}
        tp = node.child_by_field_name("type_parameters")
        if tp:
            meta["type_parameters"] = self._node_text(tp, source)
        relationships: list[Relationship] = []
        self._extract_calls(node, source, relationships)
        return ParsedEntity(
            kind=EntityKind.FUNCTION,
            name=name,
            location=CodeLocation(**loc),
            metadata=meta,
            relationships=relationships,
        )
