from django.contrib import admin
from django.utils import timezone

from import_export.admin import ImportExportModelAdmin
from import_export.formats.base_formats import CSV, XLSX

from .models import AdvisoryResource, ContentSection
from .resources import AdvisoryResourceResource, ContentSectionResource
from .services import sync_many


class ContentSectionInline(admin.StackedInline):
    model = ContentSection
    extra = 0

    fields = (
        "content_id",
        "reading_order",
        "content_header",
        "content_text",
        "page_start",
        "page_end",
        "content_warnings",
        "content_tags",
        "content_images",
        "content_tables",
    )

    ordering = (
        "reading_order",
    )


@admin.register(AdvisoryResource)
class AdvisoryResourceAdmin(ImportExportModelAdmin):
    """
    Advisory corpus administration.

    Supports:
    - CSV import/export
    - XLSX import/export
    - Screen & Classify workflow
    - Certification workflow
    - AI/vector synchronization
    """

    resource_classes = [
        AdvisoryResourceResource,
    ]

    formats = [
        CSV,
        XLSX,
    ]

    list_display = (
        "publication_id",
        "title",
        "sector",
        "value_chain",
        "content_type",
        "currency_status",
        "scientific_accuracy_check",
        "risk_level",
        "quality_flag",
        "vector_sync_status",
        "updated_at",
    )

    list_filter = (
        "sector",
        "value_chain",
        "content_type",
        "currency_status",
        "scientific_accuracy_check",
        "validation_status",
        "risk_level",
        "quality_flag",
        "vector_sync_status",
        "language",
        "requires_human_review",
    )

    search_fields = (
        "publication_id",
        "title",
        "value_chain",
        "link",
        "institution",
        "preferred_citation",
    )

    readonly_fields = (
        "vector_sync_status",
        "vector_synced_at",
        "vector_sync_error",
        "created_at",
        "updated_at",
    )

    autocomplete_fields = (
        "screened_by",
    )

    inlines = [
        ContentSectionInline,
    ]

    actions = [
        "mark_ready_to_certify",
        "sync_selected_to_ai_layer",
    ]

    date_hierarchy = "updated_at"

    ordering = (
        "-updated_at",
    )

    fieldsets = (
        (
            "Core Resource",
            {
                "fields": (
                    "title",
                    "link",
                    "publication_id",
                    "thumbnail",
                    "institution",
                    "author",
                    "publish_date",
                    "modified_date",
                    "content_type",
                    "language",
                    "available_languages",
                )
            },
        ),
        (
            "Classification",
            {
                "fields": (
                    "sector",
                    "value_chain",
                    "commodity",
                    "production_system",
                    "advisory_domain",
                    "target_users",
                )
            },
        ),
        (
            "Geography & Seasonality",
            {
                "fields": (
                    "geographic_applicability",
                    "seasonality",
                )
            },
        ),
        (
            "Licensing & Validation",
            {
                "fields": (
                    "license",
                    "validation_status",
                    "validated_by",
                    "review_date",
                    "next_review_date",
                    "preferred_citation",
                )
            },
        ),
        (
            "Advisory Safety",
            {
                "fields": (
                    "risk_level",
                    "risk_domains",
                    "requires_human_review",
                    "escalation_guidance",
                    "safety_disclaimer",
                )
            },
        ),
        (
            "Screen & Classify",
            {
                "fields": (
                    "currency_status",
                    "scientific_accuracy_check",
                    "quality_flag",
                    "screening_notes",
                    "screened_by",
                    "screened_at",
                )
            },
        ),
        (
            "AI Layer Sync",
            {
                "fields": (
                    "vector_sync_status",
                    "vector_synced_at",
                    "vector_sync_error",
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
        description="Mark selected resources as Ready to Certify"
    )
    def mark_ready_to_certify(self, request, queryset):
        updated = queryset.update(
            quality_flag="ready_to_certify",
            screened_by=request.user,
            screened_at=timezone.now(),
        )

        self.message_user(
            request,
            f"{updated} resource(s) marked Ready to Certify.",
        )

    @admin.action(
        description="Sync selected Ready to Certify resources to AI Layer"
    )
    def sync_selected_to_ai_layer(self, request, queryset):
        results = sync_many(queryset)

        self.message_user(
            request,
            (
                f"Synced: {results['synced']}, "
                f"skipped (not certified): {results['skipped']}, "
                f"failed: {results['failed']}."
            ),
        )


@admin.register(ContentSection)
class ContentSectionAdmin(ImportExportModelAdmin):
    """
    Section-level advisory content used by the RAG/vector layer.
    """

    resource_classes = [
        ContentSectionResource,
    ]

    formats = [
        CSV,
        XLSX,
    ]

    list_display = (
        "content_id",
        "resource",
        "reading_order",
        "content_header",
        "has_warnings",
    )

    list_filter = (
        "resource__sector",
        "resource__value_chain",
        "resource__content_type",
        "resource__language",
    )

    search_fields = (
        "content_id",
        "content_header",
        "content_text",
        "resource__publication_id",
        "resource__title",
    )

    autocomplete_fields = (
        "resource",
    )

    list_select_related = (
        "resource",
    )

    ordering = (
        "resource",
        "reading_order",
    )

    fieldsets = (
        (
            "Resource",
            {
                "fields": (
                    "resource",
                    "content_id",
                    "reading_order",
                )
            },
        ),
        (
            "Content",
            {
                "fields": (
                    "content_header",
                    "content_text",
                    "page_start",
                    "page_end",
                )
            },
        ),
        (
            "Metadata",
            {
                "fields": (
                    "content_tags",
                    "content_warnings",
                )
            },
        ),
        (
            "Images & Tables",
            {
                "fields": (
                    "content_images",
                    "content_tables",
                )
            },
        ),
    )