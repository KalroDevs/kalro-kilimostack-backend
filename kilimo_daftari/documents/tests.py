import tempfile
from unittest.mock import Mock, patch

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from .models import Document


class DocumentUploadTests(TestCase):
    def setUp(self):
        self.media_directory = tempfile.TemporaryDirectory()
        self.settings_override = override_settings(MEDIA_ROOT=self.media_directory.name)
        self.settings_override.enable()
        self.addCleanup(self.settings_override.disable)
        self.addCleanup(self.media_directory.cleanup)

        admin = get_user_model().objects.create_user(
            username="document-admin",
            password="test-password",
            is_staff=True,
        )
        self.client = APIClient()
        self.client.force_authenticate(admin)

    @patch("documents.services.httpx.post")
    def test_upload_processes_document_and_marks_it_verified(self, post):
        def fake_post(url, **kwargs):
            response = Mock(is_error=False)
            response.json.return_value = {
                "document_id": kwargs["data"]["document_id"],
                "status": "verified",
                "chunks_indexed": 2,
            }
            return response

        post.side_effect = fake_post

        result = self.client.post(
            "/api/v1/documents/",
            {
                "file": SimpleUploadedFile(
                    "crop-notes.txt",
                    b"Store crop seed in a cool, dry place.",
                    content_type="text/plain",
                )
            },
            format="multipart",
        )

        self.assertEqual(result.status_code, 201)
        document = Document.objects.get()
        self.assertEqual(document.status, Document.STATUS_VERIFIED)
        self.assertEqual(document.file_type, Document.TEXT)
        self.assertEqual(document.name, "crop-notes")
        self.assertEqual(document.chunks_indexed, 2)
        post.assert_called_once()

    @patch("documents.services.httpx.post")
    def test_processing_failure_is_returned_and_saved(self, post):
        response = Mock(is_error=True, status_code=422, text="invalid document")
        response.json.return_value = {"detail": "No extractable text"}
        post.return_value = response

        result = self.client.post(
            "/api/v1/documents/",
            {
                "file": SimpleUploadedFile(
                    "scan.pdf",
                    b"pdf-bytes",
                    content_type="application/pdf",
                )
            },
            format="multipart",
        )

        self.assertEqual(result.status_code, 502)
        document = Document.objects.get()
        self.assertEqual(document.status, Document.STATUS_FAILED)
        self.assertIn("No extractable text", document.processing_error)
        self.assertEqual(result.data["document"]["status"], Document.STATUS_FAILED)
        post.assert_called_once()

    def test_unsupported_file_type_is_rejected_before_processing(self):
        with patch("documents.services.httpx.post") as post:
            result = self.client.post(
                "/api/v1/documents/",
                {
                    "file": SimpleUploadedFile(
                        "program.exe",
                        b"not a document",
                        content_type="application/octet-stream",
                    )
                },
                format="multipart",
            )

        self.assertEqual(result.status_code, 400)
        self.assertFalse(Document.objects.exists())
        post.assert_not_called()
