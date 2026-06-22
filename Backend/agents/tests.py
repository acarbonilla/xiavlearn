from unittest.mock import patch

from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from rest_framework import status
from rest_framework.test import APITestCase

from agents.models import (
    LessonSession,
    LessonTurn,
    VoiceDiagnosticItem,
    VoiceDiagnosticSession,
)
from agents.services import recalculate_learner_level
from agents.voice_services import _aggregate_batch_scores
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
            ('post', '/api/teacher/speaking/sessions/start/', {}),
            ('get', '/api/teacher/speaking/sessions/1/', None),
            ('post', '/api/teacher/speaking/sessions/1/answer/', {'transcript': 'Test answer.'}),
            ('post', '/api/teacher/listening/sessions/start/', {}),
            ('get', '/api/teacher/listening/sessions/1/', None),
            ('post', '/api/teacher/listening/sessions/1/answer/', {'answer': 'Test answer.'}),
            ('post', '/api/teacher/pronunciation/sessions/start/', {}),
            ('get', '/api/teacher/pronunciation/sessions/1/', None),
            ('post', '/api/teacher/pronunciation/sessions/1/answer/', {'transcript': 'Test answer.'}),
            ('post', '/api/scheduler/generate-plan/', {}),
            ('get', '/api/coach/summary/', None),
            ('post', '/api/voice-diagnostic/sessions/start/', {}),
            ('get', '/api/voice-diagnostic/sessions/', None),
            ('get', '/api/voice-diagnostic/sessions/1/', None),
            ('get', '/api/voice-diagnostic/sessions/1/report/', None),
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
        grammar_mastery = SkillMastery.objects.get(
            user=self.user,
            skill=self.skills['Grammar'],
        )
        vocabulary_mastery = SkillMastery.objects.get(
            user=self.user,
            skill=self.skills['Vocabulary'],
        )
        self.assertEqual(int(grammar_mastery.score), data['skill_scores']['Grammar'])
        self.assertEqual(int(vocabulary_mastery.score), data['skill_scores']['Vocabulary'])
        self.assertEqual(grammar_mastery.level_code, data['overall_level'])
        self.assertEqual(vocabulary_mastery.level_code, data['overall_level'])
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
        self.assertEqual(data['level_code'], 'A1')
        self.assertEqual(
            data['pronunciation']['target_sentence'],
            'I practice English every day.',
        )
        self.assertEqual(len(data['pronunciation']['items']), 3)
        self.assertEqual(
            data['listening']['passage'],
            'My name is Anna. I live in Cebu.',
        )
        self.assertEqual(data['listening']['question'], 'Where does Anna live?')
        self.assertEqual(data['listening']['expected_answer'], 'Cebu.')
        self.assertEqual(len(data['listening']['items']), 3)
        self.assertEqual(
            data['speaking']['question'],
            'Introduce yourself in English.',
        )
        self.assertEqual(len(data['speaking']['items']), 3)

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
    def test_pronunciation_evaluate_exact_match_scores_high_and_includes_breakdown(self, mock_transcribe_audio):
        self.authenticate()
        mock_transcribe_audio.return_value = 'I practice English every day.'
        audio_file = SimpleUploadedFile(
            'pronunciation.webm',
            b'fake audio',
            content_type='audio/webm',
        )

        response = self.client.post(
            '/api/voice-diagnostic/pronunciation/evaluate/',
            {
                'audio_file': audio_file,
                'target_sentence': 'I practice English every day.',
            },
            format='multipart',
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = self.assert_success_response(response)
        self.assertEqual(data['transcript'], mock_transcribe_audio.return_value)
        self.assertGreaterEqual(data['score'], 90)
        self.assertEqual(data['word_accuracy'], 100)
        self.assertEqual(data['status'], 'Mastered')
        self.assertEqual(data['missing_words'], [])
        self.assertEqual(data['extra_words'], [])
        self.assertEqual(data['breakdown']['rubric'], 'pronunciation_v2')
        self.assertIn('score_reasons', data['breakdown'])
        self.assertFalse(
            SkillMastery.objects.filter(
                user=self.user,
                skill__name='Pronunciation',
            ).exists()
        )

    @patch('agents.voice_services.transcribe_audio')
    def test_speaking_evaluate_relevant_answer_scores_high_and_includes_breakdown(self, mock_transcribe_audio):
        self.authenticate()
        mock_transcribe_audio.return_value = (
            'My name is Ana. I want to improve my English communication for work, and I practice every day.'
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
        self.assertEqual(data['breakdown']['rubric'], 'speaking_v2')
        self.assertGreaterEqual(data['breakdown']['task_relevance'], 80)
        self.assertFalse(
            SkillMastery.objects.filter(
                user=self.user,
                skill__name='Speaking',
            ).exists()
        )

    def test_listening_evaluate_complete_answer_scores_high_and_includes_breakdown(self):
        self.authenticate()

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
        self.assertGreaterEqual(data['score'], 85)
        self.assertEqual(data['status'], 'Mastered')
        self.assertIn('Correct', data['feedback'])
        self.assertEqual(data['breakdown']['rubric'], 'listening_v2')
        self.assertEqual(data['answer_match'], 'complete')
        self.assertFalse(
            SkillMastery.objects.filter(
                user=self.user,
                skill__name='Listening',
            ).exists()
        )

    def test_listening_evaluate_paraphrase_answer_scores_reasonably(self):
        self.authenticate()

        response = self.client.post(
            '/api/voice-diagnostic/listening/evaluate/',
            {
                'question': 'What problem did the customer have?',
                'expected_answer': 'The customer could not connect to the internet.',
                'user_answer': 'He had no internet connection.',
            },
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = self.assert_success_response(response)
        self.assertGreaterEqual(data['score'], 75)
        self.assertIn(data['answer_match'], {'complete', 'partial'})
        self.assertFalse(
            SkillMastery.objects.filter(
                user=self.user,
                skill__name='Listening',
            ).exists()
        )

    def test_listening_evaluate_empty_answer_scores_very_low(self):
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

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = self.assert_success_response(response)
        self.assertLessEqual(data['score'], 15)
        self.assertEqual(data['breakdown']['answer_match'], 'none')

    @patch('agents.voice_services.transcribe_audio')
    def test_pronunciation_preview_does_not_update_mastery(self, mock_transcribe_audio):
        self.authenticate()
        mock_transcribe_audio.return_value = 'I practice English every day.'
        audio_file = SimpleUploadedFile(
            'pronunciation.webm',
            b'fake audio',
            content_type='audio/webm',
        )

        response = self.client.post(
            '/api/voice-diagnostic/pronunciation/evaluate/',
            {
                'audio_file': audio_file,
                'target_sentence': 'I practice English every day.',
                'update_mastery': 'false',
            },
            format='multipart',
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = self.assert_success_response(response)
        self.assertEqual(data['score'], 100)
        self.assertFalse(
            SkillMastery.objects.filter(
                user=self.user,
                skill__name='Pronunciation',
            ).exists()
        )

    def test_pronunciation_batch_missing_words_and_substitutions_reduce_scores(self):
        self.authenticate()

        response = self.client.post(
            '/api/voice-diagnostic/pronunciation/evaluate-batch/',
            {
                'items': [
                    {
                        'target_sentence': 'I practice English every day.',
                        'transcript': 'I practice English every day.',
                    },
                    {
                        'target_sentence': 'I practice English every day.',
                        'transcript': 'I practice English.',
                    },
                    {
                        'target_sentence': 'I practice English every day.',
                        'transcript': 'I practice Spanish every day.',
                    },
                ],
            },
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = self.assert_success_response(response)
        exact_item, missing_item, substituted_item = data['items']
        self.assertGreater(exact_item['score'], missing_item['score'])
        self.assertGreater(exact_item['score'], substituted_item['score'])
        self.assertTrue(missing_item['missing_words'])
        self.assertTrue(substituted_item['substituted_words'])
        self.assertEqual(substituted_item['breakdown']['rubric'], 'pronunciation_v2')

    def test_pronunciation_batch_unrelated_and_empty_transcripts_score_low(self):
        self.authenticate()

        response = self.client.post(
            '/api/voice-diagnostic/pronunciation/evaluate-batch/',
            {
                'items': [
                    {
                        'target_sentence': 'I practice English every day.',
                        'transcript': 'The weather is sunny outside.',
                    },
                    {
                        'target_sentence': 'My name is Anna.',
                        'transcript': '',
                    },
                    {
                        'target_sentence': 'I live in Cebu.',
                        'transcript': 'I live in Cebu.',
                    },
                ],
            },
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = self.assert_success_response(response)
        self.assertLessEqual(data['items'][0]['score'], 39)
        self.assertLessEqual(data['items'][1]['score'], 15)

    def test_listening_batch_partial_unrelated_and_empty_answers_score_lower(self):
        self.authenticate()

        response = self.client.post(
            '/api/voice-diagnostic/listening/evaluate-batch/',
            {
                'items': [
                    {
                        'passage': 'The customer could not connect to the internet.',
                        'question': 'What problem did the customer have?',
                        'expected_answer': 'The customer could not connect to the internet.',
                        'answer': 'No internet connection.',
                    },
                    {
                        'passage': 'The customer could not connect to the internet.',
                        'question': 'What problem did the customer have?',
                        'expected_answer': 'The customer could not connect to the internet.',
                        'answer': 'A customer problem.',
                    },
                    {
                        'passage': 'The customer could not connect to the internet.',
                        'question': 'What problem did the customer have?',
                        'expected_answer': 'The customer could not connect to the internet.',
                        'answer': '',
                    },
                ],
            },
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = self.assert_success_response(response)
        self.assertGreaterEqual(data['items'][0]['score'], 75)
        self.assertLessEqual(data['items'][1]['score'], 44)
        self.assertLessEqual(data['items'][2]['score'], 15)
        self.assertEqual(data['items'][0]['breakdown']['rubric'], 'listening_v2')

    def test_speaking_batch_short_unrelated_and_filler_answers_affect_scoring(self):
        self.authenticate()

        response = self.client.post(
            '/api/voice-diagnostic/speaking/evaluate-batch/',
            {
                'items': [
                    {
                        'question': 'What is your learning goal?',
                        'transcript': 'I want better English.',
                    },
                    {
                        'question': 'What is your learning goal?',
                        'transcript': 'The weather is sunny and the market is busy today.',
                    },
                    {
                        'question': 'What is your learning goal?',
                        'transcript': 'Um, um, like, you know, actually, I want to improve my English for work.',
                    },
                ],
            },
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = self.assert_success_response(response)
        self.assertGreaterEqual(data['items'][0]['score'], 40)
        self.assertLessEqual(data['items'][0]['score'], 74)
        self.assertLessEqual(data['items'][1]['score'], 39)
        self.assertLess(
            data['items'][2]['breakdown']['fluency_signal'],
            data['items'][0]['breakdown']['fluency_signal'],
        )
        self.assertEqual(data['items'][2]['breakdown']['rubric'], 'speaking_v2')

    def test_batch_aggregation_applies_consistency_adjustment(self):
        aggregated_score, aggregation = _aggregate_batch_scores(
            [{'score': 95}, {'score': 92}, {'score': 40}]
        )

        self.assertEqual(aggregation['base_average'], 76)
        self.assertEqual(aggregation['score_range'], 55)
        self.assertEqual(aggregation['consistency_adjustment'], -5)
        self.assertEqual(aggregated_score, 71)
        self.assertEqual(aggregation['final_score'], 71)

    def test_batch_aggregation_clamps_score_within_zero_to_hundred(self):
        aggregated_score, aggregation = _aggregate_batch_scores(
            [{'score': -10}, {'score': 0}, {'score': 0}]
        )

        self.assertEqual(aggregated_score, 0)
        self.assertEqual(aggregation['final_score'], 0)

    def start_voice_diagnostic_session_for_test(self):
        response = self.client.post(
            '/api/voice-diagnostic/sessions/start/',
            {},
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        return self.assert_success_response(response)

    def pronunciation_batch_payload(self):
        return {
            'items': [
                {
                    'target_sentence': 'I practice English every day.',
                    'transcript': 'I practice English every day.',
                },
                {
                    'target_sentence': 'My name is Anna.',
                    'transcript': 'My Anna.',
                },
                {
                    'target_sentence': 'I live in Cebu.',
                    'transcript': 'I live Cebu.',
                },
            ],
        }

    def listening_batch_payload(self):
        return {
            'items': [
                {
                    'passage': 'My name is Anna. I live in Cebu.',
                    'question': 'Where does Anna live?',
                    'expected_answer': 'Cebu.',
                    'answer': 'Cebu.',
                },
                {
                    'passage': 'I study English every morning.',
                    'question': 'When does the speaker study English?',
                    'expected_answer': 'Every morning.',
                    'answer': 'Morning.',
                },
                {
                    'passage': 'Maria likes coffee and bread for breakfast.',
                    'question': 'What does Maria like for breakfast?',
                    'expected_answer': 'Coffee and bread.',
                    'answer': 'Coffee.',
                },
            ],
        }

    def speaking_batch_payload(self):
        return {
            'items': [
                {
                    'question': 'Introduce yourself in English.',
                    'transcript': 'My name is Ana and I am learning English for work.',
                },
                {
                    'question': 'Describe your daily routine.',
                    'transcript': 'I wake up early and work all day.',
                },
                {
                    'question': 'What is your learning goal?',
                    'transcript': 'I want to improve my English speaking because I need it at work.',
                },
            ],
        }

    def expected_recommended_focus(self, pronunciation_score, listening_score, speaking_score):
        ordered_scores = [
            ('Pronunciation', pronunciation_score),
            ('Listening', listening_score),
            ('Speaking', speaking_score),
        ]
        ordered_scores.sort(key=lambda item: item[1])
        return ordered_scores[0][0]

    def test_voice_diagnostic_session_start_creates_in_progress_session(self):
        self.authenticate()

        data = self.start_voice_diagnostic_session_for_test()

        session = VoiceDiagnosticSession.objects.get(pk=data['session_id'])
        self.assertEqual(session.user, self.user)
        self.assertEqual(session.status, VoiceDiagnosticSession.STATUS_IN_PROGRESS)
        self.assertIsNotNone(session.started_at)
        self.assertEqual(data['status'], VoiceDiagnosticSession.STATUS_IN_PROGRESS)

    def test_pronunciation_batch_saves_voice_diagnostic_items(self):
        self.authenticate()
        session_data = self.start_voice_diagnostic_session_for_test()

        response = self.client.post(
            '/api/voice-diagnostic/pronunciation/evaluate-batch/',
            {
                **self.pronunciation_batch_payload(),
                'session_id': session_data['session_id'],
            },
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = self.assert_success_response(response)
        session = VoiceDiagnosticSession.objects.get(pk=session_data['session_id'])
        items = list(
            VoiceDiagnosticItem.objects.filter(
                session=session,
                skill='Pronunciation',
            ).order_by('item_number')
        )
        self.assertEqual(len(items), 3)
        self.assertEqual(session.status, VoiceDiagnosticSession.STATUS_IN_PROGRESS)
        self.assertEqual(int(session.pronunciation_score), data['final_score'])
        self.assertEqual(items[0].task_type, 'repeat_sentence')
        self.assertEqual(items[0].target_text, 'I practice English every day.')
        self.assertEqual(items[0].transcript, 'I practice English every day.')
        self.assertEqual(items[0].details['rubric'], 'pronunciation_v2')
        self.assertIn('score_reasons', items[0].details)
        self.assertIn('aggregation', session.metadata['skill_results']['pronunciation'])
        self.assertEqual(data['session_id'], session.id)
        self.assertEqual(data['session_status'], VoiceDiagnosticSession.STATUS_IN_PROGRESS)

    def test_listening_batch_saves_voice_diagnostic_items(self):
        self.authenticate()
        session_data = self.start_voice_diagnostic_session_for_test()

        response = self.client.post(
            '/api/voice-diagnostic/listening/evaluate-batch/',
            {
                **self.listening_batch_payload(),
                'session_id': session_data['session_id'],
            },
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = self.assert_success_response(response)
        session = VoiceDiagnosticSession.objects.get(pk=session_data['session_id'])
        items = list(
            VoiceDiagnosticItem.objects.filter(
                session=session,
                skill='Listening',
            ).order_by('item_number')
        )
        self.assertEqual(len(items), 3)
        self.assertEqual(int(session.listening_score), data['final_score'])
        self.assertEqual(items[0].passage_text, 'My name is Anna. I live in Cebu.')
        self.assertEqual(items[0].question_text, 'Where does Anna live?')
        self.assertEqual(items[0].expected_answer, 'Cebu.')
        self.assertEqual(items[0].user_answer, 'Cebu.')
        self.assertEqual(items[0].details['rubric'], 'listening_v2')
        self.assertEqual(items[0].details['answer_match'], 'complete')

    def test_speaking_batch_saves_voice_diagnostic_items(self):
        self.authenticate()
        session_data = self.start_voice_diagnostic_session_for_test()

        response = self.client.post(
            '/api/voice-diagnostic/speaking/evaluate-batch/',
            {
                **self.speaking_batch_payload(),
                'session_id': session_data['session_id'],
            },
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = self.assert_success_response(response)
        session = VoiceDiagnosticSession.objects.get(pk=session_data['session_id'])
        items = list(
            VoiceDiagnosticItem.objects.filter(
                session=session,
                skill='Speaking',
            ).order_by('item_number')
        )
        self.assertEqual(len(items), 3)
        self.assertEqual(int(session.speaking_score), data['final_score'])
        self.assertEqual(items[0].question_text, 'Introduce yourself in English.')
        self.assertTrue(items[0].transcript)
        self.assertEqual(items[0].details['rubric'], 'speaking_v2')
        self.assertTrue(items[0].details['strengths'])
        self.assertTrue(items[0].details['improvement_areas'])

    def test_voice_diagnostic_session_completes_and_preserves_skill_mastery(self):
        self.authenticate()
        session_data = self.start_voice_diagnostic_session_for_test()
        session_id = session_data['session_id']

        pronunciation_response = self.client.post(
            '/api/voice-diagnostic/pronunciation/evaluate-batch/',
            {
                **self.pronunciation_batch_payload(),
                'session_id': session_id,
            },
            format='json',
        )
        listening_response = self.client.post(
            '/api/voice-diagnostic/listening/evaluate-batch/',
            {
                **self.listening_batch_payload(),
                'session_id': session_id,
            },
            format='json',
        )
        speaking_response = self.client.post(
            '/api/voice-diagnostic/speaking/evaluate-batch/',
            {
                **self.speaking_batch_payload(),
                'session_id': session_id,
            },
            format='json',
        )

        self.assertEqual(pronunciation_response.status_code, status.HTTP_200_OK)
        self.assertEqual(listening_response.status_code, status.HTTP_200_OK)
        self.assertEqual(speaking_response.status_code, status.HTTP_200_OK)
        pronunciation_data = self.assert_success_response(pronunciation_response)
        listening_data = self.assert_success_response(listening_response)
        speaking_data = self.assert_success_response(speaking_response)

        session = VoiceDiagnosticSession.objects.get(pk=session_id)
        self.assertEqual(session.status, VoiceDiagnosticSession.STATUS_COMPLETED)
        self.assertEqual(int(session.pronunciation_score), pronunciation_data['final_score'])
        self.assertEqual(int(session.listening_score), listening_data['final_score'])
        self.assertEqual(int(session.speaking_score), speaking_data['final_score'])
        expected_focus = self.expected_recommended_focus(
            pronunciation_data['final_score'],
            listening_data['final_score'],
            speaking_data['final_score'],
        )
        self.assertEqual(session.recommended_focus, expected_focus)
        self.assertEqual(
            session.summary,
            (
                f'{expected_focus} is your recommended focus. Practice with the '
                f'{expected_focus} Teacher Session, then retake the Voice Diagnostic later.'
            ),
        )
        self.assertIsNotNone(session.completed_at)
        self.assertEqual(
            VoiceDiagnosticItem.objects.filter(session=session).count(),
            9,
        )
        self.assertEqual(speaking_data['session_status'], VoiceDiagnosticSession.STATUS_COMPLETED)
        self.assertEqual(speaking_data['recommended_focus'], expected_focus)
        self.assertEqual(
            SkillMastery.objects.get(user=self.user, skill__name='Pronunciation').score,
            pronunciation_data['final_score'],
        )
        self.assertEqual(
            SkillMastery.objects.get(user=self.user, skill__name='Listening').score,
            listening_data['final_score'],
        )
        self.assertEqual(
            SkillMastery.objects.get(user=self.user, skill__name='Speaking').score,
            speaking_data['final_score'],
        )
        self.assertIn('aggregation', session.metadata['skill_results']['speaking'])

    def test_voice_diagnostic_session_list_is_private_to_authenticated_user(self):
        self.authenticate()
        own_session = VoiceDiagnosticSession.objects.create(user=self.user, status='completed')
        VoiceDiagnosticSession.objects.create(user=self.other_user, status='completed')

        response = self.client.get('/api/voice-diagnostic/sessions/')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = self.assert_success_response(response)
        self.assertEqual([entry['id'] for entry in data], [own_session.id])

    def test_voice_diagnostic_session_detail_returns_only_owned_session(self):
        self.authenticate()
        session = VoiceDiagnosticSession.objects.create(
            user=self.user,
            status='completed',
            recommended_focus='Pronunciation',
            summary='Pronunciation is your recommended focus based on this voice diagnostic.',
        )
        VoiceDiagnosticItem.objects.create(
            session=session,
            skill='Pronunciation',
            item_number=1,
            task_type='repeat_sentence',
            target_text='I practice English every day.',
            transcript='I practice English every day.',
            score=95,
            feedback='Excellent repetition.',
            details={'word_accuracy': 100},
        )

        response = self.client.get(f'/api/voice-diagnostic/sessions/{session.id}/')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = self.assert_success_response(response)
        self.assertEqual(data['id'], session.id)
        self.assertEqual(len(data['items']), 1)
        self.assertEqual(data['items'][0]['skill'], 'Pronunciation')
        self.assertEqual(data['items'][0]['score'], 95)

    def test_voice_diagnostic_session_detail_rejects_other_users_session(self):
        self.authenticate()
        other_session = VoiceDiagnosticSession.objects.create(user=self.other_user, status='completed')

        response = self.client.get(f'/api/voice-diagnostic/sessions/{other_session.id}/')

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_voice_diagnostic_report_returns_completed_session_scores(self):
        self.authenticate()
        session_data = self.start_voice_diagnostic_session_for_test()
        session_id = session_data['session_id']
        self.client.post(
            '/api/voice-diagnostic/pronunciation/evaluate-batch/',
            {
                **self.pronunciation_batch_payload(),
                'session_id': session_id,
            },
            format='json',
        )
        self.client.post(
            '/api/voice-diagnostic/listening/evaluate-batch/',
            {
                **self.listening_batch_payload(),
                'session_id': session_id,
            },
            format='json',
        )
        speaking_response = self.client.post(
            '/api/voice-diagnostic/speaking/evaluate-batch/',
            {
                **self.speaking_batch_payload(),
                'session_id': session_id,
            },
            format='json',
        )
        speaking_data = self.assert_success_response(speaking_response)

        response = self.client.get(f'/api/voice-diagnostic/sessions/{session_id}/report/')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = self.assert_success_response(response)
        self.assertTrue(data['official_mastery_updated'])
        self.assertEqual(data['status'], VoiceDiagnosticSession.STATUS_COMPLETED)
        self.assertEqual(
            data['scores'],
            {
                'Pronunciation': int(SkillMastery.objects.get(
                    user=self.user,
                    skill__name='Pronunciation',
                ).score),
                'Listening': int(SkillMastery.objects.get(
                    user=self.user,
                    skill__name='Listening',
                ).score),
                'Speaking': int(SkillMastery.objects.get(
                    user=self.user,
                    skill__name='Speaking',
                ).score),
            },
        )
        self.assertEqual(data['recommended_focus'], speaking_data['recommended_focus'])
        self.assertTrue(data['recommended_focus_reason'])
        self.assertEqual(len(data['skill_breakdown']), 3)
        self.assertEqual(data['recommendation_href'], '/recommendation')
        self.assertEqual(data['history_href'], '/voice-diagnostic/history')
        self.assertEqual(data['dashboard_href'], '/dashboard')

    def test_voice_diagnostic_report_returns_safe_message_for_incomplete_session(self):
        self.authenticate()
        session_data = self.start_voice_diagnostic_session_for_test()

        response = self.client.get(
            f"/api/voice-diagnostic/sessions/{session_data['session_id']}/report/"
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = self.assert_success_response(response)
        self.assertFalse(data['official_mastery_updated'])
        self.assertEqual(data['status'], VoiceDiagnosticSession.STATUS_IN_PROGRESS)
        self.assertEqual(
            data['message'],
            'Complete all voice diagnostic sections to view your final report.',
        )

    def test_voice_diagnostic_report_rejects_other_users_session(self):
        self.authenticate()
        other_session = VoiceDiagnosticSession.objects.create(user=self.other_user, status='completed')

        response = self.client.get(f'/api/voice-diagnostic/sessions/{other_session.id}/report/')

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_voice_diagnostic_report_maps_pronunciation_focus_to_pronunciation_teacher(self):
        self.authenticate()
        session = VoiceDiagnosticSession.objects.create(
            user=self.user,
            status=VoiceDiagnosticSession.STATUS_COMPLETED,
            pronunciation_score=42,
            listening_score=70,
            speaking_score=88,
            recommended_focus='Pronunciation',
            summary='Pronunciation is your recommended focus.',
        )

        response = self.client.get(f'/api/voice-diagnostic/sessions/{session.id}/report/')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = self.assert_success_response(response)
        self.assertEqual(data['next_teacher_session']['href'], '/pronunciation-teacher')

    def test_voice_diagnostic_report_maps_listening_focus_to_listening_teacher(self):
        self.authenticate()
        session = VoiceDiagnosticSession.objects.create(
            user=self.user,
            status=VoiceDiagnosticSession.STATUS_COMPLETED,
            pronunciation_score=78,
            listening_score=62,
            speaking_score=88,
            recommended_focus='Listening',
            summary='Listening is your recommended focus.',
        )

        response = self.client.get(f'/api/voice-diagnostic/sessions/{session.id}/report/')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = self.assert_success_response(response)
        self.assertEqual(data['next_teacher_session']['href'], '/listening-teacher')

    def test_voice_diagnostic_report_maps_speaking_focus_to_speaking_teacher(self):
        self.authenticate()
        session = VoiceDiagnosticSession.objects.create(
            user=self.user,
            status=VoiceDiagnosticSession.STATUS_COMPLETED,
            pronunciation_score=78,
            listening_score=82,
            speaking_score=61,
            recommended_focus='Speaking',
            summary='Speaking is your recommended focus.',
        )

        response = self.client.get(f'/api/voice-diagnostic/sessions/{session.id}/report/')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = self.assert_success_response(response)
        self.assertEqual(data['next_teacher_session']['href'], '/speaking-teacher')

    def test_speaking_teacher_sessions_do_not_update_skill_mastery(self):
        self.authenticate()
        speaking_skill = self.skills['Speaking']
        SkillMastery.objects.create(
            user=self.user,
            skill=speaking_skill,
            level_code='A2',
            score=72,
            status='Learning',
        )

        start_response = self.client.post(
            '/api/teacher/speaking/sessions/start/',
            {},
            format='json',
        )
        self.assertEqual(start_response.status_code, status.HTTP_201_CREATED)
        start_data = self.assert_success_response(start_response)
        session_id = start_data['session_id']

        for transcript in [
            'My name is Ana and I want to improve my English for work.',
            'I usually wake up early and study before I start work.',
            'My learning goal is to speak more clearly in meetings.',
        ]:
            answer_response = self.client.post(
                f'/api/teacher/speaking/sessions/{session_id}/answer/',
                {'transcript': transcript},
                format='json',
            )
            self.assertEqual(answer_response.status_code, status.HTTP_200_OK)

        mastery = SkillMastery.objects.get(user=self.user, skill=speaking_skill)
        self.assertEqual(int(mastery.score), 72)
        self.assertEqual(mastery.level_code, 'A2')
        self.assertEqual(
            SkillMastery.objects.filter(user=self.user, skill=speaking_skill).count(),
            1,
        )

    def test_pronunciation_batch_requires_exactly_three_items(self):
        self.authenticate()

        response = self.client.post(
            '/api/voice-diagnostic/pronunciation/evaluate-batch/',
            {
                'items': [
                    {
                        'target_sentence': 'I practice English every day.',
                        'transcript': 'I practice English every day.',
                    },
                ],
            },
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(response.data['success'])
        self.assertEqual(
            response.data['error'],
            'pronunciation items must contain exactly 3 entries.',
        )

    def test_pronunciation_batch_aggregates_scores_and_updates_mastery_once(self):
        self.authenticate()

        response = self.client.post(
            '/api/voice-diagnostic/pronunciation/evaluate-batch/',
            {
                'items': [
                    {
                        'target_sentence': 'I practice English every day.',
                        'transcript': 'I practice English every day.',
                    },
                    {
                        'target_sentence': 'My name is Anna.',
                        'transcript': 'My Anna.',
                    },
                    {
                        'target_sentence': 'I live in Cebu.',
                        'transcript': 'I live Cebu.',
                    },
                ],
            },
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = self.assert_success_response(response)
        self.assertEqual(len(data['items']), 3)
        self.assertTrue(all('breakdown' in item for item in data['items']))
        expected_base_average = round(sum(item['score'] for item in data['items']) / 3)
        self.assertEqual(data['aggregation']['base_average'], expected_base_average)
        self.assertEqual(
            data['final_score'],
            data['aggregation']['final_score'],
        )
        mastery = SkillMastery.objects.get(user=self.user, skill__name='Pronunciation')
        self.assertEqual(SkillMastery.objects.filter(user=self.user, skill__name='Pronunciation').count(), 1)
        self.assertEqual(int(mastery.score), data['final_score'])
        self.assertEqual(mastery.level_code, data['level_code'])
        self.assertEqual(mastery.status, data['status'])

    def test_listening_batch_aggregates_scores_and_updates_mastery_once(self):
        self.authenticate()

        response = self.client.post(
            '/api/voice-diagnostic/listening/evaluate-batch/',
            {
                'items': [
                    {
                        'passage': 'My name is Anna. I live in Cebu.',
                        'question': 'Where does Anna live?',
                        'expected_answer': 'Cebu.',
                        'answer': 'Cebu.',
                    },
                    {
                        'passage': 'I study English every morning.',
                        'question': 'When does the speaker study English?',
                        'expected_answer': 'Every morning.',
                        'answer': 'Morning.',
                    },
                    {
                        'passage': 'Maria likes coffee and bread for breakfast.',
                        'question': 'What does Maria like for breakfast?',
                        'expected_answer': 'Coffee and bread.',
                        'answer': 'Coffee.',
                    },
                ],
            },
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = self.assert_success_response(response)
        self.assertEqual(len(data['items']), 3)
        self.assertTrue(all('breakdown' in item for item in data['items']))
        self.assertEqual(
            data['final_score'],
            data['aggregation']['final_score'],
        )
        self.assertEqual(data['items'][0]['answer_match'], 'complete')
        mastery = SkillMastery.objects.get(user=self.user, skill__name='Listening')
        self.assertEqual(SkillMastery.objects.filter(user=self.user, skill__name='Listening').count(), 1)
        self.assertEqual(int(mastery.score), data['final_score'])
        self.assertEqual(mastery.level_code, data['level_code'])
        self.assertEqual(mastery.status, data['status'])

    def test_speaking_batch_aggregates_scores_and_updates_mastery_once(self):
        self.authenticate()

        response = self.client.post(
            '/api/voice-diagnostic/speaking/evaluate-batch/',
            {
                'items': [
                    {
                        'question': 'Introduce yourself in English.',
                        'transcript': 'My name is Ana and I am learning English for work.',
                    },
                    {
                        'question': 'Describe your daily routine.',
                        'transcript': 'I wake up early and work all day.',
                    },
                    {
                        'question': 'What is your learning goal?',
                        'transcript': 'I want to improve my English speaking because I need it at work.',
                    },
                ],
            },
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = self.assert_success_response(response)
        self.assertEqual(len(data['items']), 3)
        self.assertTrue(all('breakdown' in item for item in data['items']))
        self.assertEqual(data['final_score'], data['aggregation']['final_score'])
        mastery = SkillMastery.objects.get(user=self.user, skill__name='Speaking')
        self.assertEqual(SkillMastery.objects.filter(user=self.user, skill__name='Speaking').count(), 1)
        self.assertEqual(int(mastery.score), data['final_score'])
        self.assertEqual(mastery.status, data['status'])

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
                'Grammar': 45,
                'Vocabulary': 62,
                'Listening': 58,
                'Speaking': 75,
                'Pronunciation': None,
            },
        )
        self.assertEqual(
            recommendation_data['current_skill_scores'],
            recommendation_data['diagnostic_scores'],
        )
        self.assertEqual(recommendation_data['recommended_focus'], 'Grammar')
        self.assertEqual(recommendation_data['recommended_action']['type'], 'module')
        self.assertEqual(recommendation_data['learner_level'], 'A2')
        self.assertEqual(recommendation_data['module_level'], 'A2')
        self.assertFalse(recommendation_data['fallback_used'])
        self.assertIsNone(recommendation_data['fallback_reason'])

    def test_recommendation_reads_latest_voice_skill_mastery_after_voice_diagnostic(self):
        self.authenticate()
        LearnerProfile.objects.create(user=self.user, current_level='A2')
        SkillMastery.objects.create(
            user=self.user,
            skill=self.skills['Grammar'],
            level_code='A2',
            score=88,
        )
        SkillMastery.objects.create(
            user=self.user,
            skill=self.skills['Vocabulary'],
            level_code='A2',
            score=82,
        )
        SkillMastery.objects.create(
            user=self.user,
            skill=self.skills['Listening'],
            level_code='A2',
            score=90,
        )
        SkillMastery.objects.create(
            user=self.user,
            skill=self.skills['Speaking'],
            level_code='A2',
            score=87,
        )
        SkillMastery.objects.create(
            user=self.user,
            skill=self.skills['Pronunciation'],
            level_code='A2',
            score=91,
        )
        session_data = self.start_voice_diagnostic_session_for_test()
        self.client.post(
            '/api/voice-diagnostic/pronunciation/evaluate-batch/',
            {
                **self.pronunciation_batch_payload(),
                'session_id': session_data['session_id'],
            },
            format='json',
        )

        response = self.client.get('/api/curriculum/recommendation/')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = self.assert_success_response(response)
        self.assertEqual(data['recommended_focus'], 'Pronunciation')
        self.assertEqual(data['weakest_skill'], 'Pronunciation')
        self.assertEqual(data['recommended_module'], None)
        self.assertEqual(data['recommended_action']['type'], 'teacher_session')
        self.assertEqual(data['recommended_action']['href'], '/pronunciation-teacher')
        self.assertEqual(
            data['current_skill_scores']['Pronunciation'],
            int(SkillMastery.objects.get(user=self.user, skill__name='Pronunciation').score),
        )

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
        mastery = SkillMastery.objects.create(
            user=self.user,
            skill=self.skills['Grammar'],
            level_code='A2',
            score=88,
            status='Mastered',
        )
        original_last_updated = mastery.last_updated

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

        mastery.refresh_from_db()
        profile = LearnerProfile.objects.get(user=self.user)
        self.assertEqual(SkillMastery.objects.filter(user=self.user).count(), 1)
        self.assertEqual(int(mastery.score), 88)
        self.assertEqual(mastery.level_code, 'A2')
        self.assertEqual(mastery.status, 'Mastered')
        self.assertEqual(mastery.last_updated, original_last_updated)
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
        mastery = SkillMastery.objects.create(
            user=self.user,
            skill=self.skills['Grammar'],
            level_code='A2',
            score=88,
            status='Mastered',
        )
        original_last_updated = mastery.last_updated
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

        mastery.refresh_from_db()
        profile = LearnerProfile.objects.get(user=self.user)
        self.assertEqual(SkillMastery.objects.filter(user=self.user).count(), 1)
        self.assertEqual(int(mastery.score), 88)
        self.assertEqual(mastery.level_code, 'A2')
        self.assertEqual(mastery.last_updated, original_last_updated)
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

    def test_speaking_teacher_session_start_reads_official_mastery_without_updating_it(self):
        self.authenticate()
        LearnerProfile.objects.create(user=self.user, current_level='A2')
        mastery = SkillMastery.objects.create(
            user=self.user,
            skill=self.skills['Speaking'],
            level_code='B1',
            score=72,
            status='Learning',
        )
        original_last_updated = mastery.last_updated

        response = self.client.post(
            '/api/teacher/speaking/sessions/start/',
            {},
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        data = self.assert_success_response(response)
        self.assertEqual(data['session_mode'], 'speaking')
        self.assertEqual(data['skill'], 'Speaking')
        self.assertTrue(data['official_mastery_assessed'])
        self.assertEqual(data['official_mastery_score'], 72)
        self.assertEqual(data['official_mastery_level'], 'B1')
        self.assertEqual(data['total_turns'], 3)
        self.assertEqual(data['current_turn'], 1)
        self.assertEqual(data['current_task']['turn_number'], 1)
        self.assertEqual(data['current_task']['task_type'], 'spoken_response')
        self.assertIn('problem', data['current_task']['teacher_prompt'].lower())
        self.assertTrue(data['current_task']['target_focus'])

        mastery.refresh_from_db()
        self.assertEqual(mastery.last_updated, original_last_updated)

        lesson_session = LessonSession.objects.get(pk=data['session_id'])
        self.assertEqual(lesson_session.session_mode, LessonSession.SESSION_MODE_SPEAKING)
        self.assertEqual(lesson_session.study_session.session_type, 'speaking_teacher_session')
        self.assertIsNone(lesson_session.study_session.module)

    @patch('agents.voice_services.transcribe_audio')
    def test_speaking_teacher_session_accepts_audio_upload_and_saves_transcript(
        self,
        mock_transcribe_audio,
    ):
        self.authenticate()
        SkillMastery.objects.create(
            user=self.user,
            skill=self.skills['Speaking'],
            level_code='A2',
            score=68,
            status='Learning',
        )
        mock_transcribe_audio.return_value = (
            'I solved a customer problem because I checked the system settings carefully.'
        )
        start_response = self.client.post(
            '/api/teacher/speaking/sessions/start/',
            {},
            format='json',
        )
        session_data = self.assert_success_response(start_response)
        audio_file = SimpleUploadedFile(
            'speaking-practice.webm',
            b'fake audio',
            content_type='audio/webm',
        )

        response = self.client.post(
            f"/api/teacher/speaking/sessions/{session_data['session_id']}/answer/",
            {'audio_file': audio_file},
            format='multipart',
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = self.assert_success_response(response)
        self.assertFalse(data['completed'])
        self.assertEqual(
            data['turn']['transcript'],
            mock_transcribe_audio.return_value,
        )
        self.assertTrue(data['turn']['evaluation_breakdown'])
        turn = LessonTurn.objects.get(session_id=session_data['session_id'], turn_number=1)
        self.assertEqual(turn.student_answer, mock_transcribe_audio.return_value)

    def test_speaking_teacher_session_transcript_fallback_completes_without_mastery_update(self):
        self.authenticate()
        LearnerProfile.objects.create(user=self.user, current_level='A2')
        mastery = SkillMastery.objects.create(
            user=self.user,
            skill=self.skills['Speaking'],
            level_code='B1',
            score=72,
            status='Learning',
        )
        original_last_updated = mastery.last_updated

        start_response = self.client.post(
            '/api/teacher/speaking/sessions/start/',
            {},
            format='json',
        )
        self.assertEqual(start_response.status_code, status.HTTP_201_CREATED)
        session_data = self.assert_success_response(start_response)

        transcripts = [
            'I solved a problem at work because the customer could not log in, so I reset the account and explained the steps.',
            'My English goal is to speak more clearly, and I practice every day because I need better communication at work.',
            'I think daily speaking practice is effective because it builds confidence and helps me organize my ideas better.',
        ]

        final_data = None
        for transcript in transcripts:
            answer_response = self.client.post(
                f"/api/teacher/speaking/sessions/{session_data['session_id']}/answer/",
                {'transcript': transcript},
                format='json',
            )
            self.assertEqual(answer_response.status_code, status.HTTP_200_OK)
            final_data = self.assert_success_response(answer_response)

        self.assertIsNotNone(final_data)
        self.assertTrue(final_data['completed'])
        self.assertIsNotNone(final_data['final_result'])
        self.assertEqual(final_data['final_result']['label'], 'Practice Score')
        self.assertGreaterEqual(final_data['final_result']['practice_score'], 75)
        self.assertIn('Speaking Diagnostic', final_data['final_result']['next_suggestion'])

        detail_response = self.client.get(
            f"/api/teacher/speaking/sessions/{session_data['session_id']}/"
        )
        self.assertEqual(detail_response.status_code, status.HTTP_200_OK)
        detail_data = self.assert_success_response(detail_response)
        self.assertEqual(detail_data['status'], 'completed')
        self.assertEqual(len(detail_data['turns']), 3)
        self.assertIsNone(detail_data['current_task'])
        self.assertEqual(detail_data['final_result']['label'], 'Practice Score')

        lesson_session = LessonSession.objects.get(pk=session_data['session_id'])
        study_session = lesson_session.study_session
        self.assertEqual(lesson_session.session_mode, LessonSession.SESSION_MODE_SPEAKING)
        self.assertEqual(LessonTurn.objects.filter(session=lesson_session).count(), 3)
        self.assertEqual(int(lesson_session.final_score), final_data['final_result']['practice_score'])
        self.assertEqual(int(study_session.score), final_data['final_result']['practice_score'])
        self.assertIsNotNone(study_session.completed_at)

        mastery.refresh_from_db()
        self.assertEqual(int(mastery.score), 72)
        self.assertEqual(mastery.level_code, 'B1')
        self.assertEqual(mastery.status, 'Learning')
        self.assertEqual(mastery.last_updated, original_last_updated)
        self.assertEqual(LearnerProfile.objects.get(user=self.user).current_level, 'A2')

        dashboard_response = self.client.get('/api/dashboard/')
        self.assertEqual(dashboard_response.status_code, status.HTTP_200_OK)
        dashboard_data = self.assert_success_response(dashboard_response)
        speaking_mastery = next(
            item for item in dashboard_data['skill_mastery']
            if item['skill']['name'] == 'Speaking'
        )
        self.assertEqual(speaking_mastery['score'], '72.00')

    def test_speaking_teacher_session_access_is_limited_to_owner(self):
        speaking_mastery = SkillMastery.objects.create(
            user=self.other_user,
            skill=self.skills['Speaking'],
            level_code='A2',
            score=68,
            status='Learning',
        )
        self.client.force_authenticate(self.other_user)
        start_response = self.client.post(
            '/api/teacher/speaking/sessions/start/',
            {},
            format='json',
        )
        self.assertEqual(start_response.status_code, status.HTTP_201_CREATED)
        session_data = self.assert_success_response(start_response)

        self.authenticate()
        detail_response = self.client.get(
            f"/api/teacher/speaking/sessions/{session_data['session_id']}/"
        )
        answer_response = self.client.post(
            f"/api/teacher/speaking/sessions/{session_data['session_id']}/answer/",
            {'transcript': 'I solved the issue because I checked the password settings.'},
            format='json',
        )

        self.assertEqual(detail_response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(answer_response.status_code, status.HTTP_404_NOT_FOUND)
        speaking_mastery.refresh_from_db()
        self.assertEqual(int(speaking_mastery.score), 68)

    def test_pronunciation_teacher_session_start_reads_official_mastery_without_updating_it(self):
        self.authenticate()
        LearnerProfile.objects.create(user=self.user, current_level='A2')
        mastery = SkillMastery.objects.create(
            user=self.user,
            skill=self.skills['Pronunciation'],
            level_code='B1',
            score=78,
            status='Learning',
        )
        original_last_updated = mastery.last_updated

        response = self.client.post(
            '/api/teacher/pronunciation/sessions/start/',
            {},
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        data = self.assert_success_response(response)
        self.assertEqual(data['session_mode'], 'pronunciation')
        self.assertEqual(data['skill'], 'Pronunciation')
        self.assertTrue(data['official_mastery_assessed'])
        self.assertEqual(data['official_mastery_score'], 78)
        self.assertEqual(data['official_mastery_level'], 'B1')
        self.assertEqual(data['current_task']['task_type'], 'repeat_sentence')
        self.assertTrue(data['current_task']['target_text'])
        self.assertTrue(data['current_task']['target_focus'])

        mastery.refresh_from_db()
        self.assertEqual(mastery.last_updated, original_last_updated)

        lesson_session = LessonSession.objects.get(pk=data['session_id'])
        self.assertEqual(lesson_session.session_mode, LessonSession.SESSION_MODE_PRONUNCIATION)
        self.assertEqual(
            lesson_session.study_session.session_type,
            'pronunciation_teacher_session',
        )
        self.assertIsNone(lesson_session.study_session.module)

    def test_pronunciation_teacher_session_exact_repetition_scores_high_and_creates_turn(self):
        self.authenticate()
        SkillMastery.objects.create(
            user=self.user,
            skill=self.skills['Pronunciation'],
            level_code='A1',
            score=55,
            status='Learning',
        )
        start_response = self.client.post(
            '/api/teacher/pronunciation/sessions/start/',
            {},
            format='json',
        )
        session_data = self.assert_success_response(start_response)
        target_text = session_data['current_task']['target_text']

        response = self.client.post(
            f"/api/teacher/pronunciation/sessions/{session_data['session_id']}/answer/",
            {'transcript': target_text},
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = self.assert_success_response(response)
        self.assertFalse(data['completed'])
        self.assertGreaterEqual(data['turn']['score'], 95)
        self.assertEqual(data['turn']['word_accuracy'], 100)
        self.assertEqual(data['turn']['missing_words'], [])
        self.assertEqual(data['turn']['extra_words'], [])
        self.assertEqual(data['turn']['substituted_words'], [])
        turn = LessonTurn.objects.get(session_id=session_data['session_id'], turn_number=1)
        self.assertEqual(turn.target_text, target_text)
        self.assertEqual(turn.student_answer, target_text)

    def test_pronunciation_teacher_session_reports_missing_and_substituted_words(self):
        self.authenticate()
        SkillMastery.objects.create(
            user=self.user,
            skill=self.skills['Pronunciation'],
            level_code='A1',
            score=55,
            status='Learning',
        )
        start_response = self.client.post(
            '/api/teacher/pronunciation/sessions/start/',
            {},
            format='json',
        )
        session_data = self.assert_success_response(start_response)

        response = self.client.post(
            f"/api/teacher/pronunciation/sessions/{session_data['session_id']}/answer/",
            {'transcript': 'My work is Anna'},
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = self.assert_success_response(response)
        self.assertLess(data['turn']['score'], 95)
        self.assertIn('name', data['turn']['missing_words'])
        self.assertIn('work', data['turn']['extra_words'])
        self.assertEqual(
            data['turn']['substituted_words'][0],
            {'expected': 'name', 'heard': 'work'},
        )

    def test_pronunciation_teacher_session_transcript_fallback_completes_without_mastery_update(self):
        self.authenticate()
        LearnerProfile.objects.create(user=self.user, current_level='A2')
        mastery = SkillMastery.objects.create(
            user=self.user,
            skill=self.skills['Pronunciation'],
            level_code='B1',
            score=78,
            status='Learning',
        )
        original_last_updated = mastery.last_updated

        start_response = self.client.post(
            '/api/teacher/pronunciation/sessions/start/',
            {},
            format='json',
        )
        self.assertEqual(start_response.status_code, status.HTTP_201_CREATED)
        session_data = self.assert_success_response(start_response)

        transcripts = [
            'I solved the problem because I checked the network settings.',
            'Although the task was difficult, I finished it on time.',
            'I want to improve my English so I can communicate more clearly.',
        ]

        final_data = None
        for transcript in transcripts:
            answer_response = self.client.post(
                f"/api/teacher/pronunciation/sessions/{session_data['session_id']}/answer/",
                {'transcript': transcript},
                format='json',
            )
            self.assertEqual(answer_response.status_code, status.HTTP_200_OK)
            final_data = self.assert_success_response(answer_response)

        self.assertIsNotNone(final_data)
        self.assertTrue(final_data['completed'])
        self.assertEqual(final_data['final_result']['label'], 'Practice Score')
        self.assertIn(
            'Pronunciation Diagnostic',
            final_data['final_result']['next_suggestion'],
        )

        detail_response = self.client.get(
            f"/api/teacher/pronunciation/sessions/{session_data['session_id']}/"
        )
        self.assertEqual(detail_response.status_code, status.HTTP_200_OK)
        detail_data = self.assert_success_response(detail_response)
        self.assertEqual(detail_data['status'], 'completed')
        self.assertEqual(len(detail_data['turns']), 3)
        self.assertIsNone(detail_data['current_task'])
        self.assertEqual(detail_data['final_result']['label'], 'Practice Score')

        lesson_session = LessonSession.objects.get(pk=session_data['session_id'])
        study_session = lesson_session.study_session
        self.assertEqual(
            lesson_session.session_mode,
            LessonSession.SESSION_MODE_PRONUNCIATION,
        )
        self.assertEqual(LessonTurn.objects.filter(session=lesson_session).count(), 3)
        self.assertEqual(
            int(lesson_session.final_score),
            final_data['final_result']['practice_score'],
        )
        self.assertEqual(
            int(study_session.score),
            final_data['final_result']['practice_score'],
        )
        self.assertIsNotNone(study_session.completed_at)

        mastery.refresh_from_db()
        self.assertEqual(int(mastery.score), 78)
        self.assertEqual(mastery.level_code, 'B1')
        self.assertEqual(mastery.status, 'Learning')
        self.assertEqual(mastery.last_updated, original_last_updated)
        self.assertEqual(LearnerProfile.objects.get(user=self.user).current_level, 'A2')

        dashboard_response = self.client.get('/api/dashboard/')
        self.assertEqual(dashboard_response.status_code, status.HTTP_200_OK)
        dashboard_data = self.assert_success_response(dashboard_response)
        pronunciation_mastery = next(
            item for item in dashboard_data['skill_mastery']
            if item['skill']['name'] == 'Pronunciation'
        )
        self.assertEqual(pronunciation_mastery['score'], '78.00')

    def test_pronunciation_teacher_session_access_is_limited_to_owner(self):
        pronunciation_mastery = SkillMastery.objects.create(
            user=self.other_user,
            skill=self.skills['Pronunciation'],
            level_code='A2',
            score=66,
            status='Learning',
        )
        self.client.force_authenticate(self.other_user)
        start_response = self.client.post(
            '/api/teacher/pronunciation/sessions/start/',
            {},
            format='json',
        )
        self.assertEqual(start_response.status_code, status.HTTP_201_CREATED)
        session_data = self.assert_success_response(start_response)

        self.authenticate()
        detail_response = self.client.get(
            f"/api/teacher/pronunciation/sessions/{session_data['session_id']}/"
        )
        answer_response = self.client.post(
            f"/api/teacher/pronunciation/sessions/{session_data['session_id']}/answer/",
            {'transcript': 'My name is Anna.'},
            format='json',
        )

        self.assertEqual(detail_response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(answer_response.status_code, status.HTTP_404_NOT_FOUND)
        pronunciation_mastery.refresh_from_db()
        self.assertEqual(int(pronunciation_mastery.score), 66)

    def test_listening_teacher_session_start_reads_official_mastery_without_updating_it(self):
        self.authenticate()
        LearnerProfile.objects.create(user=self.user, current_level='A2')
        mastery = SkillMastery.objects.create(
            user=self.user,
            skill=self.skills['Listening'],
            level_code='B1',
            score=70,
            status='Learning',
        )
        original_last_updated = mastery.last_updated

        response = self.client.post(
            '/api/teacher/listening/sessions/start/',
            {},
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        data = self.assert_success_response(response)
        self.assertEqual(data['session_mode'], 'listening')
        self.assertEqual(data['skill'], 'Listening')
        self.assertTrue(data['official_mastery_assessed'])
        self.assertEqual(data['official_mastery_score'], 70)
        self.assertEqual(data['official_mastery_level'], 'B1')
        self.assertEqual(data['current_task']['task_type'], 'detail_question')
        self.assertTrue(data['current_task']['passage_text'])
        self.assertTrue(data['current_task']['question_text'])
        self.assertIsNone(data['current_task']['audio_url'])

        mastery.refresh_from_db()
        self.assertEqual(mastery.last_updated, original_last_updated)

        lesson_session = LessonSession.objects.get(pk=data['session_id'])
        self.assertEqual(lesson_session.session_mode, LessonSession.SESSION_MODE_LISTENING)
        self.assertEqual(
            lesson_session.study_session.session_type,
            'listening_teacher_session',
        )
        self.assertIsNone(lesson_session.study_session.module)

    def test_listening_teacher_session_complete_answer_scores_high_and_creates_turn(self):
        self.authenticate()
        SkillMastery.objects.create(
            user=self.user,
            skill=self.skills['Listening'],
            level_code='B1',
            score=70,
            status='Learning',
        )
        start_response = self.client.post(
            '/api/teacher/listening/sessions/start/',
            {},
            format='json',
        )
        session_data = self.assert_success_response(start_response)

        response = self.client.post(
            f"/api/teacher/listening/sessions/{session_data['session_id']}/answer/",
            {'answer': 'The customer could not connect to the internet.'},
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = self.assert_success_response(response)
        self.assertFalse(data['completed'])
        self.assertGreaterEqual(data['turn']['score'], 90)
        self.assertEqual(data['turn']['answer_match'], 'complete')
        self.assertEqual(data['turn']['missing_keywords'], [])
        self.assertIn('internet', data['turn']['matched_keywords'])
        turn = LessonTurn.objects.get(session_id=session_data['session_id'], turn_number=1)
        self.assertEqual(turn.target_text, 'The customer could not connect to the internet.')
        self.assertEqual(turn.student_answer, 'The customer could not connect to the internet.')

    def test_listening_teacher_session_partial_answer_returns_missing_keywords(self):
        self.authenticate()
        SkillMastery.objects.create(
            user=self.user,
            skill=self.skills['Listening'],
            level_code='B1',
            score=70,
            status='Learning',
        )
        start_response = self.client.post(
            '/api/teacher/listening/sessions/start/',
            {},
            format='json',
        )
        session_data = self.assert_success_response(start_response)

        response = self.client.post(
            f"/api/teacher/listening/sessions/{session_data['session_id']}/answer/",
            {'answer': 'connect internet'},
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = self.assert_success_response(response)
        self.assertEqual(data['turn']['answer_match'], 'partial')
        self.assertGreaterEqual(data['turn']['score'], 50)
        self.assertLess(data['turn']['score'], 90)
        self.assertIn('connect', data['turn']['matched_keywords'])
        self.assertIn('internet', data['turn']['matched_keywords'])
        self.assertIn('customer', data['turn']['missing_keywords'])

    def test_listening_teacher_session_unrelated_answer_scores_low(self):
        self.authenticate()
        SkillMastery.objects.create(
            user=self.user,
            skill=self.skills['Listening'],
            level_code='B1',
            score=70,
            status='Learning',
        )
        start_response = self.client.post(
            '/api/teacher/listening/sessions/start/',
            {},
            format='json',
        )
        session_data = self.assert_success_response(start_response)

        response = self.client.post(
            f"/api/teacher/listening/sessions/{session_data['session_id']}/answer/",
            {'answer': 'I like pizza and music.'},
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = self.assert_success_response(response)
        self.assertEqual(data['turn']['answer_match'], 'unrelated')
        self.assertLessEqual(data['turn']['score'], 45)
        self.assertFalse(data['turn']['matched_keywords'])

    def test_listening_teacher_session_text_fallback_completes_without_mastery_update(self):
        self.authenticate()
        LearnerProfile.objects.create(user=self.user, current_level='A2')
        mastery = SkillMastery.objects.create(
            user=self.user,
            skill=self.skills['Listening'],
            level_code='B1',
            score=70,
            status='Learning',
        )
        original_last_updated = mastery.last_updated

        start_response = self.client.post(
            '/api/teacher/listening/sessions/start/',
            {},
            format='json',
        )
        self.assertEqual(start_response.status_code, status.HTTP_201_CREATED)
        session_data = self.assert_success_response(start_response)

        answers = [
            'The customer could not connect to the internet.',
            'The network settings.',
            'Restarting the router.',
        ]

        final_data = None
        for answer in answers:
            answer_response = self.client.post(
                f"/api/teacher/listening/sessions/{session_data['session_id']}/answer/",
                {'answer': answer},
                format='json',
            )
            self.assertEqual(answer_response.status_code, status.HTTP_200_OK)
            final_data = self.assert_success_response(answer_response)

        self.assertIsNotNone(final_data)
        self.assertTrue(final_data['completed'])
        self.assertEqual(final_data['final_result']['label'], 'Practice Score')
        self.assertIn(
            'Listening Diagnostic',
            final_data['final_result']['next_suggestion'],
        )

        detail_response = self.client.get(
            f"/api/teacher/listening/sessions/{session_data['session_id']}/"
        )
        self.assertEqual(detail_response.status_code, status.HTTP_200_OK)
        detail_data = self.assert_success_response(detail_response)
        self.assertEqual(detail_data['status'], 'completed')
        self.assertEqual(len(detail_data['turns']), 3)
        self.assertIsNone(detail_data['current_task'])
        self.assertEqual(detail_data['final_result']['label'], 'Practice Score')

        lesson_session = LessonSession.objects.get(pk=session_data['session_id'])
        study_session = lesson_session.study_session
        self.assertEqual(
            lesson_session.session_mode,
            LessonSession.SESSION_MODE_LISTENING,
        )
        self.assertEqual(LessonTurn.objects.filter(session=lesson_session).count(), 3)
        self.assertEqual(
            int(lesson_session.final_score),
            final_data['final_result']['practice_score'],
        )
        self.assertEqual(
            int(study_session.score),
            final_data['final_result']['practice_score'],
        )
        self.assertIsNotNone(study_session.completed_at)

        mastery.refresh_from_db()
        self.assertEqual(int(mastery.score), 70)
        self.assertEqual(mastery.level_code, 'B1')
        self.assertEqual(mastery.status, 'Learning')
        self.assertEqual(mastery.last_updated, original_last_updated)
        self.assertEqual(LearnerProfile.objects.get(user=self.user).current_level, 'A2')

        dashboard_response = self.client.get('/api/dashboard/')
        self.assertEqual(dashboard_response.status_code, status.HTTP_200_OK)
        dashboard_data = self.assert_success_response(dashboard_response)
        listening_mastery = next(
            item for item in dashboard_data['skill_mastery']
            if item['skill']['name'] == 'Listening'
        )
        self.assertEqual(listening_mastery['score'], '70.00')

    def test_listening_teacher_session_access_is_limited_to_owner(self):
        listening_mastery = SkillMastery.objects.create(
            user=self.other_user,
            skill=self.skills['Listening'],
            level_code='A2',
            score=64,
            status='Learning',
        )
        self.client.force_authenticate(self.other_user)
        start_response = self.client.post(
            '/api/teacher/listening/sessions/start/',
            {},
            format='json',
        )
        self.assertEqual(start_response.status_code, status.HTTP_201_CREATED)
        session_data = self.assert_success_response(start_response)

        self.authenticate()
        detail_response = self.client.get(
            f"/api/teacher/listening/sessions/{session_data['session_id']}/"
        )
        answer_response = self.client.post(
            f"/api/teacher/listening/sessions/{session_data['session_id']}/answer/",
            {'answer': 'The customer could not connect to the internet.'},
            format='json',
        )

        self.assertEqual(detail_response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(answer_response.status_code, status.HTTP_404_NOT_FOUND)
        listening_mastery.refresh_from_db()
        self.assertEqual(int(listening_mastery.score), 64)

    def test_study_plan_routes_listening_focus_to_listening_teacher(self):
        self.authenticate()
        LearnerProfile.objects.create(user=self.user, current_level='A2')
        SkillMastery.objects.create(
            user=self.user,
            skill=self.skills['Listening'],
            level_code='A2',
            score=30,
            status='Needs Review',
        )
        SkillMastery.objects.create(
            user=self.user,
            skill=self.skills['Grammar'],
            level_code='A2',
            score=42,
            status='Needs Review',
        )
        SkillMastery.objects.create(
            user=self.user,
            skill=self.skills['Pronunciation'],
            level_code='A2',
            score=74,
            status='Learning',
        )

        response = self.client.post('/api/scheduler/generate-plan/', {}, format='json')

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        data = self.assert_success_response(response)
        listening_item = next(
            item for item in data['plan']['items']
            if item['skill'] == 'Listening'
        )
        self.assertEqual(listening_item['title'], 'Listening Teacher Session')
        self.assertEqual(listening_item['href'], '/listening-teacher')
        self.assertIsNone(listening_item['module_id'])
        self.assertFalse(listening_item['fallback_used'])

    def test_study_plan_routes_pronunciation_focus_to_pronunciation_teacher(self):
        self.authenticate()
        LearnerProfile.objects.create(user=self.user, current_level='A2')
        SkillMastery.objects.create(
            user=self.user,
            skill=self.skills['Pronunciation'],
            level_code='A2',
            score=35,
            status='Needs Review',
        )
        SkillMastery.objects.create(
            user=self.user,
            skill=self.skills['Grammar'],
            level_code='A2',
            score=42,
            status='Needs Review',
        )
        SkillMastery.objects.create(
            user=self.user,
            skill=self.skills['Speaking'],
            level_code='A2',
            score=75,
            status='Learning',
        )

        response = self.client.post('/api/scheduler/generate-plan/', {}, format='json')

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        data = self.assert_success_response(response)
        pronunciation_item = next(
            item for item in data['plan']['items']
            if item['skill'] == 'Pronunciation'
        )
        self.assertEqual(pronunciation_item['title'], 'Pronunciation Teacher Session')
        self.assertEqual(pronunciation_item['href'], '/pronunciation-teacher')
        self.assertIsNone(pronunciation_item['module_id'])
        self.assertFalse(pronunciation_item['fallback_used'])

    def test_study_plan_routes_speaking_focus_to_speaking_teacher(self):
        self.authenticate()
        LearnerProfile.objects.create(user=self.user, current_level='A2')
        SkillMastery.objects.create(
            user=self.user,
            skill=self.skills['Speaking'],
            level_code='A2',
            score=31,
            status='Needs Review',
        )
        SkillMastery.objects.create(
            user=self.user,
            skill=self.skills['Grammar'],
            level_code='A2',
            score=45,
            status='Needs Review',
        )
        SkillMastery.objects.create(
            user=self.user,
            skill=self.skills['Listening'],
            level_code='A2',
            score=78,
            status='Learning',
        )

        response = self.client.post('/api/scheduler/generate-plan/', {}, format='json')

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        data = self.assert_success_response(response)
        speaking_item = next(
            item for item in data['plan']['items']
            if item['skill'] == 'Speaking'
        )
        self.assertEqual(speaking_item['title'], 'Speaking Teacher Session')
        self.assertEqual(speaking_item['href'], '/speaking-teacher')
        self.assertIsNone(speaking_item['module_id'])
        self.assertFalse(speaking_item['fallback_used'])

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
                'Day 2: Speaking Teacher Session',
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

    def test_pronunciation_recommendation_does_not_change_cefr_progression_blocker_rules(self):
        profile = LearnerProfile.objects.create(user=self.user, current_level='A1')
        SkillMastery.objects.create(user=self.user, skill=self.skills['Grammar'], level_code='A1', score=88)
        SkillMastery.objects.create(user=self.user, skill=self.skills['Vocabulary'], level_code='A1', score=82)
        SkillMastery.objects.create(user=self.user, skill=self.skills['Listening'], level_code='A1', score=90)
        SkillMastery.objects.create(user=self.user, skill=self.skills['Speaking'], level_code='A1', score=87)
        SkillMastery.objects.create(user=self.user, skill=self.skills['Pronunciation'], level_code='A1', score=35)

        updated_level = recalculate_learner_level(self.user)

        profile.refresh_from_db()
        self.assertEqual(updated_level, 'A2')
        self.assertEqual(profile.current_level, 'A2')

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
