from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import permissions, status
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.response import Response
from rest_framework.views import APIView

from agents.models import LessonSession, VoiceConversationSession
from learning.models import Module, StudySession
from xiavlearn.api import success_response

from .serializers import (
    VoiceConversationSessionDetailSerializer,
    VoiceConversationSessionSerializer,
    VoiceConversationSessionStartSerializer,
    VoiceConversationTurnSerializer,
    VoiceConversationTurnCreateSerializer,
)
from .services import (
    answer_guided_teacher_session,
    answer_listening_teacher_session,
    answer_pronunciation_teacher_session,
    answer_speaking_teacher_session,
    create_teacher_session,
    evaluate_diagnostic,
    generate_study_plan,
    get_guided_teacher_session_state,
    get_coach_summary,
    get_curriculum_recommendation,
    get_listening_teacher_session_state,
    get_pronunciation_teacher_session_state,
    get_speaking_teacher_session_state,
    start_listening_teacher_session,
    start_pronunciation_teacher_session,
    start_speaking_teacher_session,
    start_guided_teacher_session,
    submit_teacher_feedback,
)
from .voice_conversation_services import create_voice_conversation_turn
from .voice_services import VoiceDiagnosticConfigError, VoiceDiagnosticError


def _error_response(message, status_code=status.HTTP_400_BAD_REQUEST):
    return Response(
        {
            'success': False,
            'error': message,
        },
        status=status_code,
    )


def _get_voice_conversation_session_queryset(include_turns=False):
    queryset = VoiceConversationSession.objects.select_related('user')
    if include_turns:
        queryset = queryset.prefetch_related('turns')
    return queryset


