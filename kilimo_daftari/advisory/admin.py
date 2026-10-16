"""
Django admin configuration for the KALRO Advisory Content Corpus.

Place beside models.py in the same Django application.

Organised around two workflows:

1. Resource-level screening & certification (AdvisoryResource).
2. Per-chunk scientist validation & governance (ContentSection), with an
   immutable audit trail (SectionReviewLog).

Bulk actions on ContentSection route through ``ContentSection.apply_review``
so the chunk's status, review stage, quarantine flag, and audit log stay in
sync. Actions on AdvisoryResource use light-weight ``queryset.update`` since
they only touch resource-level fields.

Import/export is provided by ``django-import-export``:

* ``AdvisoryResource`` -- ImportExportModelAdmin (AdvisoryResourceResource)
* ``ContentSection``    -- ImportExportModelAdmin (ContentSectionResource)
* ``ValueChain``        -- ImportExportModelAdmin (ValueChainResource)
* ``ThematicArea``      -- ImportExportModelAdmin (ThematicAreaResource)
* ``SectionReviewLog``  -- ExportActionModelAdmin (SectionReviewLogResource)
"""

from django.contrib import admin, messages
from django.db.models import Count
from django.urls import reverse
from django.utils import timezone
from django.utils.html import format_html

from import_export.admin import ExportActionModelAdmin, ImportExportModelAdmin

from .models import (
    AdvisoryResource,
    AdvisoryStatusChoices,
    ChunkReviewStageChoices,
    ContentSection,
    GovernanceFlagChoices,
    QualityFlagChoices,
    ReviewDecisionChoices,
    SectionReviewLog,
    SectionStatusChoices,
    ThematicArea,
    ValueChain,
    VectorSyncStatusChoices,
    WorkbookUpload,
)
from .resources import (
    AdvisoryResourceResource,
    ContentSectionResource,
    SectionReviewLogResource,
    ThematicAreaResource,
    ValueChainResource,
)

from .services import sync_many
# ===========================================================================
# Display helpers
# ===========================================================================
def _badge(label: str, color: str) -> str:
    """Return a small colored pill for changelist columns."""
    return format_html(
        '<span style="display:inline-block;padding:2px 8px;border-radius:10px;'
        'background:{};color:#fff;font-size:11px;line-height:1.4;">{}</span>',
        color,
        label,
    )


ADVISORY_STATUS_COLORS = {
    AdvisoryStatusChoices.VALIDATED: "#1a7f37",
    AdvisoryStatusChoices.VALIDATED_WITH_MINOR_EDITS: "#9a6700",
    AdvisoryStatusChoices.MAJOR_REVISION: "#bf8700",
    AdvisoryStatusChoices.NOT_VALIDATED: "#cf222e",
}

SECTION_STATUS_COLORS = {
    SectionStatusChoices.VALIDATED: "#1a7f37",
    SectionStatusChoices.VALIDATED_WITH_MINOR_EDITS: "#9a6700",
    SectionStatusChoices.MAJOR_REVISION: "#bf8700",
    SectionStatusChoices.NOT_VALIDATED: "#cf222e",
}

QUALITY_FLAG_COLORS = {
    QualityFlagChoices.READY_TO_CERTIFY: "#1a7f37",
    QualityFlagChoices.NEEDS_REVIEW: "#9a6700",
    QualityFlagChoices.NEEDS_UPDATE: "#bf8700",
    QualityFlagChoices.DUPLICATE: "#57606a",
    QualityFlagChoices.REJECT: "#cf222e",
}


# ===========================================================================
# ValueChain
# ===========================================================================
@admin.register(ValueChain)
class ValueChainAdmin(ImportExportModelAdmin):
    resource_class = ValueChainResource
    list_display = (
        "name",
        "slug",
        "sector",
        "is_active",
        "resource_count",
        "section_count",
        "created_at",
    )
    list_filter = ("sector", "is_active")
    search_fields = ("name", "slug", "description")
    prepopulated_fields = {"slug": ("name",)}
    readonly_fields = ("created_at",)
    ordering = ("name",)

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.annotate(
            _resource_count=Count("resources", distinct=True),
            _section_count=Count("content_sections", distinct=True),
        )

    @admin.display(description="Resources", ordering="_resource_count")
    def resource_count(self, obj):
        return obj._resource_count

    @admin.display(description="Chunks", ordering="_section_count")
    def section_count(self, obj):
        return obj._section_count


