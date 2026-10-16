"""
Data model for the KALRO Advisory Content Corpus.

Two sources define this schema:

1. ``Advisory Content Import JSON Specification v0.1`` (JSON_Data_Specification.docx)
   -- the wire format KALRO / partners use to submit resources for ingestion
   into the Kenya AI Advisory Platform. Every top-level field in that spec has
   a matching column or JSON field below.

2. The "Screen & Classify" working template (Excel workbook produced earlier
   in this workshop's tooling) -- the human screening workflow that checks
   scientific accuracy & currency and sorts content by crop/topic/content
   type before it is certified. Those columns are reproduced here as
   first-class fields so the same review workflow that ran in spreadsheets
   can run against this database and drive what gets synced to the AI
   Layer's vector index.

Additionally, per-chunk scientist validation and content governance are
supported on ``ContentSection`` (status, assigned scientist, review stage,
governance flags, quarantine, audit log) so KALRO scientists can certify at
the granularity the AI Layer actually embeds.

Chunks are also taggable with multi-select value chains and cross-cutting
thematic areas (One Health, Productivity, Animal Health, Plant Health,
Climate Smart Agriculture, ...) via lookup tables, for sharper retrieval
and analytics.
"""

import hashlib
import os
import uuid

from django.conf import settings
from django.core.validators import (
    FileExtensionValidator,
    MaxValueValidator,
    MinValueValidator,
)
from django.db import models, transaction
from django.db.models import Q
from django.utils import timezone
from django.utils.text import slugify


# ===========================================================================
# Choices
# ===========================================================================
class ContentTypeChoices(models.TextChoices):
    PDF = "PDF", "PDF"
    HTML = "HTML", "HTML"
    FACTSHEET = "factsheet", "Factsheet"
    TRAINING_MANUAL = "training_manual", "Training Manual"
    FARMER_GUIDE = "farmer_guide", "Farmer Guide"
    TECHNICAL_MANUAL = "technical_manual", "Technical Manual"
    QA_PAIR = "qa_pair", "Q&A Pair"
    DATASET_DESCRIPTION = "dataset_description", "Dataset Description"


class SectorChoices(models.TextChoices):
    CROPS = "crops", "Crops"
    LIVESTOCK = "livestock", "Livestock"
    AQUACULTURE = "aquaculture", "Aquaculture"
    NATURAL_RESOURCE_MANAGEMENT = "natural_resource_management", "Natural Resource Management"
    CROSS_CUTTING = "cross_cutting", "Cross-Cutting"


class ValidationStatusChoices(models.TextChoices):
    SOURCE_VALIDATED = "source_validated", "Source Validated"
    EXPERT_REVIEWED = "expert_reviewed", "Expert Reviewed"
    FIELD_VALIDATED = "field_validated", "Field Validated"
    REQUIRES_REVIEW = "requires_review", "Requires Review"
    DEPRECATED = "deprecated", "Deprecated"


class CurrencyStatusChoices(models.TextChoices):
    CURRENT = "current", "Current"
    NEEDS_UPDATE = "needs_update", "Needs Update"
    OUTDATED = "outdated", "Outdated"
    NEEDS_VERIFICATION = "needs_verification", "Needs Verification"


class AccuracyCheckChoices(models.TextChoices):
    VERIFIED = "verified", "Verified"
    NEEDS_REVIEW = "needs_review", "Needs Review"
    FLAGGED_INACCURATE = "flagged_inaccurate", "Flagged - Inaccurate"


class RiskLevelChoices(models.TextChoices):
    LOW = "low", "Low"
    MEDIUM = "medium", "Medium"
    HIGH = "high", "High"


class QualityFlagChoices(models.TextChoices):
    READY_TO_CERTIFY = "ready_to_certify", "Ready to Certify"
    NEEDS_REVIEW = "needs_review", "Needs Review"
    NEEDS_UPDATE = "needs_update", "Needs Update"
    DUPLICATE = "duplicate", "Duplicate"
    REJECT = "reject", "Reject"


class VectorSyncStatusChoices(models.TextChoices):
    NOT_SYNCED = "not_synced", "Not Synced"
    PENDING = "pending", "Pending"
    SYNCED = "synced", "Synced"
    FAILED = "failed", "Failed"


