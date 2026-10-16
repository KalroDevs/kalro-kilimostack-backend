"""
django-import-export resources for the KALRO Advisory Content Corpus.

Resources
---------
* :class:`AdvisoryResourceResource`  -- stable id ``publication_id``
* :class:`ContentSectionResource`    -- stable id ``content_id``
* :class:`ValueChainResource`        -- stable id ``slug``
* :class:`ThematicAreaResource`      -- stable id ``slug``
* :class:`SectionReviewLogResource`  -- export-only audit

Conventions
-----------
* User FKs (``screened_by``, ``certified_by``, ``assigned_scientist``,
  ``reviewed_by``, ``senior_reviewer``, ``actor``) resolve by ``email``.
* ``institution`` resolves to ``providers.Provider`` by ``name``.
* ``supersedes`` (self-FK) resolves by ``slug`` on AdvisoryResource and by
  ``content_id`` on ContentSection.
* JSONFields use ``JSONWidget``; blank cells preserve the model defaults
  (empty list / dict) via ``before_save_instance``.
* M2M fields (``value_chains``, ``thematic_areas``) are imported/exported
  as comma-separated slugs via :class:`ManyToManyBySlugWidget`.
* Auto-managed fields (``slug``, ``content_hash``, ``chunk_count``,
  timestamps) are exported for visibility and stripped on import.
"""

from django.contrib.auth import get_user_model

from import_export import fields, resources
from import_export.widgets import ForeignKeyWidget, JSONWidget, Widget

from providers.models import Provider

from .models import (
    AdvisoryResource,
    ContentSection,
    SectionReviewLog,
    ThematicArea,
    ValueChain,
)


User = get_user_model()


# ===========================================================================
# Custom M2M widget
# ===========================================================================
class ManyToManyBySlugWidget(Widget):
    """
    Import/export an M2M relation as a comma-separated list of slugs.

    Slugs are preferred over names because they are stable and unique per
    model; curators can rename display names without breaking historical
    CSV/XLSX files.
    """

    def __init__(self, model, field: str = "slug", separator: str = ","):
        self.model = model
        self.field = field
        self.separator = separator

    def clean(self, value, row=None, **kwargs):
        if value in (None, ""):
            return self.model.objects.none()
        tokens = [t.strip() for t in str(value).split(self.separator) if t.strip()]
        if not tokens:
            return self.model.objects.none()
        return self.model.objects.filter(**{f"{self.field}__in": tokens})

    def render(self, value, obj=None, **kwargs):
        if value is None:
            return ""
        # `value` is a RelatedManager on the instance during export.
        return self.separator.join(value.values_list(self.field, flat=True))


