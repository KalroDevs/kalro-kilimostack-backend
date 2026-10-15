"""Thin asynchronous REST client for Ollama embeddings and chat generation."""

from __future__ import annotations

import httpx

from .config import settings


class OllamaError(RuntimeError):
    """A safe, actionable provider error without request URLs or credentials."""


class OllamaClient:
    def __init__(self, base_url: str | None = None):
        self.base_url = (base_url or settings.ollama_base_url).rstrip("/")
        self._client = httpx.AsyncClient(
            base_url=self.base_url, timeout=settings.ollama_request_timeout_seconds
        )

    @staticmethod
    def _provider_detail(response: httpx.Response) -> str:
        try:
            detail = response.json().get("error", "")
        except (ValueError, AttributeError):
            detail = ""
        return str(detail)[:240] or "no provider detail"

    async def embed(self, text: str, model: str | None = None) -> list[float]:
        model = model or settings.ollama_embed_model
        try:
            resp = await self._client.post("/api/embeddings", json={"model": model, "prompt": text})
            resp.raise_for_status()
            embedding = resp.json().get("embedding")
            if not embedding:
                raise OllamaError(f"Ollama returned no embedding for model {model!r}.")
            return embedding
        except httpx.TimeoutException as exc:
            raise OllamaError(f"Ollama embedding request timed out after {settings.ollama_request_timeout_seconds:g} seconds.") from exc
        except httpx.HTTPStatusError as exc:
            detail = self._provider_detail(exc.response)
            raise OllamaError(f"Ollama embedding request returned HTTP {exc.response.status_code}: {detail}") from exc
        except httpx.HTTPError as exc:
            raise OllamaError(f"Ollama embedding request failed ({type(exc).__name__}).") from exc

    async def embed_many(self, texts: list[str], model: str | None = None) -> list[list[float]]:
        return [await self.embed(text, model=model) for text in texts]

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
            answer = resp.json().get("message", {}).get("content", "").strip()
            if not answer:
                raise OllamaError("Ollama returned an empty chat response.")
            return answer
        except httpx.TimeoutException as exc:
            raise OllamaError(f"Ollama chat request timed out after {settings.ollama_request_timeout_seconds:g} seconds.") from exc
        except httpx.HTTPStatusError as exc:
            detail = self._provider_detail(exc.response)
            raise OllamaError(f"Ollama chat request returned HTTP {exc.response.status_code}: {detail}") from exc
        except httpx.HTTPError as exc:
            raise OllamaError(f"Ollama chat request failed ({type(exc).__name__}).") from exc

    async def health(self) -> bool:
        try:
            resp = await self._client.get("/api/tags")
            return resp.status_code == 200
        except httpx.HTTPError:
            return False

    async def aclose(self):
        await self._client.aclose()


ollama_client = OllamaClient()
