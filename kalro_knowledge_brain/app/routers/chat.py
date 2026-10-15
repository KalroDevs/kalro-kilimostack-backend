import logging

from fastapi import APIRouter, HTTPException
from chromadb.errors import InvalidArgumentError

from ..ollama_client import OllamaError
from ..rag import answer_query
from ..schemas import ChatRequest, ChatResponse

router = APIRouter(prefix="/api/v1", tags=["chat"])
logger = logging.getLogger(__name__)


@router.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest) -> ChatResponse:
    try:
        return await answer_query(query=request.query, top_k=request.top_k, filters=request.filters,
                                  include_training_documents=request.include_training_documents)
    except (OllamaError, TimeoutError) as exc:
        logger.warning("RAG provider unavailable: %s", exc)
        raise HTTPException(status_code=503, detail="The retrieval or generation service is unavailable.") from exc
    except InvalidArgumentError as exc:
        logger.exception("Chroma rejected the query embedding")
        raise HTTPException(
            status_code=503,
            detail="The configured embedding model is incompatible with the existing vector index. Reindex the configured knowledge sources with the configured embedding model.",
        ) from exc
    except Exception as exc:
        logger.exception("RAG request failed")
        raise HTTPException(status_code=503, detail="The RAG service could not complete the request.") from exc
