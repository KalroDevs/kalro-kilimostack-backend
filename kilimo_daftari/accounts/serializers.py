from django.contrib.auth.models import User
from django.contrib.auth.password_validation import validate_password
from rest_framework import serializers

from providers.models import ProviderMembership


class RegisterSerializer(serializers.Serializer):
    """
    Self-service account creation. Deliberately does NOT grant any
    ProviderMembership -- per the platform's governed-onboarding design
    (see providers/permissions.py), a new account can browse read-only
    content until a staff admin links it to a provider. This mirrors how
    Provider/ServiceCategory creation is staff-only: joining the network to
    *screen* content is an onboarding decision, not a signup checkbox.
    """

    username = serializers.CharField(max_length=150)
    email = serializers.EmailField(required=False, allow_blank=True, default="")
    password = serializers.CharField(write_only=True)

    def validate_username(self, value):
        if User.objects.filter(username=value).exists():
            raise serializers.ValidationError("That username is already taken.")
        return value

    def validate_password(self, value):
        validate_password(value)
        return value

    def create(self, validated_data):
        user = User.objects.create_user(
            username=validated_data["username"],
            email=validated_data.get("email", ""),
            password=validated_data["password"],
        )
        return user


class LoginSerializer(serializers.Serializer):
    username = serializers.CharField()
    password = serializers.CharField(write_only=True)


class ProviderMembershipSummarySerializer(serializers.ModelSerializer):
    provider_id = serializers.CharField(source="provider.provider_id")
    provider_name = serializers.CharField(source="provider.name")

    class Meta:
        model = ProviderMembership
        fields = ["provider_id", "provider_name", "role"]


class CurrentUserSerializer(serializers.ModelSerializer):
    provider_memberships = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = ["id", "username", "email", "is_staff", "provider_memberships"]

    def get_provider_memberships(self, obj):
        memberships = ProviderMembership.objects.filter(user=obj).select_related("provider")
        return ProviderMembershipSummarySerializer(memberships, many=True).data
