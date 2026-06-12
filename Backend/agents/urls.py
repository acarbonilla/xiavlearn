from django.urls import path

from .views import (
    CoachSummaryView,
    CurriculumRecommendationView,
    DiagnosticEvaluateView,
    SchedulerGeneratePlanView,
    TeacherFeedbackView,
    TeacherSessionView,
)


urlpatterns = [
    path(
        'diagnostic/evaluate/',
        DiagnosticEvaluateView.as_view(),
        name='diagnostic-evaluate',
    ),
    path(
        'curriculum/recommendation/',
        CurriculumRecommendationView.as_view(),
        name='curriculum-recommendation',
    ),
    path(
        'teacher/session/',
        TeacherSessionView.as_view(),
        name='teacher-session',
    ),
    path(
        'teacher/feedback/',
        TeacherFeedbackView.as_view(),
        name='teacher-feedback',
    ),
    path(
        'scheduler/generate-plan/',
        SchedulerGeneratePlanView.as_view(),
        name='scheduler-generate-plan',
    ),
    path(
        'coach/summary/',
        CoachSummaryView.as_view(),
        name='coach-summary',
    ),
]
