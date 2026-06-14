from django.contrib.auth.models import User
from rest_framework import status
from rest_framework.test import APIClient, APITestCase

from learning.models import LearnerProfile


class SessionAuthAPITests(APITestCase):
    def setUp(self):
        self.client = APIClient(enforce_csrf_checks=True)

    def get_csrf_token(self):
        response = self.client.get('/api/auth/csrf/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data['success'])
        return response.data['data']['csrf_token']

    def post_with_csrf(self, path, data):
        return self.client.post(
            path,
            data,
            format='json',
            HTTP_X_CSRFTOKEN=self.get_csrf_token(),
        )

    def test_register_creates_profile_logs_in_and_returns_user(self):
        response = self.post_with_csrf(
            '/api/auth/register/',
            {
                'username': 'new-learner',
                'email': 'learner@example.com',
                'password': 'Strong-password-2026',
            },
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertTrue(response.data['success'])
        user = User.objects.get(username='new-learner')
        self.assertTrue(LearnerProfile.objects.filter(user=user).exists())

        me_response = self.client.get('/api/auth/me/')
        self.assertEqual(me_response.status_code, status.HTTP_200_OK)
        self.assertEqual(me_response.data['data']['username'], 'new-learner')

    def test_login_logout_and_me_use_session_authentication(self):
        User.objects.create_user(
            username='learner',
            email='learner@example.com',
            password='Strong-password-2026',
        )

        login_response = self.post_with_csrf(
            '/api/auth/login/',
            {
                'username': 'learner',
                'password': 'Strong-password-2026',
            },
        )
        self.assertEqual(login_response.status_code, status.HTTP_200_OK)

        me_response = self.client.get('/api/auth/me/')
        self.assertEqual(me_response.status_code, status.HTTP_200_OK)
        self.assertEqual(me_response.data['data']['username'], 'learner')

        logout_response = self.post_with_csrf('/api/auth/logout/', {})
        self.assertEqual(logout_response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            self.client.get('/api/auth/me/').status_code,
            status.HTTP_403_FORBIDDEN,
        )

    def test_invalid_login_returns_standard_error_envelope(self):
        response = self.post_with_csrf(
            '/api/auth/login/',
            {'username': 'missing', 'password': 'incorrect-password'},
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(response.data['success'])
        self.assertEqual(response.data['error'], 'Invalid username or password.')

    def test_auth_post_requires_csrf_token(self):
        response = self.client.post(
            '/api/auth/register/',
            {
                'username': 'new-learner',
                'email': 'learner@example.com',
                'password': 'Strong-password-2026',
            },
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertFalse(response.data['success'])
