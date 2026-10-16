"""
Sync certified AdvisoryResource records to the FastAPI + Ollama AI Layer,
which chunks, embeds and stores them in the vector database used by the
RAG + LLM service.

Design
------
* Best-effort, synchronous HTTP so the project runs without a message
  broker. For production, wrap ``sync_resource_to_ai_layer`` in a Celery
  task (see README "Production Hardening Notes").
* Never raises by default -- ingestion failures must not block content
  screening in Django. ``raise_on_error=True`` is available for tests.
* Payload is spec-shaped JSON (``AdvisoryResourceSerializer``), including
  the nested ``content`` array and ``advisory_safety_out`` object.
* Chunks that are quarantined or flagged (see
  ``ContentSection.is_ready_for_embedding``) are filtered out of the
  payload before it leaves Django, and reported in the result.
* Retries transient errors (timeouts, connection errors, 5xx) with
  exponential backoff. 4xx responses fail fast.
* Skips the HTTP call entirely when ``content_hash`` matches the last
  successful sync, so repeated admin actions are cheap.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Iterable

import httpx
from django.conf import settings
from django.db import transaction
from django.utils import timezone

from .models import (
    AdvisoryResource,
    ContentSection,
    QualityFlagChoices,
    VectorSyncStatusChoices,
)
from .serializers import AdvisoryResourceSerializer

logger = logging.getLogger(__name__)


# ===========================================================================
# Result container
# ===========================================================================
@dataclass
class SyncResult:
    """Outcome of syncing a single resource."""

    publication_id: str
    status: str  # "synced" | "skipped" | "failed" | "not_modified"
    reason: str = ""
    chunks_sent: int = 0
    chunks_skipped: int = 0
    attempts: int = 0

    @property
    def ok(self) -> bool:
        return self.status in ("synced", "not_modified")


@dataclass
class BatchSyncResult:
    results: list[SyncResult] = field(default_factory=list)

    @property
    def synced(self) -> int:
        return sum(1 for r in self.results if r.status == "synced")

    @property
    def not_modified(self) -> int:
        return sum(1 for r in self.results if r.status == "not_modified")

    @property
    def skipped(self) -> int:
        return sum(1 for r in self.results if r.status == "skipped")

    @property
    def failed(self) -> int:
        return sum(1 for r in self.results if r.status == "failed")

    def summary(self) -> dict:
        return {
            "synced": self.synced,
            "not_modified": self.not_modified,
            "skipped": self.skipped,
            "failed": self.failed,
            "total": len(self.results),
        }


# ===========================================================================
# Settings helpers
# ===========================================================================
def _cfg(name: str, default):
    return getattr(settings, name, default)


def _resource_reference(resource: AdvisoryResource) -> str:
    return (
        resource.workbook_source_reference
        or resource.workbook_resource_id
        or str(resource.pk)
    )


def _sync_enabled() -> bool:
    return bool(_cfg("AI_LAYER_SYNC_ENABLED", False))


def _base_url() -> str:
    return _cfg("AI_LAYER_BASE_URL", "").rstrip("/")


def _ingest_path() -> str:
    return _cfg("AI_LAYER_INGEST_PATH", "/ingest")


def _timeout() -> float:
    return float(_cfg("AI_LAYER_SYNC_TIMEOUT_SECONDS", 30))


def _retries() -> int:
    return int(_cfg("AI_LAYER_SYNC_MAX_RETRIES", 3))


def _backoff() -> float:
    return float(_cfg("AI_LAYER_SYNC_BACKOFF_SECONDS", 1.0))


def _batch_size() -> int:
    return int(_cfg("AI_LAYER_SYNC_BATCH_SIZE", 25))


def _endpoint() -> str:
    return f"{_base_url()}{_ingest_path()}"


# ===========================================================================
# Payload construction
# ===========================================================================
def _sections_for_payload(resource: AdvisoryResource) -> tuple[list, int]:
    """
    Return (eligible_sections, skipped_count).

    A section is eligible for embedding when ``is_ready_for_embedding`` is
    True (validated, not quarantined, no governance flag). Sections that
    fail this check are excluded from the payload so the AI Layer never
    embeds content a KALRO scientist has flagged.
    """
    eligible = []
    skipped = 0
    for section in resource.content_sections.all():
        if section.is_ready_for_embedding:
            eligible.append(section)
        else:
            skipped += 1
    return eligible, skipped


def _build_payload(resource: AdvisoryResource) -> tuple[dict, int]:
    """
    Build the spec-shaped JSON payload for one resource and return it along
    with the number of sections that were excluded.
    """
    payload = AdvisoryResourceSerializer(resource).data
    # The AI Layer consumes the import-spec fields. Workbook imports use
    # workbook IDs and M2M value chains, while the current Django model no
    # longer has the old flat publication_id/value_chain fields.
    payload["publication_id"] = _resource_reference(resource)
    payload["value_chain"] = resource.value_chains.order_by("name").values_list("name", flat=True).first() or ""
    payload["commodity"] = payload.get("commodity") or []
    payload["institution"] = resource.institution.name if resource.institution_id else "Kenya Agricultural and Livestock Research Organization"
    for date_field in ("modified_date", "review_date", "next_review_date"):
        value = payload.get(date_field)
        payload[date_field] = value.isoformat() if hasattr(value, "isoformat") else (value or "")
    payload["advisory_safety"] = {
        "risk_level": resource.risk_level,
        "risk_domains": resource.risk_domains,
        "requires_human_review": resource.requires_human_review,
        "escalation_guidance": resource.escalation_guidance,
        "disclaimer": resource.safety_disclaimer,
    }
    # Narrow the nested `content` array to eligible sections only.
    eligible_sections, skipped = _sections_for_payload(resource)
    if skipped:
        # Re-serialize just the eligible sections for the outgoing payload.
        from .serializers import ContentSectionSerializer

        payload["content"] = ContentSectionSerializer(
            eligible_sections, many=True
        ).data
    return payload, skipped


# ===========================================================================
# HTTP post with retries
# ===========================================================================
def _post_with_retries(url: str, json_body, timeout: float) -> tuple[bool, str, int]:
    """
    POST with exponential backoff on transient errors.

    Returns (success, error_message, attempts).
    """
    max_attempts = max(1, _retries())
    backoff = _backoff()

    last_err = ""
    for attempt in range(1, max_attempts + 1):
        try:
            response = httpx.post(url, json=json_body, timeout=timeout)
            # 4xx (except 429) means the payload is wrong; fail fast.
            if 400 <= response.status_code < 500 and response.status_code != 429:
                return False, f"HTTP {response.status_code}: {response.text[:500]}", attempt
            response.raise_for_status()
            return True, "", attempt
        except (httpx.TimeoutException, httpx.TransportError, httpx.HTTPStatusError) as exc:
            last_err = f"{type(exc).__name__}: {exc}"
            if attempt < max_attempts:
                sleep_for = backoff * (2 ** (attempt - 1))
                logger.warning(
                    "AI Layer sync attempt %s/%s failed (%s); retrying in %.1fs",
                    attempt, max_attempts, last_err, sleep_for,
                )
                time.sleep(sleep_for)
            else:
                logger.error(
                    "AI Layer sync failed after %s attempts: %s", max_attempts, last_err
                )
        except Exception as exc:  # noqa: BLE001 - best-effort
            last_err = f"{type(exc).__name__}: {exc}"
            logger.exception("Unexpected error calling AI Layer")
            break
    return False, last_err, max_attempts


# ===========================================================================
# Persistence helpers
# ===========================================================================
def _mark_pending(resource: AdvisoryResource) -> None:
    resource.vector_sync_status = VectorSyncStatusChoices.PENDING
    resource.save(update_fields=["vector_sync_status", "updated_at"])


def _mark_synced(
    resource: AdvisoryResource,
    *,
    embedding_model: str = "",
    embedding_dimensions: int | None = None,
) -> None:
    resource.vector_sync_status = VectorSyncStatusChoices.SYNCED
    resource.vector_synced_at = timezone.now()
    resource.vector_sync_error = ""
    # Persist the hash that was actually accepted by the AI Layer so the
    # next call can short-circuit when nothing changed.
    resource.content_hash = _current_hash(resource)
    if embedding_model:
        resource.embedding_model = embedding_model
    if embedding_dimensions:
        resource.embedding_dimensions = embedding_dimensions
    resource.save(
        update_fields=[
            "vector_sync_status",
            "vector_synced_at",
            "vector_sync_error",
            "content_hash",
            "embedding_model",
            "embedding_dimensions",
            "updated_at",
        ]
    )


def _mark_failed(resource: AdvisoryResource, error: str) -> None:
    resource.vector_sync_status = VectorSyncStatusChoices.FAILED
    resource.vector_sync_error = error[:2000]
    resource.save(update_fields=["vector_sync_status", "vector_sync_error", "updated_at"])


def _current_hash(resource: AdvisoryResource) -> str:
    """
    Hash the currently eligible sections' content_hashes so we can skip
    re-syncing when nothing material changed.
    """
    import hashlib

    h = hashlib.sha256()
    for section in resource.content_sections.order_by("reading_order"):
        if section.is_ready_for_embedding:
            h.update(section.content_hash.encode("utf-8"))
    return h.hexdigest()


# ===========================================================================
# Public API
# ===========================================================================
def sync_resource_to_ai_layer(
    resource: AdvisoryResource,
    *,
    force: bool = False,
    raise_on_error: bool = False,
    allow_validated_workbook_content: bool = False,
) -> SyncResult:
    """
    POST a single resource (spec-shaped JSON) to the AI Layer's ingest
    endpoint and update ``vector_sync_*`` fields on success/failure.

    Parameters
    ----------
    resource
        The ``AdvisoryResource`` to sync.
    force
        When True, ignore the content-hash short-circuit and always POST.
    raise_on_error
        When True, re-raise the underlying exception instead of returning a
        failed ``SyncResult``. Intended for tests and admin actions.

    Returns
    -------
    SyncResult
        ``status`` is one of ``"synced"``, ``"not_modified"``, ``"skipped"``
        or ``"failed"``.
    """
    pub_id = _resource_reference(resource)

    if not _sync_enabled():
        logger.info("AI Layer sync disabled; skipping %s", pub_id)
        return SyncResult(publication_id=pub_id, status="skipped", reason="sync_disabled")

    eligible_sections, skipped_count = _sections_for_payload(resource)
    workbook_content_ready = (
        allow_validated_workbook_content
        and bool(resource.workbook_resource_id)
        and resource.quality_flag in ("", QualityFlagChoices.READY_TO_CERTIFY)
        and bool(eligible_sections)
    )
    if not resource.is_ready_for_ai_layer and not workbook_content_ready:
        logger.info(
            "Skipping AI Layer sync for %s: quality_flag=%s advisory_status=%s",
            pub_id, resource.quality_flag, resource.advisory_status,
        )
        return SyncResult(
            publication_id=pub_id,
            status="skipped",
            reason="not_ready_for_ai_layer",
        )

    if not eligible_sections:
        logger.info(
            "Skipping AI Layer sync for %s: no eligible sections to embed.", pub_id
        )
        return SyncResult(
            publication_id=pub_id,
            status="skipped",
            reason="no_eligible_sections",
            chunks_skipped=skipped_count,
        )

    current_hash = _current_hash(resource)
    if (
        not force
        and resource.vector_sync_status == VectorSyncStatusChoices.SYNCED
        and resource.content_hash == current_hash
        and resource.vector_synced_at is not None
    ):
        logger.debug("Skipping AI Layer sync for %s: unchanged since last sync", pub_id)
        return SyncResult(
            publication_id=pub_id,
            status="not_modified",
            chunks_sent=len(eligible_sections),
            chunks_skipped=skipped_count,
        )

    payload, _ = _build_payload(resource)

    _mark_pending(resource)
    url = _endpoint()

    try:
        timeout = (
            float(_cfg("AI_LAYER_WORKBOOK_SYNC_TIMEOUT_SECONDS", 300))
            if allow_validated_workbook_content else _timeout()
        )
        success, error, attempts = _post_with_retries(url, [payload], timeout)
    except Exception as exc:  # noqa: BLE001
        if raise_on_error:
            raise
        logger.exception("Unexpected error syncing %s", pub_id)
        _mark_failed(resource, str(exc))
        return SyncResult(
            publication_id=pub_id,
            status="failed",
            reason=str(exc),
            chunks_sent=len(eligible_sections),
            chunks_skipped=skipped_count,
        )

    if success:
        _mark_synced(resource)
        logger.info(
            "Synced %s to AI Layer (%s): %s chunk(s) sent, %s skipped",
            pub_id, url, len(eligible_sections), skipped_count,
        )
        return SyncResult(
            publication_id=pub_id,
            status="synced",
            chunks_sent=len(eligible_sections),
            chunks_skipped=skipped_count,
            attempts=attempts,
        )

    _mark_failed(resource, error)
    if raise_on_error:
        raise RuntimeError(f"AI Layer sync failed for {pub_id}: {error}")
    return SyncResult(
        publication_id=pub_id,
        status="failed",
        reason=error,
        chunks_sent=len(eligible_sections),
        chunks_skipped=skipped_count,
        attempts=attempts,
    )


def sync_batch(
    resources: Iterable[AdvisoryResource],
    *,
    force: bool = False,
    allow_validated_workbook_content: bool = False,
) -> BatchSyncResult:
    """
    Sync many resources. Batches the HTTP POST into groups of
    ``AI_LAYER_SYNC_BATCH_SIZE`` to reduce request overhead, and falls back
    to per-resource posts if the batch endpoint rejects the array.
    """
    batch = BatchSyncResult()
    resources = list(resources)

    # Filter to only resources that are ready and have something to sync.
    ready: list[AdvisoryResource] = []
    for resource in resources:
        if not _sync_enabled():
            batch.results.append(
                SyncResult(_resource_reference(resource), "skipped", reason="sync_disabled")
            )
            continue
        eligible, skipped = _sections_for_payload(resource)
        workbook_content_ready = (
            allow_validated_workbook_content
            and bool(resource.workbook_resource_id)
            and resource.quality_flag in ("", QualityFlagChoices.READY_TO_CERTIFY)
            and bool(eligible)
        )
        if not resource.is_ready_for_ai_layer and not workbook_content_ready:
            batch.results.append(
                SyncResult(_resource_reference(resource), "skipped", reason="not_ready_for_ai_layer")
            )
            continue
        if not eligible:
            batch.results.append(
                SyncResult(
                    _resource_reference(resource),
                    "skipped",
                    reason="no_eligible_sections",
                    chunks_skipped=skipped,
                )
            )
            continue
        ready.append(resource)

    # Process in chunks.
    size = max(1, _batch_size())
    for start in range(0, len(ready), size):
        chunk = ready[start : start + size]
        batch.results.extend(_sync_one_batch(
            chunk,
            force=force,
            allow_validated_workbook_content=allow_validated_workbook_content,
        ))

    return batch


def sync_validated_workbook_resources(resources: Iterable[AdvisoryResource]) -> BatchSyncResult:
    """Index validated, unflagged sections from workbook resources after import."""
    return sync_batch(resources, force=True, allow_validated_workbook_content=True)


def _sync_one_batch(
    resources: list[AdvisoryResource],
    *,
    force: bool,
    allow_validated_workbook_content: bool = False,
) -> list[SyncResult]:
    """Sync a single chunk of resources. Falls back to per-resource on error."""
    if not resources:
        return []

    # Build the combined payload, tracking which resource each entry came from.
    payloads: list[dict] = []
    meta: list[tuple[AdvisoryResource, int]] = []  # (resource, skipped_count)
    for resource in resources:
        payload, skipped = _build_payload(resource)
        payloads.append(payload)
        meta.append((resource, skipped))

    # Short-circuit resources whose content hasn't changed.
    to_send: list[tuple[AdvisoryResource, int, dict]] = []
    results: list[SyncResult] = []
    for (resource, skipped), payload in zip(meta, payloads):
        current_hash = _current_hash(resource)
        if (
            not force
            and resource.vector_sync_status == VectorSyncStatusChoices.SYNCED
            and resource.content_hash == current_hash
            and resource.vector_synced_at is not None
        ):
            results.append(
                SyncResult(
                    _resource_reference(resource),
                    "not_modified",
                    chunks_sent=len(payload.get("content", [])),
                    chunks_skipped=skipped,
                )
            )
        else:
            to_send.append((resource, skipped, payload))

    if not to_send:
        return results

    # Mark all pending in one transaction so admin filters stay coherent.
    with transaction.atomic():
        AdvisoryResource.objects.filter(
            pk__in=[r.pk for r, _, _ in to_send]
        ).update(
            vector_sync_status=VectorSyncStatusChoices.PENDING,
            updated_at=timezone.now(),
        )

    url = _endpoint()
    batch_payload = [payload for _, _, payload in to_send]

    try:
        timeout = (
            float(_cfg("AI_LAYER_WORKBOOK_SYNC_TIMEOUT_SECONDS", 300))
            if allow_validated_workbook_content else _timeout()
        )
        success, error, attempts = _post_with_retries(url, batch_payload, timeout)
    except Exception as exc:  # noqa: BLE001
        logger.exception("Unexpected error syncing batch of %s", len(to_send))
        for resource, skipped, _ in to_send:
            _mark_failed(resource, str(exc))
            results.append(
                SyncResult(_resource_reference(resource), "failed", reason=str(exc), chunks_skipped=skipped)
            )
        return results

    if success:
        for resource, skipped, payload in to_send:
            _mark_synced(resource)
            results.append(
                SyncResult(
                    _resource_reference(resource),
                    "synced",
                    chunks_sent=len(payload.get("content", [])),
                    chunks_skipped=skipped,
                    attempts=attempts,
                )
            )
        logger.info("Synced batch of %s resource(s) to AI Layer", len(to_send))
        return results

    # Batch failed -- retry each individually so one bad payload doesn't
    # poison the whole batch.
    logger.warning(
        "Batch sync failed (%s); retrying %s resource(s) individually",
        error, len(to_send),
    )
    for resource, skipped, _ in to_send:
        individual = sync_resource_to_ai_layer(
            resource,
            force=True,
            allow_validated_workbook_content=allow_validated_workbook_content,
        )
        if skipped and individual.chunks_skipped == 0:
            individual.chunks_skipped = skipped
        results.append(individual)
    return results


# ===========================================================================
# Convenience wrappers
# ===========================================================================
def schedule_sync(resource: AdvisoryResource, *, force: bool = False) -> None:
    """
    Schedule a sync to run after the current DB transaction commits.

    Safe to call from model saves or admin actions: if the surrounding
    transaction rolls back, no HTTP call is made.
    """
    transaction.on_commit(lambda: sync_resource_to_ai_layer(resource, force=force))


def sync_stale(queryset=None) -> BatchSyncResult:
    """
    Find certified resources whose stored ``content_hash`` no longer matches
    the live hash and sync them. Intended to be called from a periodic job
    (cron / Celery beat) as a self-healing pass.

    Pass a custom queryset to narrow the search (e.g. by sector or date).
    """
    qs = queryset or AdvisoryResource.objects.filter(
        is_deleted=False,
        quality_flag="ready_to_certify",
    ).prefetch_related("content_sections")

    stale: list[AdvisoryResource] = []
    for resource in qs:
        if _current_hash(resource) != resource.content_hash:
            stale.append(resource)
        elif resource.vector_sync_status == VectorSyncStatusChoices.FAILED:
            stale.append(resource)

    return sync_batch(stale, force=False)


def reset_sync_state(resource: AdvisoryResource) -> None:
    """Force the next sync to re-send everything for this resource."""
    resource.vector_sync_status = VectorSyncStatusChoices.NOT_SYNCED
    resource.vector_synced_at = None
    resource.vector_sync_error = ""
    resource.save(
        update_fields=[
            "vector_sync_status",
            "vector_synced_at",
            "vector_sync_error",
            "updated_at",
        ]
    )




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
