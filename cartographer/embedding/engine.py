from __future__ import annotations

import json
import logging
import os
import threading
from functools import lru_cache
from pathlib import Path
from typing import Any

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

import numpy as np
from fastembed import TextEmbedding
from tqdm import tqdm

logger = logging.getLogger(__name__)

EMBEDDING_MODEL = os.environ.get("CARTOGRAPHER_EMBEDDING_MODEL", "BAAI/bge-small-en-v1.5")
EMBEDDING_DIM = int(os.environ.get("CARTOGRAPHER_EMBEDDING_DIM", "384"))
EMBEDDING_BATCH_SIZE = int(os.environ.get("CARTOGRAPHER_EMBEDDING_BATCH_SIZE", "256"))
EMBEDDING_PARALLELISM = int(os.environ.get("CARTOGRAPHER_EMBEDDING_PARALLELISM", "0"))

_model: TextEmbedding | None = None
_model_lock = threading.Lock()

_vector_cache: dict[tuple[str, str], tuple[np.ndarray, list[dict[str, Any]], np.ndarray]] = {}
_vector_cache_lock = threading.Lock()
_VECTOR_CACHE_MAX_ENTRIES = 10

EMBEDDABLE_TYPES = {"class", "function", "method", "file", "interface", "enum", "type_alias"}


def _get_model() -> TextEmbedding:
    global _model
    if _model is None:
        with _model_lock:
            if _model is None:
                kwargs: dict[str, Any] = {}
                if EMBEDDING_PARALLELISM > 0:
                    kwargs["parallelism"] = EMBEDDING_PARALLELISM
                _model = TextEmbedding(EMBEDDING_MODEL, **kwargs)
    return _model


def _build_node_text(name: str, node_type: str, file_path: str, metadata: dict[str, Any]) -> str:
    parts = [f"{node_type}: {name}"]
    if file_path:
        parts.append(f"file: {file_path}")
    if metadata.get("docstring"):
        parts.append(f"docstring: {metadata['docstring']}")
    if node_type in ("function", "method") and metadata.get("signature"):
        parts.append(f"signature: {metadata['signature']}")
    if node_type == "method" and metadata.get("parent_name"):
        parts.append(f"parent: {metadata['parent_name']}")
    if node_type == "function" and metadata.get("parent_name"):
        parts.append(f"module: {metadata['parent_name']}")
    if metadata.get("parameters"):
        parts.append(f"parameters: {', '.join(metadata['parameters'])}")
    if metadata.get("return_type"):
        parts.append(f"returns: {metadata['return_type']}")
    return "\n".join(parts)


def invalidate_cache(db_path: Path, repo_name: str | None = None) -> None:
    with _vector_cache_lock:
        if repo_name is None:
            db_str = str(db_path)
            stale = [k for k in _vector_cache if k[0] == db_str]
            for k in stale:
                del _vector_cache[k]
        else:
            _vector_cache.pop((str(db_path), repo_name), None)


def _load_vectors(
    db_path: Path, repo_name: str | None = None, exclude_id: int | None = None
) -> tuple[np.ndarray, list[dict[str, Any]], np.ndarray]:
    cache_key = (str(db_path), repo_name or "")

    with _vector_cache_lock:
        if cache_key in _vector_cache:
            vectors, records, norms = _vector_cache[cache_key]
            if exclude_id is not None:
                keep = np.array([r["id"] != exclude_id for r in records])
                return vectors[keep], [r for i, r in enumerate(records) if keep[i]], norms[keep]
            return vectors, records, norms

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
        return np.empty((0, EMBEDDING_DIM), dtype=np.float32), [], np.empty(0, dtype=np.float32)

    blobs = [r[4] for r in rows]
    vectors = np.frombuffer(b"".join(blobs), dtype=np.float32).reshape(len(rows), EMBEDDING_DIM)
    records = [
        {"id": r[0], "name": r[1], "type": r[2], "file_path": r[3]}
        for r in rows
    ]
    norms = np.linalg.norm(vectors, axis=1)

    with _vector_cache_lock:
        if cache_key not in _vector_cache:
            if len(_vector_cache) >= _VECTOR_CACHE_MAX_ENTRIES:
                _vector_cache.pop(next(iter(_vector_cache)))
            _vector_cache[cache_key] = (vectors, records, norms)

    return vectors, records, norms


