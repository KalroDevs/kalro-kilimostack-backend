from rest_framework.authentication import TokenAuthentication, get_authorization_header
from rest_framework.exceptions import AuthenticationFailed


class TokenOrBearerAuthentication(TokenAuthentication):
    """Accept existing DRF Token clients and Bearer clients."""

    def authenticate(self, request):
        parts = get_authorization_header(request).split()
        if parts and parts[0].lower() == b"bearer":
            if len(parts) != 2:
                raise AuthenticationFailed("Invalid token header.")
            return self.authenticate_credentials(parts[1].decode("utf-8"))
        return super().authenticate(request)
