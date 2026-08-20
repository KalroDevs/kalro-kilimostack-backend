from django.contrib.auth import get_user_model

from import_export import fields, resources
from import_export.widgets import ForeignKeyWidget, JSONWidget

from .models import (
    CatalogItem,
    Provider,
    ProviderMembership,
    ServiceCategory,
)


User = get_user_model()


# =========================================================
# PROVIDER
# =========================================================

class ProviderResource(resources.ModelResource):
    """
    Import / export resource for providers.

    provider_id is used as the stable identifier instead of
    the database primary key.
    """

    class Meta:
        model = Provider

        import_id_fields = (
            "provider_id",
        )

        fields = (
            "provider_id",
            "name",
            "institution_type",
            "contact_email",
            "contact_phone",
            "website",
            "description",
            "is_active",
        )

        export_order = (
            "provider_id",
            "name",
            "institution_type",
            "contact_email",
            "contact_phone",
            "website",
            "description",
            "is_active",
        )

        skip_unchanged = True
        report_skipped = True
        use_bulk = False


# =========================================================
# SERVICE CATEGORY
# =========================================================

class ServiceCategoryResource(resources.ModelResource):
    """
    Import / export resource for service categories.

    code is the stable unique identifier.
    """

    schema_hint = fields.Field(
        column_name="schema_hint",
        attribute="schema_hint",
        widget=JSONWidget(),
    )

    class Meta:
        model = ServiceCategory

        import_id_fields = (
            "code",
        )

        fields = (
            "code",
            "label",
            "description",
            "schema_hint",
            "is_active",
        )

        export_order = (
            "code",
            "label",
            "description",
            "schema_hint",
            "is_active",
        )

        skip_unchanged = True
        report_skipped = True
        use_bulk = False


# =========================================================
# CATALOG ITEM
# =========================================================

class CatalogItemResource(resources.ModelResource):
    """
    Import / export resource for catalog items.

    Foreign keys are represented using stable readable values:

        provider -> Provider.provider_id
        category -> ServiceCategory.code
        screened_by -> User.email

    JSONFields are imported/exported as valid JSON strings.
    """

    provider = fields.Field(
        column_name="provider",
        attribute="provider",
        widget=ForeignKeyWidget(
            Provider,
            field="provider_id",
        ),
    )

    category = fields.Field(
        column_name="category",
        attribute="category",
        widget=ForeignKeyWidget(
            ServiceCategory,
            field="code",
        ),
    )

    screened_by = fields.Field(
        column_name="screened_by",
        attribute="screened_by",
        widget=ForeignKeyWidget(
            User,
            field="email",
        ),
    )

    location = fields.Field(
        column_name="location",
        attribute="location",
        widget=JSONWidget(),
    )

    availability = fields.Field(
        column_name="availability",
        attribute="availability",
        widget=JSONWidget(),
    )

    fulfillment = fields.Field(
        column_name="fulfillment",
        attribute="fulfillment",
        widget=JSONWidget(),
    )

    attributes = fields.Field(
        column_name="attributes",
        attribute="attributes",
        widget=JSONWidget(),
    )

    class Meta:
        model = CatalogItem

        #
        # Current model does not yet have a dedicated stable
        # catalog item identifier, therefore Django's primary
        # key is used.
        #
        # Recommended future replacement:
        #
        # import_id_fields = ("item_id",)
        #
        import_id_fields = (
            "id",
        )

        fields = (
            "id",
            "provider",
            "category",
            "title",
            "short_description",
            "price",
            "price_unit",
            "location",
            "availability",
            "fulfillment",
            "attributes",
            "currency_status",
            "validation_status",
            "risk_level",
            "quality_flag",
            "screening_notes",
            "screened_by",
            "screened_at",
        )

        export_order = (
            "id",
            "provider",
            "category",
            "title",
            "short_description",
            "price",
            "price_unit",
            "location",
            "availability",
            "fulfillment",
            "attributes",
            "currency_status",
            "validation_status",
            "risk_level",
            "quality_flag",
            "screening_notes",
            "screened_by",
            "screened_at",
        )

        skip_unchanged = True
        report_skipped = True
        use_bulk = False


# =========================================================
# PROVIDER MEMBERSHIP
# =========================================================

class ProviderMembershipResource(resources.ModelResource):
    """
    Import / export provider membership records.

    Users are referenced by email and providers by provider_id.
    """

    user = fields.Field(
        column_name="user",
        attribute="user",
        widget=ForeignKeyWidget(
            User,
            field="email",
        ),
    )

    provider = fields.Field(
        column_name="provider",
        attribute="provider",
        widget=ForeignKeyWidget(
            Provider,
            field="provider_id",
        ),
    )

    class Meta:
        model = ProviderMembership

        import_id_fields = (
            "id",
        )

        fields = (
            "id",
            "user",
            "provider",
            "role",
        )

        export_order = (
            "id",
            "user",
            "provider",
            "role",
        )

        skip_unchanged = True
        report_skipped = True
        use_bulk = False