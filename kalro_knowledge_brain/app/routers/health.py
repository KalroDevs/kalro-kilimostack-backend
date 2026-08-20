from fastapi import APIRouter

from ..config import settings
from ..ollama_client import ollama_client
from ..vector_store import vector_store

router = APIRouter(tags=["health"])


@router.get("/health")
async def health():
    ollama_ok = await ollama_client.health()
    try:
        chunk_count = vector_store.count()
        vector_ok = True
    except Exception:  # noqa: BLE001
        chunk_count = 0
        vector_ok = False

    return {
        "status": "ok" if ollama_ok and vector_ok else "degraded",
        "ollama": {"reachable": ollama_ok, "base_url": settings.ollama_base_url},
        "vector_store": {"reachable": vector_ok, "indexed_chunks": chunk_count},
        "models": {"chat": settings.ollama_chat_model, "embed": settings.ollama_embed_model},
    }
