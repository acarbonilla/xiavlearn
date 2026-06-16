from unittest.mock import patch

from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
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

    def test_diagnostic_updates_profile_and_only_text_assessed_masteries(self):
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
        self.assertEqual(data['assessment_mode'], 'text_only')
        self.assertEqual(data['assessed_skills'], ['Grammar', 'Vocabulary'])
        self.assertEqual(
            data['unassessed_skills'],
            ['Speaking', 'Listening', 'Pronunciation'],
        )
        self.assertEqual(data['overall_level'], 'A2')
        self.assertEqual(set(data['skill_scores']), {'Grammar', 'Vocabulary'})
        self.assertNotIn('Speaking', data['skill_scores'])
        self.assertEqual(data['skill_status']['Grammar'], 'Assessed')
        self.assertEqual(data['skill_status']['Speaking'], 'Requires voice test')
        self.assertEqual(data['skill_status']['Listening'], 'Requires audio test')
        self.assertEqual(data['weak_skills'], ['Vocabulary', 'Grammar'])
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
        self.assertEqual(SkillMastery.objects.filter(user=self.user).count(), 2)
        self.assertEqual(
            SkillMastery.objects.filter(
                user=self.user,
                skill__name__in=['Speaking', 'Listening', 'Pronunciation'],
            ).count(),
            0,
        )
        recommendation = self.client.get('/api/curriculum/recommendation/')
        recommendation_data = self.assert_success_response(recommendation)
        self.assertEqual(
            recommendation_data['recommended_module']['id'],
            self.grammar_module.id,
        )
        self.assertIn('Grammar', recommendation_data['reason'])

    @patch('agents.services.call_llm_json')
    def test_diagnostic_uses_llm_result_when_available_and_sanitizes_unassessed_scores(self, mock_call_llm_json):
        self.authenticate()
        mock_call_llm_json.return_value = {
            'assessment_mode': 'text_only',
            'assessed_skills': ['Grammar', 'Vocabulary'],
            'unassessed_skills': ['Speaking', 'Listening', 'Pronunciation'],
            'skill_scores': {
                'Grammar': 74,
                'Vocabulary': 78,
                'Speaking': 67,
                'Listening': 65,
                'Pronunciation': 70,
            },
            'skill_status': {
                'Grammar': 'Assessed',
                'Vocabulary': 'Assessed',
                'Speaking': 'Needs Review',
                'Listening': 'Needs Review',
                'Pronunciation': 'Needs Review',
            },
            'overall_level': 'B1',
            'weak_skills': ['Listening', 'Speaking'],
            'recommendation': 'Focus on writing clearer sentences with stronger grammar and vocabulary.',
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
        self.assertEqual(
            data['skill_scores'],
            {'Grammar': 74, 'Vocabulary': 78},
        )
        self.assertEqual(data['skill_status']['Speaking'], 'Requires voice test')
        self.assertEqual(data['weak_skills'], ['Grammar', 'Vocabulary'])
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
        self.assertEqual(SkillMastery.objects.filter(user=self.user).count(), 2)

    @patch('agents.services.call_llm_json')
    def test_diagnostic_sanitizes_llm_feedback_when_correction_is_copied_from_broken_answer(self, mock_call_llm_json):
        self.authenticate()
        original_answer = (
            "I'm Jane Doe living in this city. I am currently working as I.T. "
            'Tech support in a large and international company that base in capital region.'
        )
        mock_call_llm_json.return_value = {
            'skill_scores': {'Grammar': 42, 'Vocabulary': 48},
            'overall_level': 'A2',
            'weak_skills': ['Grammar', 'Vocabulary'],
            'recommendation': 'Focus on Grammar and Vocabulary.',
            'level_explanation': 'Your level is A2 because you can express basic ideas.',
            'answer_feedback': [
                {
                    'question': 'Introduce yourself in English.',
                    'answer': original_answer,
                    'feedback': 'Good response. Improve grammar and naturalness.',
                    'corrected_answer': original_answer,
                    'mistakes': [],
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
                        'answer': original_answer,
                    }
                ]
            },
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = self.assert_success_response(response)
        feedback = data['answer_feedback'][0]
        self.assertNotEqual(feedback['corrected_answer'], original_answer)
        self.assertTrue(feedback['mistakes'])
        self.assertIn('grammar', feedback['feedback'].lower())
        self.assertIn('I live in this city', feedback['corrected_answer'])
        self.assertIn('technical support', feedback['corrected_answer'])

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
        self.assertEqual(set(data['skill_scores']), {'Grammar', 'Vocabulary'})
        self.assertEqual(len(data['answer_feedback']), 1)
        self.assertIn('past tense', data['answer_feedback'][0]['feedback'].lower())
        self.assertTrue(data['answer_feedback'][0]['mistakes'])

    def test_low_quality_diagnostic_feedback_produces_real_corrections(self):
        self.authenticate()

        response = self.client.post(
            '/api/diagnostic/evaluate/',
            {
                'answers': [
                    {
                        'question': 'Introduce yourself in English.',
                        'answer': (
                            "I'm Jane Doe living in this city. I am currently working as I.T. "
                            'Tech support in a large and international company that base in capital region.'
                        ),
                    },
                    {
                        'question': 'Describe what you did yesterday.',
                        'answer': 'I did was I did on what we did before and after thisss.. real thing most.',
                    },
                    {
                        'question': 'What is your learning goal?',
                        'answer': 'Goal is the gola of others were are hosell making green.',
                    },
                ]
            },
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = self.assert_success_response(response)
        self.assertEqual(data['overall_level'], 'A1')
        self.assertLess(data['skill_scores']['Grammar'], 50)
        self.assertLess(data['skill_scores']['Vocabulary'], 50)
        self.assertNotIn('Speaking', data['skill_scores'])
        self.assertEqual(data['skill_status']['Speaking'], 'Requires voice test')
        self.assertEqual(data['skill_status']['Listening'], 'Requires audio test')
        self.assertEqual(data['skill_status']['Pronunciation'], 'Requires voice test')
        self.assertIn('clear basic sentences', data['recommendation'])
        self.assertIn('unclear', data['level_explanation'].lower())
        self.assertEqual(
            data['next_step'],
            'Practice simple complete sentences before moving to longer answers.',
        )

        for item in data['answer_feedback']:
            self.assertNotEqual(item['corrected_answer'], item['answer'])
            self.assertTrue(item['mistakes'])
            self.assertNotIn('Strong response', item['feedback'])
            self.assertNotIn('clear and understandable', item['feedback'].lower())

        first_feedback = data['answer_feedback'][0]
        self.assertIn('Jane Doe', first_feedback['corrected_answer'])
        self.assertIn('technical support', first_feedback['corrected_answer'])
        self.assertTrue(
            any(mistake['type'] in {'Grammar', 'Sentence Structure', 'Naturalness'} for mistake in first_feedback['mistakes'])
        )

        second_feedback = data['answer_feedback'][1]
        self.assertIn('Yesterday', second_feedback['corrected_answer'])
        self.assertIn('continued', second_feedback['corrected_answer'])
        self.assertIn('unclear', second_feedback['feedback'].lower())

        third_feedback = data['answer_feedback'][2]
        self.assertIn('learning goal', third_feedback['corrected_answer'].lower())
        self.assertIn('unclear', third_feedback['feedback'].lower())

    @patch('agents.services.call_llm_json')
    def test_diagnostic_normalizes_unclear_answers_into_question_aware_corrections(self, mock_call_llm_json):
        self.authenticate()
        answers = [
            {
                'question': 'Introduce yourself in English.',
                'answer': 'Me I am with you , ohw with us.',
            },
            {
                'question': 'Describe what you did yesterday.',
                'answer': 'Did I do not will be oyourss.',
            },
            {
                'question': 'What is your learning goal?',
                'answer': 'Me goal to goal the goalingbowekng',
            },
        ]
        mock_call_llm_json.return_value = {
            'skill_scores': {'Grammar': 25, 'Vocabulary': 29},
            'overall_level': 'A1',
            'weak_skills': ['Grammar', 'Vocabulary'],
            'recommendation': 'Focus on Grammar and Vocabulary.',
            'level_explanation': 'Your level is A1 because the answers are limited and unclear.',
            'answer_feedback': [
                {
                    'question': item['question'],
                    'answer': item['answer'],
                    'feedback': 'Your answer is already clear, correct, and complete for this question.',
                    'corrected_answer': item['answer'],
                    'mistakes': [],
                }
                for item in answers
            ],
            'next_step': 'Review your weak skills and start the recommended module.',
        }

        response = self.client.post(
            '/api/diagnostic/evaluate/',
            {'answers': answers},
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = self.assert_success_response(response)

        first_feedback, second_feedback, third_feedback = data['answer_feedback']
        self.assertEqual(
            first_feedback['corrected_answer'],
            'My name is Jane Doe. I live in this city. I am learning English to improve my communication skills.',
        )
        self.assertEqual(
            second_feedback['corrected_answer'],
            'Yesterday, I practiced English and worked on my tasks.',
        )
        self.assertEqual(
            third_feedback['corrected_answer'],
            'My learning goal is to improve my English and communicate more clearly.',
        )

        for item in data['answer_feedback']:
            self.assertIn('unclear', item['feedback'].lower())
            self.assertNotIn('already clear', item['feedback'].lower())
            self.assertNotEqual(item['corrected_answer'], item['answer'])
            self.assertTrue(item['mistakes'])

    def test_voice_diagnostic_prompts_returns_pronunciation_target(self):
        self.authenticate()

        response = self.client.get('/api/voice-diagnostic/prompts/')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = self.assert_success_response(response)
        self.assertEqual(
            data['pronunciation']['target_sentence'],
            'I want to improve my English communication skills for work and daily conversations.',
        )

    @override_settings(USE_VOICE_DIAGNOSTIC=False, DEEPGRAM_API_KEY='')
    def test_voice_diagnostic_tts_returns_safe_error_when_not_configured(self):
        self.authenticate()

        response = self.client.post(
            '/api/voice-diagnostic/tts/',
            {
                'text': 'I want to improve my English communication skills for work and daily conversations.',
            },
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_503_SERVICE_UNAVAILABLE)
        self.assertFalse(response.data['success'])
        self.assertEqual(response.data['error'], 'TTS is not configured yet.')

    @override_settings(USE_VOICE_DIAGNOSTIC=False, DEEPGRAM_API_KEY='', DEEPGRAM_STT_MODEL='nova-2')
    def test_pronunciation_evaluate_returns_safe_error_when_stt_not_configured(self):
        self.authenticate()
        audio_file = SimpleUploadedFile(
            'pronunciation.webm',
            b'fake audio',
            content_type='audio/webm',
        )

        response = self.client.post(
            '/api/voice-diagnostic/pronunciation/evaluate/',
            {
                'audio_file': audio_file,
                'target_sentence': 'I want to improve my English communication skills for work and daily conversations.',
            },
            format='multipart',
        )

        self.assertEqual(response.status_code, status.HTTP_503_SERVICE_UNAVAILABLE)
        self.assertFalse(response.data['success'])
        self.assertEqual(response.data['error'], 'Speech-to-text is not configured yet.')

    @patch('agents.voice_services.transcribe_audio')
    def test_pronunciation_evaluate_scores_transcript_and_updates_mastery(self, mock_transcribe_audio):
        self.authenticate()
        mock_transcribe_audio.return_value = (
            'I want to improve my English skills for work and daily conversations.'
        )
        audio_file = SimpleUploadedFile(
            'pronunciation.webm',
            b'fake audio',
            content_type='audio/webm',
        )

        response = self.client.post(
            '/api/voice-diagnostic/pronunciation/evaluate/',
            {
                'audio_file': audio_file,
                'target_sentence': 'I want to improve my English communication skills for work and daily conversations.',
            },
            format='multipart',
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = self.assert_success_response(response)
        self.assertEqual(data['transcript'], mock_transcribe_audio.return_value)
        self.assertEqual(data['score'], 92)
        self.assertEqual(data['word_accuracy'], 92)
        self.assertEqual(data['status'], 'Mastered')
        self.assertEqual(data['missing_words'], ['communication'])
        self.assertEqual(data['extra_words'], [])
        mastery = SkillMastery.objects.get(
            user=self.user,
            skill__name='Pronunciation',
        )
        self.assertEqual(int(mastery.score), 92)
        self.assertEqual(mastery.status, 'Mastered')

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
