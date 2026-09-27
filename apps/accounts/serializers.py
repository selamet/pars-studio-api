from rest_framework import serializers

from .models import User


class UserSerializer(serializers.ModelSerializer):
    email_verified = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = ["id", "email", "first_name", "last_name", "email_verified", "date_joined"]
        read_only_fields = ["id", "email", "email_verified", "date_joined"]

    def get_email_verified(self, user: User) -> bool:
        return user.emailaddress_set.filter(email__iexact=user.email, verified=True).exists()
