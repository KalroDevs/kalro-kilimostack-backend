import logging

import httpx
from django.conf import settings
from rest_framework import serializers, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.authentication import TokenOrBearerAuthentication

logger = logging.getLogger(__name__)


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
            response = httpx.post(url, json=payload, timeout=settings.AI_LAYER_CHAT_TIMEOUT_SECONDS)
            response.raise_for_status()
            result = response.json()
        except httpx.TimeoutException:
            return Response({"detail": "The RAG service timed out.", "retrieval": {"status": "unavailable"}}, status=status.HTTP_504_GATEWAY_TIMEOUT)
        except (httpx.HTTPError, ValueError) as exc:
            logger.warning("AI Layer ask failed (%s)", type(exc).__name__)
            return Response({"detail": "The RAG service is unavailable.", "retrieval": {"status": "unavailable"}}, status=status.HTTP_503_SERVICE_UNAVAILABLE)
        return Response(result)