# ===========================================================================
# AdvisoryResource
# ===========================================================================
class AdvisoryResourceResource(resources.ModelResource):
    """
    Import/export resource for :class:`AdvisoryResource`.

    Stable identifier: ``publication_id``.
    """

    # -- FK widgets ----------------------------------------------------
    institution = fields.Field(
        column_name="institution",
        attribute="institution",
        widget=ForeignKeyWidget(Provider, field="name"),
    )
    supersedes = fields.Field(
        column_name="supersedes",
        attribute="supersedes",
        widget=ForeignKeyWidget(AdvisoryResource, field="slug"),
    )
    screened_by = fields.Field(
        column_name="screened_by",
        attribute="screened_by",
        widget=ForeignKeyWidget(User, field="email"),
    )
    certified_by = fields.Field(
        column_name="certified_by",
        attribute="certified_by",
        widget=ForeignKeyWidget(User, field="email"),
    )

    # -- M2M -----------------------------------------------------------
    value_chains = fields.Field(
        column_name="value_chains",
        attribute="value_chains",
        widget=ManyToManyBySlugWidget(ValueChain, field="slug"),
    )

    # -- JSON ----------------------------------------------------------
    author = fields.Field(attribute="author", widget=JSONWidget())
    available_languages = fields.Field(attribute="available_languages", widget=JSONWidget())
    production_system = fields.Field(attribute="production_system", widget=JSONWidget())
    advisory_domain = fields.Field(attribute="advisory_domain", widget=JSONWidget())
    target_users = fields.Field(attribute="target_users", widget=JSONWidget())
    geographic_applicability = fields.Field(attribute="geographic_applicability", widget=JSONWidget())
    seasonality = fields.Field(attribute="seasonality", widget=JSONWidget())
    license = fields.Field(attribute="license", widget=JSONWidget())
    validated_by = fields.Field(attribute="validated_by", widget=JSONWidget())
    risk_domains = fields.Field(attribute="risk_domains", widget=JSONWidget())

    class Meta:
        model = AdvisoryResource
        import_id_fields = ("publication_id",)

        fields = (
            "publication_id",
            "title",
            "slug",
            "link",
            "thumbnail",
            "institution",
            "author",
            "publish_date",
            "modified_date",
            "content_type",
            "language",
            "available_languages",

            "sector",
            "value_chains",
            "production_system",
            "advisory_domain",
            "target_users",

            "geographic_applicability",
            "seasonality",
            "license",

            "validation_status",
            "validated_by",
            "review_date",
            "next_review_date",
            "preferred_citation",

            "advisory_status",
            "certified_by",
            "certified_at",

            "risk_level",
            "risk_domains",
            "requires_human_review",
            "escalation_guidance",
            "safety_disclaimer",

            "currency_status",
            "scientific_accuracy_check",
            "quality_flag",
            "screening_notes",
            "screened_by",
            "screened_at",

            "version",
            "supersedes",

            "vector_sync_status",
            "vector_synced_at",
            "vector_sync_error",
            "embedding_model",
            "embedding_dimensions",
            "chunk_count",
            "content_hash",

            "is_deleted",
            "deleted_at",
            "created_at",
            "updated_at",
        )
        export_order = fields

        skip_unchanged = True
        report_skipped = True
        use_bulk = False

    # Columns the importer must never write to — they're either auto-managed
    # by the model's save()/admin actions or exported for reporting only.
    READ_ONLY_COLUMNS = {
        "slug",
        "content_hash",
        "chunk_count",
        "file_checksum",
        "file_size_bytes",
        "mime_type",
        "created_at",
        "updated_at",
    }

    def before_import_row(self, row, **kwargs):
        for col in self.READ_ONLY_COLUMNS:
            row.pop(col, None)
        return super().before_import_row(row, **kwargs)

    # Preserve the model's list/dict defaults when a cell is blank.
    def before_save_instance(self, instance, row, **kwargs):
        for json_list_field in (
            "author",
            "available_languages",
            "production_system",
            "advisory_domain",
            "target_users",
            "validated_by",
            "risk_domains",
        ):
            if getattr(instance, json_list_field, None) in (None, ""):
                setattr(instance, json_list_field, [])
        for json_dict_field in (
            "geographic_applicability",
            "seasonality",
            "license",
        ):
            if getattr(instance, json_dict_field, None) in (None, ""):
                setattr(instance, json_dict_field, {})
        return super().before_save_instance(instance, row, **kwargs)


