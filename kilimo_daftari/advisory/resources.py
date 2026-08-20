from django.contrib.auth import get_user_model

from import_export import fields, resources
from import_export.widgets import ForeignKeyWidget, JSONWidget

from .models import AdvisoryResource, ContentSection


User = get_user_model()


class AdvisoryResourceResource(resources.ModelResource):
    """
    Import/export resource for AdvisoryResource.

    Stable identifier:
        publication_id

    User reference:
        screened_by -> User.email

    JSON fields are serialized/deserialized using JSONWidget.
    """

    screened_by = fields.Field(
        column_name="screened_by",
        attribute="screened_by",
        widget=ForeignKeyWidget(
            User,
            field="email",
        ),
    )

    author = fields.Field(
        column_name="author",
        attribute="author",
        widget=JSONWidget(),
    )

    available_languages = fields.Field(
        column_name="available_languages",
        attribute="available_languages",
        widget=JSONWidget(),
    )

    commodity = fields.Field(
        column_name="commodity",
        attribute="commodity",
        widget=JSONWidget(),
    )

    production_system = fields.Field(
        column_name="production_system",
        attribute="production_system",
        widget=JSONWidget(),
    )

    advisory_domain = fields.Field(
        column_name="advisory_domain",
        attribute="advisory_domain",
        widget=JSONWidget(),
    )

    target_users = fields.Field(
        column_name="target_users",
        attribute="target_users",
        widget=JSONWidget(),
    )

    geographic_applicability = fields.Field(
        column_name="geographic_applicability",
        attribute="geographic_applicability",
        widget=JSONWidget(),
    )

    seasonality = fields.Field(
        column_name="seasonality",
        attribute="seasonality",
        widget=JSONWidget(),
    )

    license = fields.Field(
        column_name="license",
        attribute="license",
        widget=JSONWidget(),
    )

    validated_by = fields.Field(
        column_name="validated_by",
        attribute="validated_by",
        widget=JSONWidget(),
    )

    risk_domains = fields.Field(
        column_name="risk_domains",
        attribute="risk_domains",
        widget=JSONWidget(),
    )

    class Meta:
        model = AdvisoryResource

        import_id_fields = (
            "publication_id",
        )

        fields = (
            "publication_id",
            "title",
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

    AdvisoryResource is referenced using publication_id
    rather than its database primary key.
    """

    resource = fields.Field(
        column_name="resource",
        attribute="resource",
        widget=ForeignKeyWidget(
            AdvisoryResource,
            field="publication_id",
        ),
    )

    content_images = fields.Field(
        column_name="content_images",
        attribute="content_images",
        widget=JSONWidget(),
    )

    content_tables = fields.Field(
        column_name="content_tables",
        attribute="content_tables",
        widget=JSONWidget(),
    )

    content_warnings = fields.Field(
        column_name="content_warnings",
        attribute="content_warnings",
        widget=JSONWidget(),
    )

    content_tags = fields.Field(
        column_name="content_tags",
        attribute="content_tags",
        widget=JSONWidget(),
    )

    class Meta:
        model = ContentSection

        import_id_fields = (
            "content_id",
        )

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
        )

        export_order = fields

        skip_unchanged = True
        report_skipped = True

        use_bulk = False