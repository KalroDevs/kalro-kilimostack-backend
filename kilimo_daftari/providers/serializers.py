from rest_framework import serializers

from .models import CatalogItem, Provider, ProviderMembership, ServiceCategory


class ProviderSerializer(serializers.ModelSerializer):
    category_codes = serializers.SerializerMethodField()

    class Meta:
        model = Provider
        fields = [
            "id",
            "provider_id",
            "name",
            "institution_type",
            "contact_email",
            "contact_phone",
            "website",
            "description",
            "is_active",
            "category_codes",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]

    def get_category_codes(self, obj) -> list[str]:
        return list(
            obj.catalog_items.filter(quality_flag="ready_to_certify")
            .values_list("category__code", flat=True)
            .distinct()
        )


class ProviderMembershipSerializer(serializers.ModelSerializer):
    provider_name = serializers.CharField(source="provider.name", read_only=True)

    class Meta:
        model = ProviderMembership
        fields = ["id", "user", "provider", "provider_name", "role", "created_at"]
        read_only_fields = ["id", "created_at"]


class ServiceCategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = ServiceCategory
        fields = ["id", "code", "label", "description", "schema_hint", "is_active"]
        read_only_fields = ["id"]


class CatalogItemSerializer(serializers.ModelSerializer):
    provider_name = serializers.CharField(source="provider.name", read_only=True)
    provider_id_slug = serializers.CharField(source="provider.provider_id", read_only=True)
    category_code = serializers.CharField(source="category.code", read_only=True)
    category_label = serializers.CharField(source="category.label", read_only=True)

    class Meta:
        model = CatalogItem
        fields = [
            "id",
            "provider",
            "provider_name",
            "provider_id_slug",
            "category",
            "category_code",
            "category_label",
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
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]


class CatalogItemScreeningSerializer(serializers.ModelSerializer):
    """Mirrors advisory.ScreeningUpdateSerializer -- same workflow, different model."""

    class Meta:
        model = CatalogItem
        fields = ["currency_status", "validation_status", "risk_level", "quality_flag", "screening_notes"]