# ===========================================================================
# ThematicArea
# ===========================================================================
@admin.register(ThematicArea)
class ThematicAreaAdmin(ImportExportModelAdmin):
    resource_class = ThematicAreaResource
    list_display = ("name", "slug", "is_active", "section_count", "created_at")
    list_filter = ("is_active",)
    search_fields = ("name", "slug", "description")
    prepopulated_fields = {"slug": ("name",)}
    readonly_fields = ("created_at",)
    ordering = ("name",)

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.annotate(_section_count=Count("content_sections", distinct=True))

    @admin.display(description="Chunks", ordering="_section_count")
    def section_count(self, obj):
        return obj._section_count


# ===========================================================================
# AdvisoryResource actions
# ===========================================================================
@admin.action(description="Certify: mark as Validated")
def certify_resources(modeladmin, request, queryset):
    count = queryset.update(
        advisory_status=AdvisoryStatusChoices.VALIDATED,
        quality_flag=QualityFlagChoices.READY_TO_CERTIFY,
        certified_by=request.user,
        certified_at=timezone.now(),
    )
    modeladmin.message_user(request, f"Certified {count} resource(s).", messages.SUCCESS)


@admin.action(description="Certify: Validated with minor edits")
def certify_with_edits(modeladmin, request, queryset):
    count = queryset.update(
        advisory_status=AdvisoryStatusChoices.VALIDATED_WITH_MINOR_EDITS,
        quality_flag=QualityFlagChoices.READY_TO_CERTIFY,
        certified_by=request.user,
        certified_at=timezone.now(),
    )
    modeladmin.message_user(
        request,
        f"Certified {count} resource(s) with minor edits.",
        messages.SUCCESS,
    )


@admin.action(description="Flag: Needs Review")
def mark_needs_review(modeladmin, request, queryset):
    count = queryset.update(quality_flag=QualityFlagChoices.NEEDS_REVIEW)
    modeladmin.message_user(request, f"Flagged {count} resource(s) for review.")


@admin.action(description="Flag: Needs Update")
def mark_needs_update(modeladmin, request, queryset):
    count = queryset.update(quality_flag=QualityFlagChoices.NEEDS_UPDATE)
    modeladmin.message_user(request, f"Flagged {count} resource(s) for update.")


@admin.action(description="Reject selected resources")
def reject_resources(modeladmin, request, queryset):
    count = queryset.update(
        advisory_status=AdvisoryStatusChoices.NOT_VALIDATED,
        quality_flag=QualityFlagChoices.REJECT,
    )
    modeladmin.message_user(request, f"Rejected {count} resource(s).")


@admin.action(description="Queue for vector sync (only certified resources)")
def mark_vector_sync_pending(modeladmin, request, queryset):
    eligible = queryset.filter(
        quality_flag=QualityFlagChoices.READY_TO_CERTIFY,
        advisory_status__in=[
            AdvisoryStatusChoices.VALIDATED,
            AdvisoryStatusChoices.VALIDATED_WITH_MINOR_EDITS,
        ],
    )
    skipped = queryset.count() - eligible.count()
    count = eligible.update(
        vector_sync_status=VectorSyncStatusChoices.PENDING,
        vector_sync_error="",
        vector_synced_at=None,
    )
    if count:
        modeladmin.message_user(
            request, f"Queued {count} resource(s) for vector sync.", messages.SUCCESS
        )
    if skipped:
        modeladmin.message_user(
            request,
            f"Skipped {skipped} resource(s) that are not certified.",
            messages.WARNING,
        )


@admin.action(description="Soft-delete selected resources")
def soft_delete_resources(modeladmin, request, queryset):
    count = queryset.filter(is_deleted=False).update(
        is_deleted=True,
        deleted_at=timezone.now(),
    )
    modeladmin.message_user(request, f"Soft-deleted {count} resource(s).")