# ===========================================================================
# ContentSection
# ===========================================================================
class ContentSectionResource(resources.ModelResource):
    """
    Import/export resource for :class:`ContentSection`.

    Stable identifier: ``content_id``.
    Parent resource resolves by ``publication_id`` (not PK).
    """

    # -- FK widgets ----------------------------------------------------
    resource = fields.Field(
        column_name="resource",
        attribute="resource",
        widget=ForeignKeyWidget(AdvisoryResource, field="publication_id"),
    )
    assigned_scientist = fields.Field(
        column_name="assigned_scientist",
        attribute="assigned_scientist",
        widget=ForeignKeyWidget(User, field="email"),
    )
    reviewed_by = fields.Field(
        column_name="reviewed_by",
        attribute="reviewed_by",
        widget=ForeignKeyWidget(User, field="email"),
    )
    senior_reviewer = fields.Field(
        column_name="senior_reviewer",
        attribute="senior_reviewer",
        widget=ForeignKeyWidget(User, field="email"),
    )
    supersedes = fields.Field(
        column_name="supersedes",
        attribute="supersedes",
        widget=ForeignKeyWidget(ContentSection, field="content_id"),
    )

    # -- M2M -----------------------------------------------------------
    value_chains = fields.Field(
        column_name="value_chains",
        attribute="value_chains",
        widget=ManyToManyBySlugWidget(ValueChain, field="slug"),
    )
    thematic_areas = fields.Field(
        column_name="thematic_areas",
        attribute="thematic_areas",
        widget=ManyToManyBySlugWidget(ThematicArea, field="slug"),
    )

    # -- JSON ----------------------------------------------------------
    content_images = fields.Field(attribute="content_images", widget=JSONWidget())
    content_tables = fields.Field(attribute="content_tables", widget=JSONWidget())
    content_warnings = fields.Field(attribute="content_warnings", widget=JSONWidget())
    content_tags = fields.Field(attribute="content_tags", widget=JSONWidget())
    evidence_citations = fields.Field(attribute="evidence_citations", widget=JSONWidget())

    class Meta:
        model = ContentSection
        import_id_fields = ("content_id",)

        fields = (
            "content_id",
            "resource",
            "reading_order",
            "content_header",
            "content_text",
            "page_start",
            "page_end",

            "content_images",
            "content_tables",
            "content_warnings",
            "content_tags",

            "value_chains",
            "thematic_areas",

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

            "governance_flag",
            "governance_notes",
            "is_quarantined",
            "requires_senior_review",
            "senior_reviewer",

            "evidence_citations",
            "version",
            "supersedes",
            "token_count",
            "content_hash",

            "created_at",
            "updated_at",
        )
        export_order = fields

        skip_unchanged = True
        report_skipped = True
        use_bulk = False

    READ_ONLY_COLUMNS = {
        "content_hash",
        "created_at",
        "updated_at",
    }

    def before_import_row(self, row, **kwargs):
        for col in self.READ_ONLY_COLUMNS:
            row.pop(col, None)
        return super().before_import_row(row, **kwargs)

    def before_save_instance(self, instance, row, **kwargs):
        # Restore default empty containers for list-valued JSON fields.
        for json_list_field in (
            "content_images",
            "content_tables",
            "content_warnings",
            "content_tags",
            "evidence_citations",
        ):
            if getattr(instance, json_list_field, None) in (None, ""):
                setattr(instance, json_list_field, [])
        return super().before_save_instance(instance, row, **kwargs)


# ===========================================================================
# ValueChain
# ===========================================================================
class ValueChainResource(resources.ModelResource):
    """
    Import/export for the value-chain controlled vocabulary.

    Stable identifier: ``slug`` (falls back to auto-slugification on save
    when omitted, but for round-trip imports it's safer to always provide
    it).
    """

    class Meta:
        model = ValueChain
        import_id_fields = ("slug",)
        fields = (
            "id",
            "name",
            "slug",
            "sector",
            "description",
            "is_active",
            "created_at",
        )
        export_order = fields
        skip_unchanged = True
        report_skipped = True

    READ_ONLY_COLUMNS = {"id", "created_at"}

    def before_import_row(self, row, **kwargs):
        for col in self.READ_ONLY_COLUMNS:
            row.pop(col, None)
        return super().before_import_row(row, **kwargs)


# ===========================================================================
# ThematicArea
# ===========================================================================
class ThematicAreaResource(resources.ModelResource):
    """
    Import/export for the thematic-area controlled vocabulary.

    Stable identifier: ``slug``.
    """

    class Meta:
        model = ThematicArea
        import_id_fields = ("slug",)
        fields = (
            "id",
            "name",
            "slug",
            "description",
            "is_active",
            "created_at",
        )
        export_order = fields
        skip_unchanged = True
        report_skipped = True

    READ_ONLY_COLUMNS = {"id", "created_at"}

    def before_import_row(self, row, **kwargs):
        for col in self.READ_ONLY_COLUMNS:
            row.pop(col, None)
        return super().before_import_row(row, **kwargs)


# ===========================================================================
# SectionReviewLog (export-only)
# ===========================================================================
class SectionReviewLogResource(resources.ModelResource):
    """
    Export-only resource for the immutable audit trail.

    Import is intentionally not supported here; review log entries are
    created by :meth:`ContentSection.apply_review`.
    """

    section = fields.Field(
        column_name="section",
        attribute="section",
        widget=ForeignKeyWidget(ContentSection, field="content_id"),
    )
    actor = fields.Field(
        column_name="actor",
        attribute="actor",
        widget=ForeignKeyWidget(User, field="email"),
    )

    class Meta:
        model = SectionReviewLog
        import_id_fields = ("id",)
        fields = (
            "id",
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
        export_order = fields
        skip_unchanged = True
        report_skipped = True