from django.contrib.auth.models import User
from rest_framework import generics, permissions
from rest_framework.response import Response

from .serializers import UserSerializer


class MeView(generics.RetrieveAPIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = UserSerializer

    def get_object(self):
        return self.request.user
