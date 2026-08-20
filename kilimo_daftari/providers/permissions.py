"""
Multi-tenancy enforcement: a user may only create/edit CatalogItems for
providers they hold a ProviderMembership for (staff/superusers bypass this).
Reading is open, matching the rest of the project's DEFAULT_PERMISSION_CLASSES
(IsAuthenticatedOrReadOnly) -- certified listings are meant to be discoverable.
"""

from rest_framework import permissions

from .models import ProviderMembership


def user_provider_ids(user) -> set[int]:
    if not user or not user.is_authenticated:
        return set()
    return set(ProviderMembership.objects.filter(user=user).values_list("provider_id", flat=True))


class IsProviderMemberOrReadOnly(permissions.BasePermission):
    """For CatalogItemViewSet: object-level check that the user belongs to
    the item's provider (or is staff)."""

    def has_permission(self, request, view):
        if request.method in permissions.SAFE_METHODS:
            return True
        if not request.user or not request.user.is_authenticated:
            return False
        if request.user.is_staff:
            return True
        # On create, the payload names the provider explicitly.
        if request.method == "POST":
            provider_id = request.data.get("provider")
            try:
                return int(provider_id) in user_provider_ids(request.user)
            except (TypeError, ValueError):
                return False
        return True  # object-level check below covers PATCH/PUT/DELETE

    def has_object_permission(self, request, view, obj):
        if request.method in permissions.SAFE_METHODS:
            return True
        if request.user.is_staff:
            return True
        return obj.provider_id in user_provider_ids(request.user)


class IsStaffOrReadOnly(permissions.BasePermission):
    """For Provider / ServiceCategory: network taxonomy is centrally managed."""

    def has_permission(self, request, view):
        if request.method in permissions.SAFE_METHODS:
            return True
        return bool(request.user and request.user.is_authenticated and request.user.is_staff)
