from django.shortcuts import get_object_or_404
from rest_framework import permissions, status
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.response import Response
from rest_framework.views import APIView

from agents.models import LessonSession
from learning.models import Module, StudySession
from xiavlearn.api import success_response

from .services import (
    answer_guided_teacher_session,
    answer_speaking_teacher_session,
    create_teacher_session,
    evaluate_diagnostic,
    generate_study_plan,
    get_guided_teacher_session_state,
    get_coach_summary,
    get_curriculum_recommendation,
    get_speaking_teacher_session_state,
    start_speaking_teacher_session,
    start_guided_teacher_session,
    submit_teacher_feedback,
)
from .voice_services import VoiceDiagnosticConfigError, VoiceDiagnosticError


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
