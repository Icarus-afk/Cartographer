from __future__ import annotations

import json
import logging
import sqlite3
from collections import defaultdict
from pathlib import Path
from typing import TypedDict

from cartographer.core.models import EntityKind, ParsedEntity, ParsedFile, RepositoryManifest
from cartographer.storage.connection import get_connection, init_schema

logger = logging.getLogger(__name__)


class GraphStats(TypedDict):
    nodes: int
    edges: int
    files: int
    functions: int
    classes: int
    methods: int
    modules: int
    constants: int
    directories: int
    api_endpoints: int
    interfaces: int
    controllers: int
    services: int
    middleware: int
    repositories: int
    jobs: int
    workers: int
    queues: int


_CLASSIFIER_SUFFIXES: dict[str, EntityKind] = {
    "Controller": EntityKind.CONTROLLER,
    "Service": EntityKind.SERVICE,
    "Middleware": EntityKind.MIDDLEWARE,
    "Repository": EntityKind.REPOSITORY_LAYER,
    "Repo": EntityKind.REPOSITORY_LAYER,
    "DAO": EntityKind.REPOSITORY_LAYER,
    "Job": EntityKind.JOB,
    "Worker": EntityKind.WORKER,
    "Queue": EntityKind.QUEUE,
}


def _reclassify_entity(entity: ParsedEntity) -> None:
    if entity.kind != EntityKind.CLASS:
        return
    name = entity.name
    for suffix, target_kind in _CLASSIFIER_SUFFIXES.items():
        if name.endswith(suffix):
            entity.kind = target_kind
            break


def _reclassify_entities(parsed_files: list[ParsedFile]) -> None:
    for pf in parsed_files:
        for entity in pf.entities:
            _reclassify_tree(entity)


def _reclassify_tree(entity: ParsedEntity) -> None:
    _reclassify_entity(entity)
    for child in entity.children:
        _reclassify_tree(child)


def build_graph(
    db_path: Path,
    repo_path: str,
    parsed_files: list[ParsedFile],
    references: list[dict] | None = None,
    manifest: RepositoryManifest | None = None,
) -> GraphStats:
    _reclassify_entities(parsed_files)

    conn = get_connection(db_path)
    init_schema(conn)

    repo_id = _ensure_repository(conn, repo_path, manifest)

    stats: dict[str, int] = {k: 0 for k in GraphStats.__annotations__}

    conn.execute(
        "DELETE FROM embeddings WHERE node_id IN (SELECT id FROM nodes WHERE repository_id = ?)",
        (repo_id,),
    )
    conn.execute(
        "DELETE FROM architecture WHERE repository_id = ?", (repo_id,)
    )
    conn.execute(
        "DELETE FROM edges WHERE repository_id = ?", (repo_id,)
    )
    conn.execute(
        "DELETE FROM nodes WHERE repository_id = ?", (repo_id,)
    )

    cursor = conn.execute("SELECT COALESCE(MAX(id), 0) + 1 FROM nodes")
    base_id = cursor.fetchone()[0]
    cursor = conn.execute("SELECT COALESCE(MAX(id), 0) + 1 FROM edges")
    edge_base_id = cursor.fetchone()[0]

    dir_cache: dict[str, int] = {}
    file_cache: dict[str, int] = {}
    node_rows: list[tuple[int, int, str, str, str, str | None]] = []
    edge_rows: list[tuple[int, int, int, int, str]] = []
    name_to_entity_ids: dict[str, list[int]] = defaultdict(list)

    def _batch_node(kind: EntityKind, name: str, file_path: str, metadata: dict) -> int:
        nonlocal node_idx
        node_idx += 1
        actual_id = base_id + node_idx - 1
        node_rows.append((
            actual_id, repo_id, kind.value, name, file_path,
            json.dumps(metadata) if metadata else None,
        ))
        name_to_entity_ids[name].append(actual_id)
        return actual_id

    def _batch_edge(src: int, tgt: int, etype: str) -> None:
        nonlocal edge_idx
        edge_idx += 1
        actual_id = edge_base_id + edge_idx - 1
        edge_rows.append((actual_id, repo_id, src, tgt, etype))

    node_idx = 0
    edge_idx = 0

    for pf in parsed_files:
        parts = pf.path.split("/")
        parent_id = None

        for i in range(len(parts) - 1):
            dir_path = "/".join(parts[: i + 1])
            if dir_path not in dir_cache:
                dir_id = _batch_node(EntityKind.DIRECTORY, parts[i], dir_path, {})
                stats["nodes"] += 1
                stats["directories"] = stats.get("directories", 0) + 1
                dir_cache[dir_path] = dir_id

                if parent_id:
                    _batch_edge(parent_id, dir_id, "CONTAINS")
                    stats["edges"] += 1
            parent_id = dir_cache[dir_path]

        file_id = _batch_node(EntityKind.FILE, pf.path, pf.path,
                              {"language": pf.language.value})
        stats["files"] += 1
        stats["nodes"] += 1
        file_cache[pf.path] = file_id

        if parent_id:
            _batch_edge(parent_id, file_id, "CONTAINS")
            stats["edges"] += 1

        for entity in pf.entities:
            _process_entity(entity, stats, file_id, pf.path, _batch_node, _batch_edge)

    if references:
        for ref in references:
            source_id = file_cache.get(ref["source"])
            target_id = file_cache.get(ref["target"])
            if source_id and target_id and source_id != target_id:
                _batch_edge(source_id, target_id, "IMPORTS")
                stats["edges"] += 1

    _resolve_relationships(parsed_files, name_to_entity_ids, stats, _batch_edge)

    conn.executemany(
        "INSERT INTO nodes (id, repository_id, node_type, name, file_path, metadata_json) "
        "VALUES (?, ?, ?, ?, ?, ?)", node_rows,
    )
    conn.executemany(
        "INSERT INTO edges (id, repository_id, source_node_id, target_node_id, edge_type) "
        "VALUES (?, ?, ?, ?, ?)", edge_rows,
    )
    conn.commit()
    conn.close()
    return stats  # type: ignore[return-value]


