from django.http import HttpResponse
from rest_framework import permissions, status
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.response import Response
from rest_framework.views import APIView

from xiavlearn.api import success_response

from .voice_services import (
    VoiceDiagnosticConfigError,
    VoiceDiagnosticError,
    evaluate_listening,
    evaluate_pronunciation,
    get_voice_diagnostic_prompts,
    synthesize_tts,
)


def _error_response(message, status_code=status.HTTP_400_BAD_REQUEST):
    return Response(
        {
            'success': False,
            'error': message,
        },
        status=status_code,
    )


class VoiceDiagnosticPromptsView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        return success_response(
            get_voice_diagnostic_prompts(),
            'Voice diagnostic prompts loaded.',
        )


class VoiceDiagnosticTTSView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        text = request.data.get('text')
        if not isinstance(text, str) or not text.strip():
            return _error_response('text must be a non-empty string.')

        try:
            audio_content, content_type = synthesize_tts(text)
        except VoiceDiagnosticConfigError as exc:
            return _error_response(str(exc), status.HTTP_503_SERVICE_UNAVAILABLE)
        except VoiceDiagnosticError as exc:
            return _error_response(str(exc), status.HTTP_502_BAD_GATEWAY)

        return HttpResponse(audio_content, content_type=content_type)


class PronunciationEvaluateView(APIView):
    permission_classes = [permissions.IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser]

    def post(self, request):
        audio_file = request.FILES.get('audio_file')
        target_sentence = request.data.get('target_sentence')
        if audio_file is None:
            return _error_response('audio_file is required.')
        if not isinstance(target_sentence, str) or not target_sentence.strip():
            return _error_response('target_sentence must be a non-empty string.')

        try:
            result = evaluate_pronunciation(
                request.user,
                audio_file,
                target_sentence,
            )
        except VoiceDiagnosticConfigError as exc:
            return _error_response(str(exc), status.HTTP_503_SERVICE_UNAVAILABLE)
        except VoiceDiagnosticError as exc:
            return _error_response(str(exc))

        return success_response(
            result,
            'Pronunciation diagnostic evaluation completed.',
        )


class ListeningEvaluateView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        question = request.data.get('question')
        expected_answer = request.data.get('expected_answer')
        user_answer = request.data.get('user_answer')
        if not isinstance(question, str) or not question.strip():
            return _error_response('question must be a non-empty string.')
        if not isinstance(expected_answer, str) or not expected_answer.strip():
            return _error_response('expected_answer must be a non-empty string.')
        if not isinstance(user_answer, str) or not user_answer.strip():
            return _error_response('user_answer must be a non-empty string.')

        try:
            result = evaluate_listening(
                request.user,
                question,
                expected_answer,
                user_answer,
            )
        except VoiceDiagnosticError as exc:
            return _error_response(str(exc))

        return success_response(
            result,
            'Listening diagnostic evaluation completed.',
        )
