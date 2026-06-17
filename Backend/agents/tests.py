from unittest.mock import patch

from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from rest_framework import status
from rest_framework.test import APITestCase

from agents.models import LessonSession, LessonTurn
from agents.services import recalculate_learner_level
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
            ('post', '/api/teacher/session/start/', {'module_id': 1}),
            (
                'post',
                '/api/teacher/session/answer/',
                {'session_id': 1, 'student_answer': 'Test answer.'},
            ),
            ('get', '/api/teacher/session/1/', None),
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
    def test_strong_text_diagnostic_answers_score_high_and_preserve_confident_phrase(self, mock_call_llm_json):
        self.authenticate()
        mock_call_llm_json.return_value = None

        response = self.client.post(
            '/api/diagnostic/evaluate/',
            {
                'answers': [
                    {
                        'question': 'Introduce yourself in English.',
                        'answer': (
                            'My name is Alfredo Jr., and I have experience working as a '
                            'Technical Support Engineer, where I helped diagnose and resolve '
                            'technical issues while ensuring customer satisfaction. I am '
                            'passionate about technology, continuously improving my skills, '
                            'and I enjoy learning new tools and technologies to grow in my '
                            'career.'
                        ),
                    },
                    {
                        'question': 'Describe what you did yesterday.',
                        'answer': (
                            'Yesterday, I spent time improving my English communication skills '
                            'through listening and shadowing exercises while also reviewing '
                            'technical topics related to IT support and software development. '
                            'I also worked on learning more about Next.js and explored career '
                            'opportunities that match my technical background.'
                        ),
                    },
                    {
                        'question': 'What is your learning goal?',
                        'answer': (
                            'My learning goal is to improve my English communication skills '
                            'and become more confident in speaking and understanding native '
                            'English conversations. I also want to strengthen my knowledge of '
                            'Next.js and modern web development so I can build better '
                            'applications and advance my career in software development.'
                        ),
                    },
                ]
            },
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = self.assert_success_response(response)
        self.assertGreaterEqual(data['skill_scores']['Grammar'], 85)
        self.assertGreaterEqual(data['skill_scores']['Vocabulary'], 85)
        self.assertIn(data['overall_level'], {'B1', 'B2'})
        self.assertIn('clear, correct, and complete', data['grammar_reason'].lower())
        self.assertIn('vocabulary', data['vocabulary_reason'].lower())

        goal_feedback = next(
            item for item in data['answer_feedback']
            if item['question'] == 'What is your learning goal?'
        )
        self.assertEqual(goal_feedback['mistakes'], [])
        self.assertIn(
            'become more confident in speaking',
            goal_feedback['corrected_answer'].lower(),
        )
        self.assertNotIn(
            'become more confidently in speaking',
            goal_feedback['corrected_answer'].lower(),
        )

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

    def test_voice_diagnostic_prompts_returns_voice_targets(self):
        self.authenticate()

        response = self.client.get('/api/voice-diagnostic/prompts/')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = self.assert_success_response(response)
        self.assertEqual(
            data['pronunciation']['target_sentence'],
            'I want to improve my English communication skills for work and daily conversations.',
        )
        self.assertEqual(
            data['listening']['passage'],
            (
                'Maria works in an office. Yesterday, she helped a customer solve a computer problem. '
                'After work, she studied English for thirty minutes.'
            ),
        )
        self.assertEqual(data['listening']['question'], 'What problem did Maria help solve?')
        self.assertEqual(data['listening']['expected_answer'], 'A computer problem.')
        self.assertEqual(
            data['speaking']['question'],
            'Tell me about yourself and why you want to improve your English.',
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

    @override_settings(USE_VOICE_DIAGNOSTIC=False, DEEPGRAM_API_KEY='', DEEPGRAM_STT_MODEL='nova-2')
    def test_speaking_evaluate_returns_safe_error_when_stt_not_configured(self):
        self.authenticate()
        audio_file = SimpleUploadedFile(
            'speaking.webm',
            b'fake audio',
            content_type='audio/webm',
        )

        response = self.client.post(
            '/api/voice-diagnostic/speaking/evaluate/',
            {
                'audio_file': audio_file,
                'question': 'Tell me about yourself and why you want to improve your English.',
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

    @patch('agents.voice_services.transcribe_audio')
    def test_speaking_evaluate_scores_transcript_and_updates_mastery(self, mock_transcribe_audio):
        self.authenticate()
        mock_transcribe_audio.return_value = (
            'My name is Ana and I want to improve my English communication for work.'
        )
        audio_file = SimpleUploadedFile(
            'speaking.webm',
            b'fake audio',
            content_type='audio/webm',
        )

        response = self.client.post(
            '/api/voice-diagnostic/speaking/evaluate/',
            {
                'audio_file': audio_file,
                'question': 'Tell me about yourself and why you want to improve your English.',
            },
            format='multipart',
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = self.assert_success_response(response)
        self.assertEqual(data['transcript'], mock_transcribe_audio.return_value)
        self.assertGreaterEqual(data['score'], 80)
        self.assertEqual(data['status'], 'Mastered')
        self.assertTrue(data['strengths'])
        self.assertTrue(data['improvement_areas'])
        mastery = SkillMastery.objects.get(
            user=self.user,
            skill__name='Speaking',
        )
        self.assertEqual(mastery.status, 'Mastered')

    @patch('agents.voice_services.call_llm_json')
    def test_listening_evaluate_uses_rule_based_fallback_and_updates_mastery(self, mock_call_llm_json):
        self.authenticate()
        mock_call_llm_json.return_value = None

        response = self.client.post(
            '/api/voice-diagnostic/listening/evaluate/',
            {
                'question': 'What problem did Maria help solve?',
                'expected_answer': 'A computer problem.',
                'user_answer': 'She helped solve a computer problem.',
            },
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = self.assert_success_response(response)
        self.assertEqual(data['score'], 90)
        self.assertEqual(data['status'], 'Mastered')
        self.assertIn('Correct', data['feedback'])
        mastery = SkillMastery.objects.get(
            user=self.user,
            skill__name='Listening',
        )
        self.assertEqual(int(mastery.score), 90)
        self.assertEqual(mastery.status, 'Mastered')

    @patch('agents.voice_services.call_llm_json')
    def test_listening_evaluate_uses_llm_result_when_available(self, mock_call_llm_json):
        self.authenticate()
        mock_call_llm_json.return_value = {
            'score': 75,
            'feedback': 'You understood the main idea but missed some detail.',
        }

        response = self.client.post(
            '/api/voice-diagnostic/listening/evaluate/',
            {
                'question': 'What problem did Maria help solve?',
                'expected_answer': 'A computer problem.',
                'user_answer': 'A customer problem.',
            },
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = self.assert_success_response(response)
        self.assertEqual(data['score'], 75)
        self.assertEqual(data['status'], 'Learning')
        self.assertEqual(
            data['feedback'],
            'You understood the main idea but missed some detail.',
        )
        mastery = SkillMastery.objects.get(
            user=self.user,
            skill__name='Listening',
        )
        self.assertEqual(int(mastery.score), 75)
        self.assertEqual(mastery.status, 'Learning')

    def test_listening_evaluate_requires_user_answer(self):
        self.authenticate()

        response = self.client.post(
            '/api/voice-diagnostic/listening/evaluate/',
            {
                'question': 'What problem did Maria help solve?',
                'expected_answer': 'A computer problem.',
                'user_answer': '',
            },
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(response.data['success'])
        self.assertEqual(response.data['error'], 'user_answer must be a non-empty string.')

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
            skill=self.skills['Vocabulary'],
            level_code='A2',
            score=62,
        )
        SkillMastery.objects.create(
            user=self.user,
            skill=self.skills['Listening'],
            level_code='A2',
            score=58,
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
        self.assertEqual(recommendation_data['weakest_skill'], 'Grammar')
        self.assertEqual(
            recommendation_data['diagnostic_scores'],
            {
                'Vocabulary': 62,
                'Grammar': 45,
                'Listening': 58,
                'Speaking': 75,
            },
        )
        self.assertEqual(
            recommendation_data['current_skill_scores'],
            recommendation_data['diagnostic_scores'],
        )
        self.assertEqual(recommendation_data['learner_level'], 'A2')
        self.assertEqual(recommendation_data['module_level'], 'A2')
        self.assertFalse(recommendation_data['fallback_used'])
        self.assertIsNone(recommendation_data['fallback_reason'])

    def test_recommendation_prefers_exact_current_level_module_for_same_skill(self):
        self.authenticate()
        level_c1 = CurriculumLevel.objects.create(
            level_code='C1',
            name='Advanced',
            sort_order=5,
        )
        c1_grammar_module = Module.objects.create(
            level=level_c1,
            skill=self.skills['Grammar'],
            title='Advanced Grammar Patterns',
            description='Practice advanced grammar patterns.',
            objectives=['Use advanced grammar accurately'],
            sort_order=1,
        )
        LearnerProfile.objects.create(user=self.user, current_level='C1')
        SkillMastery.objects.create(
            user=self.user,
            skill=self.skills['Grammar'],
            level_code='C1',
            score=41,
        )
        SkillMastery.objects.create(
            user=self.user,
            skill=self.skills['Vocabulary'],
            level_code='C1',
            score=67,
        )

        response = self.client.get('/api/curriculum/recommendation/')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = self.assert_success_response(response)
        self.assertEqual(data['recommended_module']['id'], c1_grammar_module.id)
        self.assertEqual(data['learner_level'], 'C1')
        self.assertEqual(data['module_level'], 'C1')
        self.assertFalse(data['fallback_used'])
        self.assertIsNone(data['fallback_reason'])

    def test_study_plan_reports_fallback_when_only_lower_level_skill_module_exists(self):
        self.authenticate()
        self.grammar_module.delete()
        a1_grammar_module = Module.objects.create(
            level=self.level_a1,
            skill=self.skills['Grammar'],
            title='Basic Grammar Review',
            description='Review core grammar patterns.',
            objectives=['Review simple sentence rules'],
            sort_order=1,
        )
        level_c1 = CurriculumLevel.objects.create(
            level_code='C1',
            name='Advanced',
            sort_order=5,
        )
        LearnerProfile.objects.create(user=self.user, current_level='C1')
        SkillMastery.objects.create(
            user=self.user,
            skill=self.skills['Grammar'],
            level_code='C1',
            score=38,
        )
        SkillMastery.objects.create(
            user=self.user,
            skill=self.skills['Speaking'],
            level_code='C1',
            score=52,
        )

        response = self.client.post('/api/scheduler/generate-plan/', {}, format='json')

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        data = self.assert_success_response(response)
        first_item = data['plan']['items'][0]
        self.assertEqual(first_item['skill'], 'Grammar')
        self.assertEqual(first_item['learner_level'], 'C1')
        self.assertEqual(first_item['module_level'], 'A1')
        self.assertEqual(first_item['module_id'], a1_grammar_module.id)
        self.assertTrue(first_item['fallback_used'])
        self.assertIn('No C1 Grammar module is available yet', first_item['fallback_reason'])

    def test_study_plan_prefers_exact_a2_vocabulary_module_for_focus_skill(self):
        self.authenticate()
        vocabulary_module = Module.objects.create(
            level=self.level_a2,
            skill=self.skills['Vocabulary'],
            title='Daily Conversation',
            description='Build practical conversation vocabulary.',
            objectives=['Use daily conversation vocabulary'],
            sort_order=1,
        )
        LearnerProfile.objects.create(user=self.user, current_level='A2')
        SkillMastery.objects.create(
            user=self.user,
            skill=self.skills['Vocabulary'],
            level_code='A2',
            score=35,
        )
        SkillMastery.objects.create(
            user=self.user,
            skill=self.skills['Grammar'],
            level_code='A2',
            score=50,
        )

        response = self.client.post('/api/scheduler/generate-plan/', {}, format='json')

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        data = self.assert_success_response(response)
        first_item = data['plan']['items'][0]
        self.assertEqual(first_item['skill'], 'Vocabulary')
        self.assertEqual(first_item['learner_level'], 'A2')
        self.assertEqual(first_item['module_level'], 'A2')
        self.assertEqual(first_item['module_id'], vocabulary_module.id)
        self.assertFalse(first_item['fallback_used'])
        self.assertIsNone(first_item['fallback_reason'])

    @patch('agents.services.call_llm_json')
    def test_complex_sentences_module_uses_objective_aligned_teacher_task(self, mock_call_llm_json):
        self.authenticate()
        mock_call_llm_json.return_value = None
        level_b2 = CurriculumLevel.objects.create(
            level_code='B2',
            name='Upper Intermediate',
            sort_order=4,
        )
        complex_module = Module.objects.create(
            level=level_b2,
            skill=self.skills['Grammar'],
            title='Complex Sentences',
            description='Practice writing compound and complex sentences clearly.',
            objectives=['Use compound and complex sentences.'],
            sort_order=1,
        )

        session_response = self.client.post(
            '/api/teacher/session/start/',
            {'module_id': complex_module.id},
            format='json',
        )

        self.assertEqual(session_response.status_code, status.HTTP_201_CREATED)
        session_data = self.assert_success_response(session_response)
        self.assertEqual(
            session_data['lesson_objective'],
            'Use compound and complex sentences.',
        )
        task_text = session_data['current_task']['teacher_task'].lower()
        self.assertNotIn('simple present tense', task_text)
        self.assertTrue(
            any(
                phrase in task_text
                for phrase in [
                    'complex sentence',
                    'although',
                    'because',
                    'while',
                    'dependent clause',
                ]
            )
        )

        answer_response = self.client.post(
            '/api/teacher/session/answer/',
            {
                'session_id': session_data['session_id'],
                'student_answer': 'I work as a Technical Support Engineer.',
            },
            format='json',
        )

        self.assertEqual(answer_response.status_code, status.HTTP_200_OK)
        answer_data = self.assert_success_response(answer_response)
        self.assertIn(
            'does not show a complex sentence',
            answer_data['turn']['feedback'].lower(),
        )
        self.assertIn(
            'objective match',
            answer_data['turn']['explanation'].lower(),
        )

    def test_guided_teacher_session_persists_turns_without_updating_mastery(self):
        self.authenticate()
        session_response = self.client.post(
            '/api/teacher/session/start/',
            {'module_id': self.grammar_module.id},
            format='json',
        )

        self.assertEqual(session_response.status_code, status.HTTP_201_CREATED)
        session_data = self.assert_success_response(session_response)
        self.assertEqual(session_data['status'], 'active')
        self.assertEqual(session_data['current_turn'], 1)
        self.assertIn('Past Tense', session_data['lesson'])
        self.assertTrue(session_data['current_task'])
        self.assertEqual(session_data['current_task']['turn_number'], 1)

        first_response = self.client.post(
            '/api/teacher/session/answer/',
            {
                'session_id': session_data['session_id'],
                'student_answer': 'Yesterday, I visited my friend.',
            },
            format='json',
        )
        self.assertEqual(first_response.status_code, status.HTTP_200_OK)
        first_data = self.assert_success_response(first_response)
        self.assertFalse(first_data['completed'])
        self.assertEqual(first_data['turn']['turn_number'], 1)
        self.assertEqual(first_data['next_task']['turn_number'], 2)
        self.assertFalse(
            SkillMastery.objects.filter(
                user=self.user,
                skill=self.skills['Grammar'],
            ).exists()
        )

        second_response = self.client.post(
            '/api/teacher/session/answer/',
            {
                'session_id': session_data['session_id'],
                'student_answer': 'She went to school yesterday.',
            },
            format='json',
        )
        self.assertEqual(second_response.status_code, status.HTTP_200_OK)
        second_data = self.assert_success_response(second_response)
        self.assertFalse(second_data['completed'])
        self.assertEqual(second_data['turn']['turn_number'], 2)
        self.assertEqual(second_data['next_task']['turn_number'], 3)

        third_response = self.client.post(
            '/api/teacher/session/answer/',
            {
                'session_id': session_data['session_id'],
                'student_answer': 'Last weekend, I watched a movie.',
            },
            format='json',
        )
        self.assertEqual(third_response.status_code, status.HTTP_200_OK)
        third_data = self.assert_success_response(third_response)
        self.assertTrue(third_data['completed'])
        self.assertIsNotNone(third_data['final_result'])
        self.assertGreaterEqual(third_data['final_result']['session_score'], 80)
        self.assertTrue(third_data['final_result']['strengths'])
        self.assertTrue(third_data['final_result']['improvement_areas'])
        self.assertTrue(third_data['final_result']['next_study_suggestion'])

        detail_response = self.client.get(
            f"/api/teacher/session/{session_data['session_id']}/"
        )
        self.assertEqual(detail_response.status_code, status.HTTP_200_OK)
        detail_data = self.assert_success_response(detail_response)
        self.assertEqual(detail_data['status'], 'completed')
        self.assertEqual(len(detail_data['turns']), 3)
        self.assertIsNotNone(detail_data['final_result'])

        lesson_session = LessonSession.objects.get(pk=session_data['session_id'])
        self.assertEqual(lesson_session.status, 'completed')
        self.assertEqual(LessonTurn.objects.filter(session=lesson_session).count(), 3)
        session = lesson_session.study_session
        self.assertIsNotNone(session.completed_at)
        self.assertEqual(int(session.score), third_data['final_result']['session_score'])
        self.assertFalse(
            SkillMastery.objects.filter(
                user=self.user,
                skill=self.skills['Grammar'],
            ).exists()
        )

    def test_guided_teacher_session_completion_keeps_official_mastery_and_level(self):
        self.authenticate()
        LearnerProfile.objects.create(user=self.user, current_level='A2')
        SkillMastery.objects.create(
            user=self.user,
            skill=self.skills['Grammar'],
            level_code='A2',
            score=88,
            status='Mastered',
        )

        session_response = self.client.post(
            '/api/teacher/session/start/',
            {'module_id': self.grammar_module.id},
            format='json',
        )
        self.assertEqual(session_response.status_code, status.HTTP_201_CREATED)
        session_data = self.assert_success_response(session_response)

        for answer_text in [
            'Yesterday, I go to school.',
            'She go to class yesterday.',
            'Last weekend, I go to the park.',
        ]:
            response = self.client.post(
                '/api/teacher/session/answer/',
                {
                    'session_id': session_data['session_id'],
                    'student_answer': answer_text,
                },
                format='json',
            )
            self.assertEqual(response.status_code, status.HTTP_200_OK)
            final_data = self.assert_success_response(response)

        self.assertTrue(final_data['completed'])
        self.assertEqual(final_data['final_result']['session_score'], 65)

        mastery = SkillMastery.objects.get(user=self.user, skill=self.skills['Grammar'])
        profile = LearnerProfile.objects.get(user=self.user)
        self.assertEqual(int(mastery.score), 88)
        self.assertEqual(mastery.level_code, 'A2')
        self.assertEqual(mastery.status, 'Mastered')
        self.assertEqual(profile.current_level, 'A2')

        dashboard_response = self.client.get('/api/dashboard/')
        self.assertEqual(dashboard_response.status_code, status.HTTP_200_OK)
        dashboard_data = self.assert_success_response(dashboard_response)
        grammar_mastery = next(
            item for item in dashboard_data['skill_mastery']
            if item['skill']['name'] == 'Grammar'
        )
        self.assertEqual(grammar_mastery['score'], '88.00')

    def test_teacher_feedback_endpoint_returns_session_score_without_mastery_update(self):
        self.authenticate()
        LearnerProfile.objects.create(user=self.user, current_level='A2')
        SkillMastery.objects.create(
            user=self.user,
            skill=self.skills['Grammar'],
            level_code='A2',
            score=88,
            status='Mastered',
        )
        study_session = StudySession.objects.create(
            user=self.user,
            module=self.grammar_module,
        )

        response = self.client.post(
            '/api/teacher/feedback/',
            {
                'session_id': study_session.id,
                'answer': 'Yesterday, I go to school.',
            },
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = self.assert_success_response(response)
        self.assertEqual(data['session_score'], 62)

        mastery = SkillMastery.objects.get(user=self.user, skill=self.skills['Grammar'])
        profile = LearnerProfile.objects.get(user=self.user)
        self.assertEqual(int(mastery.score), 88)
        self.assertEqual(mastery.level_code, 'A2')
        self.assertEqual(profile.current_level, 'A2')

    def test_teacher_session_detail_and_answer_cannot_access_another_users_session(self):
        self.authenticate()
        study_session = StudySession.objects.create(
            user=self.other_user,
            module=self.grammar_module,
        )
        lesson_session = LessonSession.objects.create(
            study_session=study_session,
            status='active',
            current_turn=1,
        )

        answer_response = self.client.post(
            '/api/teacher/session/answer/',
            {
                'session_id': lesson_session.id,
                'student_answer': 'Yesterday I went to the mall.',
            },
            format='json',
        )
        detail_response = self.client.get(f'/api/teacher/session/{lesson_session.id}/')

        self.assertEqual(answer_response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertFalse(answer_response.data['success'])
        self.assertEqual(detail_response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertFalse(detail_response.data['success'])

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
        self.assertEqual(
            plan_data['plan']['days'],
            [
                f'Day 1: Grammar - {self.grammar_module.title}',
                f'Day 2: Speaking - {self.speaking_module.title}',
            ],
        )
        self.assertEqual(len(plan_data['plan']['items']), 2)
        self.assertEqual(plan_data['plan']['items'][0]['day'], 'Day 1')
        self.assertEqual(plan_data['plan']['items'][0]['skill'], 'Grammar')
        self.assertEqual(plan_data['plan']['items'][0]['learner_level'], 'A2')
        self.assertEqual(plan_data['plan']['items'][0]['level'], 'A2')
        self.assertEqual(plan_data['plan']['items'][0]['module_level'], 'A2')
        self.assertEqual(plan_data['plan']['items'][0]['module_id'], self.grammar_module.id)
        self.assertEqual(plan_data['plan']['items'][0]['module_title'], self.grammar_module.title)
        self.assertFalse(plan_data['plan']['items'][0]['fallback_used'])
        self.assertIsNone(plan_data['plan']['items'][0]['fallback_reason'])
        self.assertEqual(
            plan_data['plan']['items'][0]['href'],
            f'/feedback?moduleId={self.grammar_module.id}',
        )
        self.assertEqual(StudyPlan.objects.filter(user=self.user).count(), 1)
        self.assertEqual(coach_response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            coach_data['summary'],
            'Your focus this week is Grammar and Speaking.',
        )
        self.assertEqual(
            coach_data['next_step'],
            'Complete the recommended lessons, then retake your diagnostic to update your official mastery.',
        )

    def test_invalid_agent_payloads_return_400(self):
        self.authenticate()

        diagnostic = self.client.post(
            '/api/diagnostic/evaluate/',
            {'answers': []},
            format='json',
        )
        teacher_session = self.client.post(
            '/api/teacher/session/start/',
            {'module_id': 'not-an-id'},
            format='json',
        )
        feedback = self.client.post(
            '/api/teacher/session/answer/',
            {'session_id': 1, 'student_answer': ''},
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

    def test_recalculate_learner_level_promotes_when_all_core_skills_are_80_or_higher(self):
        profile = LearnerProfile.objects.create(user=self.user, current_level='A1')
        SkillMastery.objects.create(user=self.user, skill=self.skills['Grammar'], level_code='A1', score=88)
        SkillMastery.objects.create(user=self.user, skill=self.skills['Vocabulary'], level_code='A1', score=82)
        SkillMastery.objects.create(user=self.user, skill=self.skills['Listening'], level_code='A1', score=90)
        SkillMastery.objects.create(user=self.user, skill=self.skills['Speaking'], level_code='A1', score=87)

        updated_level = recalculate_learner_level(self.user)

        profile.refresh_from_db()
        self.assertEqual(updated_level, 'A2')
        self.assertEqual(profile.current_level, 'A2')

    def test_recalculate_learner_level_does_not_promote_when_one_core_skill_is_below_80(self):
        profile = LearnerProfile.objects.create(user=self.user, current_level='A1')
        SkillMastery.objects.create(user=self.user, skill=self.skills['Grammar'], level_code='A1', score=88)
        SkillMastery.objects.create(user=self.user, skill=self.skills['Vocabulary'], level_code='A1', score=79)
        SkillMastery.objects.create(user=self.user, skill=self.skills['Listening'], level_code='A1', score=90)
        SkillMastery.objects.create(user=self.user, skill=self.skills['Speaking'], level_code='A1', score=87)

        updated_level = recalculate_learner_level(self.user)

        profile.refresh_from_db()
        self.assertEqual(updated_level, 'A1')
        self.assertEqual(profile.current_level, 'A1')

    def test_recalculate_learner_level_does_not_promote_when_core_skill_is_missing(self):
        profile = LearnerProfile.objects.create(user=self.user, current_level='A1')
        SkillMastery.objects.create(user=self.user, skill=self.skills['Grammar'], level_code='A1', score=88)
        SkillMastery.objects.create(user=self.user, skill=self.skills['Vocabulary'], level_code='A1', score=82)
        SkillMastery.objects.create(user=self.user, skill=self.skills['Speaking'], level_code='A1', score=87)

        updated_level = recalculate_learner_level(self.user)

        profile.refresh_from_db()
        self.assertEqual(updated_level, 'A1')
        self.assertEqual(profile.current_level, 'A1')

    def test_recalculate_learner_level_does_not_promote_beyond_c2(self):
        profile = LearnerProfile.objects.create(user=self.user, current_level='C2')
        SkillMastery.objects.create(user=self.user, skill=self.skills['Grammar'], level_code='C2', score=100)
        SkillMastery.objects.create(user=self.user, skill=self.skills['Vocabulary'], level_code='C2', score=100)
        SkillMastery.objects.create(user=self.user, skill=self.skills['Listening'], level_code='C2', score=100)
        SkillMastery.objects.create(user=self.user, skill=self.skills['Speaking'], level_code='C2', score=100)

        updated_level = recalculate_learner_level(self.user)

        profile.refresh_from_db()
        self.assertEqual(updated_level, 'C2')
        self.assertEqual(profile.current_level, 'C2')

    def test_recommendation_uses_updated_current_level_after_progression(self):
        self.authenticate()
        level_b1 = CurriculumLevel.objects.create(
            level_code='B1',
            name='Intermediate',
            sort_order=3,
        )
        b1_grammar_module = Module.objects.create(
            level=level_b1,
            skill=self.skills['Grammar'],
            title='Giving Opinions',
            description='Express opinions and support them with reasons.',
            objectives=['Give one opinion with a reason'],
            sort_order=1,
        )
        LearnerProfile.objects.create(user=self.user, current_level='A2')
        SkillMastery.objects.create(user=self.user, skill=self.skills['Grammar'], level_code='A2', score=88)
        SkillMastery.objects.create(user=self.user, skill=self.skills['Vocabulary'], level_code='A2', score=82)
        SkillMastery.objects.create(user=self.user, skill=self.skills['Listening'], level_code='A2', score=90)
        SkillMastery.objects.create(user=self.user, skill=self.skills['Speaking'], level_code='A2', score=87)

        recalculate_learner_level(self.user)
        response = self.client.get('/api/curriculum/recommendation/')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = self.assert_success_response(response)
        self.assertEqual(
            LearnerProfile.objects.get(user=self.user).current_level,
            'B1',
        )
        self.assertEqual(data['recommended_module']['id'], self.speaking_module.id)
        self.assertEqual(data['learner_level'], 'B1')
        self.assertEqual(data['module_level'], 'A2')
        self.assertTrue(data['fallback_used'])
        self.assertIn('No B1 Speaking module is available yet', data['fallback_reason'])