class AdvisoryStatusChoices(models.TextChoices):
    """High-level certification outcome set by the review board / KALRO."""
    VALIDATED = "validated", "Validated"
    VALIDATED_WITH_MINOR_EDITS = "validated_minor_edits", "Validated with Minor Edits"
    MAJOR_REVISION = "major_revision", "Major Revision"
    NOT_VALIDATED = "not_validated", "Not Validated"


class LanguageChoices(models.TextChoices):
    EN = "en", "English"
    SW = "sw", "Kiswahili"
    FR = "fr", "French"
    AR = "ar", "Arabic"
    SO = "so", "Somali"


# --- Per-section governance choices ---------------------------------------
class SectionStatusChoices(models.TextChoices):
    """Per-section review outcome set by the assigned KALRO scientist."""
    VALIDATED = "validated", "Validated"
    VALIDATED_WITH_MINOR_EDITS = "validated_minor_edits", "Validated with Minor Edits"
    MAJOR_REVISION = "major_revision", "Major Revision"
    NOT_VALIDATED = "not_validated", "Not Validated"


class ReviewDecisionChoices(models.TextChoices):
    """Finer-grained decision used for audit trails inside the review log."""
    APPROVE = "approve", "Approve"
    APPROVE_WITH_EDITS = "approve_with_edits", "Approve with Edits"
    REQUEST_REVISION = "request_revision", "Request Revision"
    REJECT = "reject", "Reject"
    ESCALATE = "escalate", "Escalate to Senior Reviewer"


class GovernanceFlagChoices(models.TextChoices):
    """Flags a scientist can raise on a chunk for governance follow-up."""
    NONE = "", "None"
    SENSITIVE_CONTENT = "sensitive_content", "Sensitive Content"
    POLICY_CONFLICT = "policy_conflict", "Policy Conflict"
    OUTDATED_SCIENCE = "outdated_science", "Outdated Science"
    UNSUPPORTED_CLAIM = "unsupported_claim", "Unsupported Claim"
    LOCAL_CONTEXT_MISSING = "local_context_missing", "Local Context Missing"
    COPYRIGHT_CONCERN = "copyright_concern", "Copyright Concern"
    DUPLICATE_CONTENT = "duplicate_content", "Duplicate Content"


class ChunkReviewStageChoices(models.TextChoices):
    """Workflow stage for the per-chunk review pipeline."""
    INGESTED = "ingested", "Ingested"
    AUTO_SCREENED = "auto_screened", "Auto-Screened"
    SCIENTIST_REVIEW = "scientist_review", "Scientist Review"
    SENIOR_REVIEW = "senior_review", "Senior Review"
    APPROVED = "approved", "Approved"
    REJECTED = "rejected", "Rejected"


# ===========================================================================
# Value chain lookup
# ===========================================================================
class ValueChain(models.Model):
    """
    Controlled vocabulary for value chains (e.g. Maize, Dairy, Poultry,
    Aquaculture - Tilapia). Modelled as a table rather than a CharField so
    analytics, filtering, and vocabulary curation are possible.
    """

    name = models.CharField(max_length=120, unique=True)
    slug = models.SlugField(max_length=140, unique=True, blank=True)
    sector = models.CharField(
        max_length=40, choices=SectorChoices.choices, blank=True, default=""
    )
    description = models.TextField(blank=True, default="")
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name"]
        verbose_name = "Value Chain"
        verbose_name_plural = "Value Chains"

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)[:140]
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name


# ===========================================================================
# Thematic area lookup
# ===========================================================================
class ThematicArea(models.Model):
    """
    Controlled vocabulary for KALRO thematic areas (e.g. One Health,
    Productivity, Animal Health, Plant Health, Climate Smart Agriculture).
    Used as a multi-select on ContentSection so chunks can be tagged for
    cross-cutting programmes and analytics.
    """

    name = models.CharField(max_length=120, unique=True)
    slug = models.SlugField(max_length=140, unique=True, blank=True)
    description = models.TextField(blank=True, default="")
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name"]
        verbose_name = "Thematic Area"
        verbose_name_plural = "Thematic Areas"

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)[:140]
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name


