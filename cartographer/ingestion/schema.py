from __future__ import annotations

import logging
import re
from pathlib import Path

from cartographer.core.models import CodeLocation, EntityKind, Language, ParsedEntity, ParsedFile

logger = logging.getLogger(__name__)

_DJANGO_MODEL_BASES = {"Model", "models.Model", "django.db.models.Model"}
_SQLALCHEMY_BASES = {"Base", "declarative_base"}
_PRISMA_MODEL = re.compile(r"^\s*model\s+(\w+)\s*\{")
_PRISMA_FIELD = re.compile(r"^\s+(\w+)\s+(\w+[\w<>\[\], ]*)\s*")
_SQL_CREATE_TABLE = re.compile(
    r"CREATE\s+TABLE\s+(?:\w+\.)?(?:IF\s+NOT\s+EXISTS\s+)?[`\"']?(\w+)[`\"']?\s*\(",
    re.IGNORECASE,
)
_SQL_COLUMN = re.compile(
    r"^\s*[`\"']?(\w+)[`\"']?\s+(\w+(?:\([^)]+\))?)", re.IGNORECASE | re.MULTILINE
)


def extract_schema(
    parsed_files: list[ParsedFile],
    files: list[Path],
    root: Path,
) -> None:
    for pf in parsed_files:
        if pf.language == Language.PYTHON:
            _extract_django_models(pf)
        elif pf.language == Language.JAVA:
            _extract_jpa_entities(pf)
        elif pf.language == Language.TYPESCRIPT:
            _extract_prisma(pf, files, root)

    _extract_sql_tables(parsed_files, files, root)


def _extract_django_models(pf: ParsedFile) -> None:
    for entity in pf.entities:
        _walk_django_models(entity, pf)


def _walk_django_models(entity: ParsedEntity, pf: ParsedFile) -> None:
    if entity.kind == EntityKind.CLASS:
        bases = set(entity.metadata.get("bases", []))
        if bases & _DJANGO_MODEL_BASES:
            table_name = _django_table_name(entity)
            fields = _extract_django_fields(entity)
            children = [
                ParsedEntity(
                    kind=EntityKind.CONSTANT,
                    name=field_name,
                    location=CodeLocation(
                        file_path=pf.path,
                        start_line=entity.location.start_line,
                        start_col=0,
                        end_line=entity.location.start_line,
                        end_col=0,
                    ),
                    metadata={"field_type": field_type},
                )
                for field_name, field_type in fields
            ]
            entity.children.append(
                ParsedEntity(
                    kind=EntityKind.TABLE,
                    name=table_name,
                    location=entity.location,
                    metadata={
                        "model_class": entity.name,
                        "columns": [f["name"] for f in fields],
                    },
                    children=children,
                )
            )
    for child in entity.children:
        _walk_django_models(child, pf)


def _django_table_name(entity: ParsedEntity) -> str:
    meta = entity.metadata.get("decorators", "")
    if "class Meta" in meta:
        m = re.search(r"db_table\s*=\s*['\"]([^'\"]+)['\"]", meta)
        if m:
            return m.group(1)
    return entity.name.lower()


def _extract_django_fields(entity: ParsedEntity) -> list[dict[str, str]]:
    seen: set[str] = set()
    fields: list[dict[str, str]] = []

    django_field_types = frozenset({
        "CharField", "IntegerField", "BooleanField", "DateField",
        "DateTimeField", "ForeignKey", "OneToOneField", "ManyToManyField",
        "TextField", "FloatField", "DecimalField", "EmailField",
        "URLField", "FileField", "ImageField", "SlugField", "AutoField",
    })

    for child in entity.children:
        if child.kind == EntityKind.VARIABLE:
            name = child.name
            if name in seen:
                continue
            meta = child.metadata.get("type_hint", "") or child.docstring or ""
            for field_cls in django_field_types:
                if field_cls in meta or field_cls in (child.metadata.get("decorators", "")):
                    fields.append({"name": name, "type": field_cls})
                    seen.add(name)
                    break
            else:
                fields.append({"name": name, "type": "Field"})
                seen.add(name)
    return fields


def _extract_jpa_entities(pf: ParsedFile) -> None:
    for entity in pf.entities:
        _walk_jpa_entities(entity, pf)


def _walk_jpa_entities(entity: ParsedEntity, pf: ParsedFile) -> None:
    if entity.kind == EntityKind.CLASS:
        decorators = entity.metadata.get("decorators", "")
        if "@Entity" in decorators or "Entity" in decorators:
            table_name = entity.name
            m = re.search(r"@Table\s*\(\s*name\s*=\s*\"(\w+)\"", decorators)
            if m:
                table_name = m.group(1)
            entity.children.append(
                ParsedEntity(
                    kind=EntityKind.TABLE,
                    name=table_name,
                    location=entity.location,
                    metadata={
                        "model_class": entity.name,
                        "columns": [],
                    },
                )
            )
    for child in entity.children:
        _walk_jpa_entities(child, pf)


