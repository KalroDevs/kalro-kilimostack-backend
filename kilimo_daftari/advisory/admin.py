from django.contrib import admin
from django.utils import timezone

from import_export.admin import ImportExportModelAdmin
from import_export.formats.base_formats import CSV, XLSX

from .models import AdvisoryResource, ContentSection, WorkbookUpload
from .resources import AdvisoryResourceResource, ContentSectionResource
from .services import sync_many

from django.utils.html import format_html


class ContentSectionInline(admin.TabularInline):
    model = ContentSection
    extra = 0
    fields = ("reading_order", "content_header", "pages_reference",
              "value_chain", "content_warnings", "content_tags")
    show_change_link = True
    readonly_fields = ("reading_order", "content_header", "pages_reference",
                       "value_chain", "content_warnings", "content_tags")
    can_delete = False
    max_num = 0

@admin.register(AdvisoryResource)
class AdvisoryResourceAdmin(ImportExportModelAdmin):
    resource_classes = [AdvisoryResourceResource]
    formats = [CSV, XLSX]

    list_display = (
        "resource_id",
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
        "resource_id",
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

    autocomplete_fields = ("screened_by",)

    actions = [
        "mark_ready_to_certify",
        "sync_selected_to_ai_layer",
    ]

    date_hierarchy = "updated_at"
    ordering = ("-updated_at",)

    inlines = [ContentSectionInline]

    fieldsets = (
        (
            "Core Resource",
            {
                "fields": (
                    "resource_id",
                    "publication_id",
                    "title",
                    "link",
                    "upload_file",
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

    @admin.action(description="Mark selected resources as Ready to Certify")
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

    @admin.action(description="Sync selected Ready to Certify resources to AI Layer")
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

    resource_classes = [ContentSectionResource]
    formats = [CSV, XLSX]

    list_display = (
        "content_id",
        "resource",
        "reading_order",
        "content_header",
        "value_chain",
        "pages_reference",
        "has_warnings",
    )

    list_filter = ("value_chain", "resource__sector", "resource__value_chain", "resource__content_type", "resource__language",)

    search_fields = (
        "content_id",
        "content_header",
        "content_text",
        "resource__resource_id",
        "resource__publication_id",
        "resource__title",
        "pages_reference",
    )

    autocomplete_fields = ("resource",)

    list_select_related = ("resource",)

    ordering = ("resource", "reading_order")

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
            "Excel Cross-Reference",
            {
                "fields": (
                    "pages_reference",
                    "value_chain",
                ),
                "description": (
                    "Populated by the workbook importer. ``pages_reference`` "
                    "should match the parent resource's ``resource_id``."
                ),
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

@admin.register(WorkbookUpload)
class WorkbookUploadAdmin(admin.ModelAdmin):
    list_display = (
        "id", "file_link", "status", "uploaded_at",
        "resources_created", "resources_updated",
        "sections_created", "sections_updated", "sections_skipped",
    )
    list_filter = ("status", "uploaded_at")
    readonly_fields = (
        "status", "uploaded_at",
        "resources_created", "resources_updated",
        "sections_created", "sections_updated", "sections_skipped",
        "log", "summary_html",
    )
    fieldsets = (
        ("Upload", {
            "fields": ("file",),
            "description": (
                "Upload the Screen & Classify workbook (.xlsx). "
            ),
        }),
        ("Result", {
            "fields": ("status", "uploaded_at", "summary_html",
                       "resources_created", "resources_updated",
                       "sections_created", "sections_updated",
                       "sections_skipped", "log"),
        }),
    )

    def file_link(self, obj):
        if not obj.file:
            return "—"
        return format_html('<a href="{}" target="_blank">{}</a>',
                           obj.file.url, obj.file.name)
    file_link.short_description = "file"

    def summary_html(self, obj):
        return format_html(
            "<b>{} created</b>, {} updated (resources) &nbsp;|&nbsp; "
            "<b>{} created</b>, {} updated, {} skipped (sections)",
            obj.resources_created, obj.resources_updated,
            obj.sections_created, obj.sections_updated, obj.sections_skipped,
        )
    summary_html.short_description = "Summary"

    def has_change_permission(self, request, obj=None):
        # Upload rows are read-only after creation; you can delete + re-upload.
        if obj is not None:
            return False
        return super().has_change_permission(request, obj)