@admin.action(description="Restore selected soft-deleted resources")
def restore_resources(modeladmin, request, queryset):
    count = queryset.filter(is_deleted=True).update(
        is_deleted=False,
        deleted_at=None,
    )
    modeladmin.message_user(request, f"Restored {count} resource(s).")


# ===========================================================================
# ContentSectionInline (on AdvisoryResource)
# ===========================================================================
class ContentSectionInline(admin.TabularInline):
    model = ContentSection
    extra = 0
    fields = (
        "reading_order",
        "content_id",
        "pages_reference",
        "content_header",
        "status",
        "review_stage",
        "assigned_scientist",
        "is_quarantined",
    )
    readonly_fields = ("content_id",)
    autocomplete_fields = ("assigned_scientist",)
    show_change_link = True
    ordering = ("reading_order",)


# ===========================================================================
# AdvisoryResource admin
# ===========================================================================
@admin.register(AdvisoryResource)
class AdvisoryResourceAdmin(ImportExportModelAdmin):
    resource_class = AdvisoryResourceResource

    list_display = (
        "slug",
        "title_short",
        "institution",
        "sector",
        "content_type",
        "language",
        "advisory_status_badge",
        "quality_flag_badge",
        "vector_sync_status",
        "is_deleted",
        "updated_at",
    )
    list_filter = (
        "sector",
        "content_type",
        "language",
        "validation_status",
        "advisory_status",
        "currency_status",
        "scientific_accuracy_check",
        "quality_flag",
        "risk_level",
        "vector_sync_status",
        "is_deleted",
        ("value_chains", admin.RelatedOnlyFieldListFilter),
        ("institution", admin.RelatedOnlyFieldListFilter),
    )
    search_fields = (
        "title",
        "slug",
        "author",
        "institution__name",
        "value_chains__name",
        "preferred_citation",
        "screening_notes",
    )
    date_hierarchy = "updated_at"
    ordering = ("-updated_at",)
    readonly_fields = (
        "created_at",
        "updated_at",
        "file_checksum",
        "file_size_bytes",
        "mime_type",
        "content_hash",
        "vector_synced_at",
        "chunk_count",
        "file_link",
    )
    filter_horizontal = ("value_chains",)
    autocomplete_fields = (
        "institution",
        "screened_by",
        "certified_by",
        "supersedes",
    )
    inlines = (ContentSectionInline,)
    actions = (
        certify_resources,
        certify_with_edits,
        mark_needs_review,
        mark_needs_update,
        reject_resources,
        mark_vector_sync_pending,
        soft_delete_resources,
        restore_resources,
    )
    list_per_page = 50
    save_on_top = True

    fieldsets = (
        ("Resource identity", {
            "fields": (
                "title",
                "slug",
                "link",
                "institution",
                "author",
                "publish_date",
                "modified_date",
                "content_type",
                "language",
                "available_languages",
            )
        }),
        ("Source file", {
            "fields": (
                "upload_file",
                "file_link",
                "file_size_bytes",
                "mime_type",
                "file_checksum",
            ),
            "classes": ("collapse",),
        }),
        ("Classification", {
            "fields": (
                "sector",
                "value_chains",
                "production_system",
                "advisory_domain",
                "target_users",
                "geographic_applicability",
                "seasonality",
                "license",
            )
        }),
        ("Validation and screening", {
            "fields": (
                "validation_status",
                "validated_by",
                "review_date",
                "next_review_date",
                "preferred_citation",
                "currency_status",
                "scientific_accuracy_check",
                "quality_flag",
                "screening_notes",
                "screened_by",
                "screened_at",
            )
        }),
        ("Certification", {
            "fields": (
                "advisory_status",
                "certified_by",
                "certified_at",
            )
        }),
        ("Safety", {
            "fields": (
                "risk_level",
                "risk_domains",
                "requires_human_review",
                "escalation_guidance",
                "safety_disclaimer",
            ),
            "classes": ("collapse",),
        }),
        ("AI / vector index", {
            "fields": (
                "vector_sync_status",
                "vector_synced_at",
                "vector_sync_error",
                "embedding_model",
                "embedding_dimensions",
                "chunk_count",
                "content_hash",
            )
        }),
        ("Versioning and deletion", {
            "fields": (
                "version",
                "supersedes",
                "is_deleted",
                "deleted_at",
            )
        }),
        ("Audit timestamps", {
            "fields": ("created_at", "updated_at"),
            "classes": ("collapse",),
        }),
    )

    # -- Display helpers ------------------------------------------------
    @admin.display(description="Title", ordering="title")
    def title_short(self, obj):
        return (obj.title[:70] + "…") if len(obj.title) > 70 else obj.title

    @admin.display(description="Certification", ordering="advisory_status")
    def advisory_status_badge(self, obj):
        if not obj.advisory_status:
            return "—"
        return _badge(
            obj.get_advisory_status_display(),
            ADVISORY_STATUS_COLORS.get(obj.advisory_status, "#57606a"),
        )

    @admin.display(description="Quality", ordering="quality_flag")
    def quality_flag_badge(self, obj):
        if not obj.quality_flag:
            return "—"
        return _badge(
            obj.get_quality_flag_display(),
            QUALITY_FLAG_COLORS.get(obj.quality_flag, "#57606a"),
        )

    @admin.display(description="File")
    def file_link(self, obj):
        if not obj.upload_file:
            return "—"
        return format_html(
            '<a href="{}" target="_blank" rel="noopener">{}</a>',
            obj.upload_file.url,
            obj.upload_file.name.rsplit("/", 1)[-1],
        )


