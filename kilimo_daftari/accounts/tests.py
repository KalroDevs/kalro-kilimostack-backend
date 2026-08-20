from django.contrib.auth.models import User
from django.test import TestCase
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient

from providers.models import Provider, ProviderMembership


class RegisterTests(TestCase):
    def test_register_creates_user_and_returns_token(self):
        client = APIClient()
        resp = client.post(
            "/api/v1/auth/register/",
            {"username": "new_reviewer", "email": "nr@example.com", "password": "a-strong-password-123"},
            format="json",
        )
        self.assertEqual(resp.status_code, 201, resp.content)
        self.assertIn("token", resp.data)
        self.assertEqual(resp.data["user"]["username"], "new_reviewer")
        self.assertTrue(User.objects.filter(username="new_reviewer").exists())

    def test_register_rejects_duplicate_username(self):
        User.objects.create_user(username="taken", password="x")
        client = APIClient()
        resp = client.post("/api/v1/auth/register/", {"username": "taken", "password": "a-strong-password-123"}, format="json")
        self.assertEqual(resp.status_code, 400)
        self.assertIn("username", resp.data)

    def test_register_enforces_django_password_validators(self):
        client = APIClient()
        resp = client.post("/api/v1/auth/register/", {"username": "weakpw", "password": "123"}, format="json")
        self.assertEqual(resp.status_code, 400)
        self.assertIn("password", resp.data)

    def test_new_account_has_no_provider_memberships(self):
        """Governed onboarding: registering does NOT grant provider access."""
        client = APIClient()
        resp = client.post("/api/v1/auth/register/", {"username": "unlinked", "password": "a-strong-password-123"}, format="json")
        self.assertEqual(resp.data["user"]["provider_memberships"], [])


class LoginLogoutTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="kalro_reviewer", password="correct-horse-battery-staple")

    def test_login_with_correct_credentials_returns_token(self):
        client = APIClient()
        resp = client.post(
            "/api/v1/auth/login/", {"username": "kalro_reviewer", "password": "correct-horse-battery-staple"}, format="json"
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data["token"], Token.objects.get(user=self.user).key)

    def test_login_with_wrong_password_is_rejected(self):
        client = APIClient()
        resp = client.post("/api/v1/auth/login/", {"username": "kalro_reviewer", "password": "wrong"}, format="json")
        self.assertEqual(resp.status_code, 401)

    def test_login_includes_provider_memberships(self):
        provider = Provider.objects.create(provider_id="kalro.kilimostack", name="KALRO")
        ProviderMembership.objects.create(user=self.user, provider=provider, role="reviewer")

        client = APIClient()
        resp = client.post(
            "/api/v1/auth/login/", {"username": "kalro_reviewer", "password": "correct-horse-battery-staple"}, format="json"
        )
        self.assertEqual(len(resp.data["user"]["provider_memberships"]), 1)
        self.assertEqual(resp.data["user"]["provider_memberships"][0]["provider_id"], "kalro.kilimostack")

    def test_me_requires_authentication(self):
        client = APIClient()
        resp = client.get("/api/v1/auth/me/")
        self.assertEqual(resp.status_code, 401)

    def test_me_returns_current_user_when_authenticated(self):
        token = Token.objects.create(user=self.user)
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION=f"Token {token.key}")
        resp = client.get("/api/v1/auth/me/")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data["username"], "kalro_reviewer")

    def test_logout_invalidates_token(self):
        token = Token.objects.create(user=self.user)
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION=f"Token {token.key}")

        logout_resp = client.post("/api/v1/auth/logout/")
        self.assertEqual(logout_resp.status_code, 204)

        # The same token should no longer work.
        me_resp = client.get("/api/v1/auth/me/")
        self.assertEqual(me_resp.status_code, 401)