def _extract_prisma(pf: ParsedFile, files: list[Path], root: Path) -> None:
    for f in files:
        if f.name == "schema.prisma":
            try:
                text = f.read_text(encoding="utf-8", errors="replace")
            except Exception:
                continue
            models = _parse_prisma_schema(text, pf, f, root)
            pf.entities.extend(models)


def _parse_prisma_schema(
    text: str, pf: ParsedFile, f: Path, root: Path
) -> list[ParsedEntity]:
    entities: list[ParsedEntity] = []
    current_model: str | None = None
    fields: list[dict[str, str]] = []
    rel_path = str(f.relative_to(root))

    for line in text.split("\n"):
        m = _PRISMA_MODEL.match(line)
        if m:
            if current_model:
                entities.append(_make_prisma_entity(current_model, fields, rel_path))
                fields = []
            current_model = m.group(1)
            continue

        if current_model:
            if line.strip() == "}":
                entities.append(_make_prisma_entity(current_model, fields, rel_path))
                current_model = None
                fields = []
            else:
                fm = _PRISMA_FIELD.match(line)
                if fm:
                    fields.append({"name": fm.group(1), "type": fm.group(2).strip()})

    if current_model:
        entities.append(_make_prisma_entity(current_model, fields, rel_path))

    return entities


def _make_prisma_entity(
    name: str, fields: list[dict[str, str]], rel_path: str
) -> ParsedEntity:
    loc = CodeLocation(file_path=rel_path, start_line=0, start_col=0,
                       end_line=0, end_col=0)
    return ParsedEntity(
        kind=EntityKind.TABLE,
        name=name,
        location=loc,
        metadata={
            "model_class": name,
            "columns": [f["name"] for f in fields],
            "source": "prisma",
        },
        children=[
            ParsedEntity(
                kind=EntityKind.CONSTANT, name=f["name"],
                location=loc,
                metadata={"field_type": f["type"]},
            )
            for f in fields
        ],
    )


def _split_sql_columns(body: str) -> list[str]:
    parts: list[str] = []
    current: list[str] = []
    depth = 0
    for ch in body:
        if ch == "(":
            depth += 1
            current.append(ch)
        elif ch == ")":
            depth -= 1
            current.append(ch)
        elif ch == "," and depth == 0:
            parts.append("".join(current).strip())
            current = []
        else:
            current.append(ch)
    remaining = "".join(current).strip()
    if remaining:
        parts.append(remaining)
    return parts


_SQL_NON_COLUMN_KEYWORDS = frozenset({
    "PRIMARY", "FOREIGN", "UNIQUE", "INDEX", "KEY", "CONSTRAINT",
    "CHECK", "REFERENCES", "CLUSTERED", "NONCLUSTERED",
})


def _is_column_def(part: str) -> bool:
    first_word = part.split()[0].upper() if part.split() else ""
    return first_word not in _SQL_NON_COLUMN_KEYWORDS


def _extract_sql_tables(
    parsed_files: list[ParsedFile], files: list[Path], root: Path
) -> None:
    for f in files:
        if f.suffix.lower() not in (".sql",):
            continue
        try:
            text = f.read_text(encoding="utf-8", errors="replace")
        except Exception:
            continue
        rel_path = str(f.relative_to(root))
        tables = _parse_sql(text, rel_path)
        if tables:
            pf = ParsedFile(path=rel_path, language=Language.UNKNOWN, entities=tables)
            parsed_files.append(pf)


def _parse_sql(text: str, rel_path: str) -> list[ParsedEntity]:
    entities: list[ParsedEntity] = []
    for m in _SQL_CREATE_TABLE.finditer(text):
        table_name = m.group(1)
        rest = text[m.end():]
        depth = 1
        body_end = len(rest)
        for i, ch in enumerate(rest):
            if ch == "(":
                depth += 1
            elif ch == ")":
                depth -= 1
                if depth == 0:
                    body_end = i
                    break
        body = rest[:body_end] if depth == 0 else rest
        columns: list[dict[str, str]] = []
        for part in _split_sql_columns(body):
            part = part.strip()
            if not part or not _is_column_def(part):
                continue
            cm = _SQL_COLUMN.match(part)
            if cm:
                columns.append({"name": cm.group(1), "type": cm.group(2)})

        col_children = [
            ParsedEntity(
                kind=EntityKind.CONSTANT,
                name=c["name"],
                location=CodeLocation(
                    file_path=rel_path, start_line=0, start_col=0,
                    end_line=0, end_col=0,
                ),
                metadata={"field_type": c["type"]},
            )
            for c in columns
        ]

        entities.append(
            ParsedEntity(
                kind=EntityKind.TABLE,
                name=table_name,
                location=CodeLocation(
                    file_path=rel_path,
                    start_line=0, start_col=0,
                    end_line=0, end_col=0,
                ),
                metadata={
                    "columns": [c["name"] for c in columns],
                    "source": "sql",
                },
                children=col_children,
            )
        )
    return entities
