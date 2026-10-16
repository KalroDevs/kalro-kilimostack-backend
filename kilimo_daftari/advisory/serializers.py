"""
Serializers for the KALRO Advisory Content Corpus.

Two families live here:

1. **Spec-exact ingestion/export serializers** -- field names match the
   ``Advisory Content Import JSON Specification v0.1`` verbatim (including
   the nested ``content`` array and ``advisory_safety`` object). Used by
   ``POST /api/v1/ingest/`` and by the sync payload sent to the AI Layer.

2. **Workflow serializers** -- smaller payloads for the Screen & Classify
   review step and the per-chunk scientist decision endpoint.

Source exports are looser than the spec table suggests (e.g.
``content_type: "PDF brochure"`` rather than an enum value, and empty
strings instead of nulls for optional dates), so date fields and
``content_type`` are validated leniently here rather than as strict Django
model choices/DateFields.
"""

from django.contrib.auth import get_user_model

from rest_framework import serializers

from .models import (
    AdvisoryResource,
    ContentSection,
    ReviewDecisionChoices,
    SectionReviewLog,
    ThematicArea,
    ValueChain,
)


User = get_user_model()


# ===========================================================================
# Reusable brief serializers
# ===========================================================================
class ValueChainBriefSerializer(serializers.ModelSerializer):
    class Meta:
        model = ValueChain
        fields = ("id", "name", "slug")


class ThematicAreaBriefSerializer(serializers.ModelSerializer):
    class Meta:
        model = ThematicArea
        fields = ("id", "name", "slug")


class UserBriefSerializer(serializers.ModelSerializer):
    full_name = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = ("id", "email", "full_name")
        read_only_fields = fields

    def get_full_name(self, obj) -> str:
        return obj.get_full_name() or obj.get_username()


# ===========================================================================
# Lookup tables
# ===========================================================================
class ValueChainSerializer(serializers.ModelSerializer):
    class Meta:
        model = ValueChain
        fields = (
            "id",
            "name",
            "slug",
            "sector",
            "description",
            "is_active",
            "created_at",
        )
        read_only_fields = ("id", "slug", "created_at")


class ThematicAreaSerializer(serializers.ModelSerializer):
    class Meta:
        model = ThematicArea
        fields = (
            "id",
            "name",
            "slug",
            "description",
            "is_active",
            "created_at",
        )
        read_only_fields = ("id", "slug", "created_at")


