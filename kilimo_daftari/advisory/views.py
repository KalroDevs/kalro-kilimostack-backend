from django.utils import timezone
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import filters, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from .models import AdvisoryResource
from .serializers import AdvisoryResourceSerializer, ScreeningUpdateSerializer
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
    """

    queryset = AdvisoryResource.objects.all().prefetch_related("content_sections")
    serializer_class = AdvisoryResourceSerializer
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = [
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
    search_fields = ["title", "publication_id", "value_chain", "advisory_domain", "commodity"]
    ordering_fields = ["updated_at", "publish_date", "title"]

    @action(detail=True, methods=["patch"], url_path="screen")
    def screen(self, request, pk=None):
        """Screen & Classify workflow: update just the review columns."""
        resource = self.get_object()
        serializer = ScreeningUpdateSerializer(resource, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save(screened_by=request.user if request.user.is_authenticated else None,
                         screened_at=timezone.now())
        # If screening just certified the item, best-effort sync to the AI Layer.
        if resource.quality_flag == "ready_to_certify":
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
                "publication_id": resource.publication_id,
                "vector_sync_status": resource.vector_sync_status,
                "vector_sync_error": resource.vector_sync_error,
            },
            status=code,
        )

    @action(detail=False, methods=["post"], url_path="sync-ready")
    def sync_ready(self, request):
        """Bulk-sync every 'ready_to_certify' resource that isn't already synced."""
        pending = self.get_queryset().filter(quality_flag="ready_to_certify").exclude(
            vector_sync_status="synced"
        )
        results = sync_many(pending)
        return Response(results)


class IngestView(viewsets.ViewSet):
    """
    POST /api/v1/ingest/

    Accepts the JSON specification's array-of-resources payload exactly as
    documented (Advisory Content Import JSON Specification v0.1) and
    upserts each resource by ``publication_id``. This is the endpoint
    KALRO's content pipeline (or the ``import_advisory_json`` management
    command) submits to.
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
            publication_id = item.get("publication_id")
            instance = AdvisoryResource.objects.filter(publication_id=publication_id).first()
            serializer = AdvisoryResourceSerializer(instance, data=item, partial=instance is not None)
            if serializer.is_valid():
                obj = serializer.save()
                (updated if instance else created).append(obj.publication_id)
            else:
                errors.append({"publication_id": publication_id, "errors": serializer.errors})

        return Response(
            {"created": created, "updated": updated, "errors": errors},
            status=status.HTTP_207_MULTI_STATUS if errors else status.HTTP_201_CREATED,
        )
