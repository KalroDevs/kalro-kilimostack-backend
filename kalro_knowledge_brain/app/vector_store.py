"""
Vector database wrapper (Chroma, persisted to disk) storing embedded chunks
of KALRO's certified advisory content -- the RAG index queried by
``rag.answer_query``.

Chroma was chosen because it needs no separate server process (good for a
self-contained reference implementation), but the wrapper's interface
(``upsert_chunks`` / ``query``) is narrow enough to swap for pgvector
(sharing the Django backend's Postgres) in a production deployment -- see
README "Production Hardening Notes".
"""

from __future__ import annotations

from typing import Any

import chromadb
from chromadb.config import Settings as ChromaSettings

from .config import settings


class VectorStore:
    def __init__(self):
        self._client = chromadb.PersistentClient(
            path=settings.chroma_persist_dir,
            settings=ChromaSettings(anonymized_telemetry=False),
        )
        self._collection = self._client.get_or_create_collection(
            name=settings.chroma_collection_name,
            metadata={"hnsw:space": "cosine"},
        )

    def upsert_chunks(
        self,
        ids: list[str],
        embeddings: list[list[float]],
        documents: list[str],
        metadatas: list[dict[str, Any]],
    ) -> None:
        # Chroma metadata values must be str/int/float/bool -- flatten lists.
        clean_metadatas = [_flatten_metadata(m) for m in metadatas]
        self._collection.upsert(
            ids=ids, embeddings=embeddings, documents=documents, metadatas=clean_metadatas
        )

    def delete_by_resource(self, publication_id: str) -> None:
        self._collection.delete(where={"publication_id": publication_id})

    def query(
        self,
        query_embedding: list[float],
        top_k: int = 5,
        where: dict[str, Any] | None = None,
    ) -> dict:
        return self._collection.query(
            query_embeddings=[query_embedding],
            n_results=top_k,
            where=where or None,
        )

    def count(self) -> int:
        return self._collection.count()


def _flatten_metadata(metadata: dict[str, Any]) -> dict[str, Any]:
    flat = {}
    for key, value in metadata.items():
        if isinstance(value, (list, tuple)):
            flat[key] = ", ".join(str(v) for v in value)
        elif isinstance(value, (str, int, float, bool)) or value is None:
            flat[key] = value if value is not None else ""
        else:
            flat[key] = str(value)
    return flat


vector_store = VectorStore()
