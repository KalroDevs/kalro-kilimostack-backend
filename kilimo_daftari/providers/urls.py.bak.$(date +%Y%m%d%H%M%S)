from rest_framework.routers import DefaultRouter

from .views import CatalogItemViewSet, ProviderViewSet, ServiceCategoryViewSet

router = DefaultRouter()
router.register("providers", ProviderViewSet, basename="provider")
router.register("service-categories", ServiceCategoryViewSet, basename="service-category")
router.register("catalog-items", CatalogItemViewSet, basename="catalog-item")

urlpatterns = router.urls
