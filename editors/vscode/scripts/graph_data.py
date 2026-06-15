"""Query Cartographer SQLite DB and output graph data as JSON for the VS Code extension."""
import json
import sqlite3
import sys


def main() -> None:
    if len(sys.argv) < 4:
        print(json.dumps({"error": "usage: graph_data.py <db> <repo> <limit>"}))
        sys.exit(1)

    db_path, repo_name, limit_str = sys.argv[1], sys.argv[2], sys.argv[3]
    limit = int(limit_str)
    conn = sqlite3.connect(db_path)

    repo = conn.execute(
        "SELECT id FROM repositories WHERE name = ?", (repo_name,)
    ).fetchone()
    if not repo:
        conn.close()
        print(json.dumps({"error": f"Repository '{repo_name}' not found"}))
        return

    repo_id = repo[0]

    type_counts = conn.execute(
        "SELECT node_type, COUNT(*) as cnt FROM nodes WHERE repository_id = ? GROUP BY node_type ORDER BY cnt DESC",
        (repo_id,),
    ).fetchall()

    nodes = conn.execute(
        """SELECT n.id, n.name, n.node_type, n.file_path,
                  (SELECT COUNT(*) FROM edges WHERE repository_id = ? AND (source_node_id = n.id OR target_node_id = n.id)) as degree
           FROM nodes n
           WHERE n.repository_id = ?
           ORDER BY degree DESC, RANDOM()
           LIMIT ?""",
        (repo_id, repo_id, limit),
    ).fetchall()

    node_ids = [n[0] for n in nodes]
    edges: list[tuple[int, int, str]] = []
    if node_ids:
        placeholders = ",".join("?" for _ in node_ids)
        edges = conn.execute(
            f"""SELECT source_node_id, target_node_id, edge_type FROM edges
                WHERE repository_id = ? AND source_node_id IN ({placeholders})
                AND target_node_id IN ({placeholders})""",
            (repo_id, *node_ids, *node_ids),
        ).fetchall()

    conn.close()

    count_map = {row[0]: row[1] for row in type_counts}
    node_types = {t: c for t, c in count_map.items()}
    total_nodes = sum(node_types.values())
    total_edges = conn.execute(
        "SELECT COUNT(*) FROM edges WHERE repository_id = ?", (repo_id,)
    ).fetchone()[0]

    print(json.dumps({
        "total_nodes": total_nodes,
        "total_edges": total_edges,
        "node_types": node_types,
        "nodes": [
            {"id": n[0], "name": n[1], "type": n[2], "file_path": n[3]}
            for n in nodes
        ],
        "edges": [
            {"source": e[0], "target": e[1], "type": e[2]}
            for e in edges
        ],
    }))


if __name__ == "__main__":
    main()
