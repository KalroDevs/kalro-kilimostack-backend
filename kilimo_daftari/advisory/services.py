"""
Sync certified AdvisoryResource records to the FastAPI + Ollama AI Layer,
which chunks, embeds and stores them in the vector database used by the
RAG + LLM service.

This is intentionally a simple, synchronous best-effort HTTP call so the
project stays runnable without a message broker. For a production
deployment, swap ``sync_resource_to_ai_layer`` for a Celery task (see
README "Production Hardening Notes").
"""

import logging
from django.conf import settings
from django.utils import timezone

import httpx

from .models import AdvisoryResource, VectorSyncStatusChoices
from .serializers import AdvisoryResourceSerializer

logger = logging.getLogger(__name__)


def sync_resource_to_ai_layer(resource: AdvisoryResource) -> bool:
    """
    POST a single resource (spec-shaped JSON) to the AI Layer's ingest
    endpoint. Updates the resource's vector_sync_status accordingly.
    Returns True on success, False otherwise. Never raises -- ingestion
    failures must not block content screening in Django.
    """
    if not settings.AI_LAYER_SYNC_ENABLED:
        return False

    if not resource.is_ready_for_ai_layer:
        logger.info(
            "Skipping AI Layer sync for %s: quality_flag=%s (must be ready_to_certify)",
            resource.publication_id,
            resource.quality_flag,
        )
        return False

    payload = AdvisoryResourceSerializer(resource).data
    url = f"{settings.AI_LAYER_BASE_URL}{settings.AI_LAYER_INGEST_PATH}"

    resource.vector_sync_status = VectorSyncStatusChoices.PENDING
    resource.save(update_fields=["vector_sync_status"])

    try:
        response = httpx.post(
            url,
            json=[payload],
            timeout=settings.AI_LAYER_SYNC_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        resource.vector_sync_status = VectorSyncStatusChoices.SYNCED
        resource.vector_synced_at = timezone.now()
        resource.vector_sync_error = ""
        resource.save(update_fields=["vector_sync_status", "vector_synced_at", "vector_sync_error"])
        logger.info("Synced %s to AI Layer (%s)", resource.publication_id, url)
        return True
    except Exception as exc:  # noqa: BLE001 - best-effort sync, log and continue
        resource.vector_sync_status = VectorSyncStatusChoices.FAILED
        resource.vector_sync_error = str(exc)
        resource.save(update_fields=["vector_sync_status", "vector_sync_error"])
        logger.warning("Failed to sync %s to AI Layer: %s", resource.publication_id, exc)
        return False


def sync_many(resources) -> dict:
    results = {"synced": 0, "skipped": 0, "failed": 0}
    for resource in resources:
        if not resource.is_ready_for_ai_layer:
            results["skipped"] += 1
            continue
        ok = sync_resource_to_ai_layer(resource)
        results["synced" if ok else "failed"] += 1
    return results
