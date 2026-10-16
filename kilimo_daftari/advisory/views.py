"""
DRF views for the KALRO Advisory Content Corpus.

Endpoints
---------
Ingestion (spec-exact)
  POST   /api/v1/ingest/

AdvisoryResource
  GET    /api/v1/resources/                             -> list (filters + search)
  POST   /api/v1/resources/                             -> create
  GET    /api/v1/resources/<slug>/                      -> retrieve
  PUT    /api/v1/resources/<slug>/                      -> replace
  PATCH  /api/v1/resources/<slug>/                      -> partial update
  DELETE /api/v1/resources/<slug>/                      -> soft delete
  PATCH  /api/v1/resources/<slug>/screen/               -> Screen & Classify
  POST   /api/v1/resources/<slug>/certify/              -> set certification outcome
  POST   /api/v1/resources/<slug>/sync-to-ai-layer/
  POST   /api/v1/resources/<slug>/reset-sync/
  POST   /api/v1/resources/sync-ready/
  POST   /api/v1/resources/sync-stale/

ContentSection
  GET    /api/v1/sections/
  GET    /api/v1/sections/<content_id>/
  PATCH  /api/v1/sections/<content_id>/
  POST   /api/v1/sections/<content_id>/review/
  POST   /api/v1/sections/<content_id>/assign/
  POST   /api/v1/sections/<content_id>/quarantine/
  GET    /api/v1/sections/<content_id>/review-logs/
  GET    /api/v1/sections/stats/

Lookups & audit
  /api/v1/value-chains/, /api/v1/thematic-areas/, /api/v1/review-logs/
"""

from __future__ import annotations

import logging

from django.contrib.auth import get_user_model
from django.db import transaction
from django.db.models import Count
from django.utils import timezone

from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import filters, mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import AllowAny, BasePermission, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import (
    AdvisoryResource,
    AdvisoryStatusChoices,
    ChunkReviewStageChoices,
    ContentSection,
    QualityFlagChoices,
    SectionReviewLog,
    ThematicArea,
    ValueChain,
    VectorSyncStatusChoices,
)
from .serializers import (
    AdvisoryResourceListSerializer,
    AdvisoryResourceSerializer,
    ContentSectionListSerializer,
    ContentSectionSerializer,
    ScreeningUpdateSerializer,
    SectionReviewDecisionSerializer,
    SectionReviewLogSerializer,
    ThematicAreaSerializer,
    ValueChainSerializer,
)
from .services import (
    reset_sync_state,
    sync_batch,
    sync_resource_to_ai_layer,
    sync_stale,
)


logger = logging.getLogger(__name__)
User = get_user_model()


# ===========================================================================
# Permissions
# ===========================================================================
class IsReviewerOrReadOnly(BasePermission):
    """
    Any authenticated user may read. Only staff or members of the
    ``KALRO Scientist`` group may write.
    """

    message = "You need reviewer privileges to modify advisory content."

    def has_permission(self, request, view):
        user = request.user
        if not (user and user.is_authenticated):
            return False
        if request.method in ("GET", "HEAD", "OPTIONS"):
            return True
        if user.is_staff:
            return True
        return user.groups.filter(name="KALRO Scientist").exists()


