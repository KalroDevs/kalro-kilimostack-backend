"""Copy existing Chroma chunks into collections using the configured embed model.

Run from ``kalro_knowledge_brain`` with the project environment:
    python -m scripts.reembed_chroma_collections

The old collections are read only and kept as rollback copies.
"""

import asyncio
import logging

import chromadb
from chromadb.config import Settings as ChromaSettings
from chromadb.errors import NotFoundError

from app.config import settings
from app.ollama_client import ollama_client

PAGE_SIZE = 100
SOURCES = (
    ("kalro_advisory_corpus_v2", settings.chroma_collection_name, "advisory"),
    ("kalro_training_documents", settings.chroma_documents_collection_name, "document"),
)


async def _copy_collection(client, source_name: str, target_name: str, source_type: str) -> int:
    if source_name == target_name:
        raise RuntimeError(f"Source and target collection are both {source_name!r}.")
    try:
        source = client.get_collection(name=source_name)
    except NotFoundError:
        print(f"Skipping missing source collection {source_name!r}.")
        return 0

    total = source.count()
    if not total:
        print(f"Skipping empty source collection {source_name!r}.")
        return 0

    target = client.get_or_create_collection(
        name=target_name,
        metadata={"hnsw:space": "cosine"},
    )
    for offset in range(0, total, PAGE_SIZE):
        batch = source.get(
            limit=PAGE_SIZE,
            offset=offset,
            include=["documents", "metadatas"],
        )
        documents = batch.get("documents") or []
        metadatas = batch.get("metadatas") or [{} for _ in documents]
        embeddings = []
        for document, metadata in zip(documents, metadatas):
            metadata = metadata or {}
            if source_type == "advisory":
                text = f"{metadata.get('title', '')} — {metadata.get('content_header', '')}\n\n{document}"
            else:
                text = f"{metadata.get('title', '')}\n\n{document}"
            embeddings.append(await ollama_client.embed(text))
        target.upsert(
            ids=batch["ids"],
            embeddings=embeddings,
            documents=documents,
            metadatas=metadatas,
        )
        print(f"Re-embedded {min(offset + len(documents), total)}/{total} from {source_name!r}.")

    if target.count() < total:
        raise RuntimeError(
            f"Copy verification failed for {target_name!r}: source has {total}, "
            f"target has {target.count()}."
        )
    print(f"Verified {target.count()} chunks in {target_name!r}.")
    return total


async def main() -> None:
    client = chromadb.PersistentClient(
        path=settings.chroma_persist_dir,
        settings=ChromaSettings(anonymized_telemetry=False),
    )
    try:
        for source_name, target_name, source_type in SOURCES:
            await _copy_collection(client, source_name, target_name, source_type)
    finally:
        await ollama_client.aclose()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main())