# ===========================================================================
# Upload path helper
# ===========================================================================
def advisory_upload_to(instance, filename):
    """
    Store uploads under a per-publication folder so re-uploads never collide
    and are easy to audit / bulk-delete.
    """
    ext = os.path.splitext(filename)[1].lower()
    safe_name = f"{uuid.uuid4().hex}{ext}"
    pub = instance.slug or "unpublished"
    return os.path.join("advisory_resources", pub, safe_name)


# ===========================================================================
# AdvisoryResource
# ===========================================================================
class AdvisoryResourceManager(models.Manager):
    def ready_for_ai_layer(self):
        return self.filter(quality_flag=QualityFlagChoices.READY_TO_CERTIFY)

    def active(self):
        return self.filter(is_deleted=False)

    def needing_review(self):
        return self.filter(quality_flag=QualityFlagChoices.NEEDS_REVIEW)


class AdvisoryResource(models.Model):
    """
    One row = one advisory resource (PDF manual, factsheet, training guide,
    web page, etc.) -- the top-level object in the JSON specification's
    array. Mirrors the "Content Inventory" -> "Screen & Classify" pipeline.
    """

    # -- Core resource fields (JSON spec section 1) -------------------------
    title = models.CharField(max_length=500)
    slug = models.SlugField(max_length=520, unique=True, blank=True)
    link = models.URLField(max_length=1000, blank=True, default="")
    institution = models.ForeignKey(
        "providers.Provider",
        on_delete=models.PROTECT,
        related_name="advisory_resources",
        null=True,
        blank=True,
        help_text="Institution/provider responsible for this advisory resource.",
    )
    author = models.JSONField(default=list, blank=True, help_text="List of author name strings")
    publish_date = models.CharField(
        max_length=20, blank=True, default="",
        help_text="Raw value as submitted, e.g. 2018/01/08",
    )
    modified_date = models.DateTimeField(null=True, blank=True)
    content_type = models.CharField(max_length=40, choices=ContentTypeChoices.choices)
    language = models.CharField(
        max_length=10, choices=LanguageChoices.choices, default=LanguageChoices.EN
    )
    available_languages = models.JSONField(default=list, blank=True)

    # -- Uploaded source file ---------------------------------------------
    upload_file = models.FileField(
        upload_to=advisory_upload_to,
        blank=True,
        null=True,
        validators=[
            FileExtensionValidator(
                allowed_extensions=[
                    "pdf", "doc", "docx", "xls", "xlsx",
                    "csv", "txt", "html", "htm", "md", "json",
                ]
            )
        ],
        help_text="Original file uploaded by the submitter (PDF, DOCX, XLSX, ...).",
    )
    file_size_bytes = models.PositiveBigIntegerField(null=True, blank=True)
    file_checksum = models.CharField(
        max_length=64, blank=True, default="",
        help_text="SHA-256 of the uploaded file, used for duplicate detection.",
    )
    mime_type = models.CharField(max_length=120, blank=True, default="")

    # -- Classification ----------------------------------------------------
    sector = models.CharField(max_length=40, choices=SectorChoices.choices)
    # Proper M2M multi-select for value chains.
    value_chains = models.ManyToManyField(
        ValueChain,
        related_name="resources",
        blank=True,
        help_text="One or more value chains this resource applies to.",
    )
    # Legacy / denormalized label kept for backwards compatibility and
    # JSON round-tripping (JSON spec sends a single string).
    value_chain = models.CharField(
        max_length=120, blank=True, default="", db_index=True,
        help_text="Legacy single value-chain label (from the JSON spec).",
    )
    commodity = models.JSONField(default=list, blank=True)
    production_system = models.JSONField(default=list, blank=True)
    advisory_domain = models.JSONField(default=list, blank=True)
    target_users = models.JSONField(default=list, blank=True)

    # Nested objects kept as JSON for spec-exact round-tripping.
    geographic_applicability = models.JSONField(
        default=dict, blank=True,
        help_text='{"country": "Kenya", "counties": [...], "agro_ecological_zones": [...], "notes": ""}',
    )
    seasonality = models.JSONField(
        default=dict, blank=True,
        help_text='{"season": [...], "production_stage": [...], "timing_notes": ""}',
    )
    license = models.JSONField(default=dict, blank=True)

    # -- Validation / review ----------------------------------------------
    validation_status = models.CharField(
        max_length=30, choices=ValidationStatusChoices.choices, blank=True, default=""
    )
    validated_by = models.JSONField(default=list, blank=True)
    review_date = models.DateField(null=True, blank=True)
    next_review_date = models.DateField(null=True, blank=True)
    preferred_citation = models.TextField(blank=True, default="")

    # -- High-level certification status ----------------------------------
    advisory_status = models.CharField(
        max_length=30,
        choices=AdvisoryStatusChoices.choices,
        blank=True,
        default="",
        db_index=True,
        help_text="Certification outcome from the review board.",
    )

    # -- advisory_safety (JSON spec) --------------------------------------
    risk_level = models.CharField(
        max_length=10, choices=RiskLevelChoices.choices, blank=True, default=""
    )
    risk_domains = models.JSONField(default=list, blank=True)
    requires_human_review = models.BooleanField(default=False)
    escalation_guidance = models.TextField(blank=True, default="")
    safety_disclaimer = models.TextField(blank=True, default="")

    # -- Screen & Classify fields -----------------------------------------
    currency_status = models.CharField(
        max_length=25, choices=CurrencyStatusChoices.choices, blank=True, default=""
    )
    scientific_accuracy_check = models.CharField(
        max_length=25, choices=AccuracyCheckChoices.choices, blank=True, default=""
    )
    quality_flag = models.CharField(
        max_length=25, choices=QualityFlagChoices.choices, blank=True, default=""
    )
    screening_notes = models.TextField(blank=True, default="")
    screened_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True,
        on_delete=models.SET_NULL, related_name="+",
    )
    screened_at = models.DateTimeField(null=True, blank=True)

    # -- Certification audit trail ----------------------------------------
    certified_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True,
        on_delete=models.SET_NULL, related_name="certified_resources",
    )
    certified_at = models.DateTimeField(null=True, blank=True)

    # -- Versioning / lineage ---------------------------------------------
    version = models.CharField(max_length=20, default="1.0")
    supersedes = models.ForeignKey(
        "self", null=True, blank=True,
        on_delete=models.SET_NULL, related_name="superseded_by",
        help_text="Older resource this one replaces.",
    )

    # -- AI Layer / vector sync tracking ----------------------------------
    vector_sync_status = models.CharField(
        max_length=15,
        choices=VectorSyncStatusChoices.choices,
        default=VectorSyncStatusChoices.NOT_SYNCED,
    )
    vector_synced_at = models.DateTimeField(null=True, blank=True)
    vector_sync_error = models.TextField(blank=True, default="")
    embedding_model = models.CharField(max_length=120, blank=True, default="")
    embedding_dimensions = models.PositiveIntegerField(null=True, blank=True)
    chunk_count = models.PositiveIntegerField(default=0)
    content_hash = models.CharField(
        max_length=64, blank=True, default="",
        help_text="Hash of all section text; lets the sync job skip unchanged resources.",
    )

    # -- Soft delete + audit ----------------------------------------------
    is_deleted = models.BooleanField(default=False)
    deleted_at = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = AdvisoryResourceManager()

    class Meta:
        ordering = ["-updated_at"]
        indexes = [
            models.Index(fields=["sector", "value_chain"]),
            models.Index(fields=["quality_flag"]),
            models.Index(fields=["advisory_status"]),
            models.Index(fields=["risk_level"]),
            models.Index(fields=["vector_sync_status"]),
            models.Index(fields=["is_deleted"]),
        ]

    # -- Helpers -----------------------------------------------------------
    def __str__(self):
        return f"{self.slug} — {self.title}"

    def save(self, *args, **kwargs):
        if not self.slug:
            base = slugify(self.title)[:480] or "resource"
            self.slug = f"{base}-{self.slug}"[:520]
        super().save(*args, **kwargs)

    @property
    def is_ready_for_ai_layer(self) -> bool:
        """Only certified, validated content should feed the RAG index."""
        return (
            self.quality_flag == QualityFlagChoices.READY_TO_CERTIFY
            and self.advisory_status
            in (AdvisoryStatusChoices.VALIDATED, AdvisoryStatusChoices.VALIDATED_WITH_MINOR_EDITS)
        )

    @property
    def is_validated(self) -> bool:
        return self.advisory_status in (
            AdvisoryStatusChoices.VALIDATED,
            AdvisoryStatusChoices.VALIDATED_WITH_MINOR_EDITS,
        )

    def compute_file_checksum(self) -> str:
        """Compute and store the SHA-256 of the uploaded file."""
        if not self.upload_file:
            return ""
        h = hashlib.sha256()
        self.upload_file.seek(0)
        for chunk in self.upload_file.chunks():
            h.update(chunk)
        self.upload_file.seek(0)
        self.file_checksum = h.hexdigest()
        return self.file_checksum

    def mark_synced(self, model_name: str = "", dimensions: int | None = None):
        self.vector_sync_status = VectorSyncStatusChoices.SYNCED
        self.vector_synced_at = timezone.now()
        self.vector_sync_error = ""
        if model_name:
            self.embedding_model = model_name
        if dimensions:
            self.embedding_dimensions = dimensions
        self.save(update_fields=[
            "vector_sync_status", "vector_synced_at", "vector_sync_error",
            "embedding_model", "embedding_dimensions", "updated_at",
        ])

    def soft_delete(self):
        self.is_deleted = True
        self.deleted_at = timezone.now()
        self.save(update_fields=["is_deleted", "deleted_at", "updated_at"])