# ===========================================================================
# ContentSection (nested under AdvisoryResource)
# ===========================================================================
class ContentSectionSerializer(serializers.ModelSerializer):
    """
    Section payload inside ``AdvisoryResourceSerializer.content``.

    ``content_id`` is unique at the DB level, but this serializer is nested
    inside ``AdvisoryResourceSerializer``'s create/update, which upserts by
    ``content_id`` itself. Disable DRF's auto-generated UniqueValidator so
    re-submitting the same resource doesn't fail validation before the
    upsert logic runs.

    ``value_chains`` / ``thematic_areas`` are written as slugs (via the
    ``*_slugs`` fields) and read back as nested ``{id, name, slug}`` objects.
    """

    content_id = serializers.CharField(validators=[])

    # Read side
    value_chains = ValueChainBriefSerializer(many=True, read_only=True)
    thematic_areas = ThematicAreaBriefSerializer(many=True, read_only=True)
    assigned_scientist = UserBriefSerializer(read_only=True)
    reviewed_by = UserBriefSerializer(read_only=True)
    senior_reviewer = UserBriefSerializer(read_only=True)

    # Write side (slug lists)
    value_chain_slugs = serializers.ListField(
        child=serializers.SlugField(),
        write_only=True,
        required=False,
    )
    thematic_area_slugs = serializers.ListField(
        child=serializers.SlugField(),
        write_only=True,
        required=False,
    )

    # Write side (user emails)
    assigned_scientist_email = serializers.SlugRelatedField(
        slug_field="email",
        queryset=User.objects.all(),
        write_only=True,
        required=False,
        allow_null=True,
        source="assigned_scientist",
    )
    senior_reviewer_email = serializers.SlugRelatedField(
        slug_field="email",
        queryset=User.objects.all(),
        write_only=True,
        required=False,
        allow_null=True,
        source="senior_reviewer",
    )

    class Meta:
        model = ContentSection
        fields = [
            "id",
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

            "value_chains",
            "thematic_areas",
            "value_chain_slugs",
            "thematic_area_slugs",

            "status",
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
            "evidence_citations",
            "version",
            "supersedes",
            "token_count",
            "content_hash",

            "assigned_scientist",
            "assigned_scientist_email",
            "reviewed_by",
            "reviewed_at",
            "senior_reviewer",
            "senior_reviewer_email",

            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "content_hash",
            "reviewed_by",
            "reviewed_at",
            "review_decision",
            "review_notes",
            "suggested_edits",
            "corrected_text",
            "created_at",
            "updated_at",
        ]

    def validate_confidence_score(self, value):
        if value is not None and not 0 <= value <= 100:
            raise serializers.ValidationError("confidence_score must be 0–100.")
        return value

    # -- Helpers used by the parent resource serializer --------------------
    @staticmethod
    def _resolve_slugs(model, slugs, field_label):
        if not slugs:
            return []
        objects = list(model.objects.filter(slug__in=slugs))
        missing = set(slugs) - {o.slug for o in objects}
        if missing:
            raise serializers.ValidationError(
                {field_label: f"Unknown slugs: {sorted(missing)}"}
            )
        return objects

    def pop_m2m_slugs(self, data):
        """Pop the write-only slug lists so the parent can sync them."""
        return {
            "value_chains": data.pop("value_chain_slugs", None),
            "thematic_areas": data.pop("thematic_area_slugs", None),
        }

    def apply_m2m(self, instance, slugs_by_field):
        for field, slugs in (slugs_by_field or {}).items():
            if slugs is None:
                continue
            model = ContentSection._meta.get_field(field).related_model
            objects = self._resolve_slugs(model, slugs, f"{field}_slugs")
            getattr(instance, field).set(objects)


class ContentSectionListSerializer(serializers.ModelSerializer):
    """Compact representation for list endpoints."""

    resource_slug = serializers.CharField(source="resource.slug", read_only=True)

    class Meta:
        model = ContentSection
        fields = (
            "id",
            "content_id",
            "resource",
            "resource_slug",
            "reading_order",
            "content_header",
            "status",
            "review_stage",
            "governance_flag",
            "is_quarantined",
            "assigned_scientist",
            "updated_at",
        )
        read_only_fields = fields


# ===========================================================================
# advisory_safety (nested object in the JSON spec)
# ===========================================================================
class AdvisorySafetySerializer(serializers.Serializer):
    """
    Input shape for ``advisory_safety``. Flattened onto ``AdvisoryResource``
    by ``_flatten_advisory_safety``. Kept as a plain Serializer so the JSON
    spec keys round-trip exactly, including ``disclaimer`` (model:
    ``safety_disclaimer``).
    """

    risk_level = serializers.CharField(allow_blank=True, required=False, default="")
    risk_domains = serializers.ListField(
        child=serializers.CharField(), required=False, default=list
    )
    requires_human_review = serializers.BooleanField(required=False, default=False)
    escalation_guidance = serializers.CharField(
        allow_blank=True, required=False, default=""
    )
    disclaimer = serializers.CharField(allow_blank=True, required=False, default="")


