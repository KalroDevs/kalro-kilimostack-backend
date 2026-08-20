from django.contrib import admin
from django.utils import timezone

from import_export.admin import ImportExportModelAdmin
from import_export.formats.base_formats import CSV, XLSX

from .models import (
    CatalogItem,
    Provider,
    ProviderMembership,
    ServiceCategory,
)

from .resources import (
    CatalogItemResource,
    ProviderMembershipResource,
    ProviderResource,
    ServiceCategoryResource,
)


# =========================================================
# PROVIDER MEMBERSHIP INLINE
# =========================================================

class ProviderMembershipInline(admin.TabularInline):
    model = ProviderMembership
    extra = 1

    fields = (
        "user",
        "role",
    )

    autocomplete_fields = (
        "user",
    )


# =========================================================
# PROVIDER ADMIN
# =========================================================

@admin.register(Provider)
class ProviderAdmin(ImportExportModelAdmin):
    resource_classes = [
        ProviderResource,
    ]

    formats = [
        CSV,
        XLSX,
    ]

    list_display = (
        "name",
        "provider_id",
        "institution_type",
        "contact_email",
        "is_active",
        "catalog_item_count",
        "updated_at",
    )

    list_filter = (
        "institution_type",
        "is_active",
        "created_at",
        "updated_at",
    )

    search_fields = (
        "name",
        "provider_id",
        "contact_email",
        "contact_phone",
        "website",
    )

    readonly_fields = (
        "created_at",
        "updated_at",
        "catalog_item_count",
    )

    ordering = (
        "name",
    )

    inlines = [
        ProviderMembershipInline,
    ]

    fieldsets = (
        (
            "Provider Information",
            {
                "fields": (
                    "provider_id",
                    "name",
                    "institution_type",
                    "description",
                )
            },
        ),
        (
            "Contact Information",
            {
                "fields": (
                    "contact_email",
                    "contact_phone",
                    "website",
                )
            },
        ),
        (
            "Status",
            {
                "fields": (
                    "is_active",
                )
            },
        ),
        (
            "Statistics",
            {
                "fields": (
                    "catalog_item_count",
                )
            },
        ),
        (
            "Timestamps",
            {
                "fields": (
                    "created_at",
                    "updated_at",
                )
            },
        ),
    )

    @admin.display(
        description="Catalog items",
        ordering="catalog_items",
    )
    def catalog_item_count(self, obj):
        if not obj.pk:
            return 0

        return obj.catalog_items.count()


# =========================================================
# SERVICE CATEGORY ADMIN
# =========================================================

@admin.register(ServiceCategory)
class ServiceCategoryAdmin(ImportExportModelAdmin):
    resource_classes = [
        ServiceCategoryResource,
    ]

    formats = [
        CSV,
        XLSX,
    ]

    list_display = (
        "label",
        "code",
        "is_active",
        "catalog_item_count",
    )

    list_filter = (
        "is_active",
    )

    search_fields = (
        "label",
        "code",
        "description",
    )

    readonly_fields = (
        "catalog_item_count",
    )

    ordering = (
        "label",
    )

    fieldsets = (
        (
            "Category",
            {
                "fields": (
                    "code",
                    "label",
                    "description",
                    "is_active",
                )
            },
        ),
        (
            "Schema",
            {
                "fields": (
                    "schema_hint",
                ),
                "description": (
                    "Define the recommended JSON structure for "
                    "CatalogItem.attributes."
                ),
            },
        ),
        (
            "Statistics",
            {
                "fields": (
                    "catalog_item_count",
                )
            },
        ),
    )

    @admin.display(description="Catalog items")
    def catalog_item_count(self, obj):
        if not obj.pk:
            return 0

        return obj.catalog_items.count()


# =========================================================
# CATALOG ITEM ADMIN
# =========================================================

@admin.register(CatalogItem)
class CatalogItemAdmin(ImportExportModelAdmin):
    """
    Generic catalog listing administration.

    Supports:

    - CSV import/export
    - XLSX import/export
    - Screening
    - Classification
    - Certification workflow
    - Provider filtering
    - Service-category filtering
    """

    resource_classes = [
        CatalogItemResource,
    ]

    formats = [
        CSV,
        XLSX,
    ]

    list_display = (
        "title",
        "provider",
        "category",
        "price",
        "price_unit",
        "currency_status",
        "validation_status",
        "risk_level",
        "quality_flag",
        "updated_at",
    )

    list_filter = (
        "provider",
        "category",
        "currency_status",
        "validation_status",
        "risk_level",
        "quality_flag",
        "created_at",
        "updated_at",
    )

    search_fields = (
        "title",
        "short_description",
        "provider__name",
        "provider__provider_id",
        "category__label",
        "category__code",
        "screening_notes",
    )

    readonly_fields = (
        "created_at",
        "updated_at",
    )

    autocomplete_fields = (
        "provider",
        "category",
        "screened_by",
    )

    list_select_related = (
        "provider",
        "category",
        "screened_by",
    )

    date_hierarchy = "updated_at"

    ordering = (
        "-updated_at",
    )

    actions = [
        "mark_ready_to_certify",
    ]

    fieldsets = (
        (
            "Listing",
            {
                "fields": (
                    "provider",
                    "category",
                    "title",
                    "short_description",
                )
            },
        ),
        (
            "Commercial Terms",
            {
                "fields": (
                    "price",
                    "price_unit",
                    "availability",
                    "fulfillment",
                )
            },
        ),
        (
            "Location",
            {
                "fields": (
                    "location",
                )
            },
        ),
        (
            "Category-specific Attributes",
            {
                "fields": (
                    "attributes",
                ),
                "description": (
                    "Additional category-specific information. "
                    "Use the Service Category schema hint as guidance."
                ),
            },
        ),
        (
            "Screen & Classify",
            {
                "fields": (
                    "currency_status",
                    "validation_status",
                    "risk_level",
                    "quality_flag",
                    "screening_notes",
                    "screened_by",
                    "screened_at",
                )
            },
        ),
        (
            "Timestamps",
            {
                "fields": (
                    "created_at",
                    "updated_at",
                )
            },
        ),
    )

    @admin.action(
        description="Mark selected listings as Ready to Certify"
    )
    def mark_ready_to_certify(self, request, queryset):
        updated = queryset.update(
            quality_flag="ready_to_certify",
            screened_by=request.user,
            screened_at=timezone.now(),
        )

        self.message_user(
            request,
            (
                f"{updated} listing(s) successfully marked "
                "as Ready to Certify."
            ),
        )


# =========================================================
# PROVIDER MEMBERSHIP ADMIN
# =========================================================

@admin.register(ProviderMembership)
class ProviderMembershipAdmin(ImportExportModelAdmin):
    resource_classes = [
        ProviderMembershipResource,
    ]

    formats = [
        CSV,
        XLSX,
    ]

    list_display = (
        "user",
        "provider",
        "role",
        "created_at",
    )

    list_filter = (
        "role",
        "provider",
        "created_at",
    )

    search_fields = (
        "user__email",
        "user__username",
        "provider__name",
        "provider__provider_id",
    )

    autocomplete_fields = (
        "user",
        "provider",
    )

    list_select_related = (
        "user",
        "provider",
    )

    readonly_fields = (
        "created_at",
    )

    ordering = (
        "provider__name",
        "user__email",
    )

    fieldsets = (
        (
            "Membership",
            {
                "fields": (
                    "user",
                    "provider",
                    "role",
                )
            },
        ),
        (
            "System Information",
            {
                "fields": (
                    "created_at",
                )
            },
        ),
    )