# ===========================================================================
# ContentSection
# ===========================================================================
class ContentSectionManager(models.Manager):
    def validated(self):
        return self.filter(
            status__in=[
                SectionStatusChoices.VALIDATED,
                SectionStatusChoices.VALIDATED_WITH_MINOR_EDITS,
            ]
        )

    def needing_scientist_review(self):
        return self.filter(review_stage=ChunkReviewStageChoices.SCIENTIST_REVIEW)

    def embedding_ready(self):
        """Return validated chunks without governance flags or quarantine."""
        return self.validated().filter(
            governance_flag="",
            is_quarantined=False,
        )

    def for_thematic_area(self, slug_or_name: str):
        """Filter chunks by thematic area (slug or name, case-insensitive)."""
        return self.filter(
            Q(thematic_areas__slug=slug_or_name)
            | Q(thematic_areas__name__iexact=slug_or_name)
        ).distinct()

    def for_value_chain(self, slug_or_name: str):
        """Filter chunks by value chain (slug or name, case-insensitive)."""
        return self.filter(
            Q(value_chains__slug=slug_or_name)
            | Q(value_chains__name__iexact=slug_or_name)
        ).distinct()


class ContentSection(models.Model):
    """
    One row = one section-level content chunk (JSON spec ``content[]``
    items). This is the granularity the AI Layer chunks and embeds into the
    vector database.

    Each chunk carries its own validation status, assigned scientist, review
    history, and governance flags so that KALRO can certify at *chunk*
    granularity rather than only at the resource level. A resource may be
    "Validated with minor edits" overall while a single section is "Not
    validated" and quarantined from the vector index.

    Chunks are also taggable with multi-select value chains and cross-cutting
    thematic areas for sharper retrieval and analytics.
    """

    resource = models.ForeignKey(
        AdvisoryResource, related_name="content_sections", on_delete=models.CASCADE
    )
    content_id = models.CharField(max_length=200, unique=True)
    reading_order = models.PositiveIntegerField()
    content_header = models.CharField(max_length=300, blank=True, default="")
    content_text = models.TextField()
    page_start = models.PositiveIntegerField(null=True, blank=True)
    page_end = models.PositiveIntegerField(null=True, blank=True)

    # Kept as JSON: each item is {"image_url", "image_text", "image_caption", "page_number"}
    content_images = models.JSONField(default=list, blank=True)
    # Kept as JSON: each item is {"table_id", "table_title", "page_number", "table_text", "table_json"}
    content_tables = models.JSONField(default=list, blank=True)

    content_warnings = models.JSONField(default=list, blank=True)
    content_tags = models.JSONField(default=list, blank=True)

    # ------------------------------------------------------------------
    # Multi-select value chains and thematic areas
    # ------------------------------------------------------------------
    value_chains = models.ManyToManyField(
        ValueChain,
        related_name="content_sections",
        blank=True,
        help_text="Value chains this specific chunk applies to.",
    )
    thematic_areas = models.ManyToManyField(
        ThematicArea,
        related_name="content_sections",
        blank=True,
        help_text="Cross-cutting thematic areas (One Health, Productivity, etc.).",
    )

    # ------------------------------------------------------------------
    # Per-chunk validation status (requested)
    # ------------------------------------------------------------------
    status = models.CharField(
        max_length=30,
        choices=SectionStatusChoices.choices,
        blank=True,
        default="",
        db_index=True,
        help_text="Scientist review outcome for this chunk.",
    )

    # ------------------------------------------------------------------
    # KALRO scientist validation & governance
    # ------------------------------------------------------------------
    assigned_scientist = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="assigned_sections",
        help_text="KALRO scientist responsible for reviewing this chunk.",
    )
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="reviewed_sections",
        help_text="Scientist who last acted on this chunk.",
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)
    review_stage = models.CharField(
        max_length=25,
        choices=ChunkReviewStageChoices.choices,
        default=ChunkReviewStageChoices.INGESTED,
        db_index=True,
    )
    review_decision = models.CharField(
        max_length=25,
        choices=ReviewDecisionChoices.choices,
        blank=True,
        default="",
    )
    review_notes = models.TextField(
        blank=True,
        default="",
        help_text="Scientist rationale for the decision (kept for audit).",
    )
    suggested_edits = models.TextField(
        blank=True,
        default="",
        help_text="Proposed replacement text when status is 'with minor edits' or 'major revision'.",
    )
    corrected_text = models.TextField(
        blank=True,
        default="",
        help_text="Final approved text after applying minor edits (if any).",
    )

    # Governance
    governance_flag = models.CharField(
        max_length=30,
        choices=GovernanceFlagChoices.choices,
        blank=True,
        default="",
        db_index=True,
    )
    governance_notes = models.TextField(blank=True, default="")
    is_quarantined = models.BooleanField(
        default=False,
        help_text="If True, this chunk will not be embedded into the vector index.",
    )
    requires_senior_review = models.BooleanField(default=False)
    senior_reviewer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="senior_reviewed_sections",
    )

    # Scientific provenance
    evidence_citations = models.JSONField(
        default=list,
        blank=True,
        help_text='List of {"source": "...", "url": "...", "year": 2021} supporting this chunk.',
    )
    confidence_score = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
        validators=[MinValueValidator(0), MaxValueValidator(100)],
        help_text="Scientist confidence 0-100 that the chunk is accurate and current.",
    )
    currency_checked_on = models.DateField(null=True, blank=True)

    # Versioning
    version = models.PositiveIntegerField(default=1)
    supersedes = models.ForeignKey(
        "self",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="superseded_by",
    )

    # ------------------------------------------------------------------
    # AI / embedding fields
    # ------------------------------------------------------------------
    token_count = models.PositiveIntegerField(null=True, blank=True)
    content_hash = models.CharField(max_length=64, blank=True, default="")

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = ContentSectionManager()

    class Meta:
        ordering = ["resource", "reading_order"]
        constraints = [
            models.UniqueConstraint(
                fields=["resource", "reading_order"],
                name="unique_reading_order_per_resource",
            )
        ]
        indexes = [
            models.Index(fields=["resource", "reading_order"]),
            models.Index(fields=["content_hash"]),
            models.Index(fields=["status"]),
            models.Index(fields=["review_stage"]),
            models.Index(fields=["governance_flag"]),
            models.Index(fields=["assigned_scientist", "status"]),
            models.Index(fields=["status", "review_stage"]),
            models.Index(fields=["governance_flag", "is_quarantined"]),
        ]

    # -- Helpers -------------------------------------------------------
    def __str__(self):
        return f"{self.content_id} ({self.content_header})"

    @property
    def has_warnings(self) -> bool:
        return bool(self.content_warnings)

    @property
    def is_validated(self) -> bool:
        return self.status in (
            SectionStatusChoices.VALIDATED,
            SectionStatusChoices.VALIDATED_WITH_MINOR_EDITS,
        )

    @property
    def is_ready_for_embedding(self) -> bool:
        """Only validated chunks without governance flags or quarantine may be embedded."""
        return (
            self.is_validated
            and not self.is_quarantined
            and not self.governance_flag
        )

    @property
    def thematic_area_names(self) -> str:
        return ", ".join(self.thematic_areas.values_list("name", flat=True))

    @property
    def value_chain_names(self) -> str:
        return ", ".join(self.value_chains.values_list("name", flat=True))

    def save(self, *args, **kwargs):
        """Keep the content hash synchronized whenever section text changes."""
        self.content_hash = hashlib.sha256(
            self.content_text.encode("utf-8")
        ).hexdigest()
        update_fields = kwargs.get("update_fields")
        if update_fields is not None and "content_hash" not in update_fields:
            kwargs["update_fields"] = set(update_fields) | {"content_hash"}
        super().save(*args, **kwargs)

    @transaction.atomic
    def apply_review(
        self,
        *,
        scientist,
        decision: str,
        notes: str = "",
        suggested_edits: str = "",
        confidence: int | None = None,
    ):
        """
        Convenience method used by the review UI / API to record a scientist
        decision, move the chunk through the workflow, and append an audit
        log entry in one call.
        """
        valid_decisions = {choice for choice, _label in ReviewDecisionChoices.choices}
        if decision not in valid_decisions:
            raise ValueError(f"Unsupported review decision: {decision!r}")
        if confidence is not None and not 0 <= confidence <= 100:
            raise ValueError("confidence must be between 0 and 100")

        previous_status = self.status

        self.reviewed_by = scientist
        self.reviewed_at = timezone.now()
        self.review_decision = decision
        self.review_notes = notes
        if suggested_edits:
            self.suggested_edits = suggested_edits
        if confidence is not None:
            self.confidence_score = confidence

        mapping = {
            ReviewDecisionChoices.APPROVE: (
                SectionStatusChoices.VALIDATED,
                ChunkReviewStageChoices.APPROVED,
            ),
            ReviewDecisionChoices.APPROVE_WITH_EDITS: (
                SectionStatusChoices.VALIDATED_WITH_MINOR_EDITS,
                ChunkReviewStageChoices.APPROVED,
            ),
            ReviewDecisionChoices.REQUEST_REVISION: (
                SectionStatusChoices.MAJOR_REVISION,
                ChunkReviewStageChoices.SCIENTIST_REVIEW,
            ),
            ReviewDecisionChoices.REJECT: (
                SectionStatusChoices.NOT_VALIDATED,
                ChunkReviewStageChoices.REJECTED,
            ),
            ReviewDecisionChoices.ESCALATE: (
                self.status or SectionStatusChoices.NOT_VALIDATED,
                ChunkReviewStageChoices.SENIOR_REVIEW,
            ),
        }
        new_status, new_stage = mapping.get(
            decision,
            (SectionStatusChoices.NOT_VALIDATED, ChunkReviewStageChoices.SCIENTIST_REVIEW),
        )
        self.status = new_status
        self.review_stage = new_stage
        self.is_quarantined = new_status == SectionStatusChoices.NOT_VALIDATED
        self.requires_senior_review = decision == ReviewDecisionChoices.ESCALATE
        self.save()

        SectionReviewLog.objects.create(
            section=self,
            actor=scientist,
            decision=decision,
            previous_status=previous_status,
            new_status=self.status,
            governance_flag=self.governance_flag,
            notes=notes,
            confidence_score=confidence,
        )
        return self