def _process_entity(
    entity: ParsedEntity,
    stats: GraphStats,
    file_id: int,
    file_path: str,
    batch_node,
    batch_edge,
    parent_id: int | None = None,
) -> int:
    kind = entity.kind

    if kind in (EntityKind.MODULE,):
        return file_id

    entity_id = batch_node(kind, entity.name, file_path, entity.metadata)
    stats["nodes"] += 1
    stats[kind.value] = stats.get(kind.value, 0) + 1

    edge_type = _edge_type_for(kind)
    source_id = parent_id if parent_id else file_id
    batch_edge(source_id, entity_id, edge_type)
    stats["edges"] += 1

    for child in entity.children:
        _process_entity(child, stats, file_id, file_path, batch_node, batch_edge, entity_id)

    return entity_id


def _ensure_repository(
    conn: sqlite3.Connection, repo_path: str,
    manifest: RepositoryManifest | None = None,
) -> int:
    name = Path(repo_path).name
    manifest_json = _manifest_to_json(manifest) if manifest else None
    cursor = conn.execute(
        "INSERT INTO repositories (path, name, manifest_json) VALUES (?, ?, ?) "
        "ON CONFLICT(path) DO UPDATE SET manifest_json = COALESCE(?, manifest_json)",
        (repo_path, name, manifest_json, manifest_json),
    )
    row = conn.execute("SELECT id FROM repositories WHERE path = ?", (repo_path,)).fetchone()
    return row[0]


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


def _resolve_relationships(
    parsed_files: list[ParsedFile],
    name_to_entity_ids: dict[str, list[int]],
    stats: GraphStats,
    batch_edge,
) -> None:
    for pf in parsed_files:
        _resolve_entity_relationships(pf.entities, name_to_entity_ids, stats, batch_edge)


def _resolve_entity_relationships(
    entities: list[ParsedEntity],
    name_to_entity_ids: dict[str, list[int]],
    stats: GraphStats,
    batch_edge,
) -> None:
    for entity in entities:
        for rel in entity.relationships:
            targets = name_to_entity_ids.get(rel.target_name, [])
            if len(targets) == 1:
                tgt_id = targets[0]
                src_id = name_to_entity_ids.get(entity.name, [])
                if src_id and src_id[0] != tgt_id:
                    batch_edge(src_id[0], tgt_id, rel.relationship_type)
                    stats["edges"] += 1
        for child in entity.children:
            _resolve_entity_relationships(
                [child], name_to_entity_ids, stats, batch_edge,
            )


def _edge_type_for(kind: EntityKind) -> str:
    parent_types = {
        EntityKind.CLASS: "DEFINES",
        EntityKind.FUNCTION: "DEFINES",
        EntityKind.METHOD: "DEFINES",
        EntityKind.CONSTANT: "DECLARES",
        EntityKind.VARIABLE: "DECLARES",
        EntityKind.INTERFACE: "DEFINES",
        EntityKind.ENUM: "DEFINES",
        EntityKind.API_ENDPOINT: "DEFINES",
    }
    return parent_types.get(kind, "CONTAINS")
