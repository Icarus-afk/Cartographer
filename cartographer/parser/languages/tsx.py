from __future__ import annotations

import tree_sitter_typescript
from tree_sitter import Language

from cartographer.parser.languages.javascript import JavaScriptParser


class TSXParser(JavaScriptParser):
    def _build_language(self) -> Language:
        return Language(tree_sitter_typescript.language_tsx())
