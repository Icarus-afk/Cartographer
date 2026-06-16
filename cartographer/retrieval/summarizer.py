from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

from cartographer.storage.connection import DEFAULT_DB_PATH, get_connection

Summary = dict[str, Any]


def generate_summary(
    db_path: Path = DEFAULT_DB_PATH,
    repo_name: str | None = None,
) -> Summary | None:
    conn = get_connection(db_path)

    if repo_name:
        repo = conn.execute(
            "SELECT id, name, path FROM repositories WHERE name = ?",
            (repo_name,),
        ).fetchone()
    else:
        cwd = os.getcwd()
        repo = conn.execute(
            "SELECT id, name, path FROM repositories WHERE path = ?",
            (cwd,),
        ).fetchone()
        if not repo:
            repo = conn.execute(
                "SELECT id, name, path FROM repositories "
                "ORDER BY (SELECT COUNT(*) FROM nodes WHERE repository_id = repositories.id) DESC "
                "LIMIT 1"
            ).fetchone()

    if not repo:
        conn.close()
        return None

    repo_id, name, path = repo

    type_counts = dict(
        conn.execute(
            "SELECT node_type, COUNT(*) FROM nodes WHERE repository_id = ?"
            " GROUP BY node_type ORDER BY COUNT(*) DESC",
            (repo_id,),
        ).fetchall()
    )

    edge_counts = dict(
        conn.execute(
            "SELECT edge_type, COUNT(*) FROM edges WHERE repository_id = ?"
            " GROUP BY edge_type ORDER BY COUNT(*) DESC",
            (repo_id,),
        ).fetchall()
    )

    total_nodes = sum(type_counts.values())
    total_edges = sum(edge_counts.values())

    top_files = [
        {"name": r[0], "entities": r[1]}
        for r in conn.execute(
            """SELECT file_path, COUNT(*) as cnt
               FROM nodes
               WHERE repository_id = ? AND node_type != 'file'
                 AND node_type != 'directory'
               GROUP BY file_path
               ORDER BY cnt DESC
               LIMIT 10""",
            (repo_id,),
        ).fetchall()
    ]

    top_classes = [
        {"name": r[0], "methods": r[1]}
        for r in conn.execute(
            """SELECT n.name, COUNT(*) as method_count
               FROM nodes n
               JOIN edges e ON e.source_node_id = n.id
               WHERE n.repository_id = ?
                 AND n.node_type = 'class'
                 AND e.edge_type = 'DEFINES'
                 AND e.target_node_id IN (
                     SELECT id FROM nodes
                     WHERE node_type = 'method' OR node_type = 'function'
                 )
               GROUP BY n.id
               ORDER BY method_count DESC
               LIMIT 5""",
            (repo_id,),
        ).fetchall()
    ]

    conn.close()

    return {
        "name": name,
        "path": path,
        "total_nodes": total_nodes,
        "total_edges": total_edges,
        "node_breakdown": type_counts,
        "edge_breakdown": edge_counts,
        "top_files": top_files,
        "top_classes": top_classes,
    }
