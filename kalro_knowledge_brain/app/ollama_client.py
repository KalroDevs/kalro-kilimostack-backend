"""
Thin async client for a self-hosted Ollama server, used for both:

  * embeddings (POST /api/embed) -- to build & query the vector index
  * chat generation (POST /api/chat) -- to produce grounded RAG answers

No external Ollama SDK dependency is required; this talks to Ollama's REST
API directly over httpx so the AI Layer has a minimal dependency footprint.
"""

from __future__ import annotations

import logging

import httpx

from .config import settings

logger = logging.getLogger(__name__)


class OllamaError(RuntimeError):
    pass


class OllamaClient:
    def __init__(self, base_url: str | None = None):
        self.base_url = (base_url or settings.ollama_base_url).rstrip("/")
        self._client = httpx.AsyncClient(
            base_url=self.base_url, timeout=settings.ollama_request_timeout_seconds
        )

    async def embed(self, text: str, model: str | None = None) -> list[float]:
        embeddings = await self.embed_many([text], model=model)
        if not embeddings:
            raise OllamaError(f"Ollama returned no embedding for model={model!r}")
        return embeddings[0]

    async def embed_many(self, texts: list[str], model: str | None = None) -> list[list[float]]:
        model = model or settings.ollama_embed_model
        if not texts:
            return []
        try:
            # Uses the modern /api/embed endpoint supporting batch input lists
            resp = await self._client.post("/api/embed", json={"model": model, "input": texts})
            resp.raise_for_status()
            data = resp.json()
            embeddings = data.get("embeddings")
            if not embeddings:
                raise OllamaError(f"Ollama returned no embeddings for model={model!r}")
            return embeddings
        except httpx.HTTPError as exc:
            raise OllamaError(f"Ollama embeddings call failed: {exc}") from exc

    async def chat(
        self,
        system_prompt: str,
        user_prompt: str,
        model: str | None = None,
        temperature: float = 0.2,
    ) -> str:
        model = model or settings.ollama_chat_model
        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "stream": False,
            "options": {"temperature": temperature},
        }
        try:
            resp = await self._client.post("/api/chat", json=payload)
            resp.raise_for_status()
            data = resp.json()
            return data.get("message", {}).get("content", "").strip()
        except httpx.HTTPError as exc:
            raise OllamaError(f"Ollama chat call failed: {exc}") from exc

    async def health(self) -> bool:
        try:
            resp = await self._client.get("/api/tags")
            return resp.status_code == 200
        except httpx.HTTPError:
            return False

    async def aclose(self):
        await self._client.aclose()


ollama_client = OllamaClient()