# ===========================================================================
# ContentSection actions
# ===========================================================================
@admin.action(description="Quarantine selected content sections")
def quarantine_sections(modeladmin, request, queryset):
    count = queryset.update(is_quarantined=True)
    modeladmin.message_user(request, f"Quarantined {count} section(s).")


@admin.action(description="Remove quarantine from selected content sections")
def unquarantine_sections(modeladmin, request, queryset):
    count = queryset.update(is_quarantined=False)
    modeladmin.message_user(request, f"Unquarantined {count} section(s).")


@admin.action(description="Assign selected sections to me (scientist review)")
def assign_to_me(modeladmin, request, queryset):
    count = queryset.update(
        assigned_scientist=request.user,
        review_stage=ChunkReviewStageChoices.SCIENTIST_REVIEW,
    )
    modeladmin.message_user(
        request, f"Assigned {count} section(s) to you.", messages.SUCCESS
    )


def _bulk_review(modeladmin, request, queryset, *, decision: str):
    """Route every selected section through apply_review() for a consistent audit."""
    count = 0
    for section in queryset.select_related("resource"):
        section.apply_review(
            scientist=request.user,
            decision=decision,
            notes="Bulk action from admin.",
        )
        count += 1
    modeladmin.message_user(
        request,
        f"Recorded decision '{decision}' on {count} section(s).",
        messages.SUCCESS,
    )


@admin.action(description="Mark sections as Validated")
def mark_sections_validated(modeladmin, request, queryset):
    _bulk_review(modeladmin, request, queryset, decision=ReviewDecisionChoices.APPROVE)


@admin.action(description="Mark sections as Validated with minor edits")
def mark_sections_validated_minor(modeladmin, request, queryset):
    _bulk_review(
        modeladmin, request, queryset, decision=ReviewDecisionChoices.APPROVE_WITH_EDITS
    )


@admin.action(description="Mark sections as Major Revision")
def mark_sections_major_revision(modeladmin, request, queryset):
    _bulk_review(
        modeladmin, request, queryset, decision=ReviewDecisionChoices.REQUEST_REVISION
    )


@admin.action(description="Mark sections as Not Validated")
def mark_sections_not_validated(modeladmin, request, queryset):
    _bulk_review(modeladmin, request, queryset, decision=ReviewDecisionChoices.REJECT)


