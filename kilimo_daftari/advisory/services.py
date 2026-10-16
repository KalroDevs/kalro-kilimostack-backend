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
import re
import httpx
from django.conf import settings
from django.utils import timezone
import openpyxl
from django.db import transaction
from .management.commands.ingest_workbook import (
    classify_sheet,
    parse_inventory_sheet,
    parse_section_sheet,
)
from .models import AdvisoryResource, ContentSection, VectorSyncStatusChoices, WorkbookUpload
from .serializers import AdvisoryResourceSerializer

logger = logging.getLogger(__name__)

INVENTORY_SHEETS = [("Crop", "crop"), ("Livestock", "livestock")]

def ingest_workbook(upload: "WorkbookUpload"):
    upload.status = upload.Status.PROCESSING
    upload.log = ""
    upload.save(update_fields=["status", "log"])

    log_lines = []

    def log(msg):
        log_lines.append(msg)
        logger.info(msg)

    inventory_rows = []
    section_rows = []
    try:
        upload.file.open("rb")
        wb = openpyxl.load_workbook(upload.file, data_only=True)
        for sheet in wb.sheetnames:
            ws = wb[sheet]
            role = classify_sheet(ws)
            if role == "inventory":
                group = re.sub(r"[^a-z0-9]+", "_", sheet.lower()).strip("_")
                parsed = parse_inventory_sheet(ws, group)
                log(f"Parsed inventory '{sheet}': {len(parsed)} resource rows")
                inventory_rows.extend(parsed)
            elif role == "section":
                parsed = parse_section_sheet(ws, sheet)
                log(f"Parsed section '{sheet}': {len(parsed)} rows")
                section_rows.extend(parsed)
        wb.close()
    except Exception as e:
        upload.status = upload.Status.FAILED
        upload.log = f"Failed to read workbook: {e}"
        upload.save(update_fields=["status", "log"])
        logger.exception("Workbook open or parsing failed")
        return

    resources_created = resources_updated = 0
    try:
        with transaction.atomic():
            for row in inventory_rows:
                rid = row.pop("resource_id")
                _, created = AdvisoryResource.objects.update_or_create(
                    resource_id=rid,
                    defaults=row,
                )
                if created:
                    resources_created += 1
                else:
                    resources_updated += 1
    except Exception as e:
        upload.status = upload.Status.FAILED
        upload.log = "\n".join(log_lines + [f"ERROR on AdvisoryResource: {e}"])
        upload.save(update_fields=["status", "log"])
        logger.exception("AdvisoryResource ingest failed")
        return  

    log(f"AdvisoryResource: {resources_created} created, {resources_updated} updated")

    # 2. Resolve section rows to resources and persist them.
    # Build lookup indexes for the parent resolver
    by_resource_id    = {r.resource_id: r for r in AdvisoryResource.objects.all()}
    by_publication_id = {r.publication_id: r
                         for r in AdvisoryResource.objects.all()
                         if r.publication_id}

    sections_created = sections_updated = sections_skipped = 0
    try:
        with transaction.atomic():
            for sec in section_rows:
                ref = sec["pages_reference"]
                parent = by_resource_id.get(ref) or by_publication_id.get(ref)

                if parent is None:
                    norm = re.sub(r"[^A-Za-z0-9]", "", ref).upper()
                    for rid, r in by_resource_id.items():
                        if re.sub(r"[^A-Za-z0-9]", "", rid).upper() == norm:
                            parent = r
                            break

                if parent is None:
                    sections_skipped += 1
                    log(f"SKIP: no parent for Pages='{ref}'")
                    continue

                content_id = f"{parent.resource_id}-S{sec['reading_order']:04d}"
                _, created = ContentSection.objects.update_or_create(
                    content_id=content_id,
                    defaults={
                        "resource":         parent,
                        "reading_order":    sec["reading_order"],
                        "content_header":   sec["content_header"],
                        "content_text":     sec["content_text"],
                        "pages_reference":  sec["pages_reference"],
                        "value_chain":      sec["value_chain"],
                        "content_warnings": sec["content_warnings"],
                        "content_tags":     sec["content_tags"],
                    },
                )
                if created:
                    sections_created += 1
                else:
                    sections_updated += 1
    except Exception as e:
        upload.status = upload.Status.FAILED
        upload.log = "\n".join(log_lines + [f"ERROR on ContentSection: {e}"])
        upload.save(update_fields=["status", "log"])
        logger.exception("ContentSection ingest failed")
        return

    log(f"ContentSection: {sections_created} created, {sections_updated} updated, "
        f"{sections_skipped} skipped")

    # 3. Persist summary
    upload.resources_created = resources_created
    upload.resources_updated = resources_updated
    upload.sections_created  = sections_created
    upload.sections_updated  = sections_updated
    upload.sections_skipped  = sections_skipped
    upload.status = upload.Status.PROCESSED
    upload.log = "\n".join(log_lines)
    upload.save(update_fields=[
        "resources_created", "resources_updated",
        "sections_created", "sections_updated", "sections_skipped",
        "status", "log",
    ])
    log("Done.") 

