from django.utils import timezone
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import filters, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from .models import AdvisoryResource, ContentSection, QualityFlagChoices
from .serializers import (
    AdvisoryResourceSerializer,
    ContentSectionSerializer,
    ScreeningUpdateSerializer,
)
from .services import sync_many, sync_resource_to_ai_layer


class AdvisoryResourceViewSet(viewsets.ModelViewSet):
    """
    CRUD + workflow actions for the KALRO advisory content corpus.

    Filtering supports the same "sort by crop, topic and content type" the
    Screen & Classify workbook was built for, e.g.:

        GET /api/v1/resources/?sector=livestock&value_chain=camel
        GET /api/v1/resources/?quality_flag=needs_review
        GET /api/v1/resources/?risk_level=high
        GET /api/v1/resources/?search=calf
        GET /api/v1/resources/?resource_id=CROP-007
    """

    queryset = AdvisoryResource.objects.all().prefetch_related("content_sections")
    serializer_class = AdvisoryResourceSerializer
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = [
        # Excel column A -- the join key
        "resource_id",
        "sector",
        "value_chain",
        "content_type",
        "validation_status",
        "currency_status",
        "scientific_accuracy_check",
        "risk_level",
        "quality_flag",
        "vector_sync_status",
    ]
    search_fields = [
        "resource_id",
        "publication_id",
        "title",
        "value_chain",
        "advisory_domain",
        "commodity",
    ]
    ordering_fields = ["updated_at", "publish_date", "title", "resource_id"]

    @action(detail=True, methods=["patch"], url_path="screen")
    def screen(self, request, pk=None):
        """Screen & Classify workflow: update just the review columns."""
        resource = self.get_object()
        serializer = ScreeningUpdateSerializer(resource, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save(
            screened_by=request.user if request.user.is_authenticated else None,
            screened_at=timezone.now(),
        )
        # If screening just certified the item, best-effort sync to the AI Layer.
        if resource.quality_flag == QualityFlagChoices.READY_TO_CERTIFY:
            sync_resource_to_ai_layer(resource)
        return Response(AdvisoryResourceSerializer(resource).data)

    @action(detail=True, methods=["post"], url_path="sync-to-ai-layer")
    def sync_to_ai_layer(self, request, pk=None):
        """Manually (re)push this resource to the AI Layer's vector index."""
        resource = self.get_object()
        ok = sync_resource_to_ai_layer(resource)
        code = status.HTTP_200_OK if ok else status.HTTP_409_CONFLICT
        return Response(
            {
                "resource_id": resource.resource_id,
                "publication_id": resource.publication_id,   # kept for parity
                "vector_sync_status": resource.vector_sync_status,
                "vector_sync_error": resource.vector_sync_error,
            },
            status=code,
        )

    @action(detail=False, methods=["post"], url_path="sync-ready")
    def sync_ready(self, request):
        """Bulk-sync every 'ready_to_certify' resource that isn't already synced."""
        pending = self.get_queryset().filter(
            quality_flag=QualityFlagChoices.READY_TO_CERTIFY
        ).exclude(vector_sync_status="synced")
        results = sync_many(pending)
        return Response(results)


class ContentSectionViewSet(viewsets.ReadOnlyModelViewSet):
    """
    Read-only access to section-level chunks (the RAG granularity).

    Filtering:

        GET /api/v1/sections/?resource__resource_id=CROP-007
        GET /api/v1/sections/?value_chain=Potato
        GET /api/v1/sections/?search=blight
    """

    queryset = ContentSection.objects.select_related("resource").all()
    serializer_class = ContentSectionSerializer
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = [
        "value_chain",
        "pages_reference",
        "resource__resource_id",
        "resource__sector",
        "resource__quality_flag",
    ]
    search_fields = [
        "content_id",
        "content_header",
        "content_text",
        "resource__resource_id",
        "resource__publication_id",
        "resource__title",
    ]
    ordering_fields = ["reading_order", "content_id"]


class IngestView(viewsets.ViewSet):
    """
    POST /api/v1/ingest/

    Accepts the JSON specification's array-of-resources payload exactly as
    documented (Advisory Content Import JSON Specification v0.1) and
    upserts each resource by ``resource_id`` (Excel column A -- the
    inventory / join key referenced by ContentSection.pages_reference).
    This is the endpoint KALRO's content pipeline (or the
    ``import_advisory_json`` management command) submits to.

    ``publication_id`` (Excel column C) is stored verbatim but is NOT used
    as the identity for upsert -- it may be blank or duplicated across
    resources.
    """

    def create(self, request):
        payload = request.data
        if isinstance(payload, dict):
            payload = [payload]
        if not isinstance(payload, list):
            return Response(
                {"detail": "Expected a JSON array of resource objects."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        created, updated, errors = [], [], []

        for item in payload:
            resource_id = item.get("resource_id")
            if not resource_id:
                errors.append(
                    {
                        "resource_id": None,
                        "errors": {
                            "resource_id": ["This field is required (Excel column A)."]
                        },
                    }
                )
                continue

            instance = AdvisoryResource.objects.filter(resource_id=resource_id).first()
            serializer = AdvisoryResourceSerializer(
                instance, data=item, partial=instance is not None
            )
            if serializer.is_valid():
                obj = serializer.save()
                (updated if instance else created).append(obj.resource_id)
            else:
                errors.append({"resource_id": resource_id, "errors": serializer.errors})

        if errors:
            return Response(
                {"created": created, "updated": updated, "errors": errors},
                status=status.HTTP_207_MULTI_STATUS,
            )
        if updated and not created:
            return Response(
                {"created": created, "updated": updated, "errors": errors},
                status=status.HTTP_200_OK,
            )
        return Response(
            {"created": created, "updated": updated, "errors": errors},
            status=status.HTTP_201_CREATED,
        )