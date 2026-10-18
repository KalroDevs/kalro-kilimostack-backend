"""Browsable API root listing all KilimoSTACK v1 (+ Beckn) endpoints."""
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.reverse import reverse


@api_view(["GET"])
@permission_classes([AllowAny])
def api_root(request, format=None):
    def link(name, **kwargs):
        return reverse(name, request=request, format=format, kwargs=kwargs or None)

    return Response(
        {
            "resources": link("resource-list"),
            "ingest": link("ingest"),
            "providers": link("provider-list"),
            "providers-mine": link("provider-mine"),
            "service-categories": link("service-category-list"),
            "catalog-items": link("catalog-item-list"),
            "auth": {
                "register": link("auth-register"),
                "login": link("auth-login"),
                "me": link("auth-me"),
                "logout": link("auth-logout"),
            },
            "beckn": {
                "provider-profile": link("provider-profile"),
                "catalog": link("catalog"),
                "network-providers": link("network-providers"),
            },
        }
    )