# ===========================================================================
# AdvisoryResource
# ===========================================================================
class AdvisoryResourceViewSet(viewsets.ModelViewSet):
    """
    CRUD + workflow actions for the KALRO advisory content corpus.

    Filtering supports the "sort by crop, topic and content type" workflow
    from the Screen & Classify workbook:

        GET /api/v1/resources/?sector=livestock&value_chains=camel
        GET /api/v1/resources/?quality_flag=needs_review
        GET /api/v1/resources/?risk_level=high
        GET /api/v1/resources/?search=calf
    """

    queryset = (
        AdvisoryResource.objects.select_related("institution")
        .prefetch_related("value_chains", "content_sections")
    )
    serializer_class = AdvisoryResourceSerializer
    permission_classes = [IsReviewerOrReadOnly]
    lookup_field = "slug"                     # <-- model identifier, not publication_id
    lookup_url_kwarg = "slug"
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]

    # Only concrete model fields here. M2M filtering on value_chains is
    # handled in get_queryset() via ?value_chain=<slug>.
    filterset_fields = [
        "sector",
        "content_type",
        "language",
        "validation_status",
        "advisory_status",
        "currency_status",
        "scientific_accuracy_check",
        "risk_level",
        "quality_flag",
        "vector_sync_status",
        "is_deleted",
    ]
    search_fields = [
        "title",
        "slug",
        "author",
        "advisory_domain",
        "institution__name",
        "value_chains__name",
    ]
    ordering_fields = ["updated_at", "publish_date", "title", "slug"]
    ordering = ["-updated_at"]

    def get_serializer_class(self):
        if self.action == "list":
            return AdvisoryResourceListSerializer
        return AdvisoryResourceSerializer

    def get_queryset(self):
        qs = super().get_queryset()
        # Hide soft-deleted rows unless explicitly requested.
        if self.request.query_params.get("include_deleted") != "true":
            qs = qs.filter(is_deleted=False)

        # M2M filter: ?value_chain=camel (slug or name, case-insensitive).
        if vc := self.request.query_params.get("value_chain"):
            qs = qs.filter(value_chains__slug=vc)

        return qs.distinct()

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        instance.soft_delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

    # -- Screen & Classify -------------------------------------------------
    @action(detail=True, methods=["patch"], url_path="screen")
    def screen(self, request, slug=None):
        """Update just the screening/classification columns."""
        resource = self.get_object()
        serializer = ScreeningUpdateSerializer(
            resource, data=request.data, partial=True
        )
        serializer.is_valid(raise_exception=True)
        serializer.save(
            screened_by=request.user,
            screened_at=timezone.now(),
        )
        resource.refresh_from_db()

        # Best-effort sync; never let a downstream outage fail the screening
        # write that already committed.
        if resource.quality_flag == QualityFlagChoices.READY_TO_CERTIFY:
            try:
                sync_resource_to_ai_layer(resource)
                resource.refresh_from_db()
            except Exception:  # noqa: BLE001
                logger.exception(
                    "Post-screening sync failed for resource %s", resource.slug
                )

        return Response(
            AdvisoryResourceSerializer(resource, context={"request": request}).data
        )

    # -- Certification -----------------------------------------------------
    @action(detail=True, methods=["post"], url_path="certify")
    def certify(self, request, slug=None):
        """
        Body: {"status": "validated" | "validated_minor_edits" |
                       "major_revision" | "not_validated"}
        Sets advisory_status + quality_flag together and stamps the auditor.
        """
        resource = self.get_object()
        target = request.data.get("status")
        allowed = {choice for choice, _ in AdvisoryStatusChoices.choices}
        if target not in allowed:
            raise ValidationError({"status": f"Must be one of {sorted(allowed)}"})

        update_fields = ["advisory_status", "quality_flag", "updated_at"]
        resource.advisory_status = target

        if target in (
            AdvisoryStatusChoices.VALIDATED,
            AdvisoryStatusChoices.VALIDATED_WITH_MINOR_EDITS,
        ):
            resource.quality_flag = QualityFlagChoices.READY_TO_CERTIFY
            resource.certified_by = request.user
            resource.certified_at = timezone.now()
            update_fields += ["certified_by", "certified_at"]
        elif target == AdvisoryStatusChoices.MAJOR_REVISION:
            resource.quality_flag = QualityFlagChoices.NEEDS_UPDATE
        else:
            resource.quality_flag = QualityFlagChoices.REJECT

        resource.save(update_fields=update_fields)
        return Response(
            AdvisoryResourceSerializer(resource, context={"request": request}).data
        )

    # -- AI Layer sync -----------------------------------------------------
    @action(detail=True, methods=["post"], url_path="sync-to-ai-layer")
    def sync_to_ai_layer(self, request, slug=None):
        """Manually (re)push this resource. ?force=true bypasses the hash check."""
        resource = self.get_object()
        force = request.query_params.get("force", "false").lower() == "true"
        result = sync_resource_to_ai_layer(resource, force=force)

        # The service owns the DB writes; pull the freshest state for output.
        resource.refresh_from_db()

        code = (
            status.HTTP_200_OK
            if result.ok
            else status.HTTP_409_CONFLICT
            if result.status == "skipped"
            else status.HTTP_502_BAD_GATEWAY
        )
        return Response(
            {
                "slug": resource.slug,
                "status": result.status,
                "reason": result.reason,
                "chunks_sent": result.chunks_sent,
                "chunks_skipped": result.chunks_skipped,
                "attempts": result.attempts,
                "vector_sync_status": resource.vector_sync_status,
                "vector_synced_at": resource.vector_synced_at,
                "vector_sync_error": resource.vector_sync_error,
            },
            status=code,
        )

    @action(detail=True, methods=["post"], url_path="reset-sync")
    def reset_sync(self, request, slug=None):
        resource = self.get_object()
        reset_sync_state(resource)
        resource.refresh_from_db()
        return Response(
            {
                "slug": resource.slug,
                "vector_sync_status": resource.vector_sync_status,
            }
        )

    @action(detail=False, methods=["post"], url_path="sync-ready")
    def sync_ready(self, request):
        """Bulk-sync every certified resource that isn't already synced."""
        pending = (
            self.get_queryset()
            .filter(
                quality_flag=QualityFlagChoices.READY_TO_CERTIFY,
                advisory_status__in=[
                    AdvisoryStatusChoices.VALIDATED,
                    AdvisoryStatusChoices.VALIDATED_WITH_MINOR_EDITS,
                ],
            )
            .exclude(vector_sync_status=VectorSyncStatusChoices.SYNCED)
        )
        batch = sync_batch(pending)
        return Response(
            {
                "summary": batch.summary(),
                "results": [r.__dict__ for r in batch.results],
            }
        )

    @action(detail=False, methods=["post"], url_path="sync-stale")
    def sync_stale_action(self, request):
        """Self-healing: re-sync certified resources whose content drifted."""
        batch = sync_stale()
        return Response(
            {
                "summary": batch.summary(),
                "results": [r.__dict__ for r in batch.results],
            }
        )


