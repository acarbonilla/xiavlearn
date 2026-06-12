from django.shortcuts import get_object_or_404
from rest_framework import permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView

from learning.models import Module, StudySession

from .services import (
    create_teacher_session,
    evaluate_diagnostic,
    generate_study_plan,
    get_coach_summary,
    get_curriculum_recommendation,
    submit_teacher_feedback,
)


class DiagnosticEvaluateView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        answers = request.data.get('answers')
        if not isinstance(answers, list) or not answers:
            return Response(
                {'detail': 'answers must be a non-empty list.'},
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
                    'detail': (
                        'Each answer must include question and answer strings.'
                    )
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        return Response(evaluate_diagnostic(request.user, answers))


class CurriculumRecommendationView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        return Response(get_curriculum_recommendation(request.user))


class TeacherSessionView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        module_id = request.data.get('module_id')
        if not isinstance(module_id, int):
            return Response(
                {'detail': 'module_id must be an integer.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        module = get_object_or_404(Module, pk=module_id, is_active=True)
        return Response(
            create_teacher_session(request.user, module),
            status=status.HTTP_201_CREATED,
        )


class TeacherFeedbackView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        session_id = request.data.get('session_id')
        answer = request.data.get('answer')
        if not isinstance(session_id, int):
            return Response(
                {'detail': 'session_id must be an integer.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if not isinstance(answer, str) or not answer.strip():
            return Response(
                {'detail': 'answer must be a non-empty string.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        session = get_object_or_404(
            StudySession.objects.select_related('module__skill', 'module__level'),
            pk=session_id,
            user=request.user,
            module__isnull=False,
        )
        return Response(
            submit_teacher_feedback(request.user, session, answer)
        )


class SchedulerGeneratePlanView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        return Response(
            generate_study_plan(request.user),
            status=status.HTTP_201_CREATED,
        )


class CoachSummaryView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        return Response(get_coach_summary(request.user))
