from __future__ import annotations

import tree_sitter_typescript
from tree_sitter import Language, Node

from cartographer.core.models import CodeLocation, EntityKind, ParsedEntity
from cartographer.parser.languages.typescript import TypeScriptParser


class TSXParser(TypeScriptParser):
    def _build_language(self) -> Language:
        return Language(tree_sitter_typescript.language_tsx())

    def _parse_node(self, node: Node, source: bytes, file_path: str) -> ParsedEntity | None:
        if node.type == "expression_statement":
            return self._extract_jsx_expression(node, source, file_path)
        return super()._parse_node(node, source, file_path)

    def _extract_jsx_expression(
        self, node: Node, source: bytes, file_path: str
    ) -> ParsedEntity | None:
        for child in node.children:
            if child.type in ("jsx_element", "jsx_self_closing_element"):
                tag = child.child_by_field_name("name") or child.child_by_field_name("tag_name")
                name = self._node_text(tag, source) if tag else "<jsx>"
                loc = self._location_from_node(node)
                loc["file_path"] = file_path
                return ParsedEntity(
                    kind=EntityKind.CONSTANT,
                    name=name,
                    location=CodeLocation(**loc),
                )
        return None