# ===========================================================================
# AdvisoryResource
# ===========================================================================
class AdvisoryResourceSerializer(serializers.ModelSerializer):
    """
    Spec-exact serializer: field names match the Advisory Content Import
    JSON Specification v0.1 verbatim (including the nested ``content`` array
    and ``advisory_safety`` object). This is both:

      * the ingestion payload shape (POST /api/v1/ingest/), and
      * the export/sync payload shape sent to the FastAPI AI Layer.
    """

    content = ContentSectionSerializer(
        many=True, source="content_sections", required=False
    )
    advisory_safety = AdvisorySafetySerializer(required=False, write_only=True)
    advisory_safety_out = serializers.SerializerMethodField()

    # Free-form on ingestion (spec lists suggested values, not a closed
    # enum); the model still offers the suggested set as admin choices.
    content_type = serializers.CharField(max_length=40)

    # Accept "", null, or a real date/datetime; coerce blank -> None.
    modified_date = serializers.DateTimeField(required=False, allow_null=True)
    review_date = serializers.DateField(required=False, allow_null=True)
    next_review_date = serializers.DateField(required=False, allow_null=True)

    # Multi-select value chains on the resource.
    value_chains = ValueChainBriefSerializer(many=True, read_only=True)
    value_chain_slugs = serializers.ListField(
        child=serializers.SlugField(),
        write_only=True,
        required=False,
    )

    # Reviewer identity (read-only).
    screened_by = UserBriefSerializer(read_only=True)
    certified_by = UserBriefSerializer(read_only=True)

    def validate_modified_date(self, value):
        return value or None

    def validate_review_date(self, value):
        return value or None

    def validate_next_review_date(self, value):
        return value or None

    def to_internal_value(self, data):
        # Normalize "" -> None for optional date/datetime fields before DRF's
        # field-level parsing runs (DRF's DateField/DateTimeField reject ""
        # outright rather than treating it as "not provided").
        data = dict(data)
        for date_field in ("modified_date", "review_date", "next_review_date"):
            if data.get(date_field) == "":
                data[date_field] = None
        return super().to_internal_value(data)

    class Meta:
        model = AdvisoryResource
        fields = [
            "id",
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
            "sector",

            "value_chains",
            "value_chain_slugs",
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

            "advisory_status",
            "certified_by",
            "certified_at",

            "version",
            "supersedes",

            "content",
            "advisory_safety",
            "advisory_safety_out",

            "currency_status",
            "scientific_accuracy_check",
            "quality_flag",
            "screening_notes",
            "screened_by",
            "screened_at",

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
        ]
        read_only_fields = [
            "id",
            "slug",
            "certified_at",
            "screened_by",
            "screened_at",
            "vector_sync_status",
            "vector_synced_at",
            "vector_sync_error",
            "embedding_model",
            "embedding_dimensions",
            "chunk_count",
            "content_hash",
            "deleted_at",
            "created_at",
            "updated_at",
        ]

    # -- Output: rebuild the nested advisory_safety object -----------------
    def get_advisory_safety_out(self, obj):
        return {
            "risk_level": obj.risk_level,
            "risk_domains": obj.risk_domains,
            "requires_human_review": obj.requires_human_review,
            "escalation_guidance": obj.escalation_guidance,
            "disclaimer": obj.safety_disclaimer,
        }

    # -- Flatten nested input objects onto the model -----------------------
    def _flatten_advisory_safety(self, validated_data):
        safety = validated_data.pop("advisory_safety", None)
        if safety is None:
            return validated_data
        validated_data["risk_level"] = safety.get("risk_level", "")
        validated_data["risk_domains"] = safety.get("risk_domains", [])
        validated_data["requires_human_review"] = safety.get(
            "requires_human_review", False
        )
        validated_data["escalation_guidance"] = safety.get("escalation_guidance", "")
        validated_data["safety_disclaimer"] = safety.get("disclaimer", "")
        return validated_data

    def _sync_value_chains(self, instance, slugs):
        if slugs is None:
            return
        chains = ContentSectionSerializer._resolve_slugs(
            ValueChain, slugs, "value_chain_slugs"
        )
        instance.value_chains.set(chains)

    # -- Create ------------------------------------------------------------
    def create(self, validated_data):
        sections_data = validated_data.pop("content_sections", []) or []
        vc_slugs = validated_data.pop("value_chain_slugs", None)
        validated_data = self._flatten_advisory_safety(validated_data)

        resource = AdvisoryResource.objects.create(**validated_data)
        self._sync_value_chains(resource, vc_slugs)

        for section_data in sections_data:
            section_data = dict(section_data)
            m2m = ContentSectionSerializer().pop_m2m_slugs(section_data)
            section = ContentSection.objects.create(resource=resource, **section_data)
            ContentSectionSerializer().apply_m2m(section, m2m)
        return resource

    # -- Update ------------------------------------------------------------
    def update(self, instance, validated_data):
        sections_data = validated_data.pop("content_sections", None)
        vc_slugs = validated_data.pop("value_chain_slugs", None)
        validated_data = self._flatten_advisory_safety(validated_data)

        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()

        if vc_slugs is not None:
            self._sync_value_chains(instance, vc_slugs)

        if sections_data is not None:
            existing_ids = {s.content_id for s in instance.content_sections.all()}
            incoming_ids = {s["content_id"] for s in sections_data}
            instance.content_sections.filter(
                content_id__in=existing_ids - incoming_ids
            ).delete()

            for section_data in sections_data:
                section_data = dict(section_data)
                m2m = ContentSectionSerializer().pop_m2m_slugs(section_data)
                section, _created = ContentSection.objects.update_or_create(
                    content_id=section_data["content_id"],
                    defaults={**section_data, "resource": instance},
                )
                ContentSectionSerializer().apply_m2m(section, m2m)

        return instance


