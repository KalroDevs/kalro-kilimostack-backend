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
    LanguageChoices,
    ReviewDecisionChoices,
    SectionReviewLog,
    SectorChoices,
    ThematicArea,
    ValueChain,
)


User = get_user_model()


# ===========================================================================
# Shared helpers
# ===========================================================================
def _normalize_slug_list(slugs):
    """Strip, drop blanks, and de-duplicate while preserving order."""
    if not slugs:
        return []
    seen = set()
    out = []
    for s in slugs:
        s = (s or "").strip()
        if s and s not in seen:
            seen.add(s)
            out.append(s)
    return out


def _resolve_slugs(model, slugs, field_label):
    """
    Turn a list of slugs into a list of model instances.

    Raises a ``ValidationError`` naming every unknown slug so the API
    consumer sees exactly what failed.
    """
    slugs = _normalize_slug_list(slugs)
    if not slugs:
        return []
    objects = list(model.objects.filter(slug__in=slugs))
    by_slug = {o.slug: o for o in objects}
    missing = [s for s in slugs if s not in by_slug]
    if missing:
        raise serializers.ValidationError(
            {field_label: f"Unknown slugs: {sorted(missing)}"}
        )
    return [by_slug[s] for s in slugs]


def _apply_m2m(instance, slugs_by_field):
    """Set each M2M field on ``instance`` from a {field_name: [slugs]} map."""
    for field, slugs in (slugs_by_field or {}).items():
        if slugs is None:
            continue
        model = instance._meta.get_field(field).related_model
        objects = _resolve_slugs(model, slugs, f"{field}_slugs")
        getattr(instance, field).set(objects)


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
        if hasattr(obj, "get_full_name"):
            name = obj.get_full_name() or ""
            if name:
                return name
        return obj.get_username()


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
    content_text = serializers.CharField(
        allow_blank=False,
        trim_whitespace=False,
    )

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
        allow_empty=True,
    )
    thematic_area_slugs = serializers.ListField(
        child=serializers.SlugField(),
        write_only=True,
        required=False,
        allow_empty=True,
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
            raise serializers.ValidationError("confidence_score must be 0-100.")
        return value

    def pop_m2m_slugs(self, data):
        """Pop the write-only slug lists so the parent can sync them."""
        return {
            "value_chains": data.pop("value_chain_slugs", None),
            "thematic_areas": data.pop("thematic_area_slugs", None),
        }

    def apply_m2m(self, instance, slugs_by_field):
        """Kept for backward compatibility; delegates to the shared helper."""
        _apply_m2m(instance, slugs_by_field)


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
        allow_empty=True,
    )

    # Reviewer identity (read-only).
    screened_by = UserBriefSerializer(read_only=True)
    certified_by = UserBriefSerializer(read_only=True)

    # ------------------------------------------------------------------
    # Input normalisation
    # ------------------------------------------------------------------
    def to_internal_value(self, data):
        # Normalize "" -> None for optional date/datetime fields before DRF's
        # field-level parsing runs (DRF's DateField/DateTimeField reject ""
        # outright rather than treating it as "not provided").
        data = dict(data)
        for date_field in ("modified_date", "review_date", "next_review_date"):
            if data.get(date_field) == "":
                data[date_field] = None
        return super().to_internal_value(data)

    # ------------------------------------------------------------------
    # Field-level validation
    # ------------------------------------------------------------------
    def validate_sector(self, value):
        valid = {c for c, _label in SectorChoices.choices}
        if value not in valid:
            raise serializers.ValidationError(
                f"sector must be one of {sorted(valid)}."
            )
        return value

    def validate_language(self, value):
        valid = {c for c, _label in LanguageChoices.choices}
        if value not in valid:
            raise serializers.ValidationError(
                f"language must be one of {sorted(valid)}."
            )
        return value

    def validate_content(self, value):
        """
        Guard the DB's ``UniqueConstraint(resource, reading_order)`` with a
        friendly error instead of an IntegrityError.
        """
        if value is None:
            return value
        content_ids = [s.get("content_id") for s in value]
        if len(content_ids) != len(set(content_ids)):
            raise serializers.ValidationError(
                "Duplicate content_id values in 'content'."
            )
        orders = [s.get("reading_order") for s in value]
        if len(orders) != len(set(orders)):
            raise serializers.ValidationError(
                "Duplicate reading_order values in 'content'."
            )
        return value

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

    # ------------------------------------------------------------------
    # Output: rebuild the nested advisory_safety object
    # ------------------------------------------------------------------
    def get_advisory_safety_out(self, obj):
        return {
            "risk_level": obj.risk_level,
            "risk_domains": obj.risk_domains,
            "requires_human_review": obj.requires_human_review,
            "escalation_guidance": obj.escalation_guidance,
            "disclaimer": obj.safety_disclaimer,
        }

    # ------------------------------------------------------------------
    # Flatten nested input objects onto the model
    # ------------------------------------------------------------------
    # Mapping of nested safety keys -> flat model fields.
    _SAFETY_FIELD_MAP = {
        "risk_level": "risk_level",
        "risk_domains": "risk_domains",
        "requires_human_review": "requires_human_review",
        "escalation_guidance": "escalation_guidance",
        "disclaimer": "safety_disclaimer",
    }

    def _flatten_advisory_safety(self, validated_data):
        """
        Copy the nested ``advisory_safety`` payload onto the flat model
        fields. On a partial update, only the keys the caller actually sent
        are copied, so omitting ``requires_human_review`` doesn't silently
        reset it to False.
        """
        safety = validated_data.pop("advisory_safety", None)
        if safety is None:
            return validated_data
        partial = bool(getattr(self, "partial", False))
        for nested_key, model_field in self._SAFETY_FIELD_MAP.items():
            if partial and nested_key not in safety:
                continue
            validated_data[model_field] = safety.get(
                nested_key, "" if not isinstance(safety.get(nested_key), (list, bool)) else safety.get(nested_key)
            )
        return validated_data

    def _sync_value_chains(self, instance, slugs):
        if slugs is None:
            return
        chains = _resolve_slugs(ValueChain, slugs, "value_chain_slugs")
        instance.value_chains.set(chains)

    # ------------------------------------------------------------------
    # Create
    # ------------------------------------------------------------------
    def create(self, validated_data):
        sections_data = validated_data.pop("content_sections", []) or []
        vc_slugs = validated_data.pop("value_chain_slugs", None)
        validated_data = self._flatten_advisory_safety(validated_data)

        resource = AdvisoryResource.objects.create(**validated_data)
        self._sync_value_chains(resource, vc_slugs)

        section_serializer = ContentSectionSerializer()
        for section_data in sections_data:
            section_data = dict(section_data)
            m2m = section_serializer.pop_m2m_slugs(section_data)
            section = ContentSection.objects.create(
                resource=resource, **section_data
            )
            _apply_m2m(section, m2m)
        return resource

    # ------------------------------------------------------------------
    # Update
    # ------------------------------------------------------------------
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
            existing_ids = {
                s.content_id for s in instance.content_sections.all()
            }
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
                _apply_m2m(section, m2m)

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

    Always use this serializer with ``partial=True`` so a client that omits
    ``risk_level`` doesn't clobber the value set at ingestion time via the
    ``advisory_safety`` block.
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

        if decision == ReviewDecisionChoices.ESCALATE and not attrs.get("notes"):
            raise serializers.ValidationError(
                {
                    "notes": (
                        "Explain why this chunk is being escalated to a "
                        "senior reviewer."
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