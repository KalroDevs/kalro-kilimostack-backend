from rest_framework import serializers

from .models import AdvisoryResource, ContentSection


class ContentSectionSerializer(serializers.ModelSerializer):
    # content_id is unique at the DB level, but this serializer is nested
    # inside AdvisoryResourceSerializer's create/update, which already
    # upserts by content_id itself (see update_or_create below). Disable
    # DRF's auto-generated UniqueValidator here so re-submitting the same
    # resource (create-then-update, or a straight re-import) doesn't fail
    # validation before our upsert logic ever runs.
    content_id = serializers.CharField(validators=[])

    class Meta:
        model = ContentSection
        fields = [
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
        ]


class AdvisorySafetySerializer(serializers.Serializer):
    """Mirrors the JSON spec's ``advisory_safety`` object; flattened onto the model."""

    risk_level = serializers.CharField(allow_blank=True, required=False)
    risk_domains = serializers.ListField(child=serializers.CharField(), required=False)
    requires_human_review = serializers.BooleanField(required=False, default=False)
    escalation_guidance = serializers.CharField(allow_blank=True, required=False)
    disclaimer = serializers.CharField(allow_blank=True, required=False)


class AdvisoryResourceSerializer(serializers.ModelSerializer):
    """
    Spec-exact serializer: field names match the Advisory Content Import
    JSON Specification v0.1 verbatim (including the nested ``content`` array
    and ``advisory_safety`` object), so this is both:

      * the ingestion payload shape (POST /api/v1/ingest/), and
      * the export/sync payload shape sent on to the FastAPI AI Layer.

    Screening/classification fields from the Screen & Classify workbook are
    included as additional top-level fields (``currency_status``,
    ``scientific_accuracy_check``, ``quality_flag``, ``screening_notes``)
    that sit alongside -- not inside -- the spec's own fields.

    Real-world source exports are looser than the spec table suggests
    (e.g. ``content_type: "PDF brochure"`` rather than an enum value, and
    empty strings instead of nulls for optional dates) -- so date fields and
    ``content_type`` are validated leniently here rather than as strict
    Django model choices/DateFields.
    """

    content = ContentSectionSerializer(many=True, source="content_sections", required=False)
    advisory_safety = serializers.SerializerMethodField()

    # Free-form on ingestion (spec lists suggested values, not a closed enum);
    # the underlying model field still offers the suggested set as admin choices.
    content_type = serializers.CharField(max_length=40)

    # Accept "", null, or a real date/datetime; coerce blank -> None.
    modified_date = serializers.DateTimeField(required=False, allow_null=True)
    review_date = serializers.DateField(required=False, allow_null=True)
    next_review_date = serializers.DateField(required=False, allow_null=True)

    def validate_modified_date(self, value):
        return value or None

    def validate_review_date(self, value):
        return value or None

    def validate_next_review_date(self, value):
        return value or None

    def to_internal_value(self, data):
        # Normalize "" -> None for optional date/datetime fields before DRF's
        # own field-level parsing runs (DRF's DateField/DateTimeField reject
        # "" outright rather than treating it as "not provided").
        data = dict(data)
        for date_field in ("modified_date", "review_date", "next_review_date"):
            if data.get(date_field) == "":
                data[date_field] = None
        return super().to_internal_value(data)

    class Meta:
        model = AdvisoryResource
        fields = [
            # Core resource fields (JSON spec)
            "id",
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
            "content",
            "advisory_safety",
            # Screen & Classify fields (Excel template)
            "currency_status",
            "scientific_accuracy_check",
            "quality_flag",
            "screening_notes",
            # Sync bookkeeping (read-only, not part of the JSON spec)
            "vector_sync_status",
            "vector_synced_at",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "vector_sync_status", "vector_synced_at", "created_at", "updated_at"]

    def get_advisory_safety(self, obj):
        return {
            "risk_level": obj.risk_level,
            "risk_domains": obj.risk_domains,
            "requires_human_review": obj.requires_human_review,
            "escalation_guidance": obj.escalation_guidance,
            "disclaimer": obj.safety_disclaimer,
        }

    def _flatten_advisory_safety(self, validated_data, raw_data):
        safety = raw_data.get("advisory_safety") or {}
        validated_data["risk_level"] = safety.get("risk_level", "")
        validated_data["risk_domains"] = safety.get("risk_domains", [])
        validated_data["requires_human_review"] = safety.get("requires_human_review", False)
        validated_data["escalation_guidance"] = safety.get("escalation_guidance", "")
        validated_data["safety_disclaimer"] = safety.get("disclaimer", "")
        return validated_data

    def create(self, validated_data):
        sections_data = validated_data.pop("content_sections", [])
        validated_data = self._flatten_advisory_safety(validated_data, self.initial_data)
        resource = AdvisoryResource.objects.create(**validated_data)
        for section in sections_data:
            ContentSection.objects.create(resource=resource, **section)
        return resource

    def update(self, instance, validated_data):
        sections_data = validated_data.pop("content_sections", None)
        validated_data = self._flatten_advisory_safety(validated_data, self.initial_data)
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()

        if sections_data is not None:
            existing_ids = {s.content_id for s in instance.content_sections.all()}
            incoming_ids = {s["content_id"] for s in sections_data}
            instance.content_sections.filter(content_id__in=existing_ids - incoming_ids).delete()
            for section in sections_data:
                ContentSection.objects.update_or_create(
                    content_id=section["content_id"],
                    defaults={**section, "resource": instance},
                )
        return instance


class ScreeningUpdateSerializer(serializers.ModelSerializer):
    """
    Lightweight serializer for the Screen & Classify review workflow --
    used by PATCH /api/v1/resources/{id}/screen/ so reviewers can update
    just the screening columns without resubmitting the whole resource.
    """

    class Meta:
        model = AdvisoryResource
        fields = [
            "currency_status",
            "scientific_accuracy_check",
            "validation_status",
            "risk_level",
            "quality_flag",
            "screening_notes",
        ]
