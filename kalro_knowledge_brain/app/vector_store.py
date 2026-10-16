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

import logging
from typing import Any

import chromadb
from chromadb.config import Settings as ChromaSettings
from chromadb.errors import InvalidArgumentError

from .config import settings

logger = logging.getLogger(__name__)


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
        self._documents_collection = self._client.get_or_create_collection(
            name=settings.chroma_documents_collection_name,
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

    def upsert_document_chunks(
        self,
        ids: list[str],
        embeddings: list[list[float]],
        documents: list[str],
        metadatas: list[dict[str, Any]],
    ) -> None:
        clean_metadatas = [_flatten_metadata(m) for m in metadatas]
        self._documents_collection.upsert(
            ids=ids,
            embeddings=embeddings,
            documents=documents,
            metadatas=clean_metadatas,
        )

    def delete_training_document(self, document_id: str) -> None:
        self._documents_collection.delete(where={"document_id": document_id})

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

    def query_all(self, query_embedding: list[float], top_k: int = 5, include_documents: bool = True, where: dict[str, Any] | None = None) -> list[dict]:
        
        collections = [("advisory", self._collection)]
        if include_documents:
            collections.append(("document", self._documents_collection))
        matches = []
        for source_type, collection in collections:
            if collection.count() == 0:
                continue
            try:
                result = collection.query(
                    query_embeddings=[query_embedding], n_results=top_k,
                    where=(where if source_type == "advisory" else None) or None,
                )
            except InvalidArgumentError as exc:
                logger.warning(
                    "Skipping Chroma %s collection because its embedding dimension "
                    "does not match the configured embedding model: %s",
                    source_type,
                    exc,
                )
                continue
            for i, chunk in enumerate(result.get("documents", [[]])[0]):
                matches.append({
                    "document": chunk,
                    "metadata": (result.get("metadatas", [[]])[0] or [{}])[i] or {},
                    "distance": (result.get("distances", [[]])[0] or [None] * (i + 1))[i],
                    "id": (result.get("ids", [[]])[0] or [""] * (i + 1))[i],
                    "source_type": source_type,
                })
        return sorted(matches, key=lambda match: match["distance"] if match["distance"] is not None else float("inf"))[:top_k]

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