def sync_resource_to_ai_layer(resource: AdvisoryResource) -> bool:
    """
    POST a single resource (spec-shaped JSON) to the AI Layer's ingest
    endpoint. Updates the resource's vector_sync_status accordingly.

    Returns True if the section-text payload was accepted by the AI Layer
    (regardless of whether the optional uploaded-file indexing also
    succeeded). Returns False if the section-text sync failed, or if the
    feature flag is off, or if the resource is not certified.

    Never raises -- ingestion failures must not block content screening
    in Django.
    """
    if not settings.AI_LAYER_SYNC_ENABLED:
        return False

    if not resource.is_ready_for_ai_layer:
        logger.info(
            "Skipping AI Layer sync for %s: quality_flag=%s (must be ready_to_certify)",
            resource.resource_id,
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

    except Exception as exc:  
        resource.vector_sync_status = VectorSyncStatusChoices.FAILED
        resource.vector_sync_error = str(exc)
        resource.save(update_fields=["vector_sync_status", "vector_sync_error"])
        logger.warning(
            "Failed to sync sections of %s to AI Layer: %s",
            resource.resource_id,
            exc,
        )
        return False

    resource.vector_sync_status = VectorSyncStatusChoices.SYNCED
    resource.vector_synced_at = timezone.now()
    resource.vector_sync_error = ""
    resource.save(
        update_fields=["vector_sync_status", "vector_synced_at", "vector_sync_error"]
    )
    logger.info("Synced %s to AI Layer (%s)", resource.resource_id, url)

    if resource.upload_file:
        _sync_resource_file_to_ai_layer(resource)

    return True


def _sync_resource_file_to_ai_layer(resource: AdvisoryResource) -> bool:
    """
    Push ``resource.upload_file`` to the AI Layer's document-ingest endpoint.

    On success: clears any prior file-sync error and returns True.
    On failure: records the error in ``vector_sync_error`` and returns False.
                The caller's already-set SYNCED status is left alone.
    """
    try:
        filename = Path(resource.upload_file.name).name
        url = f"{settings.AI_LAYER_BASE_URL}{settings.AI_LAYER_DOCUMENT_INGEST_PATH}"

        headers = {}
        if settings.AI_LAYER_INGEST_API_KEY:
            headers["X-API-Key"] = settings.AI_LAYER_INGEST_API_KEY

        with resource.upload_file.open("rb") as file_handle:
            response = httpx.post(
                url,
                data={
                    "document_id": f"advisory-{resource.resource_id}",
                    "name": resource.title,
                },
                files={"file": (filename, file_handle, "application/octet-stream")},
                headers=headers,
                timeout=settings.AI_LAYER_DOCUMENT_TIMEOUT_SECONDS,
            )
        response.raise_for_status()

        result = response.json()
        if result.get("status") != "verified" or result.get("chunks_indexed", 0) < 1:
            raise ValueError("AI Layer returned an invalid advisory file ingestion response.")

        # Success: clear any file-side error we may have recorded previously.
        if resource.vector_sync_error:
            resource.vector_sync_error = ""
            resource.save(update_fields=["vector_sync_error"])
        return True

    except Exception as exc:  # noqa: BLE001 - best-effort, surfaced via vector_sync_error
        resource.vector_sync_error = (
            f"Advisory file indexing failed: {type(exc).__name__}: {exc}"
        )
        resource.save(update_fields=["vector_sync_error"])
        logger.warning(
            "Failed to index uploaded advisory file for %s (%s)",
            resource.resource_id,
            type(exc).__name__,
        )
        return False


def sync_many(resources) -> dict:
    """
    Bulk entry point used by the admin action.

    Returns a dict of counts. Only ``resource.is_ready_for_ai_layer`` rows
    are attempted; everything else is counted as ``skipped``.
    """
    results = {"synced": 0, "skipped": 0, "failed": 0}

    if not settings.AI_LAYER_SYNC_ENABLED:
        # Feature flag off: report everything as skipped rather than failed,
        # otherwise the admin message is misleading.
        for _ in resources:
            results["skipped"] += 1
        return results

    for resource in resources:
        if not resource.is_ready_for_ai_layer:
            results["skipped"] += 1
            continue
        ok = sync_resource_to_ai_layer(resource)
        results["synced" if ok else "failed"] += 1

    return results
