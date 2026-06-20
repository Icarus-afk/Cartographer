from __future__ import annotations

import tree_sitter_elixir
from tree_sitter import Language, Node

from cartographer.core.models import CodeLocation, EntityKind, ParsedEntity, Relationship
from cartographer.parser.base import BaseParser

_CALL_KEYWORDS = frozenset({
    "defmodule", "defimpl", "defprotocol",
    "def", "defp", "defmacro", "defmacrop",
})


class ElixirParser(BaseParser):
    def _build_language(self) -> Language:
        return Language(tree_sitter_elixir.language())

    def extract_entities(self, source: bytes, file_path: str) -> list[ParsedEntity]:
        entities: list[ParsedEntity] = []
        root = self._parser.parse(source).root_node
        for child in root.children:
            entity = self._parse_call(child, source, file_path)
            if entity:
                entities.append(entity)
        return entities

    def _call_name(self, node: Node, source: bytes) -> str | None:
        if node.type != "call" or not node.children:
            return None
        first = node.children[0]
        if first.type == "identifier":
            return self._node_text(first, source)
        return None

    def _parse_call(self, node: Node, source: bytes, file_path: str) -> ParsedEntity | None:
        if node.type != "call":
            return None
        name = self._call_name(node, source)
        if name is None or name not in _CALL_KEYWORDS:
            return None

        args_node = node.children[1] if len(node.children) >= 2 else None
        has_do = len(node.children) >= 3 and node.children[2].type == "do_block"
        do_block = node.children[2] if has_do else None

        if name in ("defmodule", "defimpl", "defprotocol"):
            return self._extract_module(name, node, args_node, do_block, source, file_path)
        return self._extract_function(name, node, args_node, do_block, source, file_path)

    def _extract_module(
        self, call_name: str, node: Node, args_node: Node | None,
        do_block: Node | None, source: bytes, file_path: str,
    ) -> ParsedEntity | None:
        if not args_node or not args_node.children:
            return None
        mod_name_node = args_node.children[0]
        name = self._node_text(mod_name_node, source)
        loc = self._location_from_node(node)
        loc["file_path"] = file_path

        children: list[ParsedEntity] = []
        if do_block:
            for stmt in do_block.named_children:
                parsed = self._parse_call(stmt, source, file_path)
                if parsed:
                    children.append(parsed)

        kind = EntityKind.MODULE
        relationships: list[Relationship] = []
        if call_name == "defprotocol":
            kind = EntityKind.INTERFACE
        elif call_name == "defimpl":
            name = f"{name} (impl)"
            kind = EntityKind.CLASS
            if args_node and len(args_node.children) >= 2:
                protocol_node = args_node.children[0]
                rel_name = self._node_text(protocol_node, source)
                relationships.append(Relationship(
                    target_name=rel_name,
                    relationship_type="IMPLEMENTS",
                ))

        return ParsedEntity(
            kind=kind, name=name,
            location=CodeLocation(**loc), children=children,
            relationships=relationships,
        )

    def _extract_function(
        self, call_name: str, node: Node, args_node: Node | None,
        do_block: Node | None, source: bytes, file_path: str,
    ) -> ParsedEntity | None:
        if not args_node or not args_node.children:
            return None
        # Function name is the first child of args_node; may be nested in a `call`
        name_node = args_node.children[0]
        if name_node.type == "call":
            name_node = name_node.children[0] if name_node.children else None
        if not name_node:
            return None
        name = self._node_text(name_node, source)
        is_macro = call_name in ("defmacro", "defmacrop")
        if is_macro:
            name = f"macro {name}"
        loc = self._location_from_node(node)
        loc["file_path"] = file_path

        children: list[ParsedEntity] = []
        if do_block:
            for stmt in do_block.named_children:
                parsed = self._parse_call(stmt, source, file_path)
                if parsed:
                    children.append(parsed)

        relationships: list[Relationship] = []
        self._extract_calls(node, source, relationships)

        return ParsedEntity(
            kind=EntityKind.FUNCTION, name=name,
            location=CodeLocation(**loc), children=children,
            relationships=relationships,
        )
