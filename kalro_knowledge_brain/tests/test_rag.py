from unittest.mock import AsyncMock, patch

import pytest

from app.rag import answer_query


@pytest.mark.asyncio
async def test_answer_uses_retrieved_context_and_returns_real_sources():
    matches = [
        {"document": "Apply crop rotation.", "metadata": {"title": "Advisory", "content_id": "c1"}, "distance": 0.1, "id": "c1", "source_type": "advisory"},
        {"document": "Remove infected leaves.", "metadata": {"title": "Guide", "file_name": "guide.pdf", "content_id": "d1"}, "distance": 0.2, "id": "d1", "source_type": "document"},
    ]
    with patch("app.rag.ollama_client.embed", new=AsyncMock(return_value=[0.1])), \
            patch("app.rag.vector_store.query_all", return_value=matches), \
            patch("app.rag.ollama_client.chat", new=AsyncMock(return_value="Rotate crops and remove infected leaves.")) as chat:
        response = await answer_query("How do I manage the problem?")
    assert response.retrieval["context_used"] is True
    assert response.retrieval["documents_found"] == 2
    assert {source.source_type for source in response.sources} == {"advisory", "document"}
    assert response.sources[1].content == "Remove infected leaves."
    assert "Apply crop rotation." in chat.await_args.kwargs["system_prompt"]


@pytest.mark.asyncio
async def test_no_relevant_context_does_not_call_llm_or_fabricate_sources():
    with patch("app.rag.ollama_client.embed", new=AsyncMock(return_value=[0.1])), \
            patch("app.rag.vector_store.query_all", return_value=[]), \
            patch("app.rag.ollama_client.chat", new=AsyncMock()) as chat:
        response = await answer_query("Unknown topic")
    assert response.sources == []
    assert response.retrieval["status"] == "no_relevant_context"
    chat.assert_not_awaited()
