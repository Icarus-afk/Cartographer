from __future__ import annotations

import logging
import re
import subprocess
from collections import defaultdict
from pathlib import Path
from typing import Any

from cartographer.storage.connection import get_connection, init_schema

logger = logging.getLogger(__name__)


def index_commits(
    repo_path: str | Path,
    db_path: Path,
    max_count: int = 0,
) -> dict[str, Any]:
    repo_path = Path(repo_path).resolve()
    conn = get_connection(db_path)
    init_schema(conn)

    repo_row = conn.execute(
        "SELECT id FROM repositories WHERE path = ?",
        (str(repo_path),),
    ).fetchone()

    if not repo_row:
        conn.close()
        return {"error": "Repository not indexed. Run 'cartographer index' first."}

    repo_id = repo_row[0]

    result = subprocess.run(
        ["git", "log", "--format=%H||%an||%ae||%ai||%s", "--name-status"],
        cwd=str(repo_path),
        capture_output=True, text=True,
        timeout=60,
    )

    if result.returncode != 0:
        conn.close()
        return {"error": f"git log failed: {result.stderr.strip()}"}

    raw = result.stdout.strip()
    if not raw:
        conn.close()
        return {"commits_indexed": 0}

    blocks = re.split(r"\n(?=[0-9a-f]{40}\|\|)", raw)

    indexed = 0
    authors_seen: dict[str, dict[str, Any]] = {}
    commit_rows: list[tuple[int, int, str, str, str, str]] = []
    commit_file_rows: list[tuple[int, str, str]] = []
    commit_id_map: dict[str, int] = {}

    cursor = conn.execute("SELECT COALESCE(MAX(id), 0) + 1 FROM commits")
    commit_base_id = cursor.fetchone()[0]

    for block in blocks:
        block = block.strip()
        if not block:
            continue

        lines = block.split("\n")
        header = lines[0]
        parts = header.split("||")
        if len(parts) < 5:
            continue

        commit_hash = parts[0]
        author_name = parts[1]
        author_email = parts[2]
        committed_at = parts[3]
        message = parts[4]

        changed_files: list[tuple[str, str]] = []
        for fl in lines[1:]:
            fl = fl.strip()
            if not fl:
                continue
            match = re.match(r"^([AMDR])\s+(.+)$", fl)
            if match:
                change_type = match.group(1)
                fpath = match.group(2)
                changed_files.append((change_type, fpath))

        if max_count > 0 and indexed >= max_count:
            break

        existing = conn.execute(
            "SELECT id FROM commits WHERE hash = ? AND repository_id = ?",
            (commit_hash, repo_id),
        ).fetchone()

        if existing:
            commit_id_map[commit_hash] = existing[0]
            continue

        commit_id = commit_base_id + len(commit_rows)
        commit_id_map[commit_hash] = commit_id
        commit_rows.append((commit_id, repo_id, commit_hash, author_name, message, committed_at))

        for change_type, fpath in changed_files:
            commit_file_rows.append((commit_id, fpath, change_type))

        key = f"{author_name} <{author_email}>"
        if key not in authors_seen:
            authors_seen[key] = {"name": author_name, "email": author_email, "count": 0}
        authors_seen[key]["count"] += 1

        indexed += 1

    if commit_rows:
        conn.executemany(
            "INSERT INTO commits (id, repository_id, hash, author, message, committed_at) "
            "VALUES (?, ?, ?, ?, ?, ?)", commit_rows,
        )
    if commit_file_rows:
        conn.executemany(
            "INSERT INTO commit_files (commit_id, file_path, change_type) "
            "VALUES (?, ?, ?)", commit_file_rows,
        )

    author_rows: list[tuple[int, str, str, int]] = []
    author_updates: list[tuple[int, int]] = []
    for key, info in authors_seen.items():
        existing_author = conn.execute(
            "SELECT id FROM commit_authors WHERE email = ? AND repository_id = ?",
            (info["email"], repo_id),
        ).fetchone()

        if existing_author:
            author_updates.append((info["count"], existing_author[0]))
        else:
            cursor = conn.execute("SELECT COALESCE(MAX(id), 0) + 1 FROM commit_authors")
            next_id = cursor.fetchone()[0]
            author_rows.append((next_id, repo_id, info["name"], info["email"], info["count"]))

    if author_rows:
        conn.executemany(
            "INSERT INTO commit_authors (id, repository_id, name, email, commit_count) "
            "VALUES (?, ?, ?, ?, ?)", author_rows,
        )
    for count, author_id in author_updates:
        conn.execute(
            "UPDATE commit_authors SET commit_count = commit_count + ? WHERE id = ?",
            (count, author_id),
        )

    conn.commit()
    conn.close()
    logger.info("Indexed %d commits, %d authors in %s", indexed, len(authors_seen), repo_path)
    return {"commits_indexed": indexed, "authors_found": len(authors_seen)}


def _get_repo_id(conn, repo_path: str | None, repo_name: str | None) -> int | None:
    if repo_path:
        row = conn.execute(
            "SELECT id FROM repositories WHERE path = ?", (str(repo_path),)
        ).fetchone()
    elif repo_name:
        row = conn.execute(
            "SELECT id FROM repositories WHERE name = ?", (repo_name,)
        ).fetchone()
    else:
        row = conn.execute("SELECT id FROM repositories LIMIT 1").fetchone()
    return row[0] if row else None


