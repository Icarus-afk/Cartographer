from __future__ import annotations

import re
from pathlib import Path

import tree_sitter_python
from tree_sitter import Language

from cartographer.core.models import CodeLocation, EntityKind, ParsedEntity
from cartographer.parser.base import BaseParser

_HEADING = re.compile(r"^(#{1,6})\s+(.+?)\s*$")
_CODE_FENCE = re.compile(r"^```(\w*)")
_LINK = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")
_ADR_RE = re.compile(r"adr\s*[-_ ]?\d+", re.IGNORECASE)
_DIAGRAM_HINT = re.compile(r"```(?:mermaid|dot|plantuml|d2)", re.IGNORECASE)


class MarkdownParser(BaseParser):
    def _build_language(self) -> Language:
        return Language(tree_sitter_python.language())

    def parse_file(self, path: Path) -> tuple[bytes | None, list[str]]:
        try:
            source = path.read_bytes()
            return source, []
        except Exception as e:
            return None, [f"Failed to read {path}: {e}"]

    def extract_entities(self, source: bytes, file_path: str) -> list[ParsedEntity]:
        if not source.strip():
            return []
        text = source.decode("utf-8", errors="replace")
        entities: list[ParsedEntity] = []
        lines = text.splitlines()
        in_fence = False
        fence_lang = ""
        has_diagram = False
        for idx, line in enumerate(lines, start=1):
            m_fence = _CODE_FENCE.match(line)
            if m_fence:
                if not in_fence:
                    in_fence = True
                    fence_lang = m_fence.group(1).lower()
                    if fence_lang in ("mermaid", "dot", "plantuml", "d2"):
                        has_diagram = True
                else:
                    in_fence = False
                continue
            if in_fence:
                continue
            m = _HEADING.match(line)
            if m:
                hashes, title = m.groups()
                level = len(hashes)
                title = title.strip()
                if not title:
                    continue
                loc = CodeLocation(
                    file_path=file_path, start_line=idx, start_col=1,
                    end_line=idx, end_col=len(line) + 1,
                )
                if _ADR_RE.search(title) or _ADR_RE.search(file_path):
                    kind = EntityKind.ADR
                else:
                    kind = EntityKind.MARKDOWN
                entities.append(ParsedEntity(
                    kind=kind, name=title[:120], location=loc,
                    metadata={"heading_level": level},
                ))
                continue
        if not entities:
            first_line = lines[0].strip() if lines else file_path
            loc = CodeLocation(
                file_path=file_path, start_line=1, start_col=1,
                end_line=1, end_col=len(first_line) + 1,
            )
            kind = EntityKind.ADR if (
                _ADR_RE.search(file_path) or _ADR_RE.search(text[:500])
            ) else EntityKind.MARKDOWN
            entities.append(ParsedEntity(
                kind=kind, name=Path(file_path).stem[:120] or "document",
                location=loc,
            ))
        if has_diagram or _DIAGRAM_HINT.search(text):
            loc = CodeLocation(
                file_path=file_path, start_line=1, start_col=1,
                end_line=1, end_col=1,
            )
            entities.append(ParsedEntity(
                kind=EntityKind.DIAGRAM,
                name=f"diagram:{Path(file_path).stem}", location=loc,
            ))
        for m in _LINK.finditer(text):
            link_target = m.group(2).strip()
            if link_target.startswith("http") or link_target.endswith(".md"):
                loc = CodeLocation(
                    file_path=file_path, start_line=1, start_col=1,
                    end_line=1, end_col=1,
                )
                entities.append(ParsedEntity(
                    kind=EntityKind.WIKI, name=link_target[:120], location=loc,
                ))
                break
        return entities
