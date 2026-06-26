import tempfile
from types import SimpleNamespace
from unittest.mock import patch

from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import SimpleTestCase, override_settings
from rest_framework import status
from rest_framework.test import APITestCase

from agents.llm_client import call_llm_json, get_llm_runtime_diagnostic
from agents.models import VoiceConversationSession, VoiceConversationTurn
from agents.prompts import voice_conversation_response_prompt
from agents.voice_conversation_services import (
    build_voice_conversation_fallback_response,
    generate_voice_conversation_response,
)
from agents.voice_services import VoiceDiagnosticError
from learning.models import Skill, SkillMastery


class FakeLlmResponse:
    def __init__(self, payload):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return None

    def read(self):
        return self.payload


class VoiceConversationTeacherPromptTests(SimpleTestCase):
    def _session(self, cefr_level='A2', target_skill='speaking'):
        return SimpleNamespace(
            target_skill=target_skill,
            cefr_level=cefr_level,
            title='Voice practice',
        )

    def assert_one_follow_up_question(self, response_text):
        self.assertEqual(response_text.count('?'), 1)

    def test_prompt_requires_cefr_aware_practice_only_feedback(self):
        system_prompt, user_prompt = voice_conversation_response_prompt(
            self._session(cefr_level='B2'),
            'I work in technical support.',
            recent_turns=[
                {
                    'learner': 'I want to improve my speaking.',
                    'teacher': 'What is one reason for your answer?',
                }
            ],
        )

        self.assertIn('practice-only', system_prompt)
        self.assertIn('Do not use labels', system_prompt)
        self.assertIn('exactly one follow-up question', system_prompt)
        self.assertIn('one correction or one more natural rephrase', system_prompt)
        self.assertIn('Do not ask for the same information again.', system_prompt)
        self.assertIn('A1 uses very short sentences', system_prompt)
        self.assertIn('B2 improves fluency', system_prompt)
        self.assertIn('Do not mention scores', system_prompt)
        self.assertIn('SkillMastery', system_prompt)
        self.assertIn('Recent conversation history:', user_prompt)
        self.assertIn('What is one reason for your answer?', user_prompt)
        self.assertIn('CEFR level: B2', user_prompt)
        self.assertIn('avoid repeating the previous teacher question', user_prompt)

    def test_prompt_makes_correction_conditional(self):
        system_prompt, _ = voice_conversation_response_prompt(
            self._session(cefr_level='B2'),
            'AI helps me improve my speaking skills the most.',
        )

        self.assertIn('only when the learner sentence has a clear grammar', system_prompt)
        self.assertIn('already clear and natural', system_prompt)
        self.assertIn('Never present the same sentence as a correction.', system_prompt)
        self.assertIn('Do not overuse the phrase "A more natural way to say it is."', system_prompt)
        self.assertIn('You can also say', system_prompt)
        self.assertIn('A small correction is', system_prompt)

    def test_a1_fallback_uses_short_simple_feedback(self):
        response_text = build_voice_conversation_fallback_response(
            self._session(cefr_level='A1'),
            'I am work today.',
        )

        self.assertIn('Good try', response_text)
        self.assertIn('I work every day.', response_text)
        self.assertIn("Use 'I work'", response_text)
        self.assertIn('What is your job?', response_text)
        self.assertNotIn('Teacher follow-up:', response_text)
        self.assert_one_follow_up_question(response_text)

    def test_a2_fallback_corrects_want_improve_because_my_job(self):
        response_text = build_voice_conversation_fallback_response(
            self._session(cefr_level='A2'),
            'I want improve my speaking because my job.',
        )

        self.assertIn('I want to improve my speaking because of my job.', response_text)
        self.assertIn("Use 'want to' before a verb.", response_text)
        self.assertIn('When do you usually use English at work?', response_text)
        self.assert_one_follow_up_question(response_text)

    def test_b1_fallback_corrects_technical_support_answer(self):
        response_text = build_voice_conversation_fallback_response(
            self._session(cefr_level='B1'),
            'I work technical support and I help customer.',
        )

        self.assertIn(
            'I work in technical support, and I help customers.',
            response_text,
        )
        self.assertIn("Use 'work in' for a field or department.", response_text)
        self.assertIn('What kind of customer problem do you usually handle?', response_text)
        self.assert_one_follow_up_question(response_text)

    def test_b2_fallback_uses_more_natural_rephrase(self):
        response_text = build_voice_conversation_fallback_response(
            self._session(cefr_level='B2'),
            'I work in technical support.',
        )

        self.assertIn('A more natural version is', response_text)
        self.assertIn(
            'I work in technical support and help customers solve problems.',
            response_text,
        )
        self.assertIn('Add a specific action after your job field.', response_text)
        self.assertIn('What kind of customer problem do you usually handle?', response_text)
        self.assert_one_follow_up_question(response_text)

    def test_unclear_fallback_still_gives_one_question(self):
        response_text = build_voice_conversation_fallback_response(
            self._session(cefr_level='A2'),
            'um',
        )

        self.assertIn('Please try one short sentence.', response_text)
        self.assertIn('Try one short sentence with a clear idea.', response_text)
        self.assertIn('Can you try again with one short sentence?', response_text)
        self.assertNotIn('A better sentence is:', response_text)
        self.assert_one_follow_up_question(response_text)

    def test_fallback_does_not_repeat_answered_reason_question(self):
        response_text = build_voice_conversation_fallback_response(
            self._session(cefr_level='B1'),
            'The reason is to improve my speaking skills.',
            recent_turns=[
                {
                    'learner': 'I want to practice English.',
                    'teacher': 'What is one reason for your answer?',
                }
            ],
        )

        self.assertIn('I want to improve my speaking skills.', response_text)
        self.assertIn("instead of saying 'The reason is.'", response_text)
        self.assertNotIn('What is one reason for your answer?', response_text)
        self.assertNotIn('What is one reason', response_text)
        self.assertIn('When do you need to use spoken English?', response_text)
        self.assert_one_follow_up_question(response_text)

    @patch('agents.voice_conversation_services.call_llm_json')
    def test_llm_response_with_follow_up_label_still_gets_question(self, mock_call_llm_json):
        mock_call_llm_json.return_value = {
            'response_text': (
                'Good answer. A better sentence is: I work in technical support. '
                "Learning point: Use 'work in' for a department. "
                'Teacher follow-up: Tell me more about that.'
            )
        }

        response_text, response_source = generate_voice_conversation_response(
            self._session(cefr_level='B1'),
            'I work technical support.',
        )

        self.assertEqual(response_source, 'llm')
        self.assertNotIn('Practice feedback only:', response_text)
        self.assertNotIn('Teacher follow-up:', response_text)
        self.assertIn('What kind of customer problem do you usually handle?', response_text)
        self.assert_one_follow_up_question(response_text)

    @override_settings(
        USE_LLM_AGENTS=True,
        LLM_PROVIDER='openai',
        LLM_API_KEY='',
        LLM_MODEL='',
    )
    def test_llm_missing_config_logs_safe_skip(self):
        with self.assertLogs('agents.llm_client', level='WARNING') as captured:
            payload = call_llm_json('system', 'user')

        self.assertIsNone(payload)
        log_output = '\n'.join(captured.output)
        self.assertIn('VOICE_LLM_SKIPPED reason=missing_config', log_output)
        self.assertIn('LLM_API_KEY', log_output)
        self.assertIn('LLM_MODEL', log_output)
        self.assertNotIn('sk-', log_output)

    @override_settings(
        USE_LLM_AGENTS=True,
        LLM_PROVIDER='openai',
        LLM_API_KEY='test-key',
        LLM_MODEL='test-model',
    )
    @patch('agents.llm_client.request.urlopen')
    def test_llm_config_present_attempts_request(self, mock_urlopen):
        mock_urlopen.return_value = FakeLlmResponse(
            b'{"choices":[{"message":{"content":"{\\"response_text\\": \\"Good answer. What happened next?\\"}"}}]}'
        )

        diagnostic = get_llm_runtime_diagnostic()
        payload = call_llm_json('system', 'user')

        self.assertTrue(diagnostic['enabled'])
        self.assertTrue(diagnostic['provider_configured'])
        self.assertTrue(diagnostic['model_configured'])
        self.assertTrue(diagnostic['api_key_present'])
        self.assertEqual(payload['response_text'], 'Good answer. What happened next?')
        self.assertTrue(mock_urlopen.called)


