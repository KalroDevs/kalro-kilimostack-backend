"""
Retrieval-Augmented Generation over the KALRO advisory corpus.

Every answer is grounded strictly in retrieved chunks (never the model's own
unsourced knowledge), and every response that touches high-risk advisory
domains (veterinary treatment, drug/acaricide dosage, etc. -- flagged via
``advisory_safety`` on ingestion) carries an explicit escalation notice
rather than a confident answer.
"""

from __future__ import annotations

from .config import settings
from .ollama_client import ollama_client
from .schemas import ChatFilters, ChatResponse, SourceCitation
from .vector_store import vector_store

SYSTEM_PROMPT_TEMPLATE = """You are the KALRO Agricultural Advisory Assistant, serving farmers and \
extension officers on the KilimoSTACK / OpenAgriNet AI Advisory Platform in Kenya.

Rules you must follow:
1. Answer ONLY using the CONTEXT provided below. If the context does not contain enough \
information to answer safely and accurately, say so plainly and suggest contacting a local \
extension officer or KALRO expert instead of guessing.
2. Do not invent facts, statistics, dosages, or product names that are not present in the context.
3. Keep answers practical and concise, in plain language suitable for a farmer or extension officer.
4. If any retrieved context is flagged high-risk or requires human review (see SAFETY NOTES), you \
must include a clear recommendation to consult a qualified veterinarian, agronomist, or KALRO \
extension officer before acting -- do not just state the raw technical detail as if it were safe \
to self-administer.
5. Cite which source(s) your answer draws from by title, at the end of your answer.

CONTEXT:
{context}

SAFETY NOTES:
{safety_notes}
"""


def _build_where_filter(filters: ChatFilters | None) -> dict | None:
    if not filters:
        return None
    clauses = []
    if filters.sector:
        clauses.append({"sector": filters.sector})
    if filters.value_chain:
        clauses.append({"value_chain": filters.value_chain})
    if not clauses:
        return None
    return clauses[0] if len(clauses) == 1 else {"$and": clauses}


async def answer_query(
    query: str,
    top_k: int | None = None,
    filters: ChatFilters | None = None,
) -> ChatResponse:
    top_k = top_k or settings.default_top_k

    query_embedding = await ollama_client.embed(query)
    where = _build_where_filter(filters)
    results = vector_store.query(query_embedding, top_k=top_k, where=where)

    documents = results.get("documents", [[]])[0]
    metadatas = results.get("metadatas", [[]])[0]
    distances = results.get("distances", [[]])[0] if results.get("distances") else [None] * len(documents)
    ids = results.get("ids", [[]])[0]

    if not documents:
        return ChatResponse(
            answer=(
                "I don't have certified KALRO content covering this yet. "
                "Please consult your local extension officer, or rephrase your question."
            ),
            sources=[],
            safety_notice=None,
            risk_level=None,
            model=settings.ollama_chat_model,
        )

    context_parts, sources, safety_notes, max_risk = [], [], [], "low"
    risk_rank = {"low": 0, "medium": 1, "high": 2, "": 0}

    for i, (doc, meta, dist, chunk_id) in enumerate(zip(documents, metadatas, distances, ids)):
        context_parts.append(
            f"[Source {i + 1}: {meta.get('title')} — {meta.get('content_header')}]\n{doc}"
        )
        score = 1 - dist if isinstance(dist, (int, float)) else 0.0
        sources.append(
            SourceCitation(
                publication_id=meta.get("publication_id", ""),
                title=meta.get("title", ""),
                link=meta.get("link", ""),
                content_id=meta.get("content_id", chunk_id),
                content_header=meta.get("content_header", ""),
                score=round(score, 4),
            )
        )
        resource_risk = meta.get("risk_level", "") or "low"
        if risk_rank.get(resource_risk, 0) > risk_rank.get(max_risk, 0):
            max_risk = resource_risk
        if meta.get("has_warnings") or meta.get("requires_human_review"):
            safety_notes.append(
                f"- {meta.get('title')}: flagged for human review before farmer-facing use."
            )

    context = "\n\n".join(context_parts)[: settings.max_context_chars]
    safety_notes_text = "\n".join(safety_notes) if safety_notes else "None."
    system_prompt = SYSTEM_PROMPT_TEMPLATE.format(context=context, safety_notes=safety_notes_text)

    answer_text = await ollama_client.chat(system_prompt=system_prompt, user_prompt=query)

    safety_notice = None
    if max_risk in ("medium", "high") or safety_notes:
        safety_notice = (
            "This topic involves higher-risk advisory content (e.g. animal health, treatment, or "
            "dosage guidance). Please confirm details with a qualified veterinarian, agronomist, "
            "or KALRO extension officer before acting."
        )

    return ChatResponse(
        answer=answer_text,
        sources=sources,
        safety_notice=safety_notice,
        risk_level=max_risk,
        model=settings.ollama_chat_model,
    )
