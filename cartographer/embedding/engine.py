from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
from fastembed import TextEmbedding
from tqdm import tqdm

EMBEDDING_MODEL = "BAAI/bge-small-en-v1.5"
EMBEDDING_DIM = 384

_model: TextEmbedding | None = None


def _get_model() -> TextEmbedding:
    global _model
    if _model is None:
        _model = TextEmbedding(EMBEDDING_MODEL)
    return _model


EMBEDDABLE_TYPES = {"class", "function", "method", "file", "interface", "enum", "type_alias"}


def _build_node_text(name: str, node_type: str, file_path: str, metadata: dict[str, Any]) -> str:
    parts = [f"{node_type}: {name}"]
    if file_path:
        parts.append(f"file: {file_path}")
    if metadata.get("docstring"):
        parts.append(f"docstring: {metadata['docstring']}")
    return "\n".join(parts)


def generate_embeddings(
    db_path: Path,
    repo_name: str | None = None,
) -> int:
    from cartographer.storage.connection import get_connection
    conn = get_connection(db_path)
    model = _get_model()

    repo_filter = ""
    params: list[str] = []
    if repo_name:
        repo_filter = "AND r.name = ?"
        params.append(repo_name)

    rows = conn.execute(
        f"""SELECT n.id, n.name, n.node_type, n.file_path, n.metadata_json, r.name
            FROM nodes n
            JOIN repositories r ON n.repository_id = r.id
            WHERE n.node_type IN ({','.join('?' for _ in EMBEDDABLE_TYPES)})
            {repo_filter}
            AND n.id NOT IN (SELECT node_id FROM embeddings WHERE model = ?)
         """,
        [*EMBEDDABLE_TYPES, *params, EMBEDDING_MODEL],
    ).fetchall()

    if not rows:
        conn.close()
        return 0

    texts: list[str] = []
    node_ids: list[int] = []
    for row in tqdm(rows, desc="Preparing texts", unit="node"):
        node_id, name, node_type, file_path, metadata_json, _ = row
        metadata = {}
        if metadata_json:
            try:
                import json
                metadata = json.loads(metadata_json)
            except (json.JSONDecodeError, TypeError):
                pass
        texts.append(_build_node_text(name, node_type, file_path, metadata))
        node_ids.append(node_id)

    vectors = list(tqdm(model.embed(texts), desc="Embedding", total=len(texts), unit="vec"))

    inserted = 0
    for node_id, vector in tqdm(
        zip(node_ids, vectors), desc="Saving", total=len(node_ids), unit="vec"
    ):
        conn.execute(
            "INSERT INTO embeddings (node_id, model, vector) VALUES (?, ?, ?)",
            (node_id, EMBEDDING_MODEL, np.array(vector, dtype=np.float32).tobytes()),
        )
        inserted += 1

    conn.commit()
    conn.close()
    return inserted


def _load_vectors(
    db_path: Path, repo_name: str | None = None, exclude_id: int | None = None
) -> tuple[np.ndarray, list[dict[str, Any]]]:
    from cartographer.storage.connection import get_connection
    conn = get_connection(db_path)

    params: list[Any] = [EMBEDDING_MODEL]
    exclude_clause = ""
    if exclude_id is not None:
        exclude_clause = "AND n.id != ?"
        params.append(exclude_id)

    repo_clause = ""
    if repo_name:
        repo_clause = "AND r.name = ?"
        params.append(repo_name)

    rows = conn.execute(
        f"""SELECT n.id, n.name, n.node_type, n.file_path, emb.vector
            FROM embeddings emb
            JOIN nodes n ON emb.node_id = n.id
            JOIN repositories r ON n.repository_id = r.id
            WHERE emb.model = ?
            {exclude_clause}
            {repo_clause}
         """,
        params,
    ).fetchall()
    conn.close()

    if not rows:
        return np.empty((0, EMBEDDING_DIM), dtype=np.float32), []

    blobs = [r[4] for r in rows]
    vectors = np.frombuffer(b"".join(blobs), dtype=np.float32).reshape(len(rows), EMBEDDING_DIM)
    records = [
        {"id": r[0], "name": r[1], "type": r[2], "file_path": r[3]}
        for r in rows
    ]
    return vectors, records


def similarity_search(
    db_path: Path,
    query: str,
    limit: int = 20,
    repo_name: str | None = None,
) -> list[dict[str, Any]]:
    model = _get_model()
    query_vec = np.array(list(model.embed([query]))[0], dtype=np.float32)

    vectors, records = _load_vectors(db_path, repo_name)
    if len(vectors) == 0:
        return []

    norms = np.linalg.norm(vectors, axis=1)
    dot = vectors @ query_vec
    scores = dot / (norms * np.linalg.norm(query_vec))

    top_k = min(limit, len(scores))
    top_indices = np.argpartition(-scores, top_k)[:top_k]
    top_order = top_indices[np.argsort(-scores[top_indices])]

    results: list[dict[str, Any]] = []
    for idx in top_order:
        rec = dict(records[idx])
        rec["similarity"] = round(float(scores[idx]), 4)
        rec["repo_name"] = repo_name or ""
        results.append(rec)
    return results


def find_similar(
    db_path: Path,
    node_id: int,
    limit: int = 20,
) -> list[dict[str, Any]]:
    from cartographer.storage.connection import get_connection
    conn = get_connection(db_path)

    row = conn.execute(
        "SELECT vector FROM embeddings WHERE node_id = ? AND model = ?",
        (node_id, EMBEDDING_MODEL),
    ).fetchone()

    if not row:
        conn.close()
        return []

    target_vec = np.frombuffer(row[0], dtype=np.float32)
    conn.close()

    vectors, records = _load_vectors(db_path, exclude_id=node_id)
    if len(vectors) == 0:
        return []

    norms = np.linalg.norm(vectors, axis=1)
    dot = vectors @ target_vec
    scores = dot / (norms * np.linalg.norm(target_vec))

    top_k = min(limit, len(scores))
    top_indices = np.argpartition(-scores, top_k)[:top_k]
    top_order = top_indices[np.argsort(-scores[top_indices])]

    results: list[dict[str, Any]] = []
    for idx in top_order:
        rec = dict(records[idx])
        rec["similarity"] = round(float(scores[idx]), 4)
        results.append(rec)
    return results
