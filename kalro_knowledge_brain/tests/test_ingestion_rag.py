"""
Tests the ingestion + RAG pipeline end-to-end against a mocked Ollama
client, so they run without a live Ollama server (useful for CI). Swap the
monkeypatches for the real ``OllamaClient`` once you have Ollama running to
sanity-check actual model output.
"""

import json
import random
from pathlib import Path

import pytest

from app import ollama_client as ollama_client_module
from app.ingestion import ingest_resource
from app.rag import answer_query
from app.schemas import AdvisoryResource

SAMPLE_JSON = Path(__file__).resolve().parent.parent.parent / "data" / "sample_camel_calf_resource.json"


async def _fake_embed(self, text, model=None):
    # Deterministic pseudo-embedding so repeated calls for the same text
    # produce the same vector (keeps similarity search behaviour stable).
    random.seed(hash(text) % (2**32))
    return [random.random() for _ in range(32)]


async def _fake_chat(self, system_prompt, user_prompt, model=None, temperature=0.2):
    return f"MOCK ANSWER grounded in retrieved KALRO context for: {user_prompt}"


@pytest.fixture(autouse=True)
def mock_ollama(monkeypatch):
    monkeypatch.setattr(ollama_client_module.OllamaClient, "embed", _fake_embed)
    monkeypatch.setattr(ollama_client_module.OllamaClient, "chat", _fake_chat)


@pytest.fixture
def camel_calf_resource() -> AdvisoryResource:
    data = json.loads(SAMPLE_JSON.read_text())[0]
    resource = AdvisoryResource(**data)
    resource.quality_flag = "ready_to_certify"  # simulate a certified resource
    return resource


@pytest.mark.asyncio
async def test_ingest_resource_indexes_all_sections(camel_calf_resource):
    n_chunks = await ingest_resource(camel_calf_resource)
    assert n_chunks == 9


@pytest.mark.asyncio
async def test_uncertified_resource_is_skipped(camel_calf_resource):
    camel_calf_resource.quality_flag = "needs_review"
    n_chunks = await ingest_resource(camel_calf_resource)
    assert n_chunks == 0


@pytest.mark.asyncio
async def test_rag_answer_returns_sources_and_flags_high_risk(camel_calf_resource):
    await ingest_resource(camel_calf_resource)
    response = await answer_query("How do I manage tick paralysis in camel calves?")

    assert response.sources, "Expected at least one retrieved source"
    assert response.risk_level == "high"
    assert response.safety_notice is not None
    assert "MOCK ANSWER" in response.answer
