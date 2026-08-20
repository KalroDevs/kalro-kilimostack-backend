from django.urls import path

from .views import CatalogItemView, CatalogView, NetworkCatalogView, NetworkProvidersView, ProviderProfileView

urlpatterns = [
    path("provider-profile/", ProviderProfileView.as_view(), name="provider-profile"),
    path("catalog/", CatalogView.as_view(), name="catalog"),
    path("catalog/<str:publication_id>/", CatalogItemView.as_view(), name="catalog-item"),
    path("network/providers/", NetworkProvidersView.as_view(), name="network-providers"),
    path("network/<str:provider_id>/catalog/", NetworkCatalogView.as_view(), name="network-catalog"),
]
