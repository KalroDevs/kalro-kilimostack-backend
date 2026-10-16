"""
URL routes for the KALRO Advisory Content Corpus API.

Mounted by the project at ``/api/v1/`` -- see root ``urls.py``. If you'd
rather have the app own the full prefix, keep ``api/v1/`` in the paths
below and include this module with an empty prefix at the project root.

Endpoint summary
----------------
Ingestion (spec-exact)
    POST   ingest/

AdvisoryResource
    GET    resources/                                         list (filters + search)
    POST   resources/                                         create
    GET    resources/<publication_id>/                        retrieve
    PUT    resources/<publication_id>/                        replace
    PATCH  resources/<publication_id>/                        partial update
    DELETE resources/<publication_id>/                        soft delete
    PATCH  resources/<publication_id>/screen/                 Screen & Classify
    POST   resources/<publication_id>/certify/                set certification outcome
    POST   resources/<publication_id>/sync-to-ai-layer/       push to AI Layer
    POST   resources/<publication_id>/reset-sync/             mark not-synced
    POST   resources/sync-ready/                              bulk-sync certified
    POST   resources/sync-stale/                              self-healing re-sync

ContentSection
    GET    sections/                                          list (filters + search)
    GET    sections/<content_id>/                             retrieve
    PATCH  sections/<content_id>/                             update content/classification
    POST   sections/<content_id>/review/                      scientist decision
    POST   sections/<content_id>/assign/                      assign scientist
    POST   sections/<content_id>/quarantine/                  toggle quarantine
    GET    sections/<content_id>/review-logs/                 audit trail for one section
    GET    sections/stats/                                    aggregate counts

Lookups
    /value-chains/  /thematic-areas/                          CRUD (lookup by slug)

Audit
    /review-logs/                                             read-only

Health
    /health/                                                  unauthenticated
"""

from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import (
    AdvisoryResourceViewSet,
    ContentSectionViewSet,
    HealthView,
    IngestView,
    SectionReviewLogViewSet,
    ThematicAreaViewSet,
    ValueChainViewSet,
)

app_name = "advisory"

router = DefaultRouter()

# --- AdvisoryResource -------------------------------------------------------
# lookup_field = "publication_id" is set on the viewset, so URLs use the
# publication ID (e.g. KALRO-MAIZE-001) rather than a numeric pk.
router.register("resources", AdvisoryResourceViewSet, basename="resource")

# --- ContentSection ---------------------------------------------------------
# lookup_field = "content_id".
router.register("sections", ContentSectionViewSet, basename="section")

# --- Lookup tables ----------------------------------------------------------
# lookup_field = "slug" on both.
router.register("value-chains", ValueChainViewSet, basename="value-chain")
router.register("thematic-areas", ThematicAreaViewSet, basename="thematic-area")

# --- Audit trail (read-only) ------------------------------------------------
router.register("review-logs", SectionReviewLogViewSet, basename="review-log")


urlpatterns = [
    # Router-generated CRUD + @action endpoints.
    path("", include(router.urls)),

    # Spec ingestion: ViewSet, so dispatch a single POST to `create`.
    path(
        "ingest/",
        IngestView.as_view({"post": "create"}),
        name="ingest",
    ),

    # Unauthenticated health check for load balancers / uptime probes.
    path("health/", HealthView.as_view(), name="health"),
]