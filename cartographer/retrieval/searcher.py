from __future__ import annotations

import logging
import math
import sqlite3
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

from cartographer.storage.connection import DEFAULT_DB_PATH, get_connection

SearchResult = dict[str, Any]

_TYPE_PRIORITY: dict[str, float] = {
    "api_endpoint": 1.2,
    "controller": 1.1,
    "service": 1.0,
    "class": 1.0,
    "interface": 1.0,
    "function": 0.9,
    "method": 0.9,
    "middleware": 1.0,
    "repository_layer": 1.0,
    "file": 0.7,
    "directory": 0.6,
    "job": 0.9,
    "worker": 0.9,
    "queue": 0.9,
}


def _name_score(name: str, query: str) -> float:
    lower_name = name.lower()
    lower_query = query.lower()
    if lower_name == lower_query:
        return 1.0
    if lower_name.startswith(lower_query):
        return 0.8
    if lower_query in lower_name:
        return 0.5
    query_words = lower_query.split()
    if len(query_words) > 1:
        matches = sum(1 for w in query_words if w in lower_name)
        if matches > 0:
            return 0.3 + 0.1 * matches
    return 0.1


def _type_score(node_type: str) -> float:
    return _TYPE_PRIORITY.get(node_type, 0.5)


def _compute_score(
    row: tuple,
    query: str,
    ref_count: int,
    max_refs: int,
) -> float:
    name = row[2]
    node_type = row[1]
    file_path = row[3] or ""

    ns = _name_score(name, query)
    ts = _type_score(node_type)

    ref_norm = math.log2(ref_count + 1) / max(math.log2(max_refs + 1), 1) if max_refs > 0 else 0
    depth = file_path.count("/") + 1
    depth_score = 1.0 / math.sqrt(depth)

    return ns * 0.5 + ts * 0.2 + ref_norm * 0.2 + depth_score * 0.1


def _fetch_ref_counts(conn: sqlite3.Connection, repo_name: str | None) -> dict[int, int]:
    cond = ""
    params: list[Any] = []
    if repo_name:
        cond = " JOIN repositories r ON n.repository_id = r.id WHERE r.name = ?"
        params.append(repo_name)
    rows = conn.execute(
        f"SELECT n.id, COUNT(DISTINCT e.id) FROM nodes n LEFT JOIN edges e "
        f"ON n.id = e.target_node_id{cond} GROUP BY n.id",
        params,
    ).fetchall()
    return {r[0]: r[1] for r in rows}


def search_nodes(
    query: str,
    db_path: Path = DEFAULT_DB_PATH,
    repo_name: str | None = None,
    node_type: str | None = None,
    limit: int = 20,
) -> list[SearchResult]:
    conn = get_connection(db_path)
    results = _search(conn, query, repo_name, node_type, limit)
    conn.close()
    return results


def _search(
    conn: sqlite3.Connection,
    query: str,
    repo_name: str | None,
    node_type: str | None,
    limit: int,
) -> list[SearchResult]:
    ref_counts = _fetch_ref_counts(conn, repo_name)
    max_refs = max(ref_counts.values()) if ref_counts else 1

    conditions = ["n.name LIKE ?"]
    params = [f"%{query}%"]

    if repo_name:
        conditions.append("r.name = ?")
        params.append(repo_name)

    if node_type:
        conditions.append("n.node_type = ?")
        params.append(node_type)

    rows = conn.execute(
        f"""
        SELECT n.id, n.node_type, n.name, n.file_path,
               r.name as repo_name, r.path as repo_path
        FROM nodes n
        JOIN repositories r ON n.repository_id = r.id
        WHERE {' AND '.join(conditions)}
        ORDER BY
            CASE
                WHEN n.name = ? THEN 0
                WHEN n.name LIKE ? THEN 1
                ELSE 2
            END,
            n.name
        LIMIT ?
        """,
        [*params, query, f"{query}%", limit],
    ).fetchall()

    scored = []
    for row in rows:
        ref_count = ref_counts.get(row[0], 0)
        score = _compute_score(row, query, ref_count, max_refs)
        scored.append((score, row))

    scored.sort(key=lambda x: (-x[0], x[1][2]))

    return [
        {
            "id": r[0],
            "type": r[1],
            "name": r[2],
            "file_path": r[3],
            "repo_name": r[4],
            "repo_path": r[5],
            "score": round(s, 4),
        }
        for s, r in scored
    ]


def search_by_type(
    node_type: str,
    db_path: Path = DEFAULT_DB_PATH,
    repo_name: str | None = None,
    limit: int = 50,
) -> list[SearchResult]:
    conn = get_connection(db_path)
    conditions = ["n.node_type = ?"]
    params: list[Any] = [node_type]

    if repo_name:
        conditions.append("r.name = ?")
        params.append(repo_name)

    sql = f"""
        SELECT n.id, n.node_type, n.name, n.file_path,
               r.name as repo_name, r.path as repo_path
        FROM nodes n
        JOIN repositories r ON n.repository_id = r.id
        WHERE {' AND '.join(conditions)}
        ORDER BY n.name
        LIMIT ?
    """
    params.append(limit)

    rows = conn.execute(sql, params).fetchall()
    conn.close()
    return [
        {
            "id": r[0],
            "type": r[1],
            "name": r[2],
            "file_path": r[3],
            "repo_name": r[4],
            "repo_path": r[5],
        }
        for r in rows
    ]
