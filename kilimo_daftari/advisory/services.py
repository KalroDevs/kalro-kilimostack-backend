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
from pathlib import Path
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
        headers = {}
        if settings.AI_LAYER_INGEST_API_KEY:
            headers["X-API-Key"] = settings.AI_LAYER_INGEST_API_KEY
        response = httpx.post(
            url,
            json=[payload],
            headers=headers,
            timeout=settings.AI_LAYER_SYNC_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        resource.vector_sync_status = VectorSyncStatusChoices.SYNCED
        resource.vector_synced_at = timezone.now()
        resource.vector_sync_error = ""
        resource.save(update_fields=["vector_sync_status", "vector_synced_at", "vector_sync_error"])
        # The section text is synced above. If the resource also has an
        # uploaded file, index it through the same AI Layer document pipeline
        # used by the admin-only Documents section.
        if resource.upload_file:
            if not _sync_resource_file_to_ai_layer(resource):
                return False
        logger.info("Synced %s to AI Layer (%s)", resource.publication_id, url)
        return True
    except Exception as exc:  # noqa: BLE001 - best-effort sync, log and continue
        resource.vector_sync_status = VectorSyncStatusChoices.FAILED
        resource.vector_sync_error = str(exc)
        resource.save(update_fields=["vector_sync_status", "vector_sync_error"])
        logger.warning("Failed to sync %s to AI Layer: %s", resource.publication_id, exc)
        return False


def _sync_resource_file_to_ai_layer(resource: AdvisoryResource) -> bool:
    filename = Path(resource.upload_file.name).name
    url = f"{settings.AI_LAYER_BASE_URL}{settings.AI_LAYER_DOCUMENT_INGEST_PATH}"
    headers = {}
    if settings.AI_LAYER_INGEST_API_KEY:
        headers["X-API-Key"] = settings.AI_LAYER_INGEST_API_KEY
    try:
        with resource.upload_file.open("rb") as file_handle:
            response = httpx.post(
                url,
                data={"document_id": f"advisory-{resource.publication_id}", "name": resource.title},
                files={"file": (filename, file_handle, "application/octet-stream")},
                headers=headers,
                timeout=settings.AI_LAYER_DOCUMENT_TIMEOUT_SECONDS,
            )
        response.raise_for_status()
        result = response.json()
        if result.get("status") != "verified" or result.get("chunks_indexed", 0) < 1:
            raise ValueError("AI Layer returned an invalid advisory file ingestion response.")
        return True
    except Exception as exc:  # best effort failure is surfaced in the sync status
        resource.vector_sync_status = VectorSyncStatusChoices.FAILED
        resource.vector_sync_error = f"Advisory file indexing failed: {type(exc).__name__}"
        resource.save(update_fields=["vector_sync_status", "vector_sync_error"])
        logger.warning("Failed to index uploaded advisory file for %s (%s)", resource.publication_id, type(exc).__name__)
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
