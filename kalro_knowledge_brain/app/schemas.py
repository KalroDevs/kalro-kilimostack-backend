"""
Pydantic models mirroring the Advisory Content Import JSON Specification
v0.1 field-for-field. These validate whatever the Django backend (or any
other spec-compliant producer) POSTs to /api/v1/ingest.
"""

from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, Field


class GeographicApplicability(BaseModel):
    country: str = "Kenya"
    counties: list[str] = Field(default_factory=list)
    agro_ecological_zones: list[str] = Field(default_factory=list)
    notes: str = ""


class Seasonality(BaseModel):
    season: list[str] = Field(default_factory=list)
    production_stage: list[str] = Field(default_factory=list)
    timing_notes: str = ""


class License(BaseModel):
    # Spec: "Licensing and permitted downstream uses." -- kept open-shaped
    # since the spec doesn't enumerate sub-fields; commonly holds keys like
    # license_type, attribution_required, downstream_uses.
    model_config = {"extra": "allow"}


class ContentImage(BaseModel):
    image_url: str = ""
    image_text: str = ""
    image_caption: str = ""
    page_number: Optional[int] = None


class ContentTable(BaseModel):
    table_id: str = ""
    table_title: str = ""
    page_number: Optional[int] = None
    table_text: str = ""
    table_json: list[Any] = Field(default_factory=list)


class ContentSection(BaseModel):
    content_id: str
    reading_order: int
    content_header: str = ""
    content_text: str
    page_start: Optional[int] = None
    page_end: Optional[int] = None
    content_images: list[ContentImage] = Field(default_factory=list)
    content_tables: list[ContentTable] = Field(default_factory=list)
    content_warnings: list[str] = Field(default_factory=list)
    content_tags: list[str] = Field(default_factory=list)


class AdvisorySafety(BaseModel):
    risk_level: str = ""
    risk_domains: list[str] = Field(default_factory=list)
    requires_human_review: bool = False
    escalation_guidance: str = ""
    disclaimer: str = ""


class AdvisoryResource(BaseModel):
    """One resource, exactly as the JSON spec's array elements are shaped."""

    title: str
    link: str
    publication_id: str
    thumbnail: str = ""
    institution: str = "Kenya Agricultural and Livestock Research Organization"
    author: list[str] = Field(default_factory=list)
    publish_date: str = ""
    modified_date: str = ""
    content_type: str
    language: str = "en"
    available_languages: list[str] = Field(default_factory=list)

    sector: str
    value_chain: str
    commodity: list[str] = Field(default_factory=list)
    production_system: list[str] = Field(default_factory=list)
    advisory_domain: list[str] = Field(default_factory=list)
    target_users: list[str] = Field(default_factory=list)

    geographic_applicability: GeographicApplicability = Field(default_factory=GeographicApplicability)
    seasonality: Seasonality = Field(default_factory=Seasonality)
    license: License = Field(default_factory=License)

    validation_status: str = ""
    validated_by: list[str] = Field(default_factory=list)
    review_date: str = ""
    next_review_date: str = ""
    preferred_citation: str = ""

    content: list[ContentSection] = Field(default_factory=list)
    advisory_safety: AdvisorySafety = Field(default_factory=AdvisorySafety)

    # Screen & Classify fields (from the Excel working template), passed
    # through by the Django backend alongside the spec's own fields.
    currency_status: str = ""
    scientific_accuracy_check: str = ""
    quality_flag: str = ""
    screening_notes: str = ""


class IngestResponse(BaseModel):
    ingested: list[str]
    chunks_indexed: int
    skipped: list[str] = Field(default_factory=list)
    errors: list[dict] = Field(default_factory=list)


class ChatFilters(BaseModel):
    sector: Optional[str] = None
    value_chain: Optional[str] = None
    county: Optional[str] = None
    max_risk_level: Optional[str] = None  # "low" | "medium" | "high" ceiling, informational


class ChatRequest(BaseModel):
    query: str
    top_k: int = 5
    filters: Optional[ChatFilters] = None
    language: str = "en"


class SourceCitation(BaseModel):
    publication_id: str
    title: str
    link: str
    content_id: str
    content_header: str
    score: float


class ChatResponse(BaseModel):
    answer: str
    sources: list[SourceCitation]
    safety_notice: Optional[str] = None
    risk_level: Optional[str] = None
    model: str
