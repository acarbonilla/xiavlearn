from django.http import HttpResponse
from rest_framework import permissions, status
from rest_framework.generics import get_object_or_404
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.response import Response
from rest_framework.views import APIView

from xiavlearn.api import success_response

from .models import VoiceDiagnosticSession
from .serializers import (
    VoiceDiagnosticSessionDetailSerializer,
    VoiceDiagnosticSessionListSerializer,
)
from .voice_services import (
    build_voice_diagnostic_report,
    VoiceDiagnosticConfigError,
    VoiceDiagnosticError,
    evaluate_listening,
    evaluate_listening_batch,
    evaluate_pronunciation,
    evaluate_pronunciation_batch,
    evaluate_speaking,
    evaluate_speaking_batch,
    get_voice_diagnostic_prompts,
    start_voice_diagnostic_session,
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


def _parse_update_mastery(raw_value):
    if isinstance(raw_value, bool):
        return raw_value
    if isinstance(raw_value, str):
        normalized = raw_value.strip().lower()
        if normalized in {'false', '0', 'no'}:
            return False
    return True


def _parse_session_id(raw_value):
    if raw_value in (None, ''):
        return None
    try:
        session_id = int(raw_value)
    except (TypeError, ValueError):
        raise VoiceDiagnosticError('session_id must be a positive integer.')
    if session_id <= 0:
        raise VoiceDiagnosticError('session_id must be a positive integer.')
    return session_id


class VoiceDiagnosticSessionStartView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        session = start_voice_diagnostic_session(request.user)
        return success_response(
            {
                'session_id': session.id,
                'status': session.status,
                'started_at': session.started_at.isoformat().replace('+00:00', 'Z'),
            },
            'Voice diagnostic session started.',
            status.HTTP_201_CREATED,
        )


class VoiceDiagnosticSessionListView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        sessions = VoiceDiagnosticSession.objects.filter(user=request.user)
        serializer = VoiceDiagnosticSessionListSerializer(sessions, many=True)
        return success_response(serializer.data, 'Voice diagnostic sessions loaded.')


class VoiceDiagnosticSessionDetailView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, session_id):
        session = get_object_or_404(
            VoiceDiagnosticSession.objects.prefetch_related('items'),
            pk=session_id,
            user=request.user,
        )
        serializer = VoiceDiagnosticSessionDetailSerializer(session)
        return success_response(serializer.data, 'Voice diagnostic session loaded.')


class VoiceDiagnosticSessionReportView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, session_id):
        session = get_object_or_404(
            VoiceDiagnosticSession.objects.prefetch_related('items'),
            pk=session_id,
            user=request.user,
        )
        return success_response(
            build_voice_diagnostic_report(session),
            'Voice diagnostic report loaded.',
        )


class VoiceDiagnosticPromptsView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        return success_response(
            get_voice_diagnostic_prompts(request.user),
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
        transcript = request.data.get('transcript')
        update_mastery = _parse_update_mastery(request.data.get('update_mastery', False))

        if audio_file is None and not (isinstance(transcript, str) and transcript.strip()):
            return _error_response('audio_file or transcript is required.')
        if not isinstance(target_sentence, str) or not target_sentence.strip():
            return _error_response('target_sentence must be a non-empty string.')

        try:
            result = evaluate_pronunciation(
                request.user,
                audio_file,
                target_sentence,
                transcript=transcript,
                update_mastery=update_mastery,
            )
        except VoiceDiagnosticConfigError as exc:
            return _error_response(str(exc), status.HTTP_503_SERVICE_UNAVAILABLE)
        except VoiceDiagnosticError as exc:
            return _error_response(str(exc))

        return success_response(
            result,
            'Pronunciation diagnostic evaluation completed.',
        )


class PronunciationEvaluateBatchView(APIView):
    permission_classes = [permissions.IsAuthenticated]
    parser_classes = [JSONParser]

    def post(self, request):
        items = request.data.get('items')
        try:
            session_id = _parse_session_id(request.data.get('session_id'))
        except VoiceDiagnosticError as exc:
            return _error_response(str(exc))
        try:
            result = evaluate_pronunciation_batch(request.user, items, session_id=session_id)
        except VoiceDiagnosticConfigError as exc:
            return _error_response(str(exc), status.HTTP_503_SERVICE_UNAVAILABLE)
        except VoiceDiagnosticError as exc:
            return _error_response(str(exc))

        return success_response(
            result,
            'Pronunciation batch diagnostic evaluation completed.',
        )


class ListeningEvaluateView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        question = request.data.get('question')
        expected_answer = request.data.get('expected_answer')
        user_answer = request.data.get('user_answer')
        update_mastery = _parse_update_mastery(request.data.get('update_mastery', False))
        if not isinstance(question, str) or not question.strip():
            return _error_response('question must be a non-empty string.')
        if not isinstance(expected_answer, str) or not expected_answer.strip():
            return _error_response('expected_answer must be a non-empty string.')
        if not isinstance(user_answer, str):
            return _error_response('user_answer must be a string.')

        try:
            result = evaluate_listening(
                request.user,
                question,
                expected_answer,
                user_answer,
                update_mastery=update_mastery,
            )
        except VoiceDiagnosticError as exc:
            return _error_response(str(exc))

        return success_response(
            result,
            'Listening diagnostic evaluation completed.',
        )


class ListeningEvaluateBatchView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        items = request.data.get('items')
        try:
            session_id = _parse_session_id(request.data.get('session_id'))
        except VoiceDiagnosticError as exc:
            return _error_response(str(exc))
        try:
            result = evaluate_listening_batch(request.user, items, session_id=session_id)
        except VoiceDiagnosticError as exc:
            return _error_response(str(exc))

        return success_response(
            result,
            'Listening batch diagnostic evaluation completed.',
        )


class SpeakingEvaluateView(APIView):
    permission_classes = [permissions.IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser]

    def post(self, request):
        audio_file = request.FILES.get('audio_file')
        question = request.data.get('question')
        transcript = request.data.get('transcript')
        update_mastery = _parse_update_mastery(request.data.get('update_mastery', False))

        if audio_file is None and not (isinstance(transcript, str) and transcript.strip()):
            return _error_response('audio_file or transcript is required.')
        if not isinstance(question, str) or not question.strip():
            return _error_response('question must be a non-empty string.')

        try:
            result = evaluate_speaking(
                request.user,
                audio_file,
                question,
                transcript=transcript,
                update_mastery=update_mastery,
            )
        except VoiceDiagnosticConfigError as exc:
            return _error_response(str(exc), status.HTTP_503_SERVICE_UNAVAILABLE)
        except VoiceDiagnosticError as exc:
            return _error_response(str(exc))

        return success_response(
            result,
            'Speaking diagnostic evaluation completed.',
        )


class SpeakingEvaluateBatchView(APIView):
    permission_classes = [permissions.IsAuthenticated]
    parser_classes = [JSONParser]

    def post(self, request):
        items = request.data.get('items')
        try:
            session_id = _parse_session_id(request.data.get('session_id'))
        except VoiceDiagnosticError as exc:
            return _error_response(str(exc))
        try:
            result = evaluate_speaking_batch(request.user, items, session_id=session_id)
        except VoiceDiagnosticConfigError as exc:
            return _error_response(str(exc), status.HTTP_503_SERVICE_UNAVAILABLE)
        except VoiceDiagnosticError as exc:
            return _error_response(str(exc))

        return success_response(
            result,
            'Speaking batch diagnostic evaluation completed.',
        )
