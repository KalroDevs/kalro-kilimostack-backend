from django.urls import path
from rest_framework.routers import DefaultRouter

from .views import AdvisoryResourceViewSet, IngestView

router = DefaultRouter()
router.register("resources", AdvisoryResourceViewSet, basename="resource")

urlpatterns = router.urls + [
    path("ingest/", IngestView.as_view({"post": "create"}), name="ingest"),
]
