from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    Configuration for the KALRO AI Layer (FastAPI + Ollama), the "AI Layer"
    box in the KilimoSTACK / OpenAgriNet Beckn architecture diagram -- it
    sits behind the Beckn Adaptor - Seeker / Middleware and serves farmer-
    facing advisory queries.
    """

    model_config = SettingsConfigDict(env_prefix="AI_LAYER_", env_file=".env", extra="ignore")

    app_name: str = "KALRO AI Layer (KilimoSTACK / OpenAgriNet)"

    # Ollama (self-hosted LLM runtime)
    ollama_base_url: str = "http://localhost:11434"
    ollama_chat_model: str = "llama3.1"
    ollama_embed_model: str = "nomic-embed-text"
    ollama_request_timeout_seconds: float = 120.0

    # Vector store (Chroma, persisted to disk)
    chroma_persist_dir: str = "./chroma_data"
    chroma_collection_name: str = "kalro_advisory_corpus"

    # Retrieval / generation behaviour
    default_top_k: int = 5
    max_context_chars: int = 6000

    # API auth for the ingest endpoint (shared secret with the Django backend)
    ingest_api_key: str | None = None


settings = Settings()
