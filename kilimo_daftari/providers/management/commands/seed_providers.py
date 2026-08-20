"""
Usage:

    python manage.py seed_providers

Idempotent. Creates:
  * a Provider row for KALRO, matching the existing PROVIDER_ID /
    PROVIDER_INSTITUTION_NAME settings (so the single-provider identity that
    already existed becomes a real, first-class row instead of only living
    in settings.py).
  * a starter set of ServiceCategory rows covering the categories discussed
    for network expansion: advisory content plus market prices, equipment
    rental, farmer registries, credit services, input supply, aggregation,
    and FPO services.
"""

from django.conf import settings
from django.core.management.base import BaseCommand

from providers.models import InstitutionType, Provider, ServiceCategory

STARTER_CATEGORIES = [
    {
        "code": "advisory_content",
        "label": "Advisory Content",
        "description": "Certified agronomic, livestock, and climate advisory knowledge (served via the advisory app, not CatalogItem).",
        "schema_hint": {},
    },
    {
        "code": "market_prices",
        "label": "Market Prices",
        "description": "Commodity price quotes by market and date.",
        "schema_hint": {"commodity": "str", "market": "str", "price": "number", "unit": "str", "date": "YYYY-MM-DD", "trend": "up|down|stable"},
    },
    {
        "code": "equipment_rental",
        "label": "Equipment / Mechanization Services",
        "description": "Tractor hire, ploughing, harvesting and other mechanization services.",
        "schema_hint": {"equipment_type": "str", "hourly_rate": "number", "coverage_counties": ["str"], "operator_included": "bool"},
    },
    {
        "code": "farmer_registry",
        "label": "Farmer Registry",
        "description": "Farmer/farm/crop registry datasets or lookup services.",
        "schema_hint": {"registry_type": "str", "coverage_area": "str", "api_endpoint": "url", "auth_method": "str"},
    },
    {
        "code": "credit_services",
        "label": "Credit & Financial Services",
        "description": "Loan products, input financing, and related financial services.",
        "schema_hint": {"loan_product": "str", "interest_rate_pct": "number", "max_amount": "number", "eligibility": "str"},
    },
    {
        "code": "agro_input_supply",
        "label": "Agro-Input Supply",
        "description": "Seed, fertilizer, and other input availability and pricing.",
        "schema_hint": {"input_type": "str", "brand": "str", "unit_price": "number", "unit": "str", "stock_status": "str"},
    },
    {
        "code": "aggregation_services",
        "label": "Aggregation Services",
        "description": "Produce aggregation, bulking, and off-take arrangements.",
        "schema_hint": {"commodity": "str", "minimum_volume": "number", "collection_point": "str", "payment_terms": "str"},
    },
    {
        "code": "fpo_services",
        "label": "FPO / Cooperative Services",
        "description": "Services an FPO or cooperative offers its members (bulking, training, shared equipment, etc.).",
        "schema_hint": {"service_type": "str", "member_only": "bool", "membership_fee": "number"},
    },
]


class Command(BaseCommand):
    help = "Seed the KALRO Provider row and a starter set of ServiceCategory rows"

    def handle(self, *args, **options):
        provider, created = Provider.objects.get_or_create(
            provider_id=settings.PROVIDER_ID,
            defaults={
                "name": settings.PROVIDER_INSTITUTION_NAME,
                "institution_type": InstitutionType.RESEARCH_INSTITUTION,
                "description": "National anchor institution and custodian of KilimoSTACK's validated advisory content.",
            },
        )
        self.stdout.write(self.style.SUCCESS(f"{'Created' if created else 'Already exists'}: {provider}"))

        for cat in STARTER_CATEGORIES:
            _, created = ServiceCategory.objects.get_or_create(code=cat["code"], defaults=cat)
            self.stdout.write(f"  {'+ created' if created else '= exists'}  {cat['code']}")

        self.stdout.write(self.style.SUCCESS("Done."))
