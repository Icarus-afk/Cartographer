from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

from cartographer.storage.connection import DEFAULT_DB_PATH, get_connection

GraphResult = dict[str, Any]


def get_neighbors(
    node_id: int,
    db_path: Path = DEFAULT_DB_PATH,
    max_depth: int = 1,
) -> list[GraphResult]:
    conn = get_connection(db_path)
    results = _traverse(conn, node_id, max_depth)
    conn.close()
    return results


def _traverse(
    conn: sqlite3.Connection, node_id: int, max_depth: int
) -> list[GraphResult]:
    visited: set[int] = set()
    results: list[GraphResult] = []

    def walk(current_id: int, depth: int, path: list[int]) -> None:
        if current_id in visited or depth > max_depth:
            return
        visited.add(current_id)

        node = conn.execute(
            "SELECT id, node_type, name, file_path FROM nodes WHERE id = ?",
            (current_id,),
        ).fetchone()

        if node:
            results.append({
                "id": node[0],
                "type": node[1],
                "name": node[2],
                "file_path": node[3],
                "depth": depth,
            })

        edges = conn.execute(
            """SELECT source_node_id, target_node_id, edge_type
               FROM edges
               WHERE source_node_id = ? OR target_node_id = ?""",
            (current_id, current_id),
        ).fetchall()

        for src, tgt, edge_type in edges:
            neighbor = tgt if src == current_id else src
            if neighbor not in visited:
                walk(neighbor, depth + 1, path + [current_id])

    walk(node_id, 0, [])
    return results


def impact_analysis(
    target: str,
    db_path: Path = DEFAULT_DB_PATH,
    repo_name: str | None = None,
) -> list[GraphResult]:
    conn = get_connection(db_path)

    node = _resolve_target(conn, target, repo_name)
    if not node:
        conn.close()
        return []

    node_id = node["id"]
    callers: set[int] = set()
    dependents: list[GraphResult] = []

    def find_callers(current_id: int) -> None:
        if current_id in callers:
            return
        callers.add(current_id)

        edges = conn.execute(
            """SELECT DISTINCT source_node_id, edge_type
               FROM edges
               WHERE target_node_id = ?""",
            (current_id,),
        ).fetchall()

        for src_id, edge_type in edges:
            src = conn.execute(
                "SELECT id, node_type, name, file_path FROM nodes WHERE id = ?",
                (src_id,),
            ).fetchone()
            if src:
                dependents.append({
                    "id": src[0],
                    "type": src[1],
                    "name": src[2],
                    "file_path": src[3],
                    "via_edge": edge_type,
                })
                find_callers(src[0])

    find_callers(node_id)
    conn.close()
    return dependents


def _resolve_target(
    conn: sqlite3.Connection,
    target: str,
    repo_name: str | None,
) -> GraphResult | None:
    if target.isdigit():
        row = conn.execute(
            "SELECT id, node_type, name, file_path FROM nodes WHERE id = ?",
            (int(target),),
        ).fetchone()
        if row:
            return {"id": row[0], "type": row[1], "name": row[2], "file_path": row[3]}

    for exact_match in (True, False):
        if exact_match:
            condition = "n.name = ? OR n.file_path = ?"
        else:
            condition = "(n.name LIKE ? OR n.file_path LIKE ?)"
        params: list[str] = [target, target] if exact_match else [f"%{target}%", f"%{target}%"]

        if repo_name:
            sql = f"""
                SELECT n.id, n.node_type, n.name, n.file_path
                FROM nodes n
                JOIN repositories r ON n.repository_id = r.id
                WHERE ({condition}) AND r.name = ?
                ORDER BY n.node_type = 'file' DESC
                LIMIT 1
            """
            params.append(repo_name)
        else:
            sql = f"""
                SELECT n.id, n.node_type, n.name, n.file_path
                FROM nodes n
                WHERE {condition}
                ORDER BY n.node_type = 'file' DESC
                LIMIT 1
            """

        row = conn.execute(sql, params).fetchone()
        if row:
            return {"id": row[0], "type": row[1], "name": row[2], "file_path": row[3]}

    return None


def find_path(
    from_name: str,
    to_name: str,
    db_path: Path = DEFAULT_DB_PATH,
    repo_name: str | None = None,
    max_depth: int = 5,
) -> list[GraphResult]:
    conn = get_connection(db_path)

    from_node = _resolve_target(conn, from_name, repo_name)
    to_node = _resolve_target(conn, to_name, repo_name)

    if not from_node or not to_node:
        conn.close()
        return []

    path_result: list[GraphResult] = []
    found = False

    def bfs(start_id: int, target_id: int) -> list[GraphResult] | None:
        queue: list[tuple[int, list[int]]] = [(start_id, [start_id])]
        visited_ids: set[int] = {start_id}

        while queue and not found:
            current_id, path = queue.pop(0)
            if current_id == target_id:
                return _build_path_result(conn, path)

            if len(path) > max_depth:
                continue

            edges = conn.execute(
                "SELECT source_node_id, target_node_id FROM edges"
                " WHERE source_node_id = ? OR target_node_id = ?",
                (current_id, current_id),
            ).fetchall()

            for src, tgt in edges:
                neighbor = tgt if src == current_id else src
                if neighbor not in visited_ids:
                    visited_ids.add(neighbor)
                    queue.append((neighbor, path + [neighbor]))

        return None

    path_result = bfs(from_node["id"], to_node["id"]) or []
    conn.close()
    return path_result


def _build_path_result(
    conn: sqlite3.Connection, node_ids: list[int]
) -> list[GraphResult]:
    results: list[GraphResult] = []
    for i, nid in enumerate(node_ids):
        row = conn.execute(
            "SELECT id, node_type, name, file_path FROM nodes WHERE id = ?",
            (nid,),
        ).fetchone()
        if row:
            results.append({
                "id": row[0],
                "type": row[1],
                "name": row[2],
                "file_path": row[3],
                "depth": i,
            })
    return results
