"""
This app is the "Provider Platform" box in the KilimoSTACK / OpenAgriNet
Beckn architecture diagram:

    Provider Platform <-> Middleware <-> Beckn Adaptor - Provider <-> ... network

It does NOT implement the Beckn protocol itself (that is the job of the
standard Beckn Adaptor - Provider component, a separate piece of network
infrastructure this project integrates with, not reimplements). Instead it
exposes the plain, non-Beckn "provider platform" APIs that adaptor's
Client-Facing module calls to build its own Beckn ``on_search`` /
``on_select`` responses -- i.e. a certified catalog and item lookup.

Only resources KALRO has screened & certified (quality_flag =
ready_to_certify) are exposed here, so the network only ever discovers
content that has passed the Screen & Classify workflow.
"""

from django.conf import settings
from rest_framework.response import Response
from rest_framework.views import APIView

from advisory.models import AdvisoryResource
from advisory.serializers import AdvisoryResourceSerializer
from providers.models import CatalogItem, Provider


class ProviderProfileView(APIView):
    """GET /beckn/provider-profile/ -- static identity info for network registration."""

    def get(self, request):
        return Response(
            {
                "provider_id": settings.PROVIDER_ID,
                "institution": settings.PROVIDER_INSTITUTION_NAME,
                "role": "content-and-ai-provider",
                "domains": ["agriculture", "advisory-content", "ai-advisory"],
                "network": "KilimoSTACK / OpenAgriNet (OAN)",
                "catalog_endpoint": "/beckn/catalog/",
                "item_endpoint": "/beckn/catalog/{publication_id}/",
            }
        )


class CatalogView(APIView):
    """
    GET /beckn/catalog/?sector=&value_chain=

    Returns the certified subset of the advisory corpus, in a shape a Beckn
    Adaptor - Provider's client-facing module can map directly onto a
    catalog/items response (id, descriptor, tags, category = sector).
    """

    def get(self, request):
        qs = AdvisoryResource.objects.filter(quality_flag="ready_to_certify")
        sector = request.query_params.get("sector")
        value_chain = request.query_params.get("value_chain")
        if sector:
            qs = qs.filter(sector=sector)
        if value_chain:
            qs = qs.filter(value_chain=value_chain)

        items = [
            {
                "id": r.publication_id,
                "descriptor": {"name": r.title, "long_desc": r.preferred_citation},
                "category": r.sector,
                "tags": {
                    "value_chain": r.value_chain,
                    "advisory_domain": r.advisory_domain,
                    "risk_level": r.risk_level,
                },
                "url": r.link,
            }
            for r in qs
        ]
        return Response({"provider_id": settings.PROVIDER_ID, "items": items, "count": len(items)})


class CatalogItemView(APIView):
    """GET /beckn/catalog/{publication_id}/ -- full certified resource record."""

    def get(self, request, publication_id: str):
        try:
            resource = AdvisoryResource.objects.get(
                publication_id=publication_id, quality_flag="ready_to_certify"
            )
        except AdvisoryResource.DoesNotExist:
            return Response({"detail": "Not found or not yet certified."}, status=404)
        return Response(AdvisoryResourceSerializer(resource).data)


# ---------------------------------------------------------------------------
# Multi-provider network views (providers app)
#
# The views above (ProviderProfileView, CatalogView, CatalogItemView) are
# untouched and keep working exactly as before -- they are KALRO's own
# advisory-content catalog. The views below sit alongside them and expose
# the wider network: every registered Provider, and a merged catalog per
# provider that combines CatalogItem listings with, for the KALRO provider
# specifically, the existing certified AdvisoryResource corpus. This merge
# is done here in the view layer only -- AdvisoryResource itself has no
# knowledge of the providers app.
# ---------------------------------------------------------------------------


def _advisory_resource_as_catalog_entry(r: AdvisoryResource) -> dict:
    return {
        "id": r.publication_id,
        "category": "advisory_content",
        "descriptor": {"name": r.title, "long_desc": r.preferred_citation},
        "price": None,
        "tags": {"value_chain": r.value_chain, "advisory_domain": r.advisory_domain, "risk_level": r.risk_level},
        "url": r.link,
    }


def _catalog_item_as_catalog_entry(item: CatalogItem) -> dict:
    return {
        "id": str(item.id),
        "category": item.category.code,
        "descriptor": {"name": item.title, "long_desc": item.short_description},
        "price": str(item.price) if item.price is not None else None,
        "price_unit": item.price_unit,
        "tags": {"risk_level": item.risk_level, **item.attributes},
        "location": item.location,
        "fulfillment": item.fulfillment,
    }


class NetworkProvidersView(APIView):
    """
    GET /beckn/network/providers/

    Every active provider on the network, and which certified service
    categories each currently has listings for (KALRO always includes
    'advisory_content', reflecting the existing AdvisoryResource corpus).
    """

    def get(self, request):
        providers = []
        for p in Provider.objects.filter(is_active=True):
            categories = list(
                p.catalog_items.filter(quality_flag="ready_to_certify")
                .values_list("category__code", flat=True)
                .distinct()
            )
            if p.provider_id == settings.PROVIDER_ID:
                categories = ["advisory_content"] + categories
            providers.append(
                {
                    "provider_id": p.provider_id,
                    "name": p.name,
                    "institution_type": p.institution_type,
                    "categories": categories,
                    "catalog_endpoint": f"/beckn/network/{p.provider_id}/catalog/",
                }
            )
        return Response({"providers": providers, "count": len(providers)})


class NetworkCatalogView(APIView):
    """
    GET /beckn/network/{provider_id}/catalog/?category=

    Merged, certified catalog for one provider. For the KALRO provider
    (settings.PROVIDER_ID), this includes both the existing advisory
    corpus and any CatalogItem listings KALRO itself has registered;
    for every other provider, it's CatalogItem listings only.
    """

    def get(self, request, provider_id: str):
        try:
            provider = Provider.objects.get(provider_id=provider_id, is_active=True)
        except Provider.DoesNotExist:
            return Response({"detail": "Unknown or inactive provider."}, status=404)

        category_filter = request.query_params.get("category")
        entries = []

        if provider_id == settings.PROVIDER_ID and (not category_filter or category_filter == "advisory_content"):
            entries += [
                _advisory_resource_as_catalog_entry(r)
                for r in AdvisoryResource.objects.filter(quality_flag="ready_to_certify")
            ]

        items_qs = provider.catalog_items.filter(quality_flag="ready_to_certify").select_related("category")
        if category_filter:
            items_qs = items_qs.filter(category__code=category_filter)
        entries += [_catalog_item_as_catalog_entry(i) for i in items_qs]

        return Response({"provider_id": provider.provider_id, "items": entries, "count": len(entries)})