class AdvisoryResourceListSerializer(serializers.ModelSerializer):
    """Compact representation for list endpoints."""

    institution_name = serializers.CharField(
        source="institution.name", read_only=True, default=None
    )
    value_chains = ValueChainBriefSerializer(many=True, read_only=True)

    class Meta:
        model = AdvisoryResource
        fields = (
            "id",
            "title",
            "slug",
            "sector",
            "content_type",
            "language",
            "institution",
            "institution_name",
            "value_chains",
            "advisory_status",
            "quality_flag",
            "risk_level",
            "vector_sync_status",
            "is_deleted",
            "updated_at",
        )
        read_only_fields = fields


# ===========================================================================
# Screen & Classify workflow
# ===========================================================================
class ScreeningUpdateSerializer(serializers.ModelSerializer):
    """
    Lightweight serializer for the Screen & Classify review workflow -- used
    by ``PATCH /api/v1/resources/{id}/screen/`` so reviewers can update just
    the screening columns without resubmitting the whole resource.
    """

    class Meta:
        model = AdvisoryResource
        fields = [
            "currency_status",
            "scientific_accuracy_check",
            "validation_status",
            "risk_level",
            "advisory_status",
            "quality_flag",
            "screening_notes",
        ]


class SectionReviewDecisionSerializer(serializers.Serializer):
    """
    Input serializer for the per-chunk scientist review endpoint.

    POST /api/v1/sections/{content_id}/review/
    {
        "decision": "approve_with_edits",
        "notes": "Tightened the pesticide dosage.",
        "suggested_edits": "Apply 2.5 ml/L ...",
        "confidence": 90
    }
    """

    decision = serializers.ChoiceField(choices=ReviewDecisionChoices.choices)
    notes = serializers.CharField(required=False, allow_blank=True, default="")
    suggested_edits = serializers.CharField(
        required=False, allow_blank=True, default=""
    )
    confidence = serializers.IntegerField(
        required=False, allow_null=True, min_value=0, max_value=100
    )

    def validate(self, attrs):
        decision = attrs.get("decision")
        if decision in (
            ReviewDecisionChoices.APPROVE_WITH_EDITS,
            ReviewDecisionChoices.REQUEST_REVISION,
        ) and not attrs.get("suggested_edits"):
            raise serializers.ValidationError(
                {
                    "suggested_edits": (
                        "Provide suggested edits when approving with edits or "
                        "requesting revision."
                    )
                }
            )
        return attrs


class SectionReviewLogSerializer(serializers.ModelSerializer):
    """Read-only audit log entries."""

    actor = UserBriefSerializer(read_only=True)
    section_content_id = serializers.CharField(
        source="section.content_id", read_only=True
    )

    class Meta:
        model = SectionReviewLog
        fields = (
            "id",
            "section",
            "section_content_id",
            "actor",
            "decision",
            "previous_status",
            "new_status",
            "governance_flag",
            "notes",
            "confidence_score",
            "created_at",
        )
        read_only_fields = fields