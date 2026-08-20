// Mirrors advisory/serializers.py (Django) and app/schemas.py (FastAPI).
// Kept intentionally close to the JSON spec field names so payloads can be
// passed straight through without remapping.

export type Sector =
  | "crops"
  | "livestock"
  | "aquaculture"
  | "natural_resource_management"
  | "cross_cutting";

export type ContentType =
  | "PDF"
  | "HTML"
  | "factsheet"
  | "training_manual"
  | "farmer_guide"
  | "technical_manual"
  | "qa_pair"
  | "dataset_description"
  | string; // real-world exports use free text too, e.g. "PDF brochure"

export type ValidationStatus =
  | "source_validated"
  | "expert_reviewed"
  | "field_validated"
  | "requires_review"
  | "deprecated"
  | "";

export type CurrencyStatus = "current" | "needs_update" | "outdated" | "needs_verification" | "";
export type AccuracyCheck = "verified" | "needs_review" | "flagged_inaccurate" | "";
export type RiskLevel = "low" | "medium" | "high" | "";
export type QualityFlag =
  | "ready_to_certify"
  | "needs_review"
  | "needs_update"
  | "duplicate"
  | "reject"
  | "";
export type VectorSyncStatus = "not_synced" | "pending" | "synced" | "failed";

export interface GeographicApplicability {
  country: string;
  counties: string[];
  agro_ecological_zones: string[];
  notes: string;
}

export interface Seasonality {
  season: string[];
  production_stage: string[];
  timing_notes: string;
}

export interface ContentImage {
  image_url: string;
  image_text: string;
  image_caption: string;
  page_number: number | null;
}

export interface ContentTable {
  table_id: string;
  table_title: string;
  page_number: number | null;
  table_text: string;
  table_json: unknown[];
}

export interface ContentSection {
  content_id: string;
  reading_order: number;
  content_header: string;
  content_text: string;
  page_start: number | null;
  page_end: number | null;
  content_images: ContentImage[];
  content_tables: ContentTable[];
  content_warnings: string[];
  content_tags: string[];
}

export interface AdvisorySafety {
  risk_level: RiskLevel;
  risk_domains: string[];
  requires_human_review: boolean;
  escalation_guidance: string;
  disclaimer: string;
}

export interface AdvisoryResource {
  id: number;
  title: string;
  link: string;
  publication_id: string;
  thumbnail: string;
  institution: string;
  author: string[];
  publish_date: string;
  modified_date: string | null;
  content_type: ContentType;
  language: string;
  available_languages: string[];

  sector: Sector | "";
  value_chain: string;
  commodity: string[];
  production_system: string[];
  advisory_domain: string[];
  target_users: string[];

  geographic_applicability: GeographicApplicability;
  seasonality: Seasonality;
  license: Record<string, unknown>;

  validation_status: ValidationStatus;
  validated_by: string[];
  review_date: string | null;
  next_review_date: string | null;
  preferred_citation: string;

  content: ContentSection[];
  advisory_safety: AdvisorySafety;

  currency_status: CurrencyStatus;
  scientific_accuracy_check: AccuracyCheck;
  quality_flag: QualityFlag;
  screening_notes: string;

  vector_sync_status: VectorSyncStatus;
  vector_synced_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface PaginatedResponse<T> {
  count: number;
  next: string | null;
  previous: string | null;
  results: T[];
}

export interface ResourceFilters {
  sector?: string;
  value_chain?: string;
  content_type?: string;
  quality_flag?: string;
  risk_level?: string;
  validation_status?: string;
  search?: string;
  page?: number;
}

export interface ScreeningUpdate {
  currency_status?: CurrencyStatus;
  scientific_accuracy_check?: AccuracyCheck;
  validation_status?: ValidationStatus;
  risk_level?: RiskLevel;
  quality_flag?: QualityFlag;
  screening_notes?: string;
}

export interface IngestResult {
  created: string[];
  updated: string[];
  errors: { publication_id: string; errors: unknown }[];
}

// --- AI Layer (FastAPI) ---

export interface ChatFilters {
  sector?: string;
  value_chain?: string;
}

export interface ChatRequest {
  query: string;
  top_k?: number;
  filters?: ChatFilters;
}

export interface SourceCitation {
  publication_id: string;
  title: string;
  link: string;
  content_id: string;
  content_header: string;
  score: number;
}

export interface ChatResponse {
  answer: string;
  sources: SourceCitation[];
  safety_notice: string | null;
  risk_level: string | null;
  model: string;
}

export interface ProviderMembershipSummary {
  provider_id: string;
  provider_name: string;
  role: "reviewer" | "admin";
}

export interface CurrentUser {
  id: number;
  username: string;
  email: string;
  is_staff: boolean;
  provider_memberships: ProviderMembershipSummary[];
}

export interface RegisterPayload {
  username: string;
  email?: string;
  password: string;
}

export interface LoginPayload {
  username: string;
  password: string;
}

export interface AuthResponse {
  token: string;
  user: CurrentUser;
}

export interface AiLayerHealth {
  status: "ok" | "degraded";
  ollama: { reachable: boolean; base_url: string };
  vector_store: { reachable: boolean; indexed_chunks: number };
  models: { chat: string; embed: string };
}
