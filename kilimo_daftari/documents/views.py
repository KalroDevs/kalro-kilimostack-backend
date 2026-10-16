from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.permissions import IsAdminUser
from rest_framework.response import Response

from .models import Document
from .serializers import DocumentSerializer
from .services import process_document


class DocumentViewSet(mixins.CreateModelMixin, mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet,):
    queryset = Document.objects.order_by("-created_at")
    serializer_class = DocumentSerializer
    permission_classes = [IsAdminUser]
    parser_classes = [MultiPartParser, FormParser]

    def create(self, request, *args, **kwargs):
        serializer = DocumentSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        document = serializer.save(status=Document.STATUS_PENDING)

        if process_document(document):
            return Response(
                self.get_serializer(document).data,
                status=status.HTTP_201_CREATED,
            )
        return Response(
            {
                "detail": document.processing_error,
                "document": self.get_serializer(document).data,
            },
            status=status.HTTP_502_BAD_GATEWAY,
        )

    @action(detail=True, methods=["post"])
    def process(self, request, pk=None):
        document = self.get_object()
        if process_document(document):
            return Response(self.get_serializer(document).data)
        return Response(
            {
                "detail": document.processing_error,
                "document": self.get_serializer(document).data,
            },
            status=status.HTTP_502_BAD_GATEWAY,
        )