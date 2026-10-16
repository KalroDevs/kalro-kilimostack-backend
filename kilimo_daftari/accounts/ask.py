import logging
import re

import httpx
from django.conf import settings
from django.db.models import Q
from rest_framework import serializers, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.authentication import TokenOrBearerAuthentication

logger = logging.getLogger(__name__)

_SEARCH_STOP_WORDS = {
    "about", "after", "and", "are", "can", "could", "does", "for", "from",
    "how", "into", "what", "when", "where", "which", "with", "would",
}


def _advisory_context(question, limit=5):
    """Find certified advisory sections/resources directly in Django's database."""
    from advisory.models import AdvisoryResource, ContentSection, QualityFlagChoices

    terms = [
        term for term in re.findall(r"[\w'-]+", question.lower())
        if len(term) > 1 and term not in _SEARCH_STOP_WORDS
    ]
    if not terms:
        return []

    section_query = Q()
    for term in terms:
        section_query |= (
            Q(content_header__icontains=term)
            | Q(content_text__icontains=term)
            | Q(content_tags__icontains=term)
            | Q(value_chain__icontains=term)
            | Q(resource__title__icontains=term)
            | Q(resource__value_chain__icontains=term)
        )

    sections = (
        ContentSection.objects.filter(
            section_query,
            Q(resource__quality_flag=QualityFlagChoices.READY_TO_CERTIFY)
            | Q(resource__quality_flag=""),
        )
        .select_related("resource")[: limit * 4]
    )
    candidates = []
    for section in sections:
        resource = section.resource
        content = f"{section.content_header}\n{section.content_text}".strip()
        searchable = " ".join((
            content,
            section.value_chain,
            " ".join(section.content_tags or []),
            resource.title,
            resource.value_chain,
        )).lower()
        matched = sum(term in searchable for term in terms)
        score = min(0.99, 0.55 + 0.4 * matched / len(terms))
        candidates.append({
            "id": section.content_id,
            "source_type": "content_section",
            "score": score,
            "content": content,
            "metadata": {
                "publication_id": resource.publication_id,
                "resource_id": resource.resource_id,
                "title": resource.title,
                "link": resource.link,
                "sector": resource.sector,
                "value_chain": section.value_chain or resource.value_chain,
                "content_id": section.content_id,
                "content_header": section.content_header,
                "content_tags": section.content_tags,
                "content_warnings": section.content_warnings,
                "risk_level": resource.risk_level,
                "requires_human_review": resource.requires_human_review,
            },
        })

    resource_query = Q()
    for term in terms:
        resource_query |= (
            Q(title__icontains=term)
            | Q(value_chain__icontains=term)
            | Q(publication_id__icontains=term)
            | Q(institution__icontains=term)
            | Q(sector__icontains=term)
            | Q(content_type__icontains=term)
            | Q(screening_notes__icontains=term)
        )
    resources = AdvisoryResource.objects.filter(
        resource_query,
        Q(quality_flag=QualityFlagChoices.READY_TO_CERTIFY) | Q(quality_flag=""),
    )[: limit * 4]
    for resource in resources:
        content = "\n".join(filter(None, (
            resource.title,
            f"Institution: {resource.institution}" if resource.institution else "",
            f"Sector: {resource.sector}" if resource.sector else "",
            f"Value chain: {resource.value_chain}" if resource.value_chain else "",
            f"Content type: {resource.content_type}" if resource.content_type else "",
            f"Advisory domains: {', '.join(resource.advisory_domain or [])}" if resource.advisory_domain else "",
            f"Commodities: {', '.join(resource.commodity or [])}" if resource.commodity else "",
            f"Target users: {', '.join(resource.target_users or [])}" if resource.target_users else "",
            f"Risk domains: {', '.join(resource.risk_domains or [])}" if resource.risk_domains else "",
            f"Advisory notes: {resource.screening_notes}" if resource.screening_notes else "",
            f"Safety guidance: {resource.escalation_guidance}" if resource.escalation_guidance else "",
            f"Safety disclaimer: {resource.safety_disclaimer}" if resource.safety_disclaimer else "",
            f"Preferred citation: {resource.preferred_citation}" if resource.preferred_citation else "",
        )))
        searchable = content.lower()
        matched = sum(term in searchable for term in terms)
        score = min(0.9, 0.5 + 0.35 * matched / len(terms))
        candidates.append({
            "id": resource.resource_id,
            "source_type": "advisory_resource",
            "score": score,
            "content": content,
            "metadata": {
                "publication_id": resource.publication_id,
                "resource_id": resource.resource_id,
                "title": resource.title,
                "link": resource.link,
                "sector": resource.sector,
                "value_chain": resource.value_chain,
                "advisory_domain": resource.advisory_domain,
                "commodity": resource.commodity,
                "target_users": resource.target_users,
                "risk_level": resource.risk_level,
                "requires_human_review": resource.requires_human_review,
                "preferred_citation": resource.preferred_citation,
            },
        })

    candidates.sort(key=lambda item: item["score"], reverse=True)
    return candidates[:limit]


class AskSerializer(serializers.Serializer):
    question = serializers.CharField(max_length=4000, allow_blank=False, trim_whitespace=True)

    def validate_question(self, value):
        if not value.strip():
            raise serializers.ValidationError("This field may not be blank.")
        return value.strip()


class AskView(APIView):
    authentication_classes = [TokenOrBearerAuthentication]
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = AskSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        url = f"{settings.AI_LAYER_BASE_URL.rstrip('/')}/api/v1/chat"
        payload = {
            "query": serializer.validated_data["question"],
            "include_training_documents": bool(request.user.is_staff),
        }
        try:
            payload["additional_context"] = _advisory_context(payload["query"])
        except Exception:
            logger.exception("Direct advisory database retrieval failed")
            payload["additional_context"] = []
        try:
            response = httpx.post(url, json=payload, timeout=settings.AI_LAYER_CHAT_TIMEOUT_SECONDS)
            response.raise_for_status()
            result = response.json()
        except httpx.TimeoutException:
            return Response({"detail": "The RAG service timed out.", "retrieval": {"status": "unavailable"}}, status=status.HTTP_504_GATEWAY_TIMEOUT)
        except (httpx.HTTPError, ValueError) as exc:
            logger.warning("AI Layer ask failed (%s)", type(exc).__name__)
            return Response({"detail": "The RAG service is unavailable.", "retrieval": {"status": "unavailable"}}, status=status.HTTP_503_SERVICE_UNAVAILABLE)
        return Response(result)
