from __future__ import annotations

import struct
from pathlib import Path
from typing import Any

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


EMBEDDABLE_TYPES = {"class", "function", "method", "file", "interface", "enum"}


def _build_node_text(name: str, node_type: str, file_path: str, metadata: dict[str, Any]) -> str:
    parts = [f"{node_type}: {name}"]
    if file_path:
        parts.append(f"file: {file_path}")
    if metadata.get("docstring"):
        parts.append(f"docstring: {metadata['docstring']}")
    return "\n".join(parts)


def _vector_to_blob(vector: list[float]) -> bytes:
    return struct.pack(f"{len(vector)}f", *vector)


def _blob_to_vector(blob: bytes) -> list[float]:
    n = len(blob) // 4
    return list(struct.unpack(f"{n}f", blob))


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
            (node_id, EMBEDDING_MODEL, _vector_to_blob(vector)),
        )
        inserted += 1

    conn.commit()
    conn.close()
    return inserted


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = sum(x * x for x in a) ** 0.5
    nb = sum(x * x for x in b) ** 0.5
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


def similarity_search(
    db_path: Path,
    query: str,
    limit: int = 20,
    repo_name: str | None = None,
) -> list[dict[str, Any]]:
    model = _get_model()
    query_vec = list(model.embed([query]))[0]

    from cartographer.storage.connection import get_connection
    conn = get_connection(db_path)

    repo_filter = ""
    params: list[str] = []
    if repo_name:
        repo_filter = "AND r.name = ?"
        params.append(repo_name)

    rows = conn.execute(
        f"""SELECT n.id, n.name, n.node_type, n.file_path, emb.vector, r.name as repo_name
            FROM embeddings emb
            JOIN nodes n ON emb.node_id = n.id
            JOIN repositories r ON n.repository_id = r.id
            WHERE emb.model = ?
            {repo_filter}
         """,
        [EMBEDDING_MODEL, *params],
    ).fetchall()

    results: list[tuple[float, dict[str, Any]]] = []
    for row in rows:
        node_id, name, node_type, file_path, vec_blob, repo = row
        vec = _blob_to_vector(vec_blob)
        score = _cosine_similarity(query_vec, vec)
        results.append((score, {
            "id": node_id,
            "name": name,
            "type": node_type,
            "file_path": file_path,
            "repo_name": repo,
            "similarity": round(score, 4),
        }))

    conn.close()

    results.sort(key=lambda x: -x[0])
    return [r[1] for r in results[:limit]]


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

    target_vec = _blob_to_vector(row[0])

    target_repo = conn.execute(
        """SELECT r.name FROM nodes n
           JOIN repositories r ON n.repository_id = r.id
           WHERE n.id = ?""",
        (node_id,),
    ).fetchone()

    repo_name = target_repo[0] if target_repo else None

    rows = conn.execute(
        """SELECT n.id, n.name, n.node_type, n.file_path, emb.vector
            FROM embeddings emb
            JOIN nodes n ON emb.node_id = n.id
            WHERE emb.model = ? AND n.id != ?
         """,
        (EMBEDDING_MODEL, node_id),
    ).fetchall()

    results: list[tuple[float, dict[str, Any]]] = []
    for row in rows:
        nid, name, node_type, file_path, vec_blob = row
        vec = _blob_to_vector(vec_blob)
        score = _cosine_similarity(target_vec, vec)
        results.append((score, {
            "id": nid,
            "name": name,
            "type": node_type,
            "file_path": file_path,
            "repo_name": repo_name,
            "similarity": round(score, 4),
        }))

    conn.close()

    results.sort(key=lambda x: -x[0])
    return [r[1] for r in results[:limit]]
