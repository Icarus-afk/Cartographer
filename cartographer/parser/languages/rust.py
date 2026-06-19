from __future__ import annotations

import tree_sitter_rust
from tree_sitter import Language, Node

from cartographer.core.models import CodeLocation, EntityKind, ParsedEntity, Relationship
from cartographer.parser.base import BaseParser


class RustParser(BaseParser):
    def _build_language(self) -> Language:
        return Language(tree_sitter_rust.language())

    def extract_entities(self, source: bytes, file_path: str) -> list[ParsedEntity]:
        entities: list[ParsedEntity] = []
        root = self._parser.parse(source).root_node

        for child in root.children:
            entity = self._parse_item(child, source, file_path)
            if entity:
                entities.append(entity)

        return entities

    def _parse_item(self, node: Node, source: bytes, file_path: str) -> ParsedEntity | None:
        if node.type == "function_item":
            return self._extract_function(node, source, file_path)
        if node.type == "struct_item":
            return self._extract_struct(node, source, file_path)
        if node.type == "enum_item":
            return self._extract_enum(node, source, file_path)
        if node.type == "trait_item":
            return self._extract_trait(node, source, file_path)
        if node.type == "impl_item":
            return self._extract_impl(node, source, file_path)
        if node.type == "mod_item":
            return self._extract_module(node, source, file_path)
        if node.type == "use_declaration":
            return self._extract_use(node, source, file_path)
        if node.type == "type_item":
            return self._extract_type_alias(node, source, file_path)
        if node.type == "const_item":
            return self._extract_const(node, source, file_path)
        if node.type == "static_item":
            return self._extract_static(node, source, file_path)
        return None

    def _extract_function(self, node: Node, source: bytes, file_path: str) -> ParsedEntity | None:
        name_node = node.child_by_field_name("name")
        if not name_node:
            return None
        name = self._node_text(name_node, source)
        loc = self._location_from_node(node)
        loc["file_path"] = file_path

        pub = any(c.type == "pub" for c in node.children)
        signature = node.child_by_field_name("signature")
        return_type = ""
        if signature:
            ret = signature.child_by_field_name("return_type")
            if ret:
                return_type = self._node_text(ret, source)

        relationships: list[Relationship] = []
        self._extract_calls(node, source, relationships)

        return ParsedEntity(
            kind=EntityKind.FUNCTION,
            name=name,
            location=CodeLocation(**loc),
            metadata={"public": pub, "return_type": return_type},
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

        return ParsedEntity(
            kind=EntityKind.CLASS,
            name=name,
            location=CodeLocation(**loc),
            children=children,
        )

    def _extract_enum(self, node: Node, source: bytes, file_path: str) -> ParsedEntity | None:
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
                if child.type == "enum_variant":
                    vname = child.child_by_field_name("name")
                    if vname:
                        vloc = self._location_from_node(child)
                        vloc["file_path"] = file_path
                        children.append(ParsedEntity(
                            kind=EntityKind.VARIABLE,
                            name=self._node_text(vname, source),
                            location=CodeLocation(**vloc),
                        ))

        return ParsedEntity(
            kind=EntityKind.ENUM,
            name=name,
            location=CodeLocation(**loc),
            children=children,
        )

    def _extract_trait(self, node: Node, source: bytes, file_path: str) -> ParsedEntity | None:
        name_node = node.child_by_field_name("name")
        if not name_node:
            return None
        name = self._node_text(name_node, source)
        loc = self._location_from_node(node)
        loc["file_path"] = file_path

        relationships: list[Relationship] = []
        for child in node.children:
            if child.type == "type_parameter_bounds":
                for bound in child.children:
                    if bound.type == "trait_bound":
                        trait_path = bound.child_by_field_name("trait")
                        if trait_path:
                            rel_name = self._node_text(trait_path, source)
                            relationships.append(Relationship(
                                target_name=rel_name,
                                relationship_type="INHERITS",
                            ))

        return ParsedEntity(
            kind=EntityKind.INTERFACE,
            name=name,
            location=CodeLocation(**loc),
            relationships=relationships,
        )

    def _extract_impl(self, node: Node, source: bytes, file_path: str) -> ParsedEntity | None:
        trait = node.child_by_field_name("trait")
        type_name = node.child_by_field_name("type")
        name_parts = []
        if trait:
            name_parts.append(self._node_text(trait, source))
        if type_name:
            name_parts.append(self._node_text(type_name, source))
        if not name_parts:
            return None
        name = " impl ".join(name_parts)
        loc = self._location_from_node(node)
        loc["file_path"] = file_path

        relationships: list[Relationship] = []
        if trait and type_name:
            trait_str = self._node_text(trait, source)
            relationships.append(Relationship(
                target_name=trait_str,
                relationship_type="IMPLEMENTS",
            ))

        children: list[ParsedEntity] = []
        body = node.child_by_field_name("body")
        if body:
            for child in body.children:
                if child.type == "function_item":
                    fn = self._extract_function(child, source, file_path)
                    if fn:
                        fn.kind = EntityKind.METHOD
                        children.append(fn)

        return ParsedEntity(
            kind=EntityKind.CLASS,
            name=name,
            location=CodeLocation(**loc),
            children=children,
            relationships=relationships,
        )

    def _extract_module(self, node: Node, source: bytes, file_path: str) -> ParsedEntity | None:
        name_node = node.child_by_field_name("name")
        if not name_node:
            return None
        name = self._node_text(name_node, source)
        loc = self._location_from_node(node)
        loc["file_path"] = file_path
        return ParsedEntity(
            kind=EntityKind.MODULE,
            name=name,
            location=CodeLocation(**loc),
        )

    def _extract_use(self, node: Node, source: bytes, file_path: str) -> ParsedEntity | None:
        loc = self._location_from_node(node)
        loc["file_path"] = file_path
        return ParsedEntity(
            kind=EntityKind.MODULE,
            name=f"use:{self._node_text(node, source)}",
            location=CodeLocation(**loc),
        )

    def _extract_type_alias(self, node: Node, source: bytes, file_path: str) -> ParsedEntity | None:
        name_node = node.child_by_field_name("name")
        if not name_node:
            return None
        name = self._node_text(name_node, source)
        loc = self._location_from_node(node)
        loc["file_path"] = file_path
        return ParsedEntity(
            kind=EntityKind.CONSTANT,
            name=name,
            location=CodeLocation(**loc),
        )

    def _extract_const(self, node: Node, source: bytes, file_path: str) -> ParsedEntity | None:
        name_node = node.child_by_field_name("name")
        if not name_node:
            return None
        name = self._node_text(name_node, source)
        loc = self._location_from_node(node)
        loc["file_path"] = file_path
        return ParsedEntity(
            kind=EntityKind.CONSTANT,
            name=name,
            location=CodeLocation(**loc),
        )

    def _extract_static(self, node: Node, source: bytes, file_path: str) -> ParsedEntity | None:
        name_node = node.child_by_field_name("name")
        if not name_node:
            return None
        name = self._node_text(name_node, source)
        loc = self._location_from_node(node)
        loc["file_path"] = file_path
        return ParsedEntity(
            kind=EntityKind.VARIABLE,
            name=name,
            location=CodeLocation(**loc),
        )