class DiagnosticEvaluateView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        answers = request.data.get('answers')
        if not isinstance(answers, list) or not answers:
            return Response(
                {
                    'success': False,
                    'error': 'answers must be a non-empty list.',
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        if any(
            not isinstance(item, dict)
            or not isinstance(item.get('question'), str)
            or not isinstance(item.get('answer'), str)
            for item in answers
        ):
            return Response(
                {
                    'success': False,
                    'error': (
                        'Each answer must include question and answer strings.'
                    ),
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        return success_response(
            evaluate_diagnostic(request.user, answers),
            'Diagnostic evaluation completed.',
        )


class CurriculumRecommendationView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        return success_response(
            get_curriculum_recommendation(request.user),
            'Curriculum recommendation generated.',
        )


class TeacherSessionView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        module_id = request.data.get('module_id')
        if not isinstance(module_id, int):
            return Response(
                {
                    'success': False,
                    'error': 'module_id must be an integer.',
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        module = get_object_or_404(Module, pk=module_id, is_active=True)
        return success_response(
            create_teacher_session(request.user, module),
            'Teacher session created.',
            status.HTTP_201_CREATED,
        )


class TeacherSessionStartView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        module_id = request.data.get('module_id')
        module = None
        if module_id is not None:
            if not isinstance(module_id, int):
                return Response(
                    {
                        'success': False,
                        'error': 'module_id must be an integer when provided.',
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )
            module = get_object_or_404(Module, pk=module_id, is_active=True)

        try:
            session_data = start_guided_teacher_session(request.user, module)
        except ValueError as exc:
            return Response(
                {
                    'success': False,
                    'error': str(exc),
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        return success_response(
            session_data,
            'Guided teacher session started.',
            status.HTTP_201_CREATED,
        )


class TeacherSessionAnswerView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        session_id = request.data.get('session_id')
        answer = request.data.get('student_answer')
        if not isinstance(session_id, int):
            return Response(
                {
                    'success': False,
                    'error': 'session_id must be an integer.',
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        if not isinstance(answer, str) or not answer.strip():
            return Response(
                {
                    'success': False,
                    'error': 'student_answer must be a non-empty string.',
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        lesson_session = get_object_or_404(
            LessonSession.objects.select_related(
                'study_session__module__skill',
                'study_session__module__level',
                'study_session__user',
            ),
            pk=session_id,
            study_session__user=request.user,
        )
        try:
            result = answer_guided_teacher_session(
                request.user,
                lesson_session,
                answer,
            )
        except ValueError as exc:
            return Response(
                {
                    'success': False,
                    'error': str(exc),
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        return success_response(
            result,
            'Teacher session answer evaluated.',
        )


class TeacherSessionDetailView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, session_id):
        lesson_session = get_object_or_404(
            LessonSession.objects.select_related(
                'study_session__module__skill',
                'study_session__module__level',
                'study_session__user',
            ).prefetch_related('turns'),
            pk=session_id,
            study_session__user=request.user,
        )
        session_data = get_guided_teacher_session_state(
            request.user,
            lesson_session,
        )

        return success_response(
            session_data,
            'Teacher session loaded.',
        )


class SpeakingTeacherSessionStartView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        session_data = start_speaking_teacher_session(request.user)
        return success_response(
            session_data,
            'Speaking teacher session started.',
            status.HTTP_201_CREATED,
        )


class SpeakingTeacherSessionDetailView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, session_id):
        lesson_session = get_object_or_404(
            LessonSession.objects.select_related('study_session__user').prefetch_related('turns'),
            pk=session_id,
            study_session__user=request.user,
            session_mode=LessonSession.SESSION_MODE_SPEAKING,
        )
        session_data = get_speaking_teacher_session_state(
            request.user,
            lesson_session,
        )
        return success_response(
            session_data,
            'Speaking teacher session loaded.',
        )


class SpeakingTeacherSessionAnswerView(APIView):
    permission_classes = [permissions.IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser, JSONParser]

    def post(self, request, session_id):
        transcript = request.data.get('transcript')
        audio_file = request.FILES.get('audio_file')
        if (
            not isinstance(transcript, str) or not transcript.strip()
        ) and audio_file is None:
            return Response(
                {
                    'success': False,
                    'error': 'Provide a non-empty transcript or audio_file.',
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        lesson_session = get_object_or_404(
            LessonSession.objects.select_related('study_session__user'),
            pk=session_id,
            study_session__user=request.user,
            session_mode=LessonSession.SESSION_MODE_SPEAKING,
        )
        try:
            result = answer_speaking_teacher_session(
                request.user,
                lesson_session,
                transcript=transcript if isinstance(transcript, str) else None,
                audio_file=audio_file,
            )
        except ValueError as exc:
            return Response(
                {
                    'success': False,
                    'error': str(exc),
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        except VoiceDiagnosticConfigError as exc:
            return Response(
                {
                    'success': False,
                    'error': str(exc),
                },
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        except VoiceDiagnosticError as exc:
            return Response(
                {
                    'success': False,
                    'error': str(exc),
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        return success_response(
            result,
            'Speaking teacher answer evaluated.',
        )


class ListeningTeacherSessionStartView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        session_data = start_listening_teacher_session(request.user)
        return success_response(
            session_data,
            'Listening teacher session started.',
            status.HTTP_201_CREATED,
        )


class ListeningTeacherSessionDetailView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, session_id):
        lesson_session = get_object_or_404(
            LessonSession.objects.select_related('study_session__user').prefetch_related('turns'),
            pk=session_id,
            study_session__user=request.user,
            session_mode=LessonSession.SESSION_MODE_LISTENING,
        )
        session_data = get_listening_teacher_session_state(
            request.user,
            lesson_session,
        )
        return success_response(
            session_data,
            'Listening teacher session loaded.',
        )


class ListeningTeacherSessionAnswerView(APIView):
    permission_classes = [permissions.IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser, JSONParser]

    def post(self, request, session_id):
        answer = request.data.get('answer')
        audio_file = request.FILES.get('audio_file')
        if (
            not isinstance(answer, str) or not answer.strip()
        ) and audio_file is None:
            return Response(
                {
                    'success': False,
                    'error': 'Provide a non-empty answer or audio_file.',
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        lesson_session = get_object_or_404(
            LessonSession.objects.select_related('study_session__user'),
            pk=session_id,
            study_session__user=request.user,
            session_mode=LessonSession.SESSION_MODE_LISTENING,
        )
        try:
            result = answer_listening_teacher_session(
                request.user,
                lesson_session,
                answer=answer if isinstance(answer, str) else None,
                audio_file=audio_file,
            )
        except ValueError as exc:
            return Response(
                {
                    'success': False,
                    'error': str(exc),
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        except VoiceDiagnosticConfigError as exc:
            return Response(
                {
                    'success': False,
                    'error': str(exc),
                },
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        except VoiceDiagnosticError as exc:
            return Response(
                {
                    'success': False,
                    'error': str(exc),
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        return success_response(
            result,
            'Listening teacher answer evaluated.',
        )


class PronunciationTeacherSessionStartView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        session_data = start_pronunciation_teacher_session(request.user)
        return success_response(
            session_data,
            'Pronunciation teacher session started.',
            status.HTTP_201_CREATED,
        )


class PronunciationTeacherSessionDetailView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, session_id):
        lesson_session = get_object_or_404(
            LessonSession.objects.select_related('study_session__user').prefetch_related('turns'),
            pk=session_id,
            study_session__user=request.user,
            session_mode=LessonSession.SESSION_MODE_PRONUNCIATION,
        )
        session_data = get_pronunciation_teacher_session_state(
            request.user,
            lesson_session,
        )
        return success_response(
            session_data,
            'Pronunciation teacher session loaded.',
        )


class PronunciationTeacherSessionAnswerView(APIView):
    permission_classes = [permissions.IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser, JSONParser]

    def post(self, request, session_id):
        transcript = request.data.get('transcript')
        audio_file = request.FILES.get('audio_file')
        if (
            not isinstance(transcript, str) or not transcript.strip()
        ) and audio_file is None:
            return Response(
                {
                    'success': False,
                    'error': 'Provide a non-empty transcript or audio_file.',
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        lesson_session = get_object_or_404(
            LessonSession.objects.select_related('study_session__user'),
            pk=session_id,
            study_session__user=request.user,
            session_mode=LessonSession.SESSION_MODE_PRONUNCIATION,
        )
        try:
            result = answer_pronunciation_teacher_session(
                request.user,
                lesson_session,
                transcript=transcript if isinstance(transcript, str) else None,
                audio_file=audio_file,
            )
        except ValueError as exc:
            return Response(
                {
                    'success': False,
                    'error': str(exc),
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        except VoiceDiagnosticConfigError as exc:
            return Response(
                {
                    'success': False,
                    'error': str(exc),
                },
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        except VoiceDiagnosticError as exc:
            return Response(
                {
                    'success': False,
                    'error': str(exc),
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        return success_response(
            result,
            'Pronunciation teacher answer evaluated.',
        )


class TeacherFeedbackView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        session_id = request.data.get('session_id')
        answer = request.data.get('answer')
        if not isinstance(session_id, int):
            return Response(
                {
                    'success': False,
                    'error': 'session_id must be an integer.',
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        if not isinstance(answer, str) or not answer.strip():
            return Response(
                {
                    'success': False,
                    'error': 'answer must be a non-empty string.',
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        session = get_object_or_404(
            StudySession.objects.select_related('module__skill', 'module__level'),
            pk=session_id,
            user=request.user,
            module__isnull=False,
        )
        return success_response(
            submit_teacher_feedback(request.user, session, answer),
            'Teacher feedback generated for this practice session.',
        )


class SchedulerGeneratePlanView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        return success_response(
            generate_study_plan(request.user),
            'Study plan generated.',
            status.HTTP_201_CREATED,
        )


class CoachSummaryView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        return success_response(
            get_coach_summary(request.user),
            'Coach summary generated.',
        )


class VoiceConversationSessionStartView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        serializer = VoiceConversationSessionStartSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        session = VoiceConversationSession.objects.create(
            user=request.user,
            **serializer.validated_data,
        )
        response_serializer = VoiceConversationSessionSerializer(session)
        return success_response(
            response_serializer.data,
            'Voice conversation session started.',
            status.HTTP_201_CREATED,
        )


class VoiceConversationSessionListView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        sessions = _get_voice_conversation_session_queryset().filter(user=request.user)
        serializer = VoiceConversationSessionSerializer(sessions, many=True)
        return success_response(
            serializer.data,
            'Voice conversation sessions loaded.',
        )


class VoiceConversationSessionDetailView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, session_id):
        session = get_object_or_404(
            _get_voice_conversation_session_queryset(include_turns=True),
            pk=session_id,
            user=request.user,
        )
        serializer = VoiceConversationSessionDetailSerializer(session)
        return success_response(
            serializer.data,
            'Voice conversation session loaded.',
        )


class VoiceConversationTurnCreateView(APIView):
    permission_classes = [permissions.IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser, JSONParser]

    def post(self, request, session_id):
        session = get_object_or_404(
            _get_voice_conversation_session_queryset(),
            pk=session_id,
            user=request.user,
        )
        if session.status != VoiceConversationSession.STATUS_ACTIVE:
            return _error_response(
                'Only active voice conversation sessions can accept new turns.'
            )

        serializer = VoiceConversationTurnCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            turn = create_voice_conversation_turn(
                session=session,
                user_transcript=serializer.validated_data.get('user_transcript'),
                user=request.user,
                user_audio=serializer.validated_data.get('user_audio'),
                transcript_source=serializer.validated_data.get(
                    'transcript_source',
                    'fallback',
                ),
                metadata=serializer.validated_data.get('metadata', {}),
            )
        except ValueError as exc:
            return _error_response(str(exc))
        except VoiceDiagnosticConfigError as exc:
            return _error_response(str(exc), status.HTTP_503_SERVICE_UNAVAILABLE)
        except VoiceDiagnosticError as exc:
            return _error_response(str(exc))

        response_serializer = VoiceConversationTurnSerializer(turn)
        return success_response(
            response_serializer.data,
            'Voice conversation turn created.',
            status.HTTP_201_CREATED,
        )


class VoiceConversationSessionEndView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, session_id):
        session = get_object_or_404(
            _get_voice_conversation_session_queryset(),
            pk=session_id,
            user=request.user,
        )
        session.status = VoiceConversationSession.STATUS_COMPLETED
        session.ended_at = timezone.now()
        session.save(update_fields=['status', 'ended_at'])
        serializer = VoiceConversationSessionSerializer(session)
        return success_response(
            serializer.data,
            'Voice conversation session ended.',
        )
