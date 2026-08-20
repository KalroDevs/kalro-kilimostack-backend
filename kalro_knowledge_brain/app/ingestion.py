"""
Turns AdvisoryResource payloads (JSON spec shape) into embedded, metadata-
rich chunks in the vector database.

Chunking strategy: one chunk per ``content[]`` section by default (sections
in KALRO's exports are already coherent, paragraph-length units). Any
section whose text exceeds ``MAX_CHUNK_CHARS`` is further split on
paragraph boundaries so no single chunk overwhelms the LLM's context
window.
"""

from __future__ import annotations

import logging

from .ollama_client import ollama_client
from .schemas import AdvisoryResource, ContentSection
from .vector_store import vector_store

logger = logging.getLogger(__name__)

MAX_CHUNK_CHARS = 1800


def _split_long_text(text: str, max_chars: int = MAX_CHUNK_CHARS) -> list[str]:
    if len(text) <= max_chars:
        return [text]
    paragraphs = [p.strip() for p in text.split("\n") if p.strip()] or [text]
    chunks, current = [], ""
    for para in paragraphs:
        if len(current) + len(para) + 1 > max_chars and current:
            chunks.append(current.strip())
            current = para
        else:
            current = f"{current}\n{para}".strip()
    if current:
        chunks.append(current.strip())
    return chunks


def _build_metadata(resource: AdvisoryResource, section: ContentSection, chunk_index: int) -> dict:
    return {
        "publication_id": resource.publication_id,
        "title": resource.title,
        "link": resource.link,
        "institution": resource.institution,
        "sector": resource.sector,
        "value_chain": resource.value_chain,
        "commodity": resource.commodity,
        "advisory_domain": resource.advisory_domain,
        "production_system": resource.production_system,
        "target_users": resource.target_users,
        "country": resource.geographic_applicability.country,
        "counties": resource.geographic_applicability.counties,
        "agro_ecological_zones": resource.geographic_applicability.agro_ecological_zones,
        "validation_status": resource.validation_status,
        "quality_flag": resource.quality_flag,
        "risk_level": resource.advisory_safety.risk_level or resource.currency_status,
        "requires_human_review": resource.advisory_safety.requires_human_review,
        "content_id": section.content_id,
        "content_header": section.content_header,
        "content_tags": section.content_tags,
        "has_warnings": bool(section.content_warnings),
        "page_start": section.page_start,
        "page_end": section.page_end,
        "chunk_index": chunk_index,
        "preferred_citation": resource.preferred_citation,
    }


async def ingest_resource(resource: AdvisoryResource) -> int:
    """
    Embeds and upserts every content section of a resource into the vector
    store. Returns the number of chunks indexed. Resources that are not yet
    certified (``quality_flag != "ready_to_certify"``) are skipped -- the
    caller (router) is expected to have already filtered, but this is a
    defensive second check since the vector index is farmer-facing.
    """
    if resource.quality_flag and resource.quality_flag != "ready_to_certify":
        logger.info("Skipping %s: quality_flag=%s", resource.publication_id, resource.quality_flag)
        return 0

    # Make re-ingestion idempotent: clear any previously indexed chunks for
    # this resource before writing the current version.
    vector_store.delete_by_resource(resource.publication_id)

    ids, embeddings, documents, metadatas = [], [], [], []
    for section in resource.content:
        sub_chunks = _split_long_text(section.content_text)
        for i, chunk_text in enumerate(sub_chunks):
            # Prepend header/context so the embedding captures topical framing,
            # not just the raw paragraph.
            embed_text = f"{resource.title} — {section.content_header}\n\n{chunk_text}"
            embedding = await ollama_client.embed(embed_text)

            chunk_id = f"{section.content_id}" if len(sub_chunks) == 1 else f"{section.content_id}-{i}"
            ids.append(chunk_id)
            embeddings.append(embedding)
            documents.append(chunk_text)
            metadatas.append(_build_metadata(resource, section, i))

    if ids:
        vector_store.upsert_chunks(ids=ids, embeddings=embeddings, documents=documents, metadatas=metadatas)
    logger.info("Ingested %s: %d chunk(s)", resource.publication_id, len(ids))
    return len(ids)
