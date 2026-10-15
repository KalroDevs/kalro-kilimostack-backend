from unittest.mock import Mock, patch

from django.contrib.auth.models import User
from django.test import TestCase
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient


class AskEndpointTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="asker", password="a-strong-password")
        self.token = Token.objects.create(user=self.user)

    def test_ask_requires_token(self):
        self.assertEqual(APIClient().post("/api/ask/", {"question": "How to manage pests?"}, format="json").status_code, 401)

    def test_ask_rejects_invalid_token(self):
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION="Bearer invalid")
        self.assertEqual(client.post("/api/ask/", {"question": "Question?"}, format="json").status_code, 401)

    @patch("accounts.ask.httpx.post")
    def test_ask_forwards_question_and_returns_grounded_response(self, post):
        post.return_value = Mock(
            raise_for_status=Mock(),
            json=Mock(return_value={
                "answer": "Use the practices described in the guide.",
                "sources": [{"title": "Guide", "content": "Relevant excerpt", "metadata": {"file_name": "guide.pdf"}}],
                "retrieval": {"documents_found": 1, "context_used": True},
                "generation": {"status": "ok"},
            }),
        )
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {self.token.key}")
        response = client.post("/api/ask/", {"question": "How to manage pests?"}, format="json")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data["retrieval"]["context_used"])
        self.assertEqual(response.data["sources"][0]["content"], "Relevant excerpt")
        self.assertEqual(post.call_args.kwargs["json"]["query"], "How to manage pests?")
        self.assertFalse(post.call_args.kwargs["json"]["include_training_documents"])

    def test_ask_rejects_blank_question(self):
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION=f"Token {self.token.key}")
        self.assertEqual(client.post("/api/ask/", {"question": "   "}, format="json").status_code, 400)

    @patch("accounts.ask.httpx.post")
    def test_versioned_ask_route_is_available(self, post):
        post.return_value = Mock(raise_for_status=Mock(), json=Mock(return_value={"answer": "No context", "sources": [], "retrieval": {}, "generation": {}}))
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION=f"Token {self.token.key}")
        response = client.post("/api/v1/ask/", {"question": "Test question?"}, format="json")
        self.assertEqual(response.status_code, 200)
