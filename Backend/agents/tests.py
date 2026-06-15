from unittest.mock import patch

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

    def assert_success_response(self, response):
        self.assertTrue(response.data['success'])
        self.assertIn('data', response.data)
        self.assertTrue(response.data['message'])
        return response.data['data']

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
            self.assertFalse(response.data['success'])
            self.assertTrue(response.data['error'])

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
        data = self.assert_success_response(response)
        self.assertEqual(data['overall_level'], 'A2')
        self.assertEqual(set(data['skill_scores']), set(self.skills))
        self.assertEqual(data['weak_skills'], ['Listening', 'Speaking'])
        self.assertIn('Your level is A2', data['level_explanation'])
        self.assertEqual(len(data['answer_feedback']), 1)
        self.assertEqual(
            data['answer_feedback'][0]['question'],
            'Introduce yourself in English.',
        )
        self.assertTrue(data['answer_feedback'][0]['feedback'])
        self.assertIn('corrected_answer', data['answer_feedback'][0])
        self.assertIn('mistakes', data['answer_feedback'][0])
        self.assertEqual(
            data['next_step'],
            'Review your weak skills and start the recommended module.',
        )
        self.assertEqual(LearnerProfile.objects.get(user=self.user).current_level, 'A2')
        self.assertEqual(SkillMastery.objects.filter(user=self.user).count(), 5)
        recommendation = self.client.get('/api/curriculum/recommendation/')
        recommendation_data = self.assert_success_response(recommendation)
        self.assertEqual(
            recommendation_data['recommended_module']['id'],
            self.speaking_module.id,
        )
        self.assertIn('Speaking', recommendation_data['reason'])

    @patch('agents.services.call_llm_json')
    def test_diagnostic_uses_llm_result_when_available(self, mock_call_llm_json):
        self.authenticate()
        mock_call_llm_json.return_value = {
            'overall_level': 'B1',
            'skill_scores': {
                'Grammar': 74,
                'Vocabulary': 78,
                'Speaking': 67,
                'Listening': 65,
                'Pronunciation': 70,
            },
            'weak_skills': ['Listening', 'Speaking'],
            'recommendation': 'Focus on Listening and Speaking.',
            'level_explanation': 'Your level is B1 because you can express connected ideas with some detail.',
            'answer_feedback': [
                {
                    'question': 'Introduce yourself in English.',
                    'answer': 'My name is Ana and I study every night.',
                    'feedback': 'Good response. Add more detail about your routine.',
                    'corrected_answer': 'Hi, my name is Ana. I study English every night.',
                    'mistakes': [
                        {
                            'type': 'Sentence Structure',
                            'original': 'I study every night.',
                            'correction': 'I study English every night.',
                            'explanation': 'Add the object to make the idea more specific.',
                        }
                    ],
                }
            ],
            'next_step': 'Review your weak skills and start the recommended module.',
        }

        response = self.client.post(
            '/api/diagnostic/evaluate/',
            {
                'answers': [
                    {
                        'question': 'Introduce yourself in English.',
                        'answer': 'My name is Ana and I study every night.',
                    }
                ]
            },
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = self.assert_success_response(response)
        self.assertEqual(data['overall_level'], 'B1')
        self.assertEqual(data['skill_scores']['Grammar'], 74)
        self.assertEqual(
            data['level_explanation'],
            'Your level is B1 because you can express connected ideas with some detail.',
        )
        self.assertEqual(
            data['answer_feedback'][0]['corrected_answer'],
            'Hi, my name is Ana. I study English every night.',
        )
        self.assertEqual(
            data['answer_feedback'][0]['mistakes'][0]['type'],
            'Sentence Structure',
        )
        self.assertEqual(LearnerProfile.objects.get(user=self.user).current_level, 'B1')

    @patch('agents.services.call_llm_json')
    def test_diagnostic_falls_back_when_llm_payload_is_invalid(self, mock_call_llm_json):
        self.authenticate()
        mock_call_llm_json.return_value = {
            'overall_level': 'B1',
            'weak_skills': ['Listening', 'Speaking'],
        }

        response = self.client.post(
            '/api/diagnostic/evaluate/',
            {
                'answers': [
                    {
                        'question': 'Describe what you did yesterday.',
                        'answer': 'Yesterday I go to school.',
                    }
                ]
            },
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = self.assert_success_response(response)
        self.assertNotEqual(data['overall_level'], 'B1')
        self.assertIn('Your level is', data['level_explanation'])
        self.assertEqual(len(data['answer_feedback']), 1)
        self.assertIn('past tense', data['answer_feedback'][0]['feedback'].lower())
        self.assertTrue(data['answer_feedback'][0]['mistakes'])

    def test_low_quality_diagnostic_feedback_is_specific_and_beginner_friendly(self):
        self.authenticate()

        response = self.client.post(
            '/api/diagnostic/evaluate/',
            {
                'answers': [
                    {
                        'question': 'Introduce yourself in English.',
                        'answer': 'Hi Im me and you. Please be me why not.',
                    },
                    {
                        'question': 'Describe what you did yesterday.',
                        'answer': 'I did almost things look lakkee.',
                    },
                    {
                        'question': 'What is your learning goal?',
                        'answer': 'me learng was to be enough hose.',
                    },
                ]
            },
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = self.assert_success_response(response)
        self.assertEqual(data['overall_level'], 'A1')
        self.assertLess(data['skill_scores']['Grammar'], 50)
        self.assertLess(data['skill_scores']['Speaking'], 50)
        self.assertIn('clear basic sentences', data['recommendation'])
        self.assertIn('unclear', data['level_explanation'].lower())
        self.assertEqual(
            data['next_step'],
            'Practice simple complete sentences before moving to longer answers.',
        )
        first_feedback = data['answer_feedback'][0]
        self.assertNotIn('Strong response', first_feedback['feedback'])
        self.assertIn('unclear', first_feedback['feedback'].lower())
        self.assertTrue(first_feedback['corrected_answer'])
        self.assertTrue(first_feedback['mistakes'])
        self.assertEqual(first_feedback['mistakes'][0]['type'], 'Grammar')
        self.assertIn('I am', first_feedback['corrected_answer'])

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
        recommendation_data = self.assert_success_response(recommendation)
        dashboard_data = self.assert_success_response(dashboard)
        self.assertEqual(
            recommendation_data['recommended_module']['id'],
            self.grammar_module.id,
        )
        self.assertEqual(
            dashboard_data['recommended_module'],
            recommendation_data['recommended_module'],
        )

    def test_teacher_session_and_feedback_persist_progress(self):
        self.authenticate()
        session_response = self.client.post(
            '/api/teacher/session/',
            {'module_id': self.grammar_module.id},
            format='json',
        )

        self.assertEqual(session_response.status_code, status.HTTP_201_CREATED)
        session_data = self.assert_success_response(session_response)
        self.assertIn('Past Tense', session_data['lesson'])
        self.assertTrue(session_data['practice_question'])

        feedback_response = self.client.post(
            '/api/teacher/feedback/',
            {
                'session_id': session_data['session_id'],
                'answer': 'Yesterday I go to mall.',
            },
            format='json',
        )

        self.assertEqual(feedback_response.status_code, status.HTTP_200_OK)
        feedback_data = self.assert_success_response(feedback_response)
        self.assertEqual(feedback_data['score'], 62)
        self.assertEqual(
            feedback_data['feedback'],
            'Good attempt. Review verb tense.',
        )
        session = StudySession.objects.get(pk=session_data['session_id'])
        self.assertEqual(session.input_text, 'Yesterday I go to mall.')
        self.assertEqual(int(session.score), 62)
        self.assertIsNotNone(session.completed_at)
        mastery = SkillMastery.objects.get(user=self.user, skill=self.skills['Grammar'])
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
        self.assertFalse(response.data['success'])
        self.assertEqual(response.data['error'], 'No StudySession matches the given query.')

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

        plan_response = self.client.post('/api/scheduler/generate-plan/', {}, format='json')
        coach_response = self.client.get('/api/coach/summary/')

        self.assertEqual(plan_response.status_code, status.HTTP_201_CREATED)
        plan_data = self.assert_success_response(plan_response)
        coach_data = self.assert_success_response(coach_response)
        self.assertEqual(plan_data['plan']['focus'], ['Grammar', 'Speaking'])
        self.assertEqual(StudyPlan.objects.filter(user=self.user).count(), 1)
        self.assertEqual(coach_response.status_code, status.HTTP_200_OK)
        self.assertIn('Grammar', coach_data['summary'])
        self.assertEqual(coach_data['next_step'], 'Complete your recommended module.')

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

        self.assertEqual(diagnostic.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(teacher_session.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(feedback.status_code, status.HTTP_400_BAD_REQUEST)
        for response in [diagnostic, teacher_session, feedback]:
            self.assertFalse(response.data['success'])
            self.assertTrue(response.data['error'])

    def test_agent_response_includes_cors_header_for_frontend_origin(self):
        self.authenticate()

        response = self.client.get(
            '/api/coach/summary/',
            HTTP_ORIGIN='http://localhost:3000',
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response['Access-Control-Allow-Origin'], 'http://localhost:3000')
