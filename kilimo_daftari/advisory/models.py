from django.conf import settings
from django.db import models


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


class AdvisoryResource(models.Model):
    """
    One row = one advisory resource (PDF manual, factsheet, training guide,
    web page, etc.) -- the top-level object in the JSON specification's
    array. Mirrors the "Content Inventory" -> "Screen & Classify" pipeline:
    inventory fields are populated on import, screening fields are filled in
    (via the admin or API) as KALRO/partners review the item, and only items
    with ``quality_flag = ready_to_certify`` are synced to the AI Layer.
    """

    resource_id = models.CharField(max_length=50, unique=True, db_index=True,)   
    
    group = models.CharField(max_length=30, blank=True, default="", db_index=True,)
    
   
    title = models.CharField(max_length=500)
    link = models.URLField(max_length=1000, null=True, blank=True, default="")
    upload_file = models.FileField(upload_to="advisory_uploads/", blank=True, null=True)

   
    publication_id = models.CharField( max_length=1000, blank=True, default="", db_index=True,)
        

    # thumbnail = models.URLField(max_length=1000, blank=True, default="")
    institution = models.CharField(max_length=300, default="Kenya Agricultural and Livestock Research Organization")
    
    author = models.JSONField(default=list, blank=True, help_text="List of author name strings")
    publish_date = models.CharField(max_length=20, blank=True, default="", help_text="Raw value as submitted, e.g. 2018/01/08")
    
    modified_date = models.DateTimeField(null=True, blank=True)
    content_type = models.CharField(max_length=40, choices=ContentTypeChoices.choices)
    language = models.CharField(max_length=10, default="en")
    available_languages = models.JSONField(default=list, blank=True)

    sector = models.CharField(max_length=40, choices=SectorChoices.choices)
    value_chain = models.CharField(max_length=120, db_index=True)
    commodity = models.JSONField(default=list, blank=True)
    production_system = models.JSONField(default=list, blank=True)
    advisory_domain = models.JSONField(default=list, blank=True)
    target_users = models.JSONField(default=list, blank=True)

   
    geographic_applicability = models.JSONField(default=dict, blank=True,)
      
    
    seasonality = models.JSONField(default=dict, blank=True,)
    
    license = models.JSONField(default=dict, blank=True)

    validation_status = models.CharField(max_length=30, choices=ValidationStatusChoices.choices, blank=True, default="")
    
    validated_by = models.JSONField(default=list, blank=True)
    review_date = models.DateField(null=True, blank=True)
    next_review_date = models.DateField(null=True, blank=True)
    preferred_citation = models.TextField(blank=True, default="")


    risk_level = models.CharField(max_length=10, choices=RiskLevelChoices.choices, blank=True, default="")
    risk_domains = models.JSONField(default=list, blank=True)
    requires_human_review = models.BooleanField(default=False)
    escalation_guidance = models.TextField(blank=True, default="")
    safety_disclaimer = models.TextField(blank=True, default="")


    currency_status = models.CharField(max_length=25, choices=CurrencyStatusChoices.choices, blank=True, default="")
    
    scientific_accuracy_check = models.CharField(max_length=25, choices=AccuracyCheckChoices.choices, blank=True, default="")
    
    quality_flag = models.CharField(max_length=25, choices=QualityFlagChoices.choices, blank=True, default="")
    
    screening_notes = models.TextField(blank=True, default="")
    screened_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    screened_at = models.DateTimeField(null=True, blank=True)

    vector_sync_status = models.CharField(max_length=15, choices=VectorSyncStatusChoices.choices, default=VectorSyncStatusChoices.NOT_SYNCED)
    
    vector_synced_at = models.DateTimeField(null=True, blank=True)
    vector_sync_error = models.TextField(blank=True, default="")

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-updated_at"]
        indexes = [
            models.Index(fields=["sector", "value_chain"]),
            models.Index(fields=["quality_flag"]),
            models.Index(fields=["risk_level"]),
            models.Index(fields=["resource_id"]),
        ]

    def __str__(self):
        return f"{self.resource_id} — {self.title}"

    @property
    def is_ready_for_ai_layer(self) -> bool:
        
        return self.quality_flag == QualityFlagChoices.READY_TO_CERTIFY


class ContentSection(models.Model):
    """
    One row = one section-level content chunk (JSON spec ``content[]``
    items). This is the granularity the AI Layer chunks and embeds into the
    vector database.

    Maps to the "Potato", "Weather", "Hides and Skin", "Millet" and "Dairy"
    sheets of the Screen & Classify workbook.
    """

    resource = models.ForeignKey(AdvisoryResource, related_name="content_sections", on_delete=models.CASCADE)
    
    content_id = models.CharField(max_length=200, unique=True)
    reading_order = models.PositiveIntegerField()
    content_header = models.CharField(max_length=300, blank=True, default="")
    content_text = models.TextField()
    page_start = models.PositiveIntegerField(null=True, blank=True)
    page_end = models.PositiveIntegerField(null=True, blank=True)

    pages_reference = models.CharField(
        max_length=100,
        blank=True,
        default="",
        db_index=True,
    )

    value_chain = models.CharField(max_length=120, blank=True, default="", db_index=True)


    content_images = models.JSONField(default=list, blank=True)

    content_tables = models.JSONField(default=list, blank=True)

    content_warnings = models.JSONField(default=list, blank=True)
    content_tags = models.JSONField(default=list, blank=True)

    class Meta:
        ordering = ["resource", "reading_order"]
        indexes = [
            models.Index(fields=["resource", "reading_order"]),
            models.Index(fields=["value_chain"]),
        ]

    def __str__(self):
        return f"{self.content_id} ({self.content_header})"

    @property
    def has_warnings(self) -> bool:
        return bool(self.content_warnings)

class WorkbookUpload(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending"
        PROCESSING = "processing"
        PROCESSED = "processed"
        FAILED = "failed"

    file = models.FileField(upload_to="workbook/")
    uploaded_at = models.DateTimeField(auto_now_add=True)
    status = models.CharField(max_length=15, choices=Status.choices, default=Status.PENDING, db_index=True)

    resources_created = models.PositiveIntegerField(default=0)
    resources_updated = models.PositiveIntegerField(default=0)
    sections_created = models.PositiveIntegerField(default=0)
    sections_updated = models.PositiveIntegerField(default=0)
    sections_skipped = models.PositiveIntegerField(default=0)

    log = models.TextField(blank=True, default="")

    class Meta:
        ordering = ["-uploaded_at"]

        def __str__(self):
            return f"WorkbookUpload {self.id} ({self.status}) - {self.file.name}"
