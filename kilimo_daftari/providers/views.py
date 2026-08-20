from django.utils import timezone
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import filters, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from .models import CatalogItem, Provider, ServiceCategory
from .permissions import IsProviderMemberOrReadOnly, IsStaffOrReadOnly, user_provider_ids
from .serializers import (
    CatalogItemScreeningSerializer,
    CatalogItemSerializer,
    ProviderSerializer,
    ServiceCategorySerializer,
)


class ProviderViewSet(viewsets.ModelViewSet):
    """
    The tenant registry. Creating/editing providers is centrally managed
    (staff only) -- this is deliberate: joining the network is an
    onboarding decision, not a self-service signup, matching the
    Root/Registrar governance model the platform sits under.
    """

    queryset = Provider.objects.all()
    serializer_class = ProviderSerializer
    permission_classes = [IsStaffOrReadOnly]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter]
    filterset_fields = ["institution_type", "is_active"]
    search_fields = ["name", "provider_id"]

    @action(detail=False, methods=["get"], url_path="mine")
    def mine(self, request):
        """Providers the current user can screen/manage."""
        ids = user_provider_ids(request.user)
        qs = self.get_queryset().filter(id__in=ids) if not request.user.is_staff else self.get_queryset()
        return Response(ProviderSerializer(qs, many=True).data)


class ServiceCategoryViewSet(viewsets.ModelViewSet):
    """The category taxonomy -- data, not code. Staff-managed for now."""

    queryset = ServiceCategory.objects.all()
    serializer_class = ServiceCategorySerializer
    permission_classes = [IsStaffOrReadOnly]
    filter_backends = [filters.SearchFilter]
    search_fields = ["code", "label"]


class CatalogItemViewSet(viewsets.ModelViewSet):
    """
    Listings across every non-advisory service category. Filter the same
    way the advisory ledger does:

        GET /api/v1/catalog-items/?provider=3&category=2
        GET /api/v1/catalog-items/?quality_flag=needs_review
    """

    queryset = CatalogItem.objects.select_related("provider", "category").all()
    serializer_class = CatalogItemSerializer
    permission_classes = [IsProviderMemberOrReadOnly]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ["provider", "category", "quality_flag", "currency_status", "risk_level", "validation_status"]
    search_fields = ["title", "short_description"]
    ordering_fields = ["updated_at", "price", "title"]

    @action(detail=True, methods=["patch"], url_path="screen")
    def screen(self, request, pk=None):
        item = self.get_object()
        self.check_object_permissions(request, item)
        serializer = CatalogItemScreeningSerializer(item, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save(
            screened_by=request.user if request.user.is_authenticated else None,
            screened_at=timezone.now(),
        )
        return Response(CatalogItemSerializer(item).data)