def get_file_history(
    db_path: Path,
    file_path: str,
    repo_path: str | None = None,
    repo_name: str | None = None,
    limit: int = 30,
) -> list[dict[str, Any]]:
    conn = get_connection(db_path)
    repo_id = _get_repo_id(conn, repo_path, repo_name)
    if not repo_id:
        conn.close()
        return []

    rows = conn.execute(
        """SELECT c.hash, c.author, c.message, c.committed_at, cf.change_type
           FROM commits c
           JOIN commit_files cf ON c.id = cf.commit_id
           WHERE c.repository_id = ? AND cf.file_path = ?
           ORDER BY c.committed_at DESC
           LIMIT ?""",
        (repo_id, file_path, limit),
    ).fetchall()

    conn.close()
    return [
        {
            "hash": r[0],
            "author": r[1],
            "message": r[2],
            "committed_at": r[3],
            "change_type": r[4],
        }
        for r in rows
    ]


def get_node_history(
    db_path: Path,
    target: str,
    repo_path: str | None = None,
    repo_name: str | None = None,
    limit: int = 30,
) -> list[dict[str, Any]]:
    from cartographer.retrieval.traversal import _resolve_target
    from cartographer.storage.connection import get_connection

    conn = get_connection(db_path)
    node = _resolve_target(conn, target, repo_name)
    conn.close()

    if not node:
        return []

    return get_file_history(
        db_path, node["file_path"], repo_path, repo_name, limit
    )


def co_change_analysis(
    db_path: Path,
    file_path: str,
    repo_path: str | None = None,
    repo_name: str | None = None,
    limit: int = 20,
) -> list[dict[str, Any]]:
    conn = get_connection(db_path)
    repo_id = _get_repo_id(conn, repo_path, repo_name)
    if not repo_id:
        conn.close()
        return []

    commit_ids = conn.execute(
        """SELECT DISTINCT c.id FROM commits c
           JOIN commit_files cf ON c.id = cf.commit_id
           WHERE c.repository_id = ? AND cf.file_path = ?""",
        (repo_id, file_path),
    ).fetchall()

    if not commit_ids:
        conn.close()
        return []

    cids = tuple(r[0] for r in commit_ids)
    placeholders = ",".join("?" for _ in cids)

    rows = conn.execute(
        f"""SELECT cf.file_path, cf.change_type, COUNT(*) as co_count
            FROM commit_files cf
            WHERE cf.commit_id IN ({placeholders})
              AND cf.file_path != ?
            GROUP BY cf.file_path
            ORDER BY co_count DESC
            LIMIT ?""",
        [*cids, file_path, limit],
    ).fetchall()

    conn.close()
    return [
        {"file_path": r[0], "change_type": r[1], "co_occurrences": r[2]}
        for r in rows
    ]


def author_impact(
    db_path: Path,
    author_name: str,
    repo_path: str | None = None,
    repo_name: str | None = None,
    limit: int = 20,
) -> dict[str, Any]:
    conn = get_connection(db_path)
    repo_id = _get_repo_id(conn, repo_path, repo_name)
    if not repo_id:
        conn.close()
        return {"error": "No repository found."}

    rows = conn.execute(
        """SELECT c.hash, c.message, c.committed_at, cf.file_path, cf.change_type
           FROM commits c
           JOIN commit_files cf ON c.id = cf.commit_id
           WHERE c.repository_id = ? AND c.author = ?
           ORDER BY c.committed_at DESC
           LIMIT ?""",
        (repo_id, author_name, limit),
    ).fetchall()

    author_row = conn.execute(
        "SELECT name, email, commit_count FROM commit_authors "
        "WHERE repository_id = ? AND name = ?",
        (repo_id, author_name),
    ).fetchone()

    file_counts: dict[str, int] = defaultdict(int)
    commits_seen: set[str] = set()
    for row in rows:
        commits_seen.add(row[0])
        file_counts[row[3]] += 1

    top_files = sorted(file_counts.items(), key=lambda x: -x[1])[:10]

    conn.close()
    return {
        "author": author_name,
        "email": author_row[1] if author_row else None,
        "total_commits": author_row[2] if author_row else len(commits_seen),
        "commits": [
            {
                "hash": r[0],
                "message": r[1],
                "committed_at": r[2],
                "file": r[3],
                "change_type": r[4],
            }
            for r in rows
        ],
        "top_files": [
            {"file_path": f, "changes": c} for f, c in top_files
        ],
    }


def why_introduced(
    db_path: Path,
    target: str,
    repo_path: str | None = None,
    repo_name: str | None = None,
) -> dict[str, Any] | None:
    from cartographer.retrieval.traversal import _resolve_target
    from cartographer.storage.connection import get_connection

    conn = get_connection(db_path)
    node = _resolve_target(conn, target, repo_name)
    conn.close()

    if not node or not node["file_path"]:
        return None

    history = get_file_history(db_path, node["file_path"], repo_path, repo_name, limit=1)
    if not history:
        return None

    entry = history[0]
    return {
        "target": target,
        "file_path": node["file_path"],
        "introduced_in": entry["hash"],
        "by": entry["author"],
        "message": entry["message"],
        "committed_at": entry["committed_at"],
    }


def list_authors(
    db_path: Path,
    repo_path: str | None = None,
    repo_name: str | None = None,
    limit: int = 20,
) -> list[dict[str, Any]]:
    conn = get_connection(db_path)
    repo_id = _get_repo_id(conn, repo_path, repo_name)
    if not repo_id:
        conn.close()
        return []

    rows = conn.execute(
        "SELECT name, email, commit_count FROM commit_authors "
        "WHERE repository_id = ? ORDER BY commit_count DESC LIMIT ?",
        (repo_id, limit),
    ).fetchall()

    conn.close()
    return [
        {"name": r[0], "email": r[1], "commit_count": r[2]}
        for r in rows
    ]
