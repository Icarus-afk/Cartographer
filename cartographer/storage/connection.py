import sqlite3
from pathlib import Path

DEFAULT_DB_PATH = Path.home() / ".cartographer" / "index.db"


def get_connection(db_path: Path = DEFAULT_DB_PATH) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA cache_size=-8000")
    conn.execute("PRAGMA temp_store=MEMORY")
    conn.execute("PRAGMA busy_timeout=5000")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_schema(conn: sqlite3.Connection) -> None:
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS repositories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            path TEXT NOT NULL UNIQUE,
            name TEXT NOT NULL,
            indexed_at TEXT,
            manifest_json TEXT
        );

        CREATE TABLE IF NOT EXISTS nodes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            repository_id INTEGER NOT NULL,
            node_type TEXT NOT NULL,
            name TEXT NOT NULL,
            file_path TEXT,
            metadata_json TEXT,
            FOREIGN KEY (repository_id) REFERENCES repositories(id)
        );

        CREATE TABLE IF NOT EXISTS edges (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            repository_id INTEGER NOT NULL,
            source_node_id INTEGER NOT NULL,
            target_node_id INTEGER NOT NULL,
            edge_type TEXT NOT NULL,
            metadata_json TEXT,
            FOREIGN KEY (repository_id) REFERENCES repositories(id),
            FOREIGN KEY (source_node_id) REFERENCES nodes(id),
            FOREIGN KEY (target_node_id) REFERENCES nodes(id)
        );

        CREATE TABLE IF NOT EXISTS embeddings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            node_id INTEGER NOT NULL,
            model TEXT NOT NULL,
            vector BLOB NOT NULL,
            FOREIGN KEY (node_id) REFERENCES nodes(id)
        );

        CREATE TABLE IF NOT EXISTS commits (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            repository_id INTEGER NOT NULL,
            hash TEXT NOT NULL,
            author TEXT,
            message TEXT,
            committed_at TEXT,
            FOREIGN KEY (repository_id) REFERENCES repositories(id)
        );

        CREATE TABLE IF NOT EXISTS architecture (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            repository_id INTEGER NOT NULL,
            layer TEXT NOT NULL,
            pattern TEXT,
            description TEXT,
            FOREIGN KEY (repository_id) REFERENCES repositories(id)
        );

        CREATE TABLE IF NOT EXISTS commit_files (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            commit_id INTEGER NOT NULL,
            file_path TEXT NOT NULL,
            change_type TEXT,
            FOREIGN KEY (commit_id) REFERENCES commits(id)
        );

        CREATE TABLE IF NOT EXISTS commit_authors (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            repository_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            email TEXT,
            commit_count INTEGER DEFAULT 0,
            FOREIGN KEY (repository_id) REFERENCES repositories(id)
        );
    """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_nodes_repo_type
        ON nodes(repository_id, node_type)
    """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_nodes_file_path
        ON nodes(file_path)
    """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_edges_repo_type
        ON edges(repository_id, edge_type)
    """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_edges_source
        ON edges(source_node_id)
    """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_edges_target
        ON edges(target_node_id)
    """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_embeddings_node_model
        ON embeddings(node_id, model)
    """)
    conn.commit()
