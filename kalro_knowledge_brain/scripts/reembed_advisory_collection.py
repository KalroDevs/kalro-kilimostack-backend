"""Re-embed the existing advisory Chroma collection into the configured collection.

Run from kalro_knowledge_brain with the project Python environment:
    python -m scripts.reembed_advisory_collection

The legacy collection is read-only and retained as a rollback copy.
"""

import asyncio

import chromadb
from chromadb.config import Settings as ChromaSettings

from app.config import settings
from app.ollama_client import ollama_client

SOURCE_COLLECTION = "kalro_advisory_corpus"
PAGE_SIZE = 100


async def reembed_advisory_collection() -> int:
    client = chromadb.PersistentClient(
        path=settings.chroma_persist_dir,
        settings=ChromaSettings(anonymized_telemetry=False),
    )
    source = client.get_collection(name=SOURCE_COLLECTION)
    target = client.get_or_create_collection(
        name=settings.chroma_collection_name,
        metadata={"hnsw:space": "cosine"},
    )
    total = source.count()
    if total == 0:
        raise RuntimeError(f"Source collection {SOURCE_COLLECTION!r} is empty; refusing to migrate.")

    for offset in range(0, total, PAGE_SIZE):
        batch = source.get(limit=PAGE_SIZE, offset=offset, include=["documents", "metadatas"])
        documents = batch.get("documents") or []
        metadatas = batch.get("metadatas") or [{} for _ in documents]
        embeddings = []
        for document, metadata in zip(documents, metadatas):
            title = metadata.get("title", "")
            header = metadata.get("content_header", "")
            embedding_text = f"{title} — {header}\n\n{document}"
            embeddings.append(await ollama_client.embed(embedding_text))
        target.upsert(
            ids=batch["ids"],
            embeddings=embeddings,
            documents=documents,
            metadatas=metadatas,
        )
        print(f"Re-embedded {min(offset + len(documents), total)}/{total} advisory chunks")

    if target.count() != total:
        raise RuntimeError(f"Migration verification failed: expected {total} chunks, found {target.count()}.")
    sample = target.get(limit=1, include=["embeddings"])
    dimension = len(sample["embeddings"][0]) if sample.get("embeddings") is not None and len(sample["embeddings"]) else 0
    print(f"Verified {target.count()} chunks in {target.name!r}; embedding dimension={dimension}.")
    return target.count()


if __name__ == "__main__":
    asyncio.run(reembed_advisory_collection())
