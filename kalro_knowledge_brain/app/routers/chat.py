from fastapi import APIRouter

from ..rag import answer_query
from ..schemas import ChatRequest, ChatResponse

router = APIRouter(prefix="/api/v1", tags=["chat"])


@router.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest) -> ChatResponse:
    """
    Farmer/extension-officer-facing advisory Q&A endpoint. This is what the
    Beckn Adaptor - Seeker (client-facing side, per the architecture
    diagram) or a voice/USSD channel would call after a query has been
    transcribed to text.
    """
    return await answer_query(query=request.query, top_k=request.top_k, filters=request.filters)
