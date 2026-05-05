from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from cartographer.core.models import EntityKind, ParsedEntity, ParsedFile, RepositoryManifest
from cartographer.storage.connection import get_connection, init_schema

GraphStats = dict


def build_graph(
    db_path: Path,
    repo_path: str,
    parsed_files: list[ParsedFile],
    references: list[dict] | None = None,
    manifest: RepositoryManifest | None = None,
) -> GraphStats:
    conn = get_connection(db_path)
    init_schema(conn)

    repo_id = _ensure_repository(conn, repo_path, manifest)

    stats: GraphStats = {
        "nodes": 0,
        "edges": 0,
        "files": 0,
        "functions": 0,
        "classes": 0,
        "methods": 0,
        "modules": 0,
        "constants": 0,
        "directories": 0,
    }

    dir_cache: dict[str, int] = {}
    file_cache: dict[str, int] = {}

    for pf in parsed_files:
        parts = pf.path.split("/")
        parent_id = None

        for i in range(len(parts) - 1):
            dir_path = "/".join(parts[: i + 1])
            if dir_path not in dir_cache:
                dir_id = _insert_node(
                    conn, repo_id, EntityKind.DIRECTORY,
                    parts[i], dir_path, {},
                )
                stats["nodes"] += 1
                stats["directories"] = stats.get("directories", 0) + 1
                dir_cache[dir_path] = dir_id

                if parent_id:
                    _insert_edge(conn, repo_id, parent_id, dir_id, "CONTAINS")
                    stats["edges"] += 1
            parent_id = dir_cache[dir_path]

        file_id = _insert_node(
            conn, repo_id, EntityKind.FILE, pf.path,
            pf.path, {"language": pf.language.value},
        )
        stats["files"] += 1
        stats["nodes"] += 1
        file_cache[pf.path] = file_id

        if parent_id:
            _insert_edge(conn, repo_id, parent_id, file_id, "CONTAINS")
            stats["edges"] += 1

        for entity in pf.entities:
            _process_entity(conn, repo_id, file_id, pf.path, entity, stats)

    if references:
        for ref in references:
            source_id = file_cache.get(ref["source"])
            target_id = file_cache.get(ref["target"])
            if source_id and target_id and source_id != target_id:
                _insert_edge(conn, repo_id, source_id, target_id, "IMPORTS")
                stats["edges"] += 1

    conn.commit()
    conn.close()
    return stats


def _process_entity(
    conn: sqlite3.Connection,
    repo_id: int,
    file_id: int,
    file_path: str,
    entity: ParsedEntity,
    stats: GraphStats,
    parent_id: int | None = None,
) -> int:
    kind = entity.kind

    if kind in (EntityKind.MODULE,):
        return file_id

    entity_id = _insert_node(conn, repo_id, kind, entity.name, file_path, entity.metadata)
    stats["nodes"] += 1

    kind_key = kind.value
    stats[kind_key] = stats.get(kind_key, 0) + 1

    edge_type = _edge_type_for(kind)
    source_id = parent_id if parent_id else file_id
    _insert_edge(conn, repo_id, source_id, entity_id, edge_type)
    stats["edges"] += 1

    for child in entity.children:
        _process_entity(conn, repo_id, file_id, file_path, child, stats, entity_id)

    return entity_id


def _ensure_repository(
    conn: sqlite3.Connection, repo_path: str,
    manifest: RepositoryManifest | None = None,
) -> int:
    name = Path(repo_path).name
    existing = conn.execute(
        "SELECT id, manifest_json FROM repositories WHERE path = ?", (repo_path,)
    ).fetchone()
    if existing:
        repo_id = existing[0]
        if manifest:
            manifest_json = _manifest_to_json(manifest)
            conn.execute(
                "UPDATE repositories SET manifest_json = ? WHERE id = ?",
                (manifest_json, repo_id),
            )
        return repo_id
    manifest_json = _manifest_to_json(manifest) if manifest else None
    cursor = conn.execute(
        "INSERT INTO repositories (path, name, manifest_json) VALUES (?, ?, ?)",
        (repo_path, name, manifest_json),
    )
    return cursor.lastrowid


def _manifest_to_json(manifest: RepositoryManifest) -> str:
    return json.dumps({
        "frameworks": [
            {"name": fw.name, "confidence": fw.confidence}
            for fw in manifest.frameworks
        ],
        "languages": {
            lang.value if hasattr(lang, "value") else str(lang): count
            for lang, count in manifest.languages.items()
        },
        "package_managers": manifest.package_managers,
        "build_systems": manifest.build_systems,
        "is_monorepo": manifest.is_monorepo,
        "monorepo_tool": manifest.monorepo_tool,
        "total_files": manifest.total_files,
        "total_dirs": manifest.total_dirs,
        "total_references": manifest.total_references,
    })


def _insert_node(
    conn: sqlite3.Connection,
    repo_id: int,
    kind: EntityKind,
    name: str,
    file_path: str,
    metadata: dict,
) -> int:
    cursor = conn.execute(
        "INSERT INTO nodes (repository_id, node_type, name, file_path, metadata_json) "
        "VALUES (?, ?, ?, ?, ?)",
        (repo_id, kind.value, name, file_path, json.dumps(metadata) if metadata else None),
    )
    return cursor.lastrowid


def _insert_edge(
    conn: sqlite3.Connection,
    repo_id: int,
    source_id: int,
    target_id: int,
    edge_type: str,
) -> int:
    cursor = conn.execute(
        "INSERT INTO edges (repository_id, source_node_id, target_node_id, edge_type) "
        "VALUES (?, ?, ?, ?)",
        (repo_id, source_id, target_id, edge_type),
    )
    return cursor.lastrowid


def _edge_type_for(kind: EntityKind) -> str:
    parent_types = {
        EntityKind.CLASS: "DEFINES",
        EntityKind.FUNCTION: "DEFINES",
        EntityKind.METHOD: "DEFINES",
        EntityKind.CONSTANT: "DECLARES",
        EntityKind.VARIABLE: "DECLARES",
        EntityKind.INTERFACE: "DEFINES",
        EntityKind.ENUM: "DEFINES",
    }
    return parent_types.get(kind, "CONTAINS")