# ===========================================================================
# SectionReviewLog (immutable audit trail)
# ===========================================================================
class SectionReviewLog(models.Model):
    """
    Immutable audit entry: every scientist action on a ContentSection is
    appended here so KALRO can reconstruct who changed what, when, and why.
    """

    section = models.ForeignKey(
        ContentSection, related_name="review_logs", on_delete=models.CASCADE
    )
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True,
        on_delete=models.SET_NULL, related_name="section_review_actions",
    )
    decision = models.CharField(max_length=25, choices=ReviewDecisionChoices.choices)
    previous_status = models.CharField(
        max_length=30, choices=SectionStatusChoices.choices, blank=True, default=""
    )
    new_status = models.CharField(
        max_length=30, choices=SectionStatusChoices.choices, blank=True, default=""
    )
    governance_flag = models.CharField(
        max_length=30, choices=GovernanceFlagChoices.choices, blank=True, default=""
    )
    notes = models.TextField(blank=True, default="")
    confidence_score = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
        validators=[MinValueValidator(0), MaxValueValidator(100)],
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["section", "-created_at"]),
            models.Index(fields=["actor", "-created_at"]),
        ]

    def __str__(self):
        return f"{self.section.content_id} · {self.decision} @ {self.created_at:%Y-%m-%d}"