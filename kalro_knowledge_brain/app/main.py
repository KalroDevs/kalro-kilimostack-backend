from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import settings
from .routers import chat, health, ingest

app = FastAPI(
    title=settings.app_name,
    description=(
        "RAG + LLM AI Layer for KALRO's advisory content on the KilimoSTACK / "
        "OpenAgriNet (OAN) network. Retrieval runs over a Chroma vector index "
        "built from certified advisory content; generation runs on a "
        "self-hosted Ollama model."
    ),
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router)
app.include_router(ingest.router)
app.include_router(chat.router)


@app.get("/")
async def root():
    return {
        "service": settings.app_name,
        "docs": "/docs",
        "endpoints": ["/health", "/api/v1/ingest", "/api/v1/chat"],
    }