@admin.action(description="Escalate sections to senior review")
def escalate_sections(modeladmin, request, queryset):
    _bulk_review(modeladmin, request, queryset, decision=ReviewDecisionChoices.ESCALATE)


# ===========================================================================
# Filters
# ===========================================================================
class ScientistAssignmentFilter(admin.SimpleListFilter):
    title = "scientist assignment"
    parameter_name = "scientist_state"

    def lookups(self, request, model_admin):
        return (
            ("unassigned", "Unassigned"),
            ("assigned", "Assigned"),
            ("overdue", "Assigned > 14 days, no review"),
        )

    def queryset(self, request, queryset):
        value = self.value()
        if value == "unassigned":
            return queryset.filter(assigned_scientist__isnull=True)
        if value == "assigned":
            return queryset.filter(assigned_scientist__isnull=False)
        if value == "overdue":
            cutoff = timezone.now() - timezone.timedelta(days=14)
            return queryset.filter(
                assigned_scientist__isnull=False,
                reviewed_at__isnull=True,
                created_at__lt=cutoff,
            )
        return queryset


# ===========================================================================
# SectionReviewLogInline
# ===========================================================================
class SectionReviewLogInline(admin.TabularInline):
    model = SectionReviewLog
    extra = 0
    can_delete = False
    fields = (
        "created_at",
        "actor",
        "decision",
        "previous_status",
        "new_status",
        "governance_flag",
        "confidence_score",
        "notes",
    )
    readonly_fields = fields
    ordering = ("-created_at",)

    def has_add_permission(self, request, obj=None):
        return False


# ===========================================================================
# ContentSection admin
# ===========================================================================
@admin.register(ContentSection)
class ContentSectionAdmin(ImportExportModelAdmin):
    resource_class = ContentSectionResource

    list_display = (
        "content_id",
        "resource_link",
        "reading_order",
        "content_header_short",
        "status_badge",
        "review_stage",
        "thematic_areas_short",
        "value_chains_short",
        "governance_flag",
        "assigned_scientist",
        "is_quarantined",
        "updated_at",
    )
    list_filter = (
        "status",
        "review_stage",
        "review_decision",
        "governance_flag",
        "is_quarantined",
        "requires_senior_review",
        ("thematic_areas", admin.RelatedOnlyFieldListFilter),
        ("value_chains", admin.RelatedOnlyFieldListFilter),
        ("resource__sector", admin.AllValuesFieldListFilter),
        ScientistAssignmentFilter,
    )
    search_fields = (
        "content_id",
        "content_header",
        "content_text",
        "thematic_areas__name",
        "value_chains__name",
        "resource__title",
        "resource__slug",
        "review_notes",
        "governance_notes",
    )
    autocomplete_fields = (
        "resource",
        "assigned_scientist",
        "reviewed_by",
        "senior_reviewer",
        "supersedes",
        "value_chains",
        "thematic_areas",
    )
    filter_horizontal = ("value_chains", "thematic_areas")
    readonly_fields = ("content_hash", "created_at", "updated_at", "resource_link")
    date_hierarchy = "updated_at"
    ordering = ("resource", "reading_order")
    list_select_related = ("resource", "assigned_scientist", "reviewed_by")
    inlines = (SectionReviewLogInline,)
    actions = (
        assign_to_me,
        mark_sections_validated,
        mark_sections_validated_minor,
        mark_sections_major_revision,
        mark_sections_not_validated,
        escalate_sections,
        quarantine_sections,
        unquarantine_sections,
    )
    list_per_page = 50
    save_on_top = True

    fieldsets = (
        ("Section content", {
            "fields": (
                "resource",
                "resource_link",
                "content_id",
                "reading_order",
                "content_header",
                "content_text",
                "page_start",
                "page_end",
                "content_images",
                "content_tables",
                "content_warnings",
                "content_tags",
            )
        }),
        ("Classification", {
            "fields": ("value_chains", "thematic_areas")
        }),
        ("Scientist review", {
            "fields": (
                "status",
                "assigned_scientist",
                "reviewed_by",
                "reviewed_at",
                "review_stage",
                "review_decision",
                "review_notes",
                "suggested_edits",
                "corrected_text",
                "confidence_score",
                "currency_checked_on",
            )
        }),
        ("Governance", {
            "fields": (
                "governance_flag",
                "governance_notes",
                "is_quarantined",
                "requires_senior_review",
                "senior_reviewer",
            )
        }),
        ("Evidence and versioning", {
            "fields": (
                "evidence_citations",
                "version",
                "supersedes",
                "token_count",
                "content_hash",
            ),
            "classes": ("collapse",),
        }),
        ("Audit timestamps", {
            "fields": ("created_at", "updated_at"),
            "classes": ("collapse",),
        }),
    )

    # -- Display helpers ------------------------------------------------
    @admin.display(description="Resource", ordering="resource__slug")
    def resource_link(self, obj):
        url = reverse("admin:advisory_advisoryresource_change", args=[obj.resource_id])
        return format_html('<a href="{}">{}</a>', url, obj.resource.slug)

    @admin.display(description="Header", ordering="content_header")
    def content_header_short(self, obj):
        if not obj.content_header:
            return "—"
        return (
            obj.content_header[:55] + "…"
            if len(obj.content_header) > 55
            else obj.content_header
        )

    @admin.display(description="Status", ordering="status")
    def status_badge(self, obj):
        if not obj.status:
            return "—"
        return _badge(
            obj.get_status_display(),
            SECTION_STATUS_COLORS.get(obj.status, "#57606a"),
        )

    @admin.display(description="Thematic areas")
    def thematic_areas_short(self, obj):
        names = list(obj.thematic_areas.values_list("name", flat=True))
        if not names:
            return "—"
        text = ", ".join(names[:2])
        return text + (f" +{len(names) - 2}" if len(names) > 2 else "")

    @admin.display(description="Value chains")
    def value_chains_short(self, obj):
        names = list(obj.value_chains.values_list("name", flat=True))
        if not names:
            return "—"
        text = ", ".join(names[:2])
        return text + (f" +{len(names) - 2}" if len(names) > 2 else "")

    # -- Row-level safety ----------------------------------------------
    def has_delete_permission(self, request, obj=None):
        """
        Prevent accidental deletion of already-certified chunks; scientists
        must change the status first.
        """
        if obj and obj.status in (
            SectionStatusChoices.VALIDATED,
            SectionStatusChoices.VALIDATED_WITH_MINOR_EDITS,
        ):
            return False
        return super().has_delete_permission(request, obj)


