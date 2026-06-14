from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.models import User
from django.db import transaction
from django.middleware.csrf import get_token
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import ensure_csrf_cookie
from rest_framework import exceptions, permissions, status
from rest_framework.authentication import CSRFCheck
from rest_framework.response import Response
from rest_framework.views import APIView

from learning.models import LearnerProfile
from xiavlearn.api import success_response

from .serializers import LoginSerializer, RegisterSerializer, UserSerializer


def _get_response(request):
    return None


class CsrfRequired(permissions.BasePermission):
    def has_permission(self, request, view):
        check = CSRFCheck(_get_response)
        check.process_request(request)
        reason = check.process_view(request, None, (), {})
        if reason:
            raise exceptions.PermissionDenied(f'CSRF Failed: {reason}')
        return True


@method_decorator(ensure_csrf_cookie, name='dispatch')
class CsrfView(APIView):
    permission_classes = [permissions.AllowAny]

    def get(self, request):
        return success_response(
            {'csrf_token': get_token(request)},
            'CSRF token generated.',
        )


class RegisterView(APIView):
    permission_classes = [CsrfRequired]

    def post(self, request):
        serializer = RegisterSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        with transaction.atomic():
            user = User.objects.create_user(**serializer.validated_data)
            LearnerProfile.objects.create(user=user)

        login(request, user)
        return success_response(
            UserSerializer(user).data,
            'Registration successful.',
            status.HTTP_201_CREATED,
        )


class LoginView(APIView):
    permission_classes = [CsrfRequired]

    def post(self, request):
        serializer = LoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = authenticate(request, **serializer.validated_data)
        if user is None:
            return Response(
                {
                    'success': False,
                    'error': 'Invalid username or password.',
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        login(request, user)
        return success_response(
            UserSerializer(user).data,
            'Login successful.',
        )


class LogoutView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        logout(request)
        return success_response({}, 'Logout successful.')


class MeView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        return success_response(
            UserSerializer(request.user).data,
            'Current user retrieved.',
        )
