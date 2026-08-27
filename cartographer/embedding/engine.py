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
                last_exc: Exception | None = None
                for attempt in range(3):
                    try:
                        kwargs: dict[str, Any] = {}
                        if EMBEDDING_PARALLELISM > 0:
                            kwargs["parallelism"] = EMBEDDING_PARALLELISM
                        _model = TextEmbedding(EMBEDDING_MODEL, **kwargs)
                        break
                    except Exception as exc:
                        last_exc = exc
                        logger.warning("Embedding model load failed (attempt %d/3): %s", attempt + 1, exc)
                        if attempt < 2:
                            import time as _t

                            _t.sleep(2**attempt)
                if _model is None and last_exc is not None:
                    raise last_exc
    return _model  # type: ignore[return-value]


def _build_node_text(name: str, node_type: str, file_path: str, metadata: dict[str, Any]) -> str:
    parts = [f"{node_type}: {name}"]
    if file_path:
        parts.append(f"file: {file_path}")
        # include directory context for better semantics
        try:
            dir_part = "/".join(file_path.split("/")[:-1])
            if dir_part:
                parts.append(f"directory: {dir_part}")
        except Exception:
            pass
    if metadata.get("docstring"):
        doc = str(metadata["docstring"]).strip()
        if len(doc) > 500:
            doc = doc[:500] + "…"
        parts.append(f"docstring: {doc}")
    # signature / parameters / types
    if metadata.get("signature"):
        parts.append(f"signature: {metadata['signature']}")
    if metadata.get("parameters"):
        try:
            params = metadata["parameters"]
            if isinstance(params, (list, tuple)):
                parts.append(f"parameters: {', '.join(str(p) for p in params[:10])}")
            else:
                parts.append(f"parameters: {params}")
        except Exception:
            pass
    if metadata.get("return_type"):
        parts.append(f"returns: {metadata['return_type']}")
    if metadata.get("decorators"):
        dec = str(metadata["decorators"]).strip()
        if dec:
            parts.append(f"decorators: {dec[:200]}")
    if metadata.get("bases"):
        try:
            bases = metadata["bases"]
            if isinstance(bases, (list, tuple)) and bases:
                parts.append(f"bases: {', '.join(str(b) for b in bases[:5])}")
        except Exception:
            pass
    # parent/module context
    if metadata.get("parent_name"):
        key = "parent" if node_type == "method" else "module"
        parts.append(f"{key}: {metadata['parent_name']}")
    if metadata.get("language"):
        parts.append(f"language: {metadata['language']}")
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

    # filter corrupted blobs (must be EMBEDDING_DIM*4 bytes)
    valid_rows: list = []
    blobs: list[bytes] = []
    for r in rows:
        blob = r[4]
        if isinstance(blob, (bytes, bytearray)) and len(blob) == EMBEDDING_DIM * 4:
            valid_rows.append(r)
            blobs.append(bytes(blob))
        else:
            logger.debug("Skipping corrupted embedding for node %s (size %s)", r[0], len(blob) if isinstance(blob, (bytes, bytearray)) else type(blob))
            # try to recover: if blob is wrong size but divisible, skip
            continue
    if not valid_rows:
        return np.empty((0, EMBEDDING_DIM), dtype=np.float32), [], np.empty(0, dtype=np.float32)
    # for very large repos, warn if >100k vectors
    if len(valid_rows) > 100000:
        logger.warning("Large embedding set (%d vectors) — consider per-repo search", len(valid_rows))
    try:
        vectors = np.frombuffer(b"".join(blobs), dtype=np.float32).reshape(len(valid_rows), EMBEDDING_DIM)
    except Exception as exc:
        logger.warning("Vector assembly failed: %s — falling back to per-row", exc)
        # fallback: build incrementally, skipping bad rows
        vecs = []
        recs = []
        for r, b in zip(valid_rows, blobs):
            try:
                v = np.frombuffer(b, dtype=np.float32)
                if v.shape[0] == EMBEDDING_DIM:
                    vecs.append(v)
                    recs.append(r)
            except Exception:
                continue
        if not vecs:
            return np.empty((0, EMBEDDING_DIM), dtype=np.float32), [], np.empty(0, dtype=np.float32)
        vectors = np.stack(vecs)
        valid_rows = recs
    records = [
        {"id": r[0], "name": r[1], "type": r[2], "file_path": r[3]}
        for r in valid_rows
    ]
    try:
        norms = np.linalg.norm(vectors, axis=1)
        # guard against zero norms
        norms = np.where(norms == 0, 1, norms)
    except Exception:
        norms = np.ones(len(vectors), dtype=np.float32)

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

    try:
        model = _get_model()
    except Exception as exc:
        logger.error("Embedding model unavailable: %s — skipping embeddings", exc)
        return 0, 0
    conn = get_connection(db_path)

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

    # Count total embeddable nodes to compute skip count
    total_row = conn.execute(
        f"""SELECT COUNT(*) FROM nodes n
            JOIN repositories r ON n.repository_id = r.id
            WHERE n.node_type IN ({placeholders})
            {repo_filter}""",
        [*embeddable_types_list, *params],
    ).fetchone()
    total_embeddable = total_row[0] if total_row else 0
    skip_count = total_embeddable - len(rows)

    # chunked processing to avoid OOM on large repos (~100k nodes)
    CHUNK = 500
    total_embedded = 0
    # prepare all texts first (still in memory but smaller than vectors)
    all_texts: list[str] = []
    all_ids: list[int] = []
    for row in tqdm(rows, desc="Preparing texts", unit="node"):
        node_id, name, node_type, file_path, metadata_json, _ = row
        metadata = {}
        if metadata_json:
            try:
                metadata = json.loads(metadata_json)
            except (json.JSONDecodeError, TypeError) as e:
                logger.debug("Failed to parse metadata for node %d: %s", node_id, e)
        all_texts.append(_build_node_text(name, node_type, file_path, metadata))
        all_ids.append(node_id)

    # embed in chunks to limit memory and allow incremental DB commits
    for start in tqdm(range(0, len(all_texts), CHUNK), desc="Embedding chunks", unit="chunk"):
        chunk_texts = all_texts[start : start + CHUNK]
        chunk_ids = all_ids[start : start + CHUNK]
        try:
            chunk_vectors = list(model.embed(chunk_texts, batch_size=EMBEDDING_BATCH_SIZE))
        except Exception as exc:
            logger.warning("Embedding chunk %d failed: %s — skipping", start // CHUNK, exc)
            continue
        try:
            conn.executemany(
                "INSERT OR IGNORE INTO embeddings (node_id, model, vector) VALUES (?, ?, ?)",
                [
                    (nid, EMBEDDING_MODEL, np.array(vec, dtype=np.float32).tobytes())
                    for nid, vec in zip(chunk_ids, chunk_vectors)
                ],
            )
            conn.commit()
            total_embedded += len(chunk_ids)
        except Exception as exc:
            logger.warning("DB insert failed for chunk %d: %s", start // CHUNK, exc)
            try:
                conn.rollback()
            except Exception:
                pass

    conn.close()

    return total_embedded, skip_count


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
    try:
        model = _get_model()
        vec = np.array(list(model.embed([query]))[0], dtype=np.float32)
        return vec.tobytes()
    except Exception as exc:
        logger.warning("Query encode failed for '%s': %s", query[:50], exc)
        # fallback: zero vector (will yield empty results, caller handles)
        return np.zeros(EMBEDDING_DIM, dtype=np.float32).tobytes()


def similarity_search(
    db_path: Path,
    query: str,
    limit: int = 20,
    repo_name: str | None = None,
) -> list[dict[str, Any]]:
    if not query or not query.strip():
        return []
    limit = max(1, min(int(limit) if isinstance(limit, int) else 20, 100))
    try:
        query_vec = np.frombuffer(_encode_query(query), dtype=np.float32)
    except Exception:
        return []
    try:
        query_norm = np.linalg.norm(query_vec)
    except Exception:
        return []
    if query_norm == 0:
        return []

    try:
        vectors, records, norms = _load_vectors(db_path, repo_name)
    except Exception as exc:
        logger.warning("Load vectors failed: %s", exc)
        return []
    if len(vectors) == 0:
        # fallback: no embeddings yet — return empty so caller can hint to run embed
        return []

    try:
        scores = (vectors @ query_vec) / (norms * query_norm)
        # sanitize NaN
        scores = np.nan_to_num(scores, nan=0.0)
    except Exception as exc:
        logger.warning("Score computation failed: %s", exc)
        return []

    # hybrid boost: always blend vector cosine with keyword overlap + type priority for better recall
    # This fixes cases where pure cosine misses exact name matches due to embedding vagueness
    try:
        import re

        def _tok(s: str) -> set[str]:
            # split camelCase, snake, slash, dot
            if not s:
                return set()
            s = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", s)
            s = re.sub(r"[^a-zA-Z0-9]+", " ", s)
            return set(s.lower().split())

        q_words = _tok(query)
        # type priority similar to searcher
        _type_boost = {
            "class": 0.05,
            "interface": 0.05,
            "controller": 0.08,
            "service": 0.06,
            "api_endpoint": 0.08,
            "function": 0.03,
            "method": 0.03,
        }
        for i, rec in enumerate(records):
            boost = 0.0
            name_words = _tok(rec.get("name") or "")
            file_words = _tok(rec.get("file_path") or "")
            overlap = len(q_words & (name_words | file_words))
            if overlap:
                # scale by overlap ratio, not just count
                boost += 0.12 * overlap / max(len(q_words), 1)
                # exact name match bonus
                if query.lower().strip() == (rec.get("name") or "").lower():
                    boost += 0.15
                elif query.lower().strip() in (rec.get("name") or "").lower():
                    boost += 0.08
            # type priority
            t = rec.get("type") or ""
            boost += _type_boost.get(t, 0.0) * 0.5  # smaller
            if boost:
                scores[i] += boost
    except Exception:
        pass

    top_k = min(limit, len(scores))
    if top_k <= 0:
        return []
    try:
        top_indices = np.argpartition(-scores, top_k - 1)[:top_k]
        top_order = top_indices[np.argsort(-scores[top_indices])]
    except Exception:
        # fallback to sorted
        top_order = np.argsort(-scores)[:top_k]

    results: list[dict[str, Any]] = []
    for idx in top_order:
        try:
            rec = dict(records[int(idx)])
            rec["similarity"] = round(float(scores[int(idx)]), 4)
            rec["repo_name"] = repo_name or ""
            results.append(rec)
        except Exception:
            continue
    # filter very low similarity (<0.15) to avoid noise, but keep at least 3 results
    if len(results) > 3:
        filtered = [r for r in results if r.get("similarity", 0) >= 0.15]
        if filtered:
            results = filtered
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
