import json
from pathlib import Path

from django.contrib.auth.models import User
from django.test import TestCase
from rest_framework.test import APIClient

from advisory.serializers import AdvisoryResourceSerializer
from .models import CatalogItem, Provider, ProviderMembership, ServiceCategory

SAMPLE_JSON = Path(__file__).resolve().parent.parent.parent / "data" / "sample_camel_calf_resource.json"


class ProviderMultiTenancyTests(TestCase):
    """
    The core claim of this app: two different institutions (e.g. KALRO and
    a partner tractor-hire FPO) can each manage their own catalog, and
    neither can edit the other's listings.
    """

    def setUp(self):
        self.kalro = Provider.objects.create(provider_id="kalro.kilimostack", name="KALRO", institution_type="research_institution")
        self.tractor_fpo = Provider.objects.create(provider_id="mavuno.fpo", name="Mavuno FPO", institution_type="cooperative_fpo")
        self.equipment_category = ServiceCategory.objects.create(code="equipment_rental", label="Equipment Rental")
        self.market_category = ServiceCategory.objects.create(code="market_prices", label="Market Prices")

        self.kalro_user = User.objects.create_user("kalro_reviewer", password="x")
        ProviderMembership.objects.create(user=self.kalro_user, provider=self.kalro, role="reviewer")

        self.fpo_user = User.objects.create_user("fpo_reviewer", password="x")
        ProviderMembership.objects.create(user=self.fpo_user, provider=self.tractor_fpo, role="reviewer")

        self.tractor_item = CatalogItem.objects.create(
            provider=self.tractor_fpo,
            category=self.equipment_category,
            title="Tractor + Plough Hire, Nakuru",
            price=1500,
            price_unit="per hour",
            attributes={"equipment_type": "tractor + plough", "coverage_counties": ["Nakuru"]},
        )

    def test_fpo_user_can_edit_own_listing(self):
        client = APIClient()
        client.force_authenticate(self.fpo_user)
        resp = client.patch(f"/api/v1/catalog-items/{self.tractor_item.id}/screen/", {"quality_flag": "ready_to_certify"}, format="json")
        self.assertEqual(resp.status_code, 200, resp.content)
        self.tractor_item.refresh_from_db()
        self.assertEqual(self.tractor_item.quality_flag, "ready_to_certify")

    def test_kalro_user_cannot_edit_fpo_listing(self):
        client = APIClient()
        client.force_authenticate(self.kalro_user)
        resp = client.patch(f"/api/v1/catalog-items/{self.tractor_item.id}/screen/", {"quality_flag": "ready_to_certify"}, format="json")
        self.assertEqual(resp.status_code, 403)

    def test_anonymous_can_read_but_not_screen(self):
        client = APIClient()
        list_resp = client.get("/api/v1/catalog-items/")
        self.assertEqual(list_resp.status_code, 200)
        screen_resp = client.patch(f"/api/v1/catalog-items/{self.tractor_item.id}/screen/", {"quality_flag": "reject"}, format="json")
        self.assertEqual(screen_resp.status_code, 401)

    def test_flexible_attributes_differ_by_category_without_schema_change(self):
        """The whole point of `attributes`: wildly different shapes, same model, no migration."""
        market_item = CatalogItem.objects.create(
            provider=self.kalro,
            category=self.market_category,
            title="Maize price, Wakulima Market",
            price=4200,
            price_unit="per 90kg bag",
            attributes={"commodity": "maize", "market": "Wakulima Market, Nairobi", "date": "2026-08-15", "trend": "up"},
        )
        self.assertNotEqual(set(market_item.attributes.keys()), set(self.tractor_item.attributes.keys()))
        # Both persist and round-trip through the same serializer/model with no per-category table.
        self.assertEqual(CatalogItem.objects.filter(category__code="market_prices").count(), 1)
        self.assertEqual(CatalogItem.objects.filter(category__code="equipment_rental").count(), 1)


class NetworkCatalogMergeTests(TestCase):
    """
    Confirms the beckn_provider network endpoints merge AdvisoryResource
    (untouched, advisory app) with CatalogItem (new, providers app) into one
    per-provider catalog, without any FK between the two apps.
    """

    def setUp(self):
        from django.conf import settings

        self.kalro = Provider.objects.create(provider_id=settings.PROVIDER_ID, name=settings.PROVIDER_INSTITUTION_NAME)
        self.credit_category = ServiceCategory.objects.create(code="credit_services", label="Credit Services")

        data = json.loads(SAMPLE_JSON.read_text())[0]
        serializer = AdvisoryResourceSerializer(data=data)
        serializer.is_valid(raise_exception=True)
        self.advisory_resource = serializer.save()
        self.advisory_resource.quality_flag = "ready_to_certify"
        self.advisory_resource.save()

        self.credit_item = CatalogItem.objects.create(
            provider=self.kalro,
            category=self.credit_category,
            title="Input Advance Loan",
            quality_flag="ready_to_certify",
            attributes={"interest_rate_pct": 11.5},
        )

    def test_network_providers_lists_kalro_with_both_category_types(self):
        client = APIClient()
        resp = client.get("/beckn/network/providers/")
        self.assertEqual(resp.status_code, 200)
        kalro_entry = next(p for p in resp.data["providers"] if p["provider_id"] == self.kalro.provider_id)
        self.assertIn("advisory_content", kalro_entry["categories"])
        self.assertIn("credit_services", kalro_entry["categories"])

    def test_network_catalog_merges_advisory_and_catalog_items(self):
        client = APIClient()
        resp = client.get(f"/beckn/network/{self.kalro.provider_id}/catalog/")
        self.assertEqual(resp.status_code, 200)
        categories = {item["category"] for item in resp.data["items"]}
        self.assertIn("advisory_content", categories)
        self.assertIn("credit_services", categories)
        self.assertEqual(resp.data["count"], 2)

    def test_network_catalog_category_filter(self):
        client = APIClient()
        resp = client.get(f"/beckn/network/{self.kalro.provider_id}/catalog/?category=credit_services")
        self.assertEqual(resp.data["count"], 1)
        self.assertEqual(resp.data["items"][0]["category"], "credit_services")

    def test_advisory_resource_model_is_unmodified(self):
        """Guardrail for the 'AdvisoryResource untouched' constraint itself."""
        from advisory.models import AdvisoryResource

        field_names = {f.name for f in AdvisoryResource._meta.get_fields()}
        self.assertNotIn("provider", field_names)
        self.assertNotIn("catalogitem", field_names)