# ===========================================================================
# ContentSection
# ===========================================================================
class ContentSectionViewSet(
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.UpdateModelMixin,
    viewsets.GenericViewSet,
):
    """
    List / retrieve / update content sections.

    Sections are created and removed through the parent resource (nested
    inside ``AdvisoryResourceSerializer.content``), so this viewset has no
    create/destroy. The review workflow is exposed at ``.../review/`` so
    status, stage, quarantine, and the audit log always move together.
    """

    queryset = (
        ContentSection.objects.select_related(
            "resource", "assigned_scientist", "reviewed_by", "senior_reviewer"
        ).prefetch_related("value_chains", "thematic_areas")
    )
    serializer_class = ContentSectionSerializer
    permission_classes = [IsReviewerOrReadOnly]
    lookup_field = "content_id"
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = [
        "status",
        "review_stage",
        "review_decision",
        "governance_flag",
        "is_quarantined",
        "requires_senior_review",
        "resource__sector",
    ]
    search_fields = [
        "content_id",
        "content_header",
        "content_text",
        "resource__slug",
        "resource__title",
        "review_notes",
        "governance_notes",
    ]
    ordering_fields = ["updated_at", "reading_order", "confidence_score"]
    ordering = ["resource", "reading_order"]

    def get_serializer_class(self):
        if self.action == "list":
            return ContentSectionListSerializer
        if self.action == "review":
            return SectionReviewDecisionSerializer
        return ContentSectionSerializer

    def get_queryset(self):
        qs = super().get_queryset()
        p = self.request.query_params

        if v := p.get("value_chain"):
            qs = qs.filter(value_chains__slug=v)
        if v := p.get("thematic_area"):
            qs = qs.filter(thematic_areas__slug=v)
        if v := p.get("assigned_scientist"):
            qs = qs.filter(assigned_scientist__email=v)
        if p.get("unassigned") == "true":
            qs = qs.filter(assigned_scientist__isnull=True)
        if p.get("embedding_ready") == "true":
            qs = qs.filter(
                status__in=[
                    "validated",
                    "validated_minor_edits",
                ],
                governance_flag="",
                is_quarantined=False,
            )
        return qs.distinct()

    # -- Scientist review --------------------------------------------------
    @action(detail=True, methods=["post"], url_path="review")
    def review(self, request, content_id=None):
        """
        Record a scientist decision.

        Body:
            {
                "decision": "approve" | "approve_with_edits" |
                            "request_revision" | "reject" | "escalate",
                "notes": "...",
                "suggested_edits": "...",
                "confidence": 0-100
            }

        Delegates to ``ContentSection.apply_review`` so status, stage,
        quarantine, and the audit log are always updated atomically.
        """
        section = self.get_object()
        serializer = SectionReviewDecisionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            section.apply_review(
                scientist=request.user,
                **serializer.validated_data,
            )
        except ValueError as exc:
            raise ValidationError({"detail": str(exc)})

        section.refresh_from_db()
        return Response(
            ContentSectionSerializer(section, context={"request": request}).data
        )

    @action(detail=True, methods=["get"], url_path="review-logs")
    def review_logs(self, request, content_id=None):
        section = self.get_object()
        logs = section.review_logs.select_related("actor").all()
        return Response(SectionReviewLogSerializer(logs, many=True).data)

    @action(detail=True, methods=["post"], url_path="assign")
    def assign(self, request, content_id=None):
        """Body: {"email": "scientist@kalro.org"} — omit or null to unassign."""
        section = self.get_object()
        email = request.data.get("email")

        if email is None:
            section.assigned_scientist = None
        else:
            try:
                section.assigned_scientist = User.objects.get(email=email)
            except User.DoesNotExist:
                raise ValidationError({"email": "No user with that email."})

        # Move a freshly-ingested chunk into the scientist queue.
        if (
            section.assigned_scientist is not None
            and section.review_stage == ChunkReviewStageChoices.INGESTED
        ):
            section.review_stage = ChunkReviewStageChoices.SCIENTIST_REVIEW

        section.save(
            update_fields=["assigned_scientist", "review_stage", "updated_at"]
        )
        return Response(
            ContentSectionSerializer(section, context={"request": request}).data
        )

    @action(detail=True, methods=["post"], url_path="quarantine")
    def quarantine(self, request, content_id=None):
        """Body: {"quarantined": true|false}. Default true."""
        section = self.get_object()
        value = bool(request.data.get("quarantined", True))
        section.is_quarantined = value
        section.save(update_fields=["is_quarantined", "updated_at"])
        return Response(
            {
                "content_id": section.content_id,
                "is_quarantined": section.is_quarantined,
            }
        )

    @action(detail=False, methods=["get"], url_path="stats")
    def stats(self, request):
        """Aggregate counts by status, stage, and governance flag."""
        base = self.get_queryset()

        by_status = dict(
            base.values_list("status").annotate(n=Count("id")).values_list("status", "n")
        )
        by_stage = dict(
            base.values_list("review_stage")
            .annotate(n=Count("id"))
            .values_list("review_stage", "n")
        )
        by_flag = dict(
            base.values_list("governance_flag")
            .annotate(n=Count("id"))
            .values_list("governance_flag", "n")
        )

        return Response(
            {
                "total": base.count(),
                "by_status": by_status,
                "by_stage": by_stage,
                "by_governance_flag": by_flag,
                "quarantined": base.filter(is_quarantined=True).count(),
                "awaiting_scientist_review": base.filter(
                    review_stage=ChunkReviewStageChoices.SCIENTIST_REVIEW
                ).count(),
            }
        )


