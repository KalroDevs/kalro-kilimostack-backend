from django.contrib.auth import get_user_model

from import_export import fields, resources
from import_export.widgets import ForeignKeyWidget, JSONWidget

from .models import AdvisoryResource, ContentSection


User = get_user_model()


# ---------------------------------------------------------------------------
# Shared widget construction
# ---------------------------------------------------------------------------
def _json_field(name: str) -> fields.Field:
    """Helper: a JSONField backed by JSONWidget, keyed on ``name``."""
    return fields.Field(
        column_name=name,
        attribute=name,
        widget=JSONWidget(),
    )


class AdvisoryResourceResource(resources.ModelResource):
    """
    Import/export resource for AdvisoryResource.

    Stable identifier:
        resource_id   (Excel column A -- the inventory / join key)

    Note: ``publication_id`` is Excel column C, is NOT unique, and may be
    blank. It is retained as an ordinary column, not as the import key.

    User reference:
        screened_by -> User.email

    JSON fields are serialized/deserialized using JSONWidget.
    """

    screened_by = fields.Field(
        column_name="screened_by",
        attribute="screened_by",
        widget=ForeignKeyWidget(User, field="email"),
    )

    # JSON fields
    author = _json_field("author")
    available_languages = _json_field("available_languages")
    commodity = _json_field("commodity")
    production_system = _json_field("production_system")
    advisory_domain = _json_field("advisory_domain")
    target_users = _json_field("target_users")
    geographic_applicability = _json_field("geographic_applicability")
    seasonality = _json_field("seasonality")
    license = _json_field("license")
    validated_by = _json_field("validated_by")
    risk_domains = _json_field("risk_domains")

    class Meta:
        model = AdvisoryResource

        # Excel column A -- unique, stable, referenced by ContentSection.pages_reference
        import_id_fields = ("resource_id",)

        fields = (
            # Excel column A -- join key
            "resource_id",
            # Excel column C -- free-form publication identifier / URL
            "publication_id",
            "title",
            "link",
            # "thumbnail",   # commented out on the model; not importable
            "institution",
            "author",
            "publish_date",
            "modified_date",
            "content_type",
            "language",
            "available_languages",

            "sector",
            "value_chain",
            "commodity",
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

            "vector_sync_status",
            "vector_synced_at",
            "vector_sync_error",
        )

        export_order = fields

        skip_unchanged = True
        report_skipped = True
        use_bulk = False


class ContentSectionResource(resources.ModelResource):
    """
    Import/export resource for ContentSection.

    Stable identifier:
        content_id

    AdvisoryResource is referenced using ``resource_id`` -- the Excel
    column A value the section sheets carry in their "Pages" column
    (e.g. "CROP-007") -- NOT by publication_id.
    """

    resource = fields.Field(
        column_name="resource",
        attribute="resource",
        widget=ForeignKeyWidget(
            AdvisoryResource,
            field="resource_id",       # ✅ matches Excel "Pages"
        ),
    )

    # JSON fields
    content_images = _json_field("content_images")
    content_tables = _json_field("content_tables")
    content_warnings = _json_field("content_warnings")
    content_tags = _json_field("content_tags")

    # Plain strings -- prevent Excel from coercing e.g. "CROP-007" or a raw
    # Pages value into a number/date during round-trips.
    pages_reference = fields.Field(
        column_name="pages_reference",
        attribute="pages_reference",
    )
    value_chain = fields.Field(
        column_name="value_chain",
        attribute="value_chain",
    )

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
            # Excel cross-reference (Sheet 3-7)
            "pages_reference",
            "value_chain",
            # Structured payloads
            "content_images",
            "content_tables",
            "content_warnings",
            "content_tags",
        )

        export_order = fields

        skip_unchanged = True
        report_skipped = True
        use_bulk = False