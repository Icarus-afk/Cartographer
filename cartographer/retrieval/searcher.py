from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

from cartographer.storage.connection import DEFAULT_DB_PATH, get_connection

SearchResult = dict[str, Any]


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
    conditions = ["n.name LIKE ?"]
    params = [f"%{query}%"]

    if repo_name:
        conditions.append("r.name = ?")
        params.append(repo_name)

    if node_type:
        conditions.append("n.node_type = ?")
        params.append(node_type)

    sql = f"""
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
    """
    params.extend([query, f"{query}%", limit])

    rows = conn.execute(sql, params).fetchall()
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
