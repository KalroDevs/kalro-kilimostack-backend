from django.contrib import admin
from django.urls import include, path
from advisory.views import AskView

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/v1/auth/", include("accounts.urls")),
    path("api/v1/ask/", AskView.as_view(), name="advisory-ask"),
    path("api/v1/advisory/", include("advisory.urls")),
    path("api/v1/providers/", include("providers.urls")),
    path("api/v1/documents/ingest/", include("documents.urls")),
    path("beckn/", include("beckn_provider.urls")),
]