@override_settings(USE_LLM_AGENTS=False)
class VoiceConversationAPITests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username='voice-learner',
            password='test-password-123',
        )
        self.other_user = User.objects.create_user(
            username='other-voice-learner',
            password='test-password-123',
        )
        self.temp_media = tempfile.TemporaryDirectory()
        self.media_override = override_settings(MEDIA_ROOT=self.temp_media.name)
        self.media_override.enable()
        self.addCleanup(self.media_override.disable)
        self.addCleanup(self.temp_media.cleanup)

    def authenticate(self, user=None):
        self.client.force_authenticate(user or self.user)

    def assert_success_response(self, response):
        self.assertTrue(response.data['success'])
        self.assertIn('data', response.data)
        self.assertTrue(response.data['message'])
        return response.data['data']

    def start_session(self, user=None, payload=None):
        self.authenticate(user)
        response = self.client.post(
            '/api/voice-conversation/sessions/start/',
            payload or {},
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        return self.assert_success_response(response)

    def test_authenticated_user_can_start_voice_conversation_session(self):
        session_data = self.start_session(
            payload={
                'target_skill': 'speaking',
                'cefr_level': 'A2',
                'title': 'Speaking Practice',
            }
        )

        self.assertEqual(session_data['title'], 'Speaking Practice')
        self.assertEqual(session_data['target_skill'], 'speaking')
        self.assertEqual(session_data['cefr_level'], 'A2')
        self.assertEqual(session_data['status'], 'active')
        self.assertTrue(session_data['started_at'])
        self.assertIsNone(session_data['ended_at'])
        self.assertEqual(VoiceConversationSession.objects.filter(user=self.user).count(), 1)

    def test_unauthenticated_user_cannot_access_voice_conversation_endpoints(self):
        session = VoiceConversationSession.objects.create(user=self.user)
        requests = [
            ('post', '/api/voice-conversation/sessions/start/', {}),
            ('get', '/api/voice-conversation/sessions/', None),
            ('get', f'/api/voice-conversation/sessions/{session.id}/', None),
            ('delete', f'/api/voice-conversation/sessions/{session.id}/', None),
            (
                'post',
                f'/api/voice-conversation/sessions/{session.id}/turns/',
                {'user_transcript': 'Hello teacher.'},
            ),
            ('post', f'/api/voice-conversation/sessions/{session.id}/end/', {}),
        ]

        for method, path, data in requests:
            response = getattr(self.client, method)(path, data, format='json')
            self.assertIn(
                response.status_code,
                [status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN],
            )
            self.assertFalse(response.data['success'])
            self.assertTrue(response.data['error'])

    def test_authenticated_user_can_list_only_own_sessions(self):
        VoiceConversationSession.objects.create(
            user=self.user,
            title='My latest session',
        )
        VoiceConversationSession.objects.create(
            user=self.other_user,
            title='Other user session',
        )

        self.authenticate()
        response = self.client.get('/api/voice-conversation/sessions/')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = self.assert_success_response(response)
        self.assertEqual(len(data), 1)
        self.assertEqual(data[0]['title'], 'My latest session')

    def test_authenticated_user_can_retrieve_own_session_with_turns(self):
        session = VoiceConversationSession.objects.create(
            user=self.user,
            title='Conversation detail',
        )
        VoiceConversationTurn.objects.create(
            session=session,
            turn_number=1,
            user_transcript='Hello teacher.',
            ai_response_text='AI response generation will be added in V5A-2.',
            transcript_source=VoiceConversationTurn.TRANSCRIPT_SOURCE_FALLBACK,
        )

        self.authenticate()
        response = self.client.get(f'/api/voice-conversation/sessions/{session.id}/')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = self.assert_success_response(response)
        self.assertEqual(data['id'], session.id)
        self.assertEqual(data['title'], 'Conversation detail')
        self.assertEqual(len(data['turns']), 1)
        self.assertEqual(data['turns'][0]['turn_number'], 1)
        self.assertEqual(data['turns'][0]['user_transcript'], 'Hello teacher.')

    def test_user_cannot_retrieve_another_users_session(self):
        session = VoiceConversationSession.objects.create(user=self.other_user)

        self.authenticate()
        response = self.client.get(f'/api/voice-conversation/sessions/{session.id}/')

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_user_can_delete_own_session_and_related_turns(self):
        session = VoiceConversationSession.objects.create(
            user=self.user,
            title='Delete me',
        )
        VoiceConversationTurn.objects.create(
            session=session,
            turn_number=1,
            user_transcript='Please remove this practice session.',
            ai_response_text='Practice feedback only: Session can be deleted.',
            transcript_source=VoiceConversationTurn.TRANSCRIPT_SOURCE_FALLBACK,
        )

        self.authenticate()
        response = self.client.delete(f'/api/voice-conversation/sessions/{session.id}/')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = self.assert_success_response(response)
        self.assertEqual(data, {})
        self.assertFalse(VoiceConversationSession.objects.filter(pk=session.id).exists())
        self.assertFalse(VoiceConversationTurn.objects.filter(session_id=session.id).exists())

    def test_user_cannot_delete_another_users_session(self):
        session = VoiceConversationSession.objects.create(user=self.other_user)

        self.authenticate()
        response = self.client.delete(f'/api/voice-conversation/sessions/{session.id}/')

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_authenticated_user_can_create_manual_transcript_turn(self):
        session_data = self.start_session(payload={'title': 'Fallback session'})
        response = self.client.post(
            f"/api/voice-conversation/sessions/{session_data['id']}/turns/",
            {'user_transcript': 'Hello teacher, I want to practice English.'},
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        data = self.assert_success_response(response)
        self.assertEqual(data['turn_number'], 1)
        self.assertEqual(
            data['user_transcript'],
            'Hello teacher, I want to practice English.',
        )
        self.assertEqual(data['transcript_source'], 'fallback')
        self.assertEqual(
            data['ai_response_text'],
            (
                'Good answer. I understood your idea. '
                'A better sentence is: Hello teacher, I want to practice English. '
                'Keep the sentence direct and easy to say aloud. '
                'Which English situation do you want to practice first?'
            ),
        )
        self.assertTrue(data['metadata']['practice_only'])
        self.assertEqual(data['metadata']['word_count'], 7)
        self.assertEqual(data['metadata']['response_mode'], 'deterministic_fallback')

    def test_turn_number_increments_automatically(self):
        session_data = self.start_session()
        session_id = session_data['id']

        first = self.client.post(
            f'/api/voice-conversation/sessions/{session_id}/turns/',
            {'user_transcript': 'First turn.'},
            format='json',
        )
        second = self.client.post(
            f'/api/voice-conversation/sessions/{session_id}/turns/',
            {'user_transcript': 'Second turn.'},
            format='json',
        )

        self.assertEqual(first.status_code, status.HTTP_201_CREATED)
        self.assertEqual(second.status_code, status.HTTP_201_CREATED)
        first_data = self.assert_success_response(first)
        second_data = self.assert_success_response(second)
        self.assertEqual(first_data['turn_number'], 1)
        self.assertEqual(second_data['turn_number'], 2)

    def test_turn_creation_accepts_manual_transcript_source(self):
        session_data = self.start_session(payload={'target_skill': 'general'})

        response = self.client.post(
            f"/api/voice-conversation/sessions/{session_data['id']}/turns/",
            {
                'user_transcript': 'I studied English today.',
                'transcript_source': 'manual',
            },
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        data = self.assert_success_response(response)
        self.assertEqual(data['transcript_source'], 'manual')
        self.assertTrue(data['metadata']['practice_only'])
        self.assertNotIn('Practice feedback only:', data['ai_response_text'])
        self.assertNotIn('Teacher follow-up:', data['ai_response_text'])
        self.assertEqual(data['ai_response_text'].count('?'), 1)

    @patch('agents.voice_conversation_services.synthesize_tts')
    @patch('agents.voice_conversation_services.call_llm_json')
    def test_manual_transcript_uses_llm_response_and_saves_tts_audio(
        self,
        mock_call_llm_json,
        mock_synthesize_tts,
    ):
        mock_call_llm_json.return_value = {
            'response_text': (
                'Practice feedback only: That was a clear answer with a useful '
                'example. Try to explain one reason in more detail. Teacher '
                'follow-up: What happened next?'
            )
        }
        mock_synthesize_tts.return_value = (b'fake-mp3-audio', 'audio/mpeg')
        session_data = self.start_session(payload={'target_skill': 'speaking'})

        response = self.client.post(
            f"/api/voice-conversation/sessions/{session_data['id']}/turns/",
            {'user_transcript': 'Yesterday I practiced English after work.'},
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        data = self.assert_success_response(response)
        self.assertEqual(data['metadata']['response_mode'], 'llm')
        self.assertTrue(data['metadata']['tts_generated'])
        self.assertEqual(data['metadata']['tts_provider'], 'deepgram')
        self.assertEqual(data['metadata']['tts_content_type'], 'audio/mpeg')
        self.assertTrue(data['ai_audio'])
        self.assertEqual(
            data['ai_response_text'],
            (
                'That was a clear answer with a useful example. Try to explain '
                'one reason in more detail. What happened next?'
            ),
        )

        turn = VoiceConversationTurn.objects.get(session_id=session_data['id'], turn_number=1)
        self.assertTrue(turn.ai_audio.name.endswith('.mp3'))
        self.assertIn('session-', turn.ai_audio.name)

    @patch('agents.voice_conversation_services.synthesize_tts')
    def test_turn_creation_still_succeeds_when_tts_generation_fails(self, mock_synthesize_tts):
        mock_synthesize_tts.side_effect = VoiceDiagnosticError('TTS request failed: timeout')
        session_data = self.start_session(payload={'target_skill': 'general'})

        response = self.client.post(
            f"/api/voice-conversation/sessions/{session_data['id']}/turns/",
            {'user_transcript': 'I want to practice more.'},
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        data = self.assert_success_response(response)
        self.assertFalse(data['metadata']['tts_generated'])
        self.assertEqual(data['metadata']['tts_error'], 'TTS request failed: timeout')
        self.assertIsNone(data['ai_audio'])
        self.assertTrue(data['metadata']['practice_only'])
        self.assertNotIn('Practice feedback only:', data['ai_response_text'])
        self.assertEqual(data['ai_response_text'].count('?'), 1)

    @patch('agents.voice_conversation_services.transcribe_audio')
    def test_audio_upload_creates_turn_with_deepgram_transcript(self, mock_transcribe_audio):
        mock_transcribe_audio.return_value = 'I want to practice English today.'
        session_data = self.start_session(payload={'target_skill': 'speaking'})
        audio_file = SimpleUploadedFile(
            'practice.webm',
            b'fake-audio-content',
            content_type='audio/webm',
        )

        response = self.client.post(
            f"/api/voice-conversation/sessions/{session_data['id']}/turns/",
            {'audio_file': audio_file},
            format='multipart',
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        data = self.assert_success_response(response)
        self.assertEqual(data['turn_number'], 1)
        self.assertEqual(data['transcript_source'], 'deepgram')
        self.assertEqual(
            data['user_transcript'],
            'I want to practice English today.',
        )
        self.assertTrue(data['user_audio'])
        self.assertTrue(data['metadata']['practice_only'])
        self.assertTrue(data['metadata']['audio_uploaded'])
        self.assertEqual(data['metadata']['transcription_provider'], 'deepgram')
        self.assertEqual(data['metadata']['input_mode'], 'audio_upload')
        self.assertEqual(data['metadata']['response_mode'], 'deterministic_fallback')
        self.assertFalse(data['metadata']['tts_generated'])
        self.assertNotIn('Practice feedback only:', data['ai_response_text'])
        self.assertEqual(data['ai_response_text'].count('?'), 1)

        turn = VoiceConversationTurn.objects.get(session_id=session_data['id'], turn_number=1)
        self.assertTrue(turn.user_audio.name.endswith('practice.webm'))
        self.assertEqual(turn.user_transcript, mock_transcribe_audio.return_value)

    @patch('agents.voice_conversation_services.synthesize_tts')
    def test_voice_conversation_audio_route_serves_generated_audio(self, mock_synthesize_tts):
        mock_synthesize_tts.return_value = (b'fake-mp3-audio', 'audio/mpeg')
        session_data = self.start_session(payload={'target_skill': 'general'})

        response = self.client.post(
            f"/api/voice-conversation/sessions/{session_data['id']}/turns/",
            {'user_transcript': 'I want to practice more.'},
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        data = self.assert_success_response(response)
        self.assertTrue(data['ai_audio'].startswith('/api/voice-conversation/media/'))

        media_response = self.client.get(data['ai_audio'])
        self.assertEqual(media_response.status_code, status.HTTP_200_OK)
        self.assertEqual(media_response['Content-Type'], 'audio/mpeg')
        self.assertEqual(b''.join(media_response.streaming_content), b'fake-mp3-audio')

    @patch('agents.voice_conversation_services.synthesize_tts')
    @patch('agents.voice_conversation_services.call_llm_json')
    @patch('agents.voice_conversation_services.transcribe_audio')
    def test_audio_upload_can_save_ai_audio_after_stt_and_llm(
        self,
        mock_transcribe_audio,
        mock_call_llm_json,
        mock_synthesize_tts,
    ):
        mock_transcribe_audio.return_value = 'I studied English today.'
        mock_call_llm_json.return_value = {
            'response_text': (
                'Practice feedback only: Good detail. Try to connect your idea '
                'with one more reason. Teacher follow-up: What did you study?'
            )
        }
        mock_synthesize_tts.return_value = (b'fake-ogg-audio', 'audio/ogg')
        session_data = self.start_session(payload={'target_skill': 'speaking'})
        audio_file = SimpleUploadedFile(
            'practice.webm',
            b'fake-audio-content',
            content_type='audio/webm',
        )

        response = self.client.post(
            f"/api/voice-conversation/sessions/{session_data['id']}/turns/",
            {'audio_file': audio_file},
            format='multipart',
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        data = self.assert_success_response(response)
        self.assertEqual(data['transcript_source'], 'deepgram')
        self.assertEqual(data['metadata']['response_mode'], 'llm')
        self.assertTrue(data['metadata']['tts_generated'])
        self.assertEqual(data['metadata']['tts_content_type'], 'audio/ogg')
        self.assertTrue(data['ai_audio'])

    @override_settings(USE_VOICE_DIAGNOSTIC=False, DEEPGRAM_API_KEY='')
    def test_audio_upload_returns_503_when_deepgram_stt_is_not_configured(self):
        session_data = self.start_session(payload={'target_skill': 'speaking'})
        audio_file = SimpleUploadedFile(
            'practice.webm',
            b'fake-audio-content',
            content_type='audio/webm',
        )

        response = self.client.post(
            f"/api/voice-conversation/sessions/{session_data['id']}/turns/",
            {'audio_file': audio_file},
            format='multipart',
        )

        self.assertEqual(response.status_code, status.HTTP_503_SERVICE_UNAVAILABLE)
        self.assertFalse(response.data['success'])
        self.assertEqual(response.data['error'], 'Speech-to-text is not configured yet.')
        self.assertEqual(
            VoiceConversationTurn.objects.filter(session_id=session_data['id']).count(),
            0,
        )

    @patch('agents.voice_conversation_services.transcribe_audio')
    def test_audio_upload_failure_does_not_create_turn(self, mock_transcribe_audio):
        mock_transcribe_audio.side_effect = VoiceDiagnosticError('Speech-to-text request failed: timeout')
        session_data = self.start_session(payload={'target_skill': 'speaking'})
        audio_file = SimpleUploadedFile(
            'practice.webm',
            b'fake-audio-content',
            content_type='audio/webm',
        )

        response = self.client.post(
            f"/api/voice-conversation/sessions/{session_data['id']}/turns/",
            {'audio_file': audio_file},
            format='multipart',
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(response.data['success'])
        self.assertEqual(
            response.data['error'],
            'Speech-to-text request failed: timeout',
        )
        self.assertEqual(
            VoiceConversationTurn.objects.filter(session_id=session_data['id']).count(),
            0,
        )

    def test_completed_session_cannot_accept_new_turn(self):
        session_data = self.start_session()
        self.client.post(
            f"/api/voice-conversation/sessions/{session_data['id']}/end/",
            {},
            format='json',
        )

        response = self.client.post(
            f"/api/voice-conversation/sessions/{session_data['id']}/turns/",
            {'user_transcript': 'This should fail.'},
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(response.data['success'])
        self.assertEqual(
            response.data['error'],
            'Only active voice conversation sessions can accept new turns.',
        )

    def test_user_can_end_own_session_and_completion_sets_status_and_ended_at(self):
        session_data = self.start_session()

        response = self.client.post(
            f"/api/voice-conversation/sessions/{session_data['id']}/end/",
            {},
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = self.assert_success_response(response)
        self.assertEqual(data['status'], 'completed')
        self.assertIsNotNone(data['ended_at'])

        session = VoiceConversationSession.objects.get(pk=session_data['id'])
        self.assertEqual(session.status, VoiceConversationSession.STATUS_COMPLETED)
        self.assertIsNotNone(session.ended_at)

    def test_creating_turn_does_not_update_skill_mastery(self):
        skill = Skill.objects.create(name='Speaking')
        mastery = SkillMastery.objects.create(
            user=self.user,
            skill=skill,
            level_code='A2',
            score=72,
            status='Learning',
        )
        original_score = mastery.score
        original_level_code = mastery.level_code
        original_status = mastery.status
        original_last_updated = mastery.last_updated

        session_data = self.start_session(
            payload={
                'target_skill': 'speaking',
                'cefr_level': 'A2',
            }
        )
        self.client.post(
            f"/api/voice-conversation/sessions/{session_data['id']}/turns/",
            {'user_transcript': 'Practice only. Do not update mastery.'},
            format='json',
        )
        self.client.post(
            f"/api/voice-conversation/sessions/{session_data['id']}/end/",
            {},
            format='json',
        )

        mastery.refresh_from_db()
        self.assertEqual(mastery.score, original_score)
        self.assertEqual(mastery.level_code, original_level_code)
        self.assertEqual(mastery.status, original_status)
        self.assertEqual(mastery.last_updated, original_last_updated)