# ===========================================================================
# SectionReviewLog admin (read-only audit view + export)
# ===========================================================================
@admin.register(SectionReviewLog)
class SectionReviewLogAdmin(ExportActionModelAdmin):
    resource_class = SectionReviewLogResource

    list_display = (
        "created_at",
        "section_link",
        "actor",
        "decision",
        "previous_status",
        "new_status",
        "governance_flag",
        "confidence_score",
    )
    list_filter = (
        "decision",
        "previous_status",
        "new_status",
        "governance_flag",
        ("actor", admin.RelatedOnlyFieldListFilter),
        "created_at",
    )
    search_fields = (
        "section__content_id",
        "section__content_header",
        "actor__username",
        "notes",
    )
    date_hierarchy = "created_at"
    ordering = ("-created_at",)
    list_select_related = ("section", "actor")
    readonly_fields = (
        "section",
        "actor",
        "decision",
        "previous_status",
        "new_status",
        "governance_flag",
        "notes",
        "confidence_score",
        "created_at",
    )
    list_per_page = 100

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        # Append-only audit; only superusers may prune if policy requires.
        return request.user.is_superuser

    @admin.display(description="Section", ordering="section__content_id")
    def section_link(self, obj):
        url = reverse("admin:advisory_contentsection_change", args=[obj.section_id])
        return format_html('<a href="{}">{}</a>', url, obj.section.content_id)




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

# ===========================================================================
# Admin site branding
# ===========================================================================
admin.site.site_header = "KALRO Advisory Content Administration"
admin.site.site_title = "KALRO Advisory"
admin.site.index_title = "Content Governance & Certification"
