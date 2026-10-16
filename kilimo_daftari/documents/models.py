from pathlib import Path

from django.db import models


class Document(models.Model):
    PDF = "pdf"
    DOCX = "docx"
    EXCEL = "excel"
    JSON = "json"
    TEXT = "txt"
    MARKDOWN = "md"

    FILE_TYPE_CHOICES = [
        (PDF, "PDF"),
        (DOCX, "DOCX"),
        (EXCEL, "EXCEL"),
        (JSON, "JSON"),
        (TEXT, "Text"),
        (MARKDOWN, "Markdown"),
    ]
    FILE_TYPE_BY_EXTENSION = {
        ".pdf": PDF,
        ".docx": DOCX,
        ".xlsx": EXCEL,
        ".json": JSON,
        ".txt": TEXT,
        ".md": MARKDOWN,
        ".markdown": MARKDOWN,
    }

    STATUS_PENDING = "pending"
    STATUS_PROCESSING = "processing"
    STATUS_VERIFIED = "verified"
    STATUS_FAILED = "failed"

    STATUS_CHOICES = [
        (STATUS_PENDING, "Pending"),
        (STATUS_PROCESSING, "Processing"),
        (STATUS_VERIFIED, "Verified"),
        (STATUS_FAILED, "Failed"),
    ]

    name = models.CharField(max_length=255)
    file = models.FileField(upload_to="documents/")
    file_type = models.CharField(max_length=10, choices=FILE_TYPE_CHOICES)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_PENDING)
    chunks_indexed = models.PositiveIntegerField(default=0)
    processing_error = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    @classmethod
    def file_type_for_name(cls, filename):
        return cls.FILE_TYPE_BY_EXTENSION.get(Path(filename).suffix.lower())

    def __str__(self):
        return f"{self.name} ({self.file_type})"