# ===========================================================================
# Lookup tables
# ===========================================================================
class ValueChainViewSet(viewsets.ModelViewSet):
    queryset = ValueChain.objects.all()
    serializer_class = ValueChainSerializer
    permission_classes = [IsReviewerOrReadOnly]
    lookup_field = "slug"
    filter_backends = [DjangoFilterBackend, filters.SearchFilter]
    filterset_fields = ["sector", "is_active"]
    search_fields = ["name", "slug", "description"]


class ThematicAreaViewSet(viewsets.ModelViewSet):
    queryset = ThematicArea.objects.all()
    serializer_class = ThematicAreaSerializer
    permission_classes = [IsReviewerOrReadOnly]
    lookup_field = "slug"
    filter_backends = [DjangoFilterBackend, filters.SearchFilter]
    filterset_fields = ["is_active"]
    search_fields = ["name", "slug", "description"]


# ===========================================================================
# Audit trail (read-only)
# ===========================================================================
class SectionReviewLogViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = SectionReviewLog.objects.select_related("section", "actor")
    serializer_class = SectionReviewLogSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ["decision", "new_status", "governance_flag"]
    search_fields = ["section__content_id", "notes", "actor__email"]
    ordering_fields = ["created_at", "confidence_score"]
    ordering = ["-created_at"]


