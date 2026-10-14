from pathlib import Path

from rest_framework import serializers

from .models import Document


class DocumentSerializer(serializers.ModelSerializer):
    name = serializers.CharField(required=False, max_length=255)
    file_type = serializers.CharField(read_only=True)

    class Meta:
        model = Document
        fields = ["id", "name", "file", "file_type", "status", "chunks_indexed", "processing_error", "created_at", "updated_at",]
        read_only_fields = ["id", "status", "chunks_indexed", "processing_error", "created_at", "updated_at",]

    def validate_file(self, uploaded_file):
        file_type = Document.file_type_for_name(uploaded_file.name)
        if file_type is None:
            supported = ", ".join(Document.FILE_TYPE_BY_EXTENSION)
            raise serializers.ValidationError(
                f"Unsupported file type. Supported extensions: {supported}."
            )
        if uploaded_file.size > 25 * 1024 * 1024:
            raise serializers.ValidationError("The maximum document size is 25 MB.")
        self._file_type = file_type
        return uploaded_file

    def create(self, validated_data):
        uploaded_file = validated_data["file"]
        validated_data["name"] = (
            validated_data.get("name") or Path(uploaded_file.name).stem
        )
        validated_data["file_type"] = self._file_type
        return super().create(validated_data)