"""
Multi-tenant / multi-service extension of the KilimoSTACK Provider Platform.

This app is deliberately separate from ``advisory`` and does not modify it.
``advisory.AdvisoryResource`` remains the specialized model for advisory
knowledge content (documents, section-level chunks, RAG-ready); this app
adds:

  * ``Provider`` -- a real, first-class institution/tenant on the network
    (KALRO, a partner university, an FPO, a financial institution, an
    equipment-rental business, ...), replacing the old single hardcoded
    PROVIDER_ID/PROVIDER_INSTITUTION_NAME settings with actual rows.
  * ``ProviderMembership`` -- which users can screen/manage which provider's
    listings. This is what makes multi-tenancy real rather than cosmetic.
  * ``ServiceCategory`` -- a taxonomy stored as data (DB rows), not a Python
    enum, so a new category (e.g. "insurance_services") can be added by an
    admin without a code deploy.
  * ``CatalogItem`` -- a single flexible model covering every NON-advisory
    service type (market prices, equipment rental, farmer registries,
    credit services, input supply, aggregation, FPO services, ...). Shared
    fields (price, location, availability, fulfillment) live as real
    columns; whatever is specific to a given category lives in the
    ``attributes`` JSONField by convention, documented per-category on
    ``ServiceCategory.schema_hint``.

The same Screen & Classify vocabulary already built for AdvisoryResource
(currency status, validation status, risk level, quality flag) is reused
here via import, so every provider -- whatever they sell -- goes through
the same certification workflow before appearing on the network.
"""

from django.conf import settings
from django.db import models

from advisory.models import (
    CurrencyStatusChoices,
    QualityFlagChoices,
    RiskLevelChoices,
    ValidationStatusChoices,
)


class InstitutionType(models.TextChoices):
    RESEARCH_INSTITUTION = "research_institution", "Research Institution"
    UNIVERSITY = "university", "University"
    NGO = "ngo", "NGO"
    COOPERATIVE_FPO = "cooperative_fpo", "Cooperative / FPO"
    FINANCIAL_INSTITUTION = "financial_institution", "Financial Institution"
    EQUIPMENT_SERVICE = "equipment_service", "Equipment / Mechanization Service"
    INPUT_SUPPLIER = "input_supplier", "Agro-Input Supplier"
    MARKET_DATA_PROVIDER = "market_data_provider", "Market Data Provider"
    AGGREGATOR = "aggregator", "Aggregator / Off-taker"
    GOVERNMENT_AGENCY = "government_agency", "Government Agency"
    OTHER = "other", "Other"


class Provider(models.Model):
    """One row per institution registered on the KilimoSTACK / OAN network."""

    provider_id = models.SlugField(max_length=100, unique=True, help_text="Network identity, e.g. 'kalro.kilimostack'")
    name = models.CharField(max_length=200)
    institution_type = models.CharField(max_length=30, choices=InstitutionType.choices, default=InstitutionType.OTHER)
    contact_email = models.EmailField(blank=True, default="")
    contact_phone = models.CharField(max_length=40, blank=True, default="")
    website = models.URLField(blank=True, default="")
    description = models.TextField(blank=True, default="")
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return f"{self.name} ({self.provider_id})"


class ProviderRole(models.TextChoices):
    REVIEWER = "reviewer", "Reviewer"
    ADMIN = "admin", "Admin"


class ProviderMembership(models.Model):
    """Which users may screen/manage a given provider's catalog. This is the
    multi-tenancy enforcement point -- see providers/permissions.py."""

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="provider_memberships")
    provider = models.ForeignKey(Provider, on_delete=models.CASCADE, related_name="memberships")
    role = models.CharField(max_length=10, choices=ProviderRole.choices, default=ProviderRole.REVIEWER)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = [("user", "provider")]

    def __str__(self):
        return f"{self.user} @ {self.provider} ({self.role})"


class ServiceCategory(models.Model):
    """
    A service type a provider can offer, e.g. 'market_prices',
    'equipment_rental', 'credit_services'. Stored as data so partners can
    add new categories without a code change. ``schema_hint`` documents the
    recommended (not enforced) shape of CatalogItem.attributes for this
    category, e.g.:

        {"commodity": "str", "market": "str", "price": "number", "unit": "str", "date": "YYYY-MM-DD"}
    """

    code = models.SlugField(max_length=60, unique=True)
    label = models.CharField(max_length=120)
    description = models.TextField(blank=True, default="")
    schema_hint = models.JSONField(default=dict, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["label"]
        verbose_name_plural = "Service categories"

    def __str__(self):
        return self.label


class CatalogItem(models.Model):
    """
    One row = one listing offered by a provider under a service category --
    a tractor rental, a market price quote, a credit product, a farmer
    registry, an input supply offer, etc. Category-specific detail lives in
    ``attributes``; everything else is shared, queryable structure.
    """

    provider = models.ForeignKey(Provider, on_delete=models.CASCADE, related_name="catalog_items")
    category = models.ForeignKey(ServiceCategory, on_delete=models.PROTECT, related_name="catalog_items")

    title = models.CharField(max_length=300)
    short_description = models.TextField(blank=True, default="")

    price = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    price_unit = models.CharField(max_length=60, blank=True, default="", help_text="e.g. 'per hour', 'per 90kg bag', 'per acre'")

    location = models.JSONField(default=dict, blank=True, help_text='{"country", "counties": [...], "agro_ecological_zones": [...]}')
    availability = models.JSONField(default=dict, blank=True, help_text="Hours/days/seasonal windows this listing is offered")
    fulfillment = models.JSONField(default=dict, blank=True, help_text="How to book/order: phone, method, delivery terms")
    attributes = models.JSONField(default=dict, blank=True, help_text="Category-specific fields -- see ServiceCategory.schema_hint")

    # Same Screen & Classify vocabulary as AdvisoryResource, reused so every
    # category goes through one consistent certification workflow.
    currency_status = models.CharField(max_length=25, choices=CurrencyStatusChoices.choices, blank=True, default="")
    validation_status = models.CharField(max_length=30, choices=ValidationStatusChoices.choices, blank=True, default="")
    risk_level = models.CharField(max_length=10, choices=RiskLevelChoices.choices, blank=True, default="")
    quality_flag = models.CharField(max_length=25, choices=QualityFlagChoices.choices, blank=True, default="")
    screening_notes = models.TextField(blank=True, default="")
    screened_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    screened_at = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-updated_at"]
        indexes = [
            models.Index(fields=["provider", "category"]),
            models.Index(fields=["quality_flag"]),
        ]

    def __str__(self):
        return f"{self.title} ({self.provider.provider_id} / {self.category.code})"

    @property
    def is_certified(self) -> bool:
        return self.quality_flag == QualityFlagChoices.READY_TO_CERTIFY