# ===========================================================================
# Spec ingestion
# ===========================================================================
class IngestView(viewsets.ViewSet):
    """
    POST /api/v1/ingest/

    Accepts the JSON specification's array-of-resources payload exactly as
    documented (Advisory Content Import JSON Specification v0.1) and
    upserts each resource by ``slug``. This is the endpoint KALRO's content
    pipeline (or the ``import_advisory_json`` management command) submits
    to.

    Body may be a single object or an array. Per-row results are returned
    with a stable shape so callers can retry just the failures.

    NOTE: the JSON spec's ``publication_id`` is expected to arrive as the
    ``slug`` field. If a future spec version adds an explicit
    ``publication_id``, update ``_extract_identifier`` here and the
    corresponding lookup in ``AdvisoryResourceSerializer``.
    """

    permission_classes = [IsAuthenticated]

    # ---- helpers --------------------------------------------------------
    @staticmethod
    def _extract_identifier(item: dict) -> str | None:
        """The upsert key: prefer slug, fall back to title-based slugify."""
        slug = (item or {}).get("slug") or ""
        if slug:
            return slug.strip()
        title = (item or {}).get("title") or ""
        return title.strip() or None

    # ---- create ---------------------------------------------------------
    def create(self, request):
        payload = request.data
        if isinstance(payload, dict):
            payload = [payload]
        if not isinstance(payload, list):
            return Response(
                {"detail": "Expected a JSON array of resource objects."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        created: list[str] = []
        updated: list[str] = []
        errors: list[dict] = []

        for item in payload:
            item = item or {}
            identifier = self._extract_identifier(item)
            if not identifier:
                errors.append(
                    {
                        "slug": None,
                        "errors": {
                            "slug": ["Provide a 'slug' or a non-empty 'title'."]
                        },
                    }
                )
                continue

            # Lock the row so concurrent ingest calls can't lose updates.
            with transaction.atomic():
                instance = (
                    AdvisoryResource.objects.select_for_update()
                    .filter(slug=identifier)
                    .first()
                )
                serializer = AdvisoryResourceSerializer(
                    instance,
                    data=item,
                    partial=instance is not None,
                    context={"request": request},
                )
                if not serializer.is_valid():
                    errors.append(
                        {"slug": identifier, "errors": serializer.errors}
                    )
                    continue
                try:
                    obj = serializer.save()
                except Exception as exc:  # noqa: BLE001
                    logger.exception("Ingest failed for %s", identifier)
                    errors.append(
                        {
                            "slug": identifier,
                            "errors": {"non_field_errors": [str(exc)]},
                        }
                    )
                    continue

            (updated if instance else created).append(obj.slug)

        http_status = (
            status.HTTP_201_CREATED
            if created and not errors
            else status.HTTP_200_OK
            if not errors
            else status.HTTP_207_MULTI_STATUS
        )
        return Response(
            {"created": created, "updated": updated, "errors": errors},
            status=http_status,
        )


# ===========================================================================
# Health check
# ===========================================================================
class HealthView(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        return Response({"status": "ok", "time": timezone.now()})