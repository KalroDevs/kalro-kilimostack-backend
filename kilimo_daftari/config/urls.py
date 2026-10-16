from django.contrib import admin
from django.conf import settings
from django.conf.urls.static import static
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/", include("accounts.ask_urls")),
    path("api/v1/", include("accounts.ask_urls")),
    path("api/v1/auth/", include("accounts.urls")),
    path("api/v1/", include("advisory.urls")),
    path("api/v1/", include("providers.urls")),
    path("api/v1/", include("documents.urls")),
    path("beckn/", include("beckn_provider.urls")),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
