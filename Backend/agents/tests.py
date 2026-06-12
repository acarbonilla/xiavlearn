from django.contrib.auth.models import User
from rest_framework import status
from rest_framework.test import APITestCase

from learning.models import (
    CurriculumLevel,
    LearnerProfile,
    Module,
    Skill,
    SkillMastery,
    StudyPlan,
    StudySession,
)


class AgentMVPAPITests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username='learner',
            password='test-password-123',
        )
        self.other_user = User.objects.create_user(
            username='other-learner',
            password='test-password-123',
        )
        self.level_a1 = CurriculumLevel.objects.create(
            level_code='A1',
            name='Beginner',
            sort_order=1,
        )
        self.level_a2 = CurriculumLevel.objects.create(
            level_code='A2',
            name='Elementary',
            sort_order=2,
        )
        self.skills = {
            name: Skill.objects.create(name=name)
            for name in [
                'Grammar',
                'Vocabulary',
                'Speaking',
                'Listening',
                'Pronunciation',
            ]
        }
        self.grammar_module = Module.objects.create(
            level=self.level_a2,
            skill=self.skills['Grammar'],
            title='Past Tense',
            description='Practice regular and irregular past tense verbs.',
            objectives=['Describe yesterday activities'],
            sort_order=1,
        )
        self.speaking_module = Module.objects.create(
            level=self.level_a2,
            skill=self.skills['Speaking'],
            title='Asking and Answering Questions',
            description='Practice basic information exchange.',
            objectives=['Answer questions in complete sentences'],
            sort_order=2,
        )

    def authenticate(self):
        self.client.force_authenticate(self.user)

    def test_all_agent_endpoints_require_authentication(self):
        requests = [
            ('post', '/api/diagnostic/evaluate/', {'answers': []}),
            ('get', '/api/curriculum/recommendation/', None),
            ('post', '/api/teacher/session/', {'module_id': 1}),
            (
                'post',
                '/api/teacher/feedback/',
                {'session_id': 1, 'answer': 'Test answer.'},
            ),
            ('post', '/api/scheduler/generate-plan/', {}),
            ('get', '/api/coach/summary/', None),
        ]

        for method, path, data in requests:
            response = getattr(self.client, method)(path, data, format='json')
            self.assertIn(
                response.status_code,
                [status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN],
                path,
            )

    def test_diagnostic_updates_profile_and_all_skill_masteries(self):
        self.authenticate()

        response = self.client.post(
            '/api/diagnostic/evaluate/',
            {
                'answers': [
                    {
                        'question': 'Introduce yourself in English.',
                        'answer': 'My name is Alfie and I live in Cebu.',
                    }
                ]
            },
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['overall_level'], 'A2')
        self.assertEqual(
            set(response.data['skill_scores']),
            set(self.skills),
        )
        self.assertEqual(
            response.data['weak_skills'],
            ['Listening', 'Speaking'],
        )
        self.assertEqual(
            LearnerProfile.objects.get(user=self.user).current_level,
            'A2',
        )
        self.assertEqual(
            SkillMastery.objects.filter(user=self.user).count(),
            5,
        )
        recommendation = self.client.get('/api/curriculum/recommendation/')
        self.assertEqual(
            recommendation.data['recommended_module']['id'],
            self.speaking_module.id,
        )
        self.assertIn('Speaking', recommendation.data['reason'])

    def test_recommendation_and_dashboard_reuse_same_module(self):
        self.authenticate()
        LearnerProfile.objects.create(user=self.user, current_level='A2')
        SkillMastery.objects.create(
            user=self.user,
            skill=self.skills['Grammar'],
            level_code='A2',
            score=45,
        )
        SkillMastery.objects.create(
            user=self.user,
            skill=self.skills['Speaking'],
            level_code='A2',
            score=75,
        )

        recommendation = self.client.get('/api/curriculum/recommendation/')
        dashboard = self.client.get('/api/dashboard/')

        self.assertEqual(recommendation.status_code, status.HTTP_200_OK)
        self.assertEqual(dashboard.status_code, status.HTTP_200_OK)
        self.assertEqual(
            recommendation.data['recommended_module']['id'],
            self.grammar_module.id,
        )
        self.assertEqual(
            dashboard.data['recommended_module'],
            recommendation.data['recommended_module'],
        )

    def test_teacher_session_and_feedback_persist_progress(self):
        self.authenticate()
        session_response = self.client.post(
            '/api/teacher/session/',
            {'module_id': self.grammar_module.id},
            format='json',
        )

        self.assertEqual(
            session_response.status_code,
            status.HTTP_201_CREATED,
        )
        self.assertIn('Past Tense', session_response.data['lesson'])
        self.assertTrue(session_response.data['practice_question'])

        feedback_response = self.client.post(
            '/api/teacher/feedback/',
            {
                'session_id': session_response.data['session_id'],
                'answer': 'Yesterday I go to mall.',
            },
            format='json',
        )

        self.assertEqual(feedback_response.status_code, status.HTTP_200_OK)
        self.assertEqual(feedback_response.data['score'], 62)
        self.assertEqual(
            feedback_response.data['feedback'],
            'Good attempt. Review verb tense.',
        )
        session = StudySession.objects.get(
            pk=session_response.data['session_id']
        )
        self.assertEqual(session.input_text, 'Yesterday I go to mall.')
        self.assertEqual(int(session.score), 62)
        self.assertIsNotNone(session.completed_at)
        mastery = SkillMastery.objects.get(
            user=self.user,
            skill=self.skills['Grammar'],
        )
        self.assertEqual(int(mastery.score), 62)
        self.assertEqual(mastery.status, 'Learning')

    def test_feedback_cannot_update_another_users_session(self):
        self.authenticate()
        session = StudySession.objects.create(
            user=self.other_user,
            module=self.grammar_module,
        )

        response = self.client.post(
            '/api/teacher/feedback/',
            {
                'session_id': session.id,
                'answer': 'Yesterday I went to the mall.',
            },
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_scheduler_and_coach_return_saved_progress(self):
        self.authenticate()
        SkillMastery.objects.create(
            user=self.user,
            skill=self.skills['Grammar'],
            level_code='A2',
            score=40,
        )
        SkillMastery.objects.create(
            user=self.user,
            skill=self.skills['Speaking'],
            level_code='A2',
            score=55,
        )

        plan_response = self.client.post(
            '/api/scheduler/generate-plan/',
            {},
            format='json',
        )
        coach_response = self.client.get('/api/coach/summary/')

        self.assertEqual(
            plan_response.status_code,
            status.HTTP_201_CREATED,
        )
        self.assertEqual(
            plan_response.data['plan']['focus'],
            ['Grammar', 'Speaking'],
        )
        self.assertEqual(StudyPlan.objects.filter(user=self.user).count(), 1)
        self.assertEqual(coach_response.status_code, status.HTTP_200_OK)
        self.assertIn('Grammar', coach_response.data['summary'])
        self.assertEqual(
            coach_response.data['next_step'],
            'Complete your recommended module.',
        )

    def test_invalid_agent_payloads_return_400(self):
        self.authenticate()

        diagnostic = self.client.post(
            '/api/diagnostic/evaluate/',
            {'answers': []},
            format='json',
        )
        teacher_session = self.client.post(
            '/api/teacher/session/',
            {'module_id': 'not-an-id'},
            format='json',
        )
        feedback = self.client.post(
            '/api/teacher/feedback/',
            {'session_id': 1, 'answer': ''},
            format='json',
        )

        self.assertEqual(
            diagnostic.status_code,
            status.HTTP_400_BAD_REQUEST,
        )
        self.assertEqual(
            teacher_session.status_code,
            status.HTTP_400_BAD_REQUEST,
        )
        self.assertEqual(
            feedback.status_code,
            status.HTTP_400_BAD_REQUEST,
        )