def generate_embeddings(
    db_path: Path,
    repo_name: str | None = None,
) -> tuple[int, int]:
    invalidate_cache(db_path, repo_name)
    from cartographer.storage.connection import get_connection
    conn = get_connection(db_path)
    model = _get_model()

    repo_filter = ""
    params: list[str] = []
    if repo_name:
        repo_filter = "AND r.name = ?"
        params.append(repo_name)

    embeddable_types_list = list(EMBEDDABLE_TYPES)
    placeholders = ",".join("?" for _ in embeddable_types_list)

    rows = conn.execute(
        f"""SELECT n.id, n.name, n.node_type, n.file_path, n.metadata_json, r.name
            FROM nodes n
            JOIN repositories r ON n.repository_id = r.id
            LEFT JOIN embeddings e ON e.node_id = n.id AND e.model = ?
            WHERE n.node_type IN ({placeholders})
            {repo_filter}
            AND e.id IS NULL
         """,
        [EMBEDDING_MODEL, *embeddable_types_list, *params],
    ).fetchall()

    if not rows:
        conn.close()
        return 0, 0

    texts: list[str] = []
    node_ids: list[int] = []
    for row in tqdm(rows, desc="Preparing texts", unit="node"):
        node_id, name, node_type, file_path, metadata_json, _ = row
        metadata = {}
        if metadata_json:
            try:
                metadata = json.loads(metadata_json)
            except (json.JSONDecodeError, TypeError) as e:
                logger.debug("Failed to parse metadata for node %d: %s", node_id, e)
        texts.append(_build_node_text(name, node_type, file_path, metadata))
        node_ids.append(node_id)

    vectors = list(tqdm(
        model.embed(texts, batch_size=EMBEDDING_BATCH_SIZE),
        desc="Embedding", total=len(texts), unit="vec",
    ))

    conn.executemany(
        "INSERT OR IGNORE INTO embeddings (node_id, model, vector) VALUES (?, ?, ?)",
        [
            (node_id, EMBEDDING_MODEL, np.array(vector, dtype=np.float32).tobytes())
            for node_id, vector in zip(node_ids, vectors)
        ],
    )
    conn.commit()
    conn.close()

    return len(node_ids), 0


def embed_nodes(
    db_path: Path,
    node_ids: list[int],
) -> int:
    """Generate embeddings for a specific set of node IDs."""
    if not node_ids:
        return 0
    invalidate_cache(db_path)
    from cartographer.storage.connection import get_connection
    conn = get_connection(db_path)
    model = _get_model()

    ph = ",".join("?" for _ in node_ids)
    rows = conn.execute(
        f"""SELECT n.id, n.name, n.node_type, n.file_path, n.metadata_json
            FROM nodes n
            WHERE n.id IN ({ph})
            AND n.node_type IN ({','.join('?' for _ in EMBEDDABLE_TYPES)})""",
        [*node_ids, *EMBEDDABLE_TYPES],
    ).fetchall()

    if not rows:
        conn.close()
        return 0

    texts: list[str] = []
    ids: list[int] = []
    for row in rows:
        node_id, name, node_type, file_path, metadata_json = row
        metadata = {}
        if metadata_json:
            try:
                metadata = json.loads(metadata_json)
            except (json.JSONDecodeError, TypeError):
                pass
        texts.append(_build_node_text(name, node_type, file_path, metadata))
        ids.append(node_id)

    vectors = list(model.embed(texts, batch_size=EMBEDDING_BATCH_SIZE))
    conn.executemany(
        "INSERT OR REPLACE INTO embeddings (node_id, model, vector) VALUES (?, ?, ?)",
        [
            (node_id, EMBEDDING_MODEL, np.array(vector, dtype=np.float32).tobytes())
            for node_id, vector in zip(ids, vectors)
        ],
    )
    conn.commit()
    conn.close()
    return len(ids)


@lru_cache(maxsize=128)
def _encode_query(query: str) -> bytes:
    model = _get_model()
    vec = np.array(list(model.embed([query]))[0], dtype=np.float32)
    return vec.tobytes()


def similarity_search(
    db_path: Path,
    query: str,
    limit: int = 20,
    repo_name: str | None = None,
) -> list[dict[str, Any]]:
    query_vec = np.frombuffer(_encode_query(query), dtype=np.float32)
    query_norm = np.linalg.norm(query_vec)
    if query_norm == 0:
        return []

    vectors, records, norms = _load_vectors(db_path, repo_name)
    if len(vectors) == 0:
        return []

    scores = (vectors @ query_vec) / (norms * query_norm)

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
    target_norm = np.linalg.norm(target_vec)
    conn.close()

    if target_norm == 0:
        return []

    vectors, records, norms = _load_vectors(db_path, exclude_id=node_id)
    if len(vectors) == 0:
        return []

    scores = (vectors @ target_vec) / (norms * target_norm)

    top_k = min(limit, len(scores))
    top_indices = np.argpartition(-scores, top_k)[:top_k]
    top_order = top_indices[np.argsort(-scores[top_indices])]

    results: list[dict[str, Any]] = []
    for idx in top_order:
        rec = dict(records[idx])
        rec["similarity"] = round(float(scores[idx]), 4)
        results.append(rec)
    